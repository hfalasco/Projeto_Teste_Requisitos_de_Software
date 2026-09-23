"""Testes unitários do repositório e dos casos de uso do Serviço de Estoque."""

import threading
from decimal import Decimal

import pytest

from estoque_service.dominio import (
    CAPACIDADE_MAXIMA,
    DadosInvalidos,
    EstoqueInsuficiente,
    Produto,
    ProdutoJaCadastrado,
    ProdutoNaoEncontrado,
)
from estoque_service.repositorio import RepositorioProdutosEmMemoria
from estoque_service.servico import MAXIMO_ITENS_POR_LOTE, ServicoEstoque, normalizar_itens


@pytest.fixture
def servico():
    """Serviço com dois produtos cadastrados: TEC-001 (saldo 10) e MOU-001 (saldo 5)."""
    servico = ServicoEstoque()
    servico.cadastrar({"sku": "TEC-001", "nome": "Teclado", "preco": "250.00",
                       "quantidade": 10, "estoque_minimo": 3})
    servico.cadastrar({"sku": "MOU-001", "nome": "Mouse", "preco": "120.00",
                       "quantidade": 5, "estoque_minimo": 2})
    return servico


def saldos(servico):
    return {p.sku: p.quantidade for p in servico.listar()}


class TestRepositorio:
    def test_adicionar_e_obter_produto(self):
        """Objetivo: Verificar que um produto adicionado ao repositório pode ser recuperado pelo SKU.
        Técnica: Partição de equivalência (classe válida)
        Requisitos: RF-E01, RF-E02
        """
        repositorio = RepositorioProdutosEmMemoria()
        produto = Produto("ABC", "Produto", Decimal("1.00"))
        repositorio.adicionar(produto)
        assert repositorio.obter("ABC") is produto
        assert len(repositorio) == 1

    def test_adicionar_sku_duplicado_lanca_erro(self):
        """Objetivo: Garantir que o repositório não aceita dois produtos com o mesmo SKU.
        Técnica: Partição de equivalência (classe inválida: duplicidade)
        Requisitos: RN-E01
        """
        repositorio = RepositorioProdutosEmMemoria()
        repositorio.adicionar(Produto("ABC", "Produto", Decimal("1.00")))
        with pytest.raises(ProdutoJaCadastrado):
            repositorio.adicionar(Produto("ABC", "Outro", Decimal("2.00")))

    def test_obter_sku_inexistente_lanca_erro(self):
        """Objetivo: Verificar que consultar um SKU inexistente lança ProdutoNaoEncontrado.
        Técnica: Partição de equivalência (classe inválida)
        Requisitos: RF-E02
        """
        with pytest.raises(ProdutoNaoEncontrado):
            RepositorioProdutosEmMemoria().obter("NAO-EXISTE")

    def test_listar_retorna_produtos_ordenados_por_sku(self):
        """Objetivo: Verificar que a listagem é ordenada alfabeticamente pelo SKU.
        Técnica: Verificação de ordenação
        Requisitos: RF-E02
        """
        repositorio = RepositorioProdutosEmMemoria()
        for sku in ["ZZZ", "AAA", "MMM"]:
            repositorio.adicionar(Produto(sku, sku, Decimal("1.00")))
        assert [p.sku for p in repositorio.listar()] == ["AAA", "MMM", "ZZZ"]


class TestNormalizarItens:
    def test_agrupa_skus_repetidos_somando_quantidades(self):
        """Objetivo: Verificar que itens com o mesmo SKU (inclusive com grafias diferentes) são agrupados e somados.
        Técnica: Partição de equivalência (classe válida com repetição)
        Requisitos: RN-E06
        """
        itens = [{"sku": "tec-001", "quantidade": 2}, {"sku": "MOU-001", "quantidade": 1},
                 {"sku": "TEC-001", "quantidade": 3}]
        assert normalizar_itens(itens) == {"TEC-001": 5, "MOU-001": 1}

    @pytest.mark.parametrize("itens", [None, [], {}, "TEC-001"])
    def test_rejeita_lista_vazia_ou_ausente(self, itens):
        """Objetivo: Garantir que a operação exige uma lista com pelo menos um item.
        Técnica: Análise de valor limite (0 itens) e partição de equivalência (tipo inválido)
        Requisitos: RN-E06
        """
        with pytest.raises(DadosInvalidos, match="pelo menos um item"):
            normalizar_itens(itens)

    def test_aceita_lote_com_numero_maximo_de_itens(self):
        """Objetivo: Garantir que um lote com exatamente 50 itens é aceito.
        Técnica: Análise de valor limite (máximo)
        Requisitos: RN-E06
        """
        itens = [{"sku": f"SKU-{n:03d}", "quantidade": 1} for n in range(MAXIMO_ITENS_POR_LOTE)]
        assert len(normalizar_itens(itens)) == MAXIMO_ITENS_POR_LOTE

    def test_rejeita_lote_acima_do_numero_maximo_de_itens(self):
        """Objetivo: Garantir que um lote com 51 itens é rejeitado.
        Técnica: Análise de valor limite (máximo+1)
        Requisitos: RN-E06
        """
        itens = [{"sku": f"SKU-{n:03d}", "quantidade": 1} for n in range(MAXIMO_ITENS_POR_LOTE + 1)]
        with pytest.raises(DadosInvalidos, match="no máximo 50"):
            normalizar_itens(itens)

    def test_rejeita_item_que_nao_e_objeto(self):
        """Objetivo: Verificar que cada item precisa ser um objeto com sku e quantidade.
        Técnica: Partição de equivalência (tipo inválido)
        Requisitos: RN-E06, RNF01
        """
        with pytest.raises(DadosInvalidos, match="Cada item"):
            normalizar_itens(["TEC-001"])

    def test_rejeita_soma_agrupada_acima_do_limite_por_operacao(self):
        """Objetivo: Garantir que o limite de 10.000 unidades vale para a soma dos itens agrupados (5.000 + 5.001).
        Técnica: Análise de valor limite após agrupamento
        Requisitos: RN-E04, RN-E06
        """
        itens = [{"sku": "TEC-001", "quantidade": 5_000}, {"sku": "TEC-001", "quantidade": 5_001}]
        with pytest.raises(DadosInvalidos, match="no máximo 10000"):
            normalizar_itens(itens)


class TestCadastroEConsulta:
    def test_cadastrar_produto_o_torna_disponivel_na_listagem(self, servico):
        """Objetivo: Verificar que produtos cadastrados aparecem na listagem e na consulta por SKU.
        Técnica: Partição de equivalência (classe válida)
        Requisitos: RF-E01, RF-E02
        """
        assert [p.sku for p in servico.listar()] == ["MOU-001", "TEC-001"]
        assert servico.obter("TEC-001").nome == "Teclado"

    def test_cadastrar_sku_duplicado_com_outra_grafia_e_rejeitado(self, servico):
        """Objetivo: Garantir a unicidade do SKU independentemente de maiúsculas/minúsculas.
        Técnica: Partição de equivalência (classe inválida: duplicidade)
        Requisitos: RN-E01
        """
        with pytest.raises(ProdutoJaCadastrado):
            servico.cadastrar({"sku": "tec-001", "nome": "Outro", "preco": 1})

    def test_obter_normaliza_sku_informado(self, servico):
        """Objetivo: Verificar que a consulta aceita o SKU em minúsculas.
        Técnica: Partição de equivalência (classe válida)
        Requisitos: RF-E02, RN-E01
        """
        assert servico.obter(" mou-001 ").sku == "MOU-001"

    def test_obter_com_sku_invalido_lanca_dados_invalidos(self, servico):
        """Objetivo: Verificar que uma consulta com SKU fora do padrão é rejeitada antes da busca.
        Técnica: Partição de equivalência (classe inválida)
        Requisitos: RN-E01
        """
        with pytest.raises(DadosInvalidos):
            servico.obter("x")


class TestEntrada:
    def test_registrar_entrada_incrementa_saldo(self, servico):
        """Objetivo: Verificar que registrar entrada aumenta o saldo do produto.
        Técnica: Partição de equivalência (classe válida)
        Requisitos: RF-E03
        """
        assert servico.registrar_entrada("MOU-001", 7).quantidade == 12

    @pytest.mark.parametrize("quantidade", [0, -1, "3", None])
    def test_registrar_entrada_com_quantidade_invalida_nao_altera_saldo(self, servico, quantidade):
        """Objetivo: Garantir que entradas com quantidade inválida são rejeitadas sem alterar o saldo.
        Técnica: Análise de valor limite (0) e partição de equivalência (tipos inválidos)
        Requisitos: RF-E03, RN-E04
        """
        with pytest.raises(DadosInvalidos):
            servico.registrar_entrada("MOU-001", quantidade)
        assert servico.obter("MOU-001").quantidade == 5

    def test_registrar_entrada_em_produto_inexistente(self, servico):
        """Objetivo: Verificar que não é possível registrar entrada para produto inexistente.
        Técnica: Partição de equivalência (classe inválida)
        Requisitos: RF-E03
        """
        with pytest.raises(ProdutoNaoEncontrado):
            servico.registrar_entrada("NAO-EXISTE", 1)


class TestBaixa:
    def test_baixa_retorna_nome_preco_e_saldo_restante(self, servico):
        """Objetivo: Verificar que a baixa em lote atualiza os saldos e retorna nome, preço vigente e saldo restante.
        Técnica: Partição de equivalência (classe válida) e verificação de contrato
        Requisitos: RF-E04, RN-P02
        """
        resultado = servico.baixar([{"sku": "TEC-001", "quantidade": 2},
                                    {"sku": "MOU-001", "quantidade": 1}])
        assert resultado == [
            {"sku": "TEC-001", "nome": "Teclado", "preco": "250.00", "quantidade": 2, "saldo": 8},
            {"sku": "MOU-001", "nome": "Mouse", "preco": "120.00", "quantidade": 1, "saldo": 4},
        ]
        assert saldos(servico) == {"TEC-001": 8, "MOU-001": 4}

    def test_baixa_de_todo_o_saldo_gera_alerta_de_reposicao(self, servico):
        """Objetivo: Garantir que baixar exatamente o saldo zera o estoque e o produto passa a precisar de reposição.
        Técnica: Análise de valor limite (quantidade = saldo)
        Requisitos: RF-E04, RN-E05
        """
        servico.baixar([{"sku": "MOU-001", "quantidade": 5}])
        assert servico.obter("MOU-001").quantidade == 0
        assert [p.sku for p in servico.produtos_para_reposicao()] == ["MOU-001"]

    def test_baixa_e_atomica_quando_um_item_nao_tem_saldo(self, servico):
        """Objetivo: Garantir que, se um item do lote não tem saldo, nenhum item é baixado (tudo ou nada).
        Técnica: Teste de transação/atomicidade com valor limite (saldo+1)
        Requisitos: RN-E06, RN-P04
        """
        with pytest.raises(EstoqueInsuficiente) as erro:
            servico.baixar([{"sku": "TEC-001", "quantidade": 2}, {"sku": "MOU-001", "quantidade": 6}])
        assert erro.value.sku == "MOU-001"
        assert saldos(servico) == {"TEC-001": 10, "MOU-001": 5}

    def test_baixa_e_atomica_quando_um_produto_nao_existe(self, servico):
        """Objetivo: Garantir que um SKU inexistente no lote impede a baixa dos demais itens.
        Técnica: Teste de atomicidade (classe inválida)
        Requisitos: RN-E06
        """
        with pytest.raises(ProdutoNaoEncontrado):
            servico.baixar([{"sku": "TEC-001", "quantidade": 1}, {"sku": "NAO-EXISTE", "quantidade": 1}])
        assert saldos(servico) == {"TEC-001": 10, "MOU-001": 5}

    def test_baixa_considera_soma_de_itens_repetidos(self, servico):
        """Objetivo: Garantir que itens repetidos são somados antes da verificação de saldo (3 + 3 > 5).
        Técnica: Análise de valor limite após agrupamento
        Requisitos: RN-E06
        """
        with pytest.raises(EstoqueInsuficiente):
            servico.baixar([{"sku": "MOU-001", "quantidade": 3}, {"sku": "MOU-001", "quantidade": 3}])
        assert servico.obter("MOU-001").quantidade == 5

    def test_baixas_concorrentes_nunca_deixam_saldo_negativo(self, servico):
        """Objetivo: Verificar que 30 baixas simultâneas de 1 unidade sobre saldo 10 resultam em exatamente 10 sucessos.
        Técnica: Teste de concorrência (condição de corrida)
        Requisitos: RNF04
        """
        sucessos, falhas = [], []
        barreira = threading.Barrier(30)

        def comprar():
            barreira.wait()
            try:
                servico.baixar([{"sku": "TEC-001", "quantidade": 1}])
                sucessos.append(1)
            except EstoqueInsuficiente:
                falhas.append(1)

        threads = [threading.Thread(target=comprar) for _ in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert (len(sucessos), len(falhas)) == (10, 20)
        assert servico.obter("TEC-001").quantidade == 0


class TestDevolucao:
    def test_devolucao_incrementa_saldos(self, servico):
        """Objetivo: Verificar que a devolução (estorno) soma as quantidades aos saldos.
        Técnica: Partição de equivalência (classe válida)
        Requisitos: RF-E05
        """
        produtos = servico.devolver([{"sku": "TEC-001", "quantidade": 2}, {"sku": "MOU-001", "quantidade": 1}])
        assert [p.sku for p in produtos] == ["TEC-001", "MOU-001"]
        assert saldos(servico) == {"TEC-001": 12, "MOU-001": 6}

    def test_devolucao_com_produto_inexistente_nao_altera_nada(self, servico):
        """Objetivo: Garantir que a devolução é atômica quando um SKU não existe.
        Técnica: Teste de atomicidade (classe inválida)
        Requisitos: RF-E05, RN-E06
        """
        with pytest.raises(ProdutoNaoEncontrado):
            servico.devolver([{"sku": "TEC-001", "quantidade": 2}, {"sku": "NAO-EXISTE", "quantidade": 1}])
        assert saldos(servico) == {"TEC-001": 10, "MOU-001": 5}

    def test_devolucao_acima_da_capacidade_nao_altera_nada(self, servico):
        """Objetivo: Garantir que, se um item exceder a capacidade máxima, nenhum saldo é alterado.
        Técnica: Análise de valor limite (capacidade+1) e atomicidade
        Requisitos: RF-E05, RN-E04
        """
        servico.obter("MOU-001").quantidade = CAPACIDADE_MAXIMA
        with pytest.raises(DadosInvalidos, match="Capacidade"):
            servico.devolver([{"sku": "TEC-001", "quantidade": 2}, {"sku": "MOU-001", "quantidade": 1}])
        assert saldos(servico) == {"TEC-001": 10, "MOU-001": CAPACIDADE_MAXIMA}


class TestReposicao:
    def test_lista_apenas_produtos_com_saldo_ate_o_minimo(self, servico):
        """Objetivo: Verificar que a lista de reposição contém somente produtos com saldo menor ou igual ao mínimo.
        Técnica: Análise de valor limite (saldo = mínimo)
        Requisitos: RF-E06, RN-E05
        """
        assert servico.produtos_para_reposicao() == []
        servico.baixar([{"sku": "TEC-001", "quantidade": 7}])  # saldo 3 = mínimo 3
        assert [p.sku for p in servico.produtos_para_reposicao()] == ["TEC-001"]
