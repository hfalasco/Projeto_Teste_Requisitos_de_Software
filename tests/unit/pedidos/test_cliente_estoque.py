"""Testes unitários do cliente HTTP do estoque, isolado da rede com dublês de requests."""

from decimal import Decimal
from unittest.mock import Mock

import pytest
import requests

from pedidos_service.cliente_estoque import TIMEOUT_PADRAO, ClienteEstoque
from pedidos_service.dominio import (
    DadosInvalidos,
    EstoqueIndisponivel,
    EstoqueInsuficiente,
    ProdutoInexistente,
    RespostaInvalidaEstoque,
)
from tests.unit.pedidos.dubles import RespostaFalsa

URL = "http://estoque.teste"


def cliente_com(resposta=None, erro=None):
    """Cria um ClienteEstoque cuja sessão HTTP é um mock que retorna ``resposta`` ou lança ``erro``."""
    sessao = Mock(spec=requests.Session)
    if erro is not None:
        sessao.request.side_effect = erro
    else:
        sessao.request.return_value = resposta
    return ClienteEstoque(URL + "/", timeout=1.5, sessao=sessao), sessao


class TestConfiguracao:
    def test_remove_barra_final_e_cria_sessao_padrao(self):
        """Objetivo: Verificar que a URL base é normalizada e que uma sessão requests é criada quando não injetada.
        Técnica: Verificação de configuração padrão
        Requisitos: RNF03, RNF05
        """
        cliente = ClienteEstoque("http://localhost:5001/")
        assert cliente.url_base == "http://localhost:5001"
        assert cliente.timeout == TIMEOUT_PADRAO == 3.0
        assert isinstance(cliente._sessao, requests.Session)


class TestChamadasBemSucedidas:
    def test_listar_produtos_faz_get_com_timeout(self):
        """Objetivo: Verificar que o catálogo é obtido via GET /api/produtos respeitando o timeout configurado.
        Técnica: Dublê de teste (mock) para verificar a interação HTTP
        Requisitos: RF-P01, RNF03
        """
        produtos = [{"sku": "TEC-001", "nome": "Teclado", "preco": "250.00", "quantidade": 10}]
        cliente, sessao = cliente_com(RespostaFalsa(200, produtos))
        assert cliente.listar_produtos() == produtos
        sessao.request.assert_called_once_with("GET", f"{URL}/api/produtos", json=None, timeout=1.5)

    def test_baixar_envia_itens_e_converte_preco_para_decimal(self):
        """Objetivo: Verificar que a baixa envia POST com os itens e converte o preço recebido para Decimal.
        Técnica: Dublê de teste (mock) e verificação de contrato de integração (consumidor)
        Requisitos: RF-E04, RN-P02
        """
        corpo = {"itens": [{"sku": "TEC-001", "nome": "Teclado", "preco": "250.00", "quantidade": 2, "saldo": 8}]}
        cliente, sessao = cliente_com(RespostaFalsa(200, corpo))
        itens = [{"sku": "TEC-001", "quantidade": 2}]
        assert cliente.baixar(itens) == [
            {"sku": "TEC-001", "nome": "Teclado", "quantidade": 2, "preco": Decimal("250.00")}]
        sessao.request.assert_called_once_with(
            "POST", f"{URL}/api/estoque/baixas", json={"itens": itens}, timeout=1.5)

    def test_devolver_envia_post_de_devolucao(self):
        """Objetivo: Verificar que a devolução envia POST /api/estoque/devolucoes com os itens.
        Técnica: Dublê de teste (mock) para verificar a interação HTTP
        Requisitos: RF-E05, RF-P04
        """
        cliente, sessao = cliente_com(RespostaFalsa(200, {"itens": []}))
        cliente.devolver([{"sku": "TEC-001", "quantidade": 1}])
        sessao.request.assert_called_once_with(
            "POST", f"{URL}/api/estoque/devolucoes", json={"itens": [{"sku": "TEC-001", "quantidade": 1}]},
            timeout=1.5)

    def test_esta_disponivel_quando_health_responde(self):
        """Objetivo: Verificar que o estoque é considerado disponível quando GET /health responde 200.
        Técnica: Dublê de teste (stub)
        Requisitos: RF-P05
        """
        cliente, sessao = cliente_com(RespostaFalsa(200, {"status": "ok"}))
        assert cliente.esta_disponivel() is True
        assert sessao.request.call_args.args == ("GET", f"{URL}/health")


class TestTraducaoDeErros:
    @pytest.mark.parametrize(
        "status, codigo, excecao",
        [
            (409, "ESTOQUE_INSUFICIENTE", EstoqueInsuficiente),
            (404, "PRODUTO_NAO_ENCONTRADO", ProdutoInexistente),
            (400, "DADOS_INVALIDOS", DadosInvalidos),
        ],
    )
    def test_erros_de_negocio_do_estoque_viram_excecoes_do_pedido(self, status, codigo, excecao):
        """Objetivo: Verificar que cada código de erro do estoque é traduzido para a exceção correspondente, preservando a mensagem.
        Técnica: Tabela de decisão (código HTTP/código de erro → exceção)
        Requisitos: RN-P04, RNF01
        """
        cliente, _ = cliente_com(RespostaFalsa(status, {"erro": "mensagem do estoque", "codigo": codigo}))
        with pytest.raises(excecao, match="mensagem do estoque"):
            cliente.baixar([{"sku": "TEC-001", "quantidade": 1}])

    @pytest.mark.parametrize("dados, mensagem", [
        ({"erro": "Método não permitido.", "codigo": "METODO_NAO_PERMITIDO"}, "Método não permitido"),
        (["lista", "inesperada"], "Erro HTTP 405"),
    ])
    def test_erro_4xx_desconhecido_vira_resposta_invalida(self, dados, mensagem):
        """Objetivo: Garantir que erros 4xx sem código conhecido (ou com corpo inesperado) viram RespostaInvalidaEstoque.
        Técnica: Tabela de decisão (caso padrão) e partição de equivalência
        Requisitos: RN-P06
        """
        cliente, _ = cliente_com(RespostaFalsa(405, dados))
        with pytest.raises(RespostaInvalidaEstoque, match=mensagem):
            cliente.listar_produtos()

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_erro_5xx_indica_estoque_indisponivel(self, status):
        """Objetivo: Verificar que respostas 5xx do estoque resultam em EstoqueIndisponivel.
        Técnica: Partição de equivalência (classe 5xx)
        Requisitos: RN-P06
        """
        cliente, _ = cliente_com(RespostaFalsa(status, json_invalido=True))
        with pytest.raises(EstoqueIndisponivel, match=f"HTTP {status}"):
            cliente.listar_produtos()

    def test_timeout_indica_estoque_indisponivel(self):
        """Objetivo: Verificar que um timeout na chamada HTTP resulta em EstoqueIndisponivel com mensagem de tempo limite.
        Técnica: Dublê de teste (mock que lança exceção) - injeção de falha
        Requisitos: RN-P06, RNF03
        """
        cliente, _ = cliente_com(erro=requests.Timeout("lento"))
        with pytest.raises(EstoqueIndisponivel, match="tempo limite"):
            cliente.baixar([{"sku": "TEC-001", "quantidade": 1}])

    def test_falha_de_conexao_indica_estoque_indisponivel(self):
        """Objetivo: Verificar que uma falha de conexão resulta em EstoqueIndisponivel.
        Técnica: Dublê de teste (mock que lança exceção) - injeção de falha
        Requisitos: RN-P06
        """
        cliente, _ = cliente_com(erro=requests.ConnectionError("recusada"))
        with pytest.raises(EstoqueIndisponivel, match="conectar"):
            cliente.listar_produtos()

    def test_resposta_que_nao_e_json_e_invalida(self):
        """Objetivo: Garantir que uma resposta 200 sem JSON válido é tratada como RespostaInvalidaEstoque.
        Técnica: Dublê de teste (stub) com resposta malformada
        Requisitos: RN-P06
        """
        cliente, _ = cliente_com(RespostaFalsa(200, json_invalido=True))
        with pytest.raises(RespostaInvalidaEstoque, match="não é JSON"):
            cliente.listar_produtos()

    def test_catalogo_em_formato_inesperado_e_invalido(self):
        """Objetivo: Garantir que um catálogo que não é uma lista é rejeitado.
        Técnica: Dublê de teste (stub) com contrato violado
        Requisitos: RF-P01, RN-P06
        """
        cliente, _ = cliente_com(RespostaFalsa(200, {"produtos": []}))
        with pytest.raises(RespostaInvalidaEstoque, match="formato inesperado"):
            cliente.listar_produtos()

    @pytest.mark.parametrize("corpo", [
        {},
        {"itens": [{"sku": "TEC-001", "nome": "Teclado", "quantidade": 1}]},
        {"itens": [{"sku": "TEC-001", "nome": "Teclado", "quantidade": 1, "preco": "abc"}]},
        {"itens": [{"sku": "TEC-001", "nome": "Teclado", "quantidade": "um", "preco": "1.00"}]},
        {"itens": None},
    ])
    def test_resposta_de_baixa_com_contrato_violado_e_invalida(self, corpo):
        """Objetivo: Garantir que respostas de baixa sem campos obrigatórios ou com valores inválidos são rejeitadas.
        Técnica: Partição de equivalência (violações do contrato de integração)
        Requisitos: RN-P02, RN-P06
        """
        cliente, _ = cliente_com(RespostaFalsa(200, corpo))
        with pytest.raises(RespostaInvalidaEstoque, match="formato inesperado"):
            cliente.baixar([{"sku": "TEC-001", "quantidade": 1}])

    def test_esta_disponivel_retorna_falso_quando_estoque_falha(self):
        """Objetivo: Verificar que falhas de comunicação fazem esta_disponivel() retornar False, sem lançar exceção.
        Técnica: Dublê de teste (mock que lança exceção)
        Requisitos: RF-P05
        """
        cliente, _ = cliente_com(erro=requests.ConnectionError("recusada"))
        assert cliente.esta_disponivel() is False
