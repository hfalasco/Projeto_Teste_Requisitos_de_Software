"""Testes unitários das entidades e validações do Serviço de Estoque."""

from decimal import Decimal

import pytest

from estoque_service.dominio import (
    CAPACIDADE_MAXIMA,
    DadosInvalidos,
    EstoqueInsuficiente,
    Produto,
    ProdutoJaCadastrado,
    ProdutoNaoEncontrado,
    validar_nome,
    validar_preco,
    validar_quantidade,
    validar_sku,
)


def novo_produto(**alteracoes) -> Produto:
    dados = {"sku": "TEC-001", "nome": "Teclado", "preco": Decimal("250.00"),
             "quantidade": 10, "estoque_minimo": 3}
    dados.update(alteracoes)
    return Produto(**dados)


class TestValidarSku:
    def test_normaliza_para_maiusculas_e_remove_espacos(self):
        """Objetivo: Verificar que o SKU informado com espaços e letras minúsculas é normalizado.
        Técnica: Partição de equivalência (classe válida)
        Requisitos: RN-E01
        """
        assert validar_sku("  tec-001 ") == "TEC-001"

    @pytest.mark.parametrize("sku", ["ABC", "A" * 20, "1-2", "X9-Y8-Z7"])
    def test_aceita_skus_nos_limites_validos(self, sku):
        """Objetivo: Garantir que SKUs com 3 e 20 caracteres (limites) e formatos válidos são aceitos.
        Técnica: Análise de valor limite (mínimo e máximo válidos)
        Requisitos: RN-E01
        """
        assert validar_sku(sku) == sku

    @pytest.mark.parametrize("sku", ["AB", "A" * 21, "", "TEC_001", "TEC 001", "-TEC", "TÉC-01"])
    def test_rejeita_skus_fora_do_padrao(self, sku):
        """Objetivo: Garantir que SKUs curtos (2), longos (21), vazios ou com caracteres inválidos são rejeitados.
        Técnica: Valor limite (mínimo-1, máximo+1) e partição de equivalência (classes inválidas)
        Requisitos: RN-E01
        """
        with pytest.raises(DadosInvalidos, match="SKU inválido"):
            validar_sku(sku)

    @pytest.mark.parametrize("valor", [None, 123, ["TEC-001"]])
    def test_rejeita_sku_que_nao_e_texto(self, valor):
        """Objetivo: Verificar que um SKU ausente ou de tipo diferente de texto é rejeitado.
        Técnica: Partição de equivalência (tipo inválido)
        Requisitos: RN-E01
        """
        with pytest.raises(DadosInvalidos, match="obrigatório"):
            validar_sku(valor)


class TestValidarNome:
    def test_remove_espacos_das_pontas(self):
        """Objetivo: Verificar que o nome válido é aceito sem os espaços das extremidades.
        Técnica: Partição de equivalência (classe válida)
        Requisitos: RN-E02
        """
        assert validar_nome("  Teclado mecânico  ") == "Teclado mecânico"

    def test_aceita_nome_com_tamanho_maximo(self):
        """Objetivo: Garantir que um nome com exatamente 100 caracteres é aceito.
        Técnica: Análise de valor limite (máximo)
        Requisitos: RN-E02
        """
        assert len(validar_nome("N" * 100)) == 100

    def test_rejeita_nome_acima_do_tamanho_maximo(self):
        """Objetivo: Garantir que um nome com 101 caracteres é rejeitado.
        Técnica: Análise de valor limite (máximo+1)
        Requisitos: RN-E02
        """
        with pytest.raises(DadosInvalidos, match="no máximo 100"):
            validar_nome("N" * 101)

    @pytest.mark.parametrize("valor", [None, "", "   ", 42])
    def test_rejeita_nome_vazio_ou_invalido(self, valor):
        """Objetivo: Verificar que nome ausente, vazio, só com espaços ou não textual é rejeitado.
        Técnica: Partição de equivalência (classes inválidas)
        Requisitos: RN-E02
        """
        with pytest.raises(DadosInvalidos, match="obrigatório"):
            validar_nome(valor)


class TestValidarPreco:
    @pytest.mark.parametrize(
        "entrada, esperado",
        [
            ("10", Decimal("10.00")),
            (10, Decimal("10.00")),
            (10.5, Decimal("10.50")),
            (Decimal("99.9"), Decimal("99.90")),
            (" 7.25 ", Decimal("7.25")),
            ("0.01", Decimal("0.01")),
            ("1000000.00", Decimal("1000000.00")),
        ],
    )
    def test_aceita_precos_validos_e_normaliza_duas_casas(self, entrada, esperado):
        """Objetivo: Verificar que preços em texto, inteiro, float e Decimal são aceitos e normalizados para 2 casas, incluindo os limites 0,01 e 1.000.000,00.
        Técnica: Partição de equivalência e análise de valor limite
        Requisitos: RN-E03
        """
        assert validar_preco(entrada) == esperado

    def test_arredonda_meio_centavo_para_cima(self):
        """Objetivo: Garantir o arredondamento comercial (half-up) na terceira casa decimal.
        Técnica: Análise de valor limite (ponto de arredondamento)
        Requisitos: RN-E03
        """
        assert validar_preco("10.005") == Decimal("10.01")
        assert validar_preco("10.004") == Decimal("10.00")

    @pytest.mark.parametrize("entrada", [0, "0.00", "-1", "0.004"])
    def test_rejeita_preco_zero_ou_negativo(self, entrada):
        """Objetivo: Garantir que preços iguais a zero, negativos ou que arredondam para zero são rejeitados.
        Técnica: Análise de valor limite (mínimo-1 centavo)
        Requisitos: RN-E03
        """
        with pytest.raises(DadosInvalidos, match="maior que zero"):
            validar_preco(entrada)

    def test_rejeita_preco_acima_do_maximo(self):
        """Objetivo: Garantir que um preço de 1.000.000,01 (máximo + 1 centavo) é rejeitado.
        Técnica: Análise de valor limite (máximo+1)
        Requisitos: RN-E03
        """
        with pytest.raises(DadosInvalidos, match="no máximo"):
            validar_preco("1000000.01")

    @pytest.mark.parametrize("entrada", [None, True, [], "abc", "NaN", "Infinity", ""])
    def test_rejeita_preco_nao_numerico(self, entrada):
        """Objetivo: Verificar que valores ausentes, booleanos, listas, textos não numéricos, NaN e infinito são rejeitados.
        Técnica: Partição de equivalência (classes inválidas)
        Requisitos: RN-E03
        """
        with pytest.raises(DadosInvalidos, match="numérico"):
            validar_preco(entrada)


class TestValidarQuantidade:
    @pytest.mark.parametrize("valor", [1, 500, 10_000])
    def test_aceita_quantidades_dentro_do_intervalo(self, valor):
        """Objetivo: Verificar que quantidades de 1 a 10.000 (inclusive os limites) são aceitas.
        Técnica: Análise de valor limite (mínimo, nominal, máximo)
        Requisitos: RN-E04
        """
        assert validar_quantidade(valor) == valor

    @pytest.mark.parametrize("valor, mensagem", [(0, "no mínimo 1"), (-5, "no mínimo 1"),
                                                 (10_001, "no máximo 10000")])
    def test_rejeita_quantidades_fora_do_intervalo(self, valor, mensagem):
        """Objetivo: Garantir que as quantidades 0, negativas e 10.001 são rejeitadas com mensagem adequada.
        Técnica: Análise de valor limite (mínimo-1, máximo+1)
        Requisitos: RN-E04
        """
        with pytest.raises(DadosInvalidos, match=mensagem):
            validar_quantidade(valor)

    @pytest.mark.parametrize("valor", [True, 1.0, "5", None])
    def test_rejeita_quantidade_nao_inteira(self, valor):
        """Objetivo: Verificar que booleanos, floats, textos e valor ausente não são aceitos como quantidade.
        Técnica: Partição de equivalência (tipos inválidos)
        Requisitos: RN-E04
        """
        with pytest.raises(DadosInvalidos, match="número inteiro"):
            validar_quantidade(valor)

    def test_minimo_configuravel_aceita_zero_e_informa_o_campo(self):
        """Objetivo: Verificar que o mínimo pode ser 0 (saldo inicial) e que a mensagem cita o campo validado.
        Técnica: Análise de valor limite (mínimo configurável)
        Requisitos: RN-E04
        """
        assert validar_quantidade(0, "estoque_minimo", minimo=0) == 0
        with pytest.raises(DadosInvalidos, match="'estoque_minimo'"):
            validar_quantidade(-1, "estoque_minimo", minimo=0)


class TestProduto:
    def test_criar_com_dados_validos_normaliza_campos(self):
        """Objetivo: Verificar que um produto é criado a partir de um dicionário válido, com SKU, nome e preço normalizados.
        Técnica: Partição de equivalência (classe válida)
        Requisitos: RF-E01, RN-E01, RN-E02, RN-E03
        """
        produto = Produto.criar({"sku": "tec-001", "nome": " Teclado ", "preco": "250",
                                 "quantidade": 10, "estoque_minimo": 3})
        assert produto == novo_produto()

    def test_criar_usa_zero_como_padrao_para_saldo_e_minimo(self):
        """Objetivo: Garantir que quantidade e estoque mínimo são opcionais e assumem 0.
        Técnica: Partição de equivalência (campos opcionais omitidos)
        Requisitos: RF-E01
        """
        produto = Produto.criar({"sku": "ABC", "nome": "X", "preco": 1})
        assert (produto.quantidade, produto.estoque_minimo) == (0, 0)

    @pytest.mark.parametrize("dados", [None, [], "texto"])
    def test_criar_rejeita_dados_que_nao_sao_objeto(self, dados):
        """Objetivo: Verificar que dados que não são um objeto JSON (dicionário) são rejeitados.
        Técnica: Partição de equivalência (tipo inválido)
        Requisitos: RF-E01, RNF01
        """
        with pytest.raises(DadosInvalidos, match="objeto JSON"):
            Produto.criar(dados)

    @pytest.mark.parametrize("quantidade, esperado", [(2, True), (3, True), (4, False)])
    def test_precisa_reposicao_quando_saldo_menor_ou_igual_ao_minimo(self, quantidade, esperado):
        """Objetivo: Verificar o alerta de reposição com saldo abaixo (2), igual (3) e acima (4) do mínimo 3.
        Técnica: Análise de valor limite em torno do estoque mínimo
        Requisitos: RN-E05
        """
        assert novo_produto(quantidade=quantidade).precisa_reposicao is esperado

    def test_adicionar_incrementa_saldo(self):
        """Objetivo: Verificar que uma entrada soma a quantidade ao saldo atual.
        Técnica: Partição de equivalência (classe válida)
        Requisitos: RF-E03
        """
        produto = novo_produto()
        produto.adicionar(5)
        assert produto.quantidade == 15

    def test_adicionar_ate_a_capacidade_maxima_e_permitido(self):
        """Objetivo: Garantir que é possível atingir exatamente a capacidade máxima de armazenamento.
        Técnica: Análise de valor limite (capacidade máxima)
        Requisitos: RN-E04
        """
        produto = novo_produto(quantidade=CAPACIDADE_MAXIMA - 10_000)
        produto.adicionar(10_000)
        assert produto.quantidade == CAPACIDADE_MAXIMA

    def test_adicionar_acima_da_capacidade_maxima_e_rejeitado_sem_alterar_saldo(self):
        """Objetivo: Garantir que uma entrada que ultrapassa a capacidade em 1 unidade é rejeitada e o saldo não muda.
        Técnica: Análise de valor limite (capacidade+1)
        Requisitos: RN-E04
        """
        produto = novo_produto(quantidade=CAPACIDADE_MAXIMA)
        with pytest.raises(DadosInvalidos, match="Capacidade máxima"):
            produto.adicionar(1)
        assert produto.quantidade == CAPACIDADE_MAXIMA

    def test_remover_decrementa_saldo(self):
        """Objetivo: Verificar que uma baixa subtrai a quantidade do saldo.
        Técnica: Partição de equivalência (classe válida)
        Requisitos: RF-E04
        """
        produto = novo_produto()
        produto.remover(4)
        assert produto.quantidade == 6

    def test_remover_exatamente_o_saldo_zera_o_estoque(self):
        """Objetivo: Garantir que é possível baixar exatamente todo o saldo (saldo final 0).
        Técnica: Análise de valor limite (quantidade = saldo)
        Requisitos: RF-E04, RN-E04
        """
        produto = novo_produto()
        produto.remover(10)
        assert produto.quantidade == 0

    def test_remover_mais_que_o_saldo_lanca_estoque_insuficiente(self):
        """Objetivo: Garantir que baixar saldo+1 lança EstoqueInsuficiente com os dados do erro e não altera o saldo.
        Técnica: Análise de valor limite (saldo+1)
        Requisitos: RN-E04
        """
        produto = novo_produto()
        with pytest.raises(EstoqueInsuficiente) as erro:
            produto.remover(11)
        assert (erro.value.sku, erro.value.disponivel, erro.value.solicitado) == ("TEC-001", 10, 11)
        assert erro.value.codigo == "ESTOQUE_INSUFICIENTE"
        assert produto.quantidade == 10

    def test_para_dict_serializa_preco_como_texto_com_duas_casas(self):
        """Objetivo: Verificar o formato JSON do produto (preço em texto com 2 casas e indicador de reposição).
        Técnica: Verificação de contrato de saída
        Requisitos: RF-E02, RNF01
        """
        assert novo_produto(preco=Decimal("5")).para_dict() == {
            "sku": "TEC-001", "nome": "Teclado", "preco": "5.00", "quantidade": 10,
            "estoque_minimo": 3, "precisa_reposicao": False,
        }


class TestExcecoes:
    def test_excecoes_informam_codigo_e_mensagem(self):
        """Objetivo: Verificar que as exceções de negócio expõem código padronizado e mensagem legível.
        Técnica: Verificação de contrato de erro
        Requisitos: RNF01
        """
        nao_encontrado = ProdutoNaoEncontrado("XYZ")
        duplicado = ProdutoJaCadastrado("XYZ")
        assert (nao_encontrado.codigo, nao_encontrado.sku) == ("PRODUTO_NAO_ENCONTRADO", "XYZ")
        assert "não encontrado" in str(nao_encontrado)
        assert (duplicado.codigo, duplicado.sku) == ("PRODUTO_JA_CADASTRADO", "XYZ")
        assert "Já existe" in str(duplicado)
