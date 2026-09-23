"""Testes unitários das entidades e regras de negócio do Serviço de Pedidos."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from pedidos_service.dominio import (
    DadosInvalidos,
    ItemPedido,
    Pedido,
    PedidoNaoEncontrado,
    StatusPedido,
    TransicaoInvalida,
    calcular_desconto,
    taxa_desconto,
    validar_cliente,
    validar_itens,
    validar_quantidade,
    validar_sku,
    validar_solicitacao,
)

MOMENTO = datetime(2026, 9, 24, 19, 0, tzinfo=timezone.utc)


def novo_pedido(*precos_e_quantidades) -> Pedido:
    itens = [ItemPedido(f"SKU-{n}", f"Produto {n}", quantidade, Decimal(preco))
             for n, (preco, quantidade) in enumerate(precos_e_quantidades)]
    return Pedido(id=1, cliente="Maria Souza", itens=itens, criado_em=MOMENTO)


class TestDescontoProgressivo:
    @pytest.mark.parametrize(
        "subtotal, taxa, desconto",
        [
            ("0.00", "0", "0.00"),
            ("499.99", "0", "0.00"),
            ("500.00", "0.05", "25.00"),
            ("999.99", "0.05", "50.00"),
            ("1000.00", "0.10", "100.00"),
            ("1234.56", "0.10", "123.46"),
        ],
    )
    def test_desconto_por_faixa_de_subtotal(self, subtotal, taxa, desconto):
        """Objetivo: Verificar a taxa e o valor do desconto nas fronteiras das faixas (499,99 / 500,00 / 999,99 / 1000,00) com arredondamento half-up.
        Técnica: Análise de valor limite e partição de equivalência (3 faixas)
        Requisitos: RN-P03
        """
        assert taxa_desconto(Decimal(subtotal)) == Decimal(taxa)
        assert calcular_desconto(Decimal(subtotal)) == Decimal(desconto)


class TestValidarCliente:
    def test_normaliza_espacos_internos_e_das_pontas(self):
        """Objetivo: Verificar que espaços repetidos e das extremidades são removidos do nome do cliente.
        Técnica: Partição de equivalência (classe válida)
        Requisitos: RN-P01
        """
        assert validar_cliente("  Maria    Souza ") == "Maria Souza"

    @pytest.mark.parametrize("nome", ["Ana", "A" * 80])
    def test_aceita_nomes_nos_limites(self, nome):
        """Objetivo: Garantir que nomes com 3 e 80 caracteres (limites) são aceitos.
        Técnica: Análise de valor limite (mínimo e máximo)
        Requisitos: RN-P01
        """
        assert validar_cliente(nome) == nome

    @pytest.mark.parametrize("nome", ["Al", "A" * 81])
    def test_rejeita_nomes_fora_dos_limites(self, nome):
        """Objetivo: Garantir que nomes com 2 e 81 caracteres são rejeitados.
        Técnica: Análise de valor limite (mínimo-1 e máximo+1)
        Requisitos: RN-P01
        """
        with pytest.raises(DadosInvalidos, match="entre 3 e 80"):
            validar_cliente(nome)

    @pytest.mark.parametrize("valor", [None, "", "    ", 123])
    def test_rejeita_cliente_ausente_ou_invalido(self, valor):
        """Objetivo: Verificar que cliente ausente, vazio ou não textual é rejeitado.
        Técnica: Partição de equivalência (classes inválidas)
        Requisitos: RN-P01
        """
        with pytest.raises(DadosInvalidos, match="obrigatório"):
            validar_cliente(valor)


class TestValidarItens:
    def test_validar_sku_normaliza_e_rejeita_invalidos(self):
        """Objetivo: Verificar que o SKU é normalizado para maiúsculas e que formatos inválidos são rejeitados.
        Técnica: Partição de equivalência (válida e inválidas)
        Requisitos: RN-P01
        """
        assert validar_sku(" tec-001 ") == "TEC-001"
        for invalido in [None, "", "X", "TEC_001", 10]:
            with pytest.raises(DadosInvalidos, match="SKU inválido"):
                validar_sku(invalido)

    @pytest.mark.parametrize("valor, valido", [(0, False), (1, True), (100, True), (101, False)])
    def test_quantidade_por_item_entre_1_e_100(self, valor, valido):
        """Objetivo: Verificar os limites da quantidade por item (0 e 101 inválidos; 1 e 100 válidos).
        Técnica: Análise de valor limite
        Requisitos: RN-P01
        """
        if valido:
            assert validar_quantidade(valor) == valor
        else:
            with pytest.raises(DadosInvalidos, match="entre 1 e 100"):
                validar_quantidade(valor)

    @pytest.mark.parametrize("valor", [True, 2.0, "2", None])
    def test_quantidade_deve_ser_inteira(self, valor):
        """Objetivo: Verificar que booleanos, floats, textos e ausência não são aceitos como quantidade.
        Técnica: Partição de equivalência (tipos inválidos)
        Requisitos: RN-P01
        """
        with pytest.raises(DadosInvalidos, match="número inteiro"):
            validar_quantidade(valor)

    def test_agrupa_itens_repetidos_mantendo_ordem(self):
        """Objetivo: Verificar que itens com o mesmo SKU são somados, preservando a ordem da primeira ocorrência.
        Técnica: Partição de equivalência (classe válida com repetição)
        Requisitos: RN-P01
        """
        itens = [{"sku": "mou-001", "quantidade": 1}, {"sku": "TEC-001", "quantidade": 2},
                 {"sku": "MOU-001", "quantidade": 3}]
        assert validar_itens(itens) == [{"sku": "MOU-001", "quantidade": 4},
                                        {"sku": "TEC-001", "quantidade": 2}]

    def test_rejeita_soma_de_itens_repetidos_acima_de_100(self):
        """Objetivo: Garantir que o limite de 100 unidades vale para a soma dos itens repetidos (60 + 41).
        Técnica: Análise de valor limite após agrupamento
        Requisitos: RN-P01
        """
        with pytest.raises(DadosInvalidos, match="entre 1 e 100"):
            validar_itens([{"sku": "TEC-001", "quantidade": 60}, {"sku": "TEC-001", "quantidade": 41}])

    def test_aceita_ate_20_produtos_distintos(self):
        """Objetivo: Garantir que um pedido com exatamente 20 produtos distintos é aceito.
        Técnica: Análise de valor limite (máximo)
        Requisitos: RN-P01
        """
        itens = [{"sku": f"SKU-{n:02d}", "quantidade": 1} for n in range(20)]
        assert len(validar_itens(itens)) == 20

    def test_rejeita_21_produtos_distintos(self):
        """Objetivo: Garantir que um pedido com 21 produtos distintos é rejeitado.
        Técnica: Análise de valor limite (máximo+1)
        Requisitos: RN-P01
        """
        itens = [{"sku": f"SKU-{n:02d}", "quantidade": 1} for n in range(21)]
        with pytest.raises(DadosInvalidos, match="no máximo 20"):
            validar_itens(itens)

    @pytest.mark.parametrize("itens", [None, [], {}, "TEC-001"])
    def test_rejeita_pedido_sem_itens(self, itens):
        """Objetivo: Verificar que o pedido precisa de uma lista com pelo menos um item.
        Técnica: Análise de valor limite (0 itens) e partição de equivalência
        Requisitos: RN-P01
        """
        with pytest.raises(DadosInvalidos, match="pelo menos um item"):
            validar_itens(itens)

    def test_rejeita_item_que_nao_e_objeto(self):
        """Objetivo: Verificar que cada item deve ser um objeto com sku e quantidade.
        Técnica: Partição de equivalência (tipo inválido)
        Requisitos: RN-P01, RNF01
        """
        with pytest.raises(DadosInvalidos, match="Cada item"):
            validar_itens([["TEC-001", 1]])

    def test_validar_solicitacao_retorna_cliente_e_itens(self):
        """Objetivo: Verificar que uma solicitação válida resulta no par (cliente, itens normalizados).
        Técnica: Partição de equivalência (classe válida)
        Requisitos: RF-P02, RN-P01
        """
        cliente, itens = validar_solicitacao({"cliente": "Ana", "itens": [{"sku": "abc", "quantidade": 1}]})
        assert (cliente, itens) == ("Ana", [{"sku": "ABC", "quantidade": 1}])

    @pytest.mark.parametrize("dados", [None, [], "pedido"])
    def test_validar_solicitacao_rejeita_corpo_que_nao_e_objeto(self, dados):
        """Objetivo: Verificar que a solicitação precisa ser um objeto JSON.
        Técnica: Partição de equivalência (tipo inválido)
        Requisitos: RF-P02, RNF01
        """
        with pytest.raises(DadosInvalidos, match="objeto JSON"):
            validar_solicitacao(dados)


class TestPedido:
    def test_item_calcula_total_e_serializa(self):
        """Objetivo: Verificar o total do item (preço × quantidade) e seu formato JSON.
        Técnica: Verificação de cálculo e contrato de saída
        Requisitos: RF-P02, RNF01
        """
        item = ItemPedido("TEC-001", "Teclado", 3, Decimal("33.33"))
        assert item.total == Decimal("99.99")
        assert item.para_dict() == {"sku": "TEC-001", "nome": "Teclado", "quantidade": 3,
                                    "preco_unitario": "33.33", "total": "99.99"}

    def test_totais_sem_desconto(self):
        """Objetivo: Verificar subtotal, desconto zero e total para pedido abaixo de R$ 500,00.
        Técnica: Partição de equivalência (faixa sem desconto)
        Requisitos: RN-P03
        """
        pedido = novo_pedido(("120.00", 2), ("99.99", 1))
        assert (pedido.subtotal, pedido.desconto, pedido.total) == (
            Decimal("339.99"), Decimal("0.00"), Decimal("339.99"))

    def test_totais_com_desconto_de_5_por_cento(self):
        """Objetivo: Verificar o desconto de 5% quando o subtotal atinge exatamente R$ 500,00.
        Técnica: Análise de valor limite (início da faixa de 5%)
        Requisitos: RN-P03
        """
        pedido = novo_pedido(("250.00", 2))
        assert (pedido.subtotal, pedido.desconto, pedido.total) == (
            Decimal("500.00"), Decimal("25.00"), Decimal("475.00"))

    def test_totais_com_desconto_de_10_por_cento(self):
        """Objetivo: Verificar o desconto de 10% para subtotal acima de R$ 1.000,00.
        Técnica: Partição de equivalência (faixa de 10%)
        Requisitos: RN-P03
        """
        pedido = novo_pedido(("1200.00", 1), ("120.00", 1))
        assert (pedido.subtotal, pedido.desconto, pedido.total) == (
            Decimal("1320.00"), Decimal("132.00"), Decimal("1188.00"))

    def test_pedido_novo_nasce_confirmado_e_serializa(self):
        """Objetivo: Verificar que o pedido nasce CONFIRMADO e o formato JSON completo (incluindo percentual de desconto).
        Técnica: Verificação de estado inicial e contrato de saída
        Requisitos: RF-P02, RF-P03, RNF01
        """
        dados = novo_pedido(("250.00", 2)).para_dict()
        assert dados == {
            "id": 1, "cliente": "Maria Souza", "status": "CONFIRMADO",
            "itens": [{"sku": "SKU-0", "nome": "Produto 0", "quantidade": 2,
                       "preco_unitario": "250.00", "total": "500.00"}],
            "subtotal": "500.00", "percentual_desconto": 5, "desconto": "25.00", "total": "475.00",
            "criado_em": "2026-09-24T19:00:00+00:00", "cancelado_em": None,
        }

    def test_cancelar_pedido_confirmado_registra_data(self):
        """Objetivo: Verificar a transição CONFIRMADO → CANCELADO e o registro da data de cancelamento.
        Técnica: Teste de transição de estados
        Requisitos: RF-P04, RN-P05
        """
        pedido = novo_pedido(("10.00", 1))
        pedido.cancelar(MOMENTO)
        assert pedido.status is StatusPedido.CANCELADO
        assert pedido.para_dict()["cancelado_em"] == "2026-09-24T19:00:00+00:00"

    def test_cancelar_sem_momento_usa_relogio_atual(self):
        """Objetivo: Verificar que, sem momento informado, o cancelamento usa a data/hora atual (UTC).
        Técnica: Partição de equivalência (parâmetro opcional omitido)
        Requisitos: RF-P04
        """
        pedido = novo_pedido(("10.00", 1))
        antes = datetime.now(timezone.utc)
        pedido.cancelar()
        assert antes <= pedido.cancelado_em <= datetime.now(timezone.utc)

    def test_cancelar_pedido_ja_cancelado_e_transicao_invalida(self):
        """Objetivo: Garantir que um pedido CANCELADO não pode ser cancelado novamente.
        Técnica: Teste de transição de estados (transição inválida)
        Requisitos: RN-P05
        """
        pedido = novo_pedido(("10.00", 1))
        pedido.cancelar(MOMENTO)
        with pytest.raises(TransicaoInvalida, match="não pode ser cancelado"):
            pedido.cancelar(MOMENTO)

    def test_pedido_nao_encontrado_informa_id(self):
        """Objetivo: Verificar que a exceção de pedido inexistente expõe o id e o código padronizado.
        Técnica: Verificação de contrato de erro
        Requisitos: RF-P03, RNF01
        """
        erro = PedidoNaoEncontrado(42)
        assert (erro.id_pedido, erro.codigo, str(erro)) == (42, "PEDIDO_NAO_ENCONTRADO",
                                                             "Pedido 42 não encontrado.")
