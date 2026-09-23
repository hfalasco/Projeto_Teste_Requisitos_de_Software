"""Testes unitários dos casos de uso do Serviço de Pedidos com o estoque substituído por dublês."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest

from pedidos_service.cliente_estoque import ClienteEstoque
from pedidos_service.dominio import (
    DadosInvalidos,
    EstoqueIndisponivel,
    EstoqueInsuficiente,
    ItemPedido,
    PedidoNaoEncontrado,
    ProdutoInexistente,
    StatusPedido,
    TransicaoInvalida,
)
from pedidos_service.repositorio import RepositorioPedidosEmMemoria
from pedidos_service.servico import ServicoPedidos
from tests.unit.pedidos.dubles import EstoqueFalso

AGORA = datetime(2026, 9, 24, 19, 0, tzinfo=timezone.utc)


@pytest.fixture
def estoque():
    return EstoqueFalso()


@pytest.fixture
def servico(estoque):
    return ServicoPedidos(estoque, relogio=lambda: AGORA)


def pedido_valido(**alteracoes):
    dados = {"cliente": "Maria Souza", "itens": [{"sku": "TEC-001", "quantidade": 2},
                                                  {"sku": "MOU-001", "quantidade": 1}]}
    dados.update(alteracoes)
    return dados


class TestRepositorioPedidos:
    def test_ids_sao_sequenciais_e_listagem_e_do_mais_recente(self):
        """Objetivo: Verificar que o repositório gera ids sequenciais e lista do pedido mais recente para o mais antigo.
        Técnica: Verificação de estado
        Requisitos: RF-P03
        """
        repositorio = RepositorioPedidosEmMemoria()
        item = ItemPedido("TEC-001", "Teclado", 1, Decimal("1.00"))
        primeiro = repositorio.criar("Ana", [item], AGORA)
        segundo = repositorio.criar("Bia", [item], AGORA)
        assert (primeiro.id, segundo.id) == (1, 2)
        assert [p.id for p in repositorio.listar()] == [2, 1]
        assert repositorio.obter(1) is primeiro

    def test_obter_id_inexistente_lanca_erro(self):
        """Objetivo: Verificar que consultar um id inexistente lança PedidoNaoEncontrado.
        Técnica: Partição de equivalência (classe inválida)
        Requisitos: RF-P03
        """
        with pytest.raises(PedidoNaoEncontrado):
            RepositorioPedidosEmMemoria().obter(99)


class TestCriarPedido:
    def test_cria_pedido_confirmado_com_preco_vindo_do_estoque(self, servico, estoque):
        """Objetivo: Verificar que o pedido é criado CONFIRMADO, com preços informados pelo estoque (ignorando preço enviado pelo cliente) e data do relógio injetado.
        Técnica: Dublê de teste (fake do estoque) e injeção de dependência (relógio)
        Requisitos: RF-P02, RN-P02
        """
        dados = pedido_valido(itens=[{"sku": "TEC-001", "quantidade": 2, "preco": "0.01"}])
        pedido = servico.criar_pedido(dados)
        assert pedido.id == 1
        assert pedido.status is StatusPedido.CONFIRMADO
        assert pedido.itens == [ItemPedido("TEC-001", "Teclado", 2, Decimal("250.00"))]
        assert pedido.criado_em == AGORA
        assert (pedido.subtotal, pedido.desconto, pedido.total) == (
            Decimal("500.00"), Decimal("25.00"), Decimal("475.00"))

    def test_envia_ao_estoque_itens_normalizados_e_agrupados(self, servico, estoque):
        """Objetivo: Verificar que o estoque recebe os itens já validados, normalizados e agrupados.
        Técnica: Dublê de teste (spy) para verificar a interação
        Requisitos: RN-P01, RN-P04
        """
        servico.criar_pedido(pedido_valido(itens=[{"sku": "tec-001", "quantidade": 1},
                                                  {"sku": "TEC-001", "quantidade": 2}]))
        assert estoque.chamadas == [("baixar", [{"sku": "TEC-001", "quantidade": 3}])]
        assert estoque.saldo("TEC-001") == 7

    def test_dados_invalidos_nao_chegam_ao_estoque(self):
        """Objetivo: Garantir que uma solicitação inválida é rejeitada antes de qualquer chamada ao estoque.
        Técnica: Dublê de teste (mock) com verificação de ausência de chamada
        Requisitos: RN-P01
        """
        estoque = Mock(spec=ClienteEstoque)
        servico = ServicoPedidos(estoque)
        with pytest.raises(DadosInvalidos):
            servico.criar_pedido(pedido_valido(itens=[{"sku": "TEC-001", "quantidade": 0}]))
        estoque.baixar.assert_not_called()

    @pytest.mark.parametrize("itens, excecao", [
        ([{"sku": "MOU-001", "quantidade": 6}], EstoqueInsuficiente),
        ([{"sku": "NAO-EXISTE", "quantidade": 1}], ProdutoInexistente),
    ])
    def test_recusa_do_estoque_nao_gera_pedido(self, servico, itens, excecao):
        """Objetivo: Garantir que, se o estoque recusar a reserva (saldo insuficiente ou produto inexistente), nenhum pedido é registrado.
        Técnica: Dublê de teste (fake) com injeção de falha
        Requisitos: RN-P04
        """
        with pytest.raises(excecao):
            servico.criar_pedido(pedido_valido(itens=itens))
        assert servico.listar_pedidos() == []

    def test_estoque_indisponivel_nao_gera_pedido(self, servico, estoque):
        """Objetivo: Garantir que, com o estoque fora do ar, a criação falha com EstoqueIndisponivel e nada é registrado.
        Técnica: Dublê de teste (fake) com injeção de falha
        Requisitos: RN-P06
        """
        estoque.disponivel = False
        with pytest.raises(EstoqueIndisponivel):
            servico.criar_pedido(pedido_valido())
        assert servico.listar_pedidos() == []


class TestConsultas:
    def test_listar_e_obter_pedidos(self, servico):
        """Objetivo: Verificar a listagem (mais recente primeiro) e a consulta de pedidos por id.
        Técnica: Verificação de estado
        Requisitos: RF-P03
        """
        primeiro = servico.criar_pedido(pedido_valido())
        segundo = servico.criar_pedido(pedido_valido(cliente="João Lima"))
        assert servico.listar_pedidos() == [segundo, primeiro]
        assert servico.obter_pedido(1) is primeiro

    def test_obter_pedido_inexistente(self, servico):
        """Objetivo: Verificar que consultar um pedido inexistente lança PedidoNaoEncontrado.
        Técnica: Partição de equivalência (classe inválida)
        Requisitos: RF-P03
        """
        with pytest.raises(PedidoNaoEncontrado):
            servico.obter_pedido(123)

    def test_catalogo_e_saude_delegam_ao_estoque(self, servico, estoque):
        """Objetivo: Verificar que catálogo e verificação de saúde são obtidos do cliente de estoque injetado.
        Técnica: Dublê de teste (fake)
        Requisitos: RF-P01, RF-P05
        """
        assert [p["sku"] for p in servico.catalogo()] == ["MON-001", "MOU-001", "TEC-001"]
        assert servico.estoque_disponivel() is True
        estoque.disponivel = False
        assert servico.estoque_disponivel() is False
        assert servico.cliente_estoque is estoque


class TestCancelarPedido:
    def test_cancelamento_devolve_itens_e_marca_cancelado(self, servico, estoque):
        """Objetivo: Verificar que cancelar devolve os itens ao estoque e marca o pedido como CANCELADO com a data do relógio.
        Técnica: Dublê de teste (spy) e teste de transição de estados
        Requisitos: RF-P04, RN-P05, RF-E05
        """
        pedido = servico.criar_pedido(pedido_valido())
        servico.cancelar_pedido(pedido.id)
        assert pedido.status is StatusPedido.CANCELADO
        assert pedido.cancelado_em == AGORA
        assert estoque.chamadas[-1] == ("devolver", [{"sku": "TEC-001", "quantidade": 2},
                                                     {"sku": "MOU-001", "quantidade": 1}])
        assert (estoque.saldo("TEC-001"), estoque.saldo("MOU-001")) == (10, 5)

    def test_cancelar_duas_vezes_nao_devolve_em_dobro(self, servico, estoque):
        """Objetivo: Garantir que o segundo cancelamento é recusado e o estoque recebe a devolução uma única vez.
        Técnica: Teste de transição de estados (transição inválida)
        Requisitos: RN-P05
        """
        pedido = servico.criar_pedido(pedido_valido())
        servico.cancelar_pedido(pedido.id)
        with pytest.raises(TransicaoInvalida):
            servico.cancelar_pedido(pedido.id)
        assert [c[0] for c in estoque.chamadas].count("devolver") == 1
        assert estoque.saldo("TEC-001") == 10

    def test_estoque_indisponivel_mantem_pedido_confirmado(self, servico, estoque):
        """Objetivo: Garantir que, se o estoque estiver fora do ar no cancelamento, o pedido permanece CONFIRMADO (consistência entre serviços).
        Técnica: Dublê de teste (fake) com injeção de falha
        Requisitos: RN-P05, RN-P06
        """
        pedido = servico.criar_pedido(pedido_valido())
        estoque.disponivel = False
        with pytest.raises(EstoqueIndisponivel):
            servico.cancelar_pedido(pedido.id)
        assert pedido.status is StatusPedido.CONFIRMADO
        assert pedido.cancelado_em is None

    def test_cancelar_pedido_inexistente_nao_chama_estoque(self):
        """Objetivo: Verificar que cancelar um id inexistente lança PedidoNaoEncontrado sem chamar o estoque.
        Técnica: Dublê de teste (mock) com verificação de ausência de chamada
        Requisitos: RF-P04
        """
        estoque = Mock(spec=ClienteEstoque)
        with pytest.raises(PedidoNaoEncontrado):
            ServicoPedidos(estoque).cancelar_pedido(7)
        estoque.devolver.assert_not_called()
