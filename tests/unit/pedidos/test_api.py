"""Testes unitários da camada HTTP do Serviço de Pedidos (Flask test client + estoque falso)."""

import runpy
import sys

import pytest
from flask import Flask

import pedidos_service.__main__ as principal
from pedidos_service.app import URL_ESTOQUE_PADRAO, criar_app, criar_servico_padrao
from pedidos_service.dominio import ErroPedido, RespostaInvalidaEstoque
from pedidos_service.servico import ServicoPedidos
from tests.unit.pedidos.dubles import EstoqueFalso


@pytest.fixture
def estoque():
    return EstoqueFalso()


@pytest.fixture
def cliente(estoque):
    app = criar_app(ServicoPedidos(estoque))
    app.testing = True
    return app.test_client()


PEDIDO = {"cliente": "Maria Souza", "itens": [{"sku": "TEC-001", "quantidade": 2}]}


class TestPaginasESaude:
    def test_pagina_inicial_retorna_html_da_interface(self, cliente):
        """Objetivo: Verificar que a rota / entrega a interface web de pedidos.
        Técnica: Teste de rota (caixa-preta)
        Requisitos: RF-P02
        """
        resposta = cliente.get("/")
        assert resposta.status_code == 200
        assert "Serviço de Pedidos" in resposta.get_data(as_text=True)

    @pytest.mark.parametrize("disponivel, situacao", [(True, "ok"), (False, "indisponivel")])
    def test_health_informa_situacao_da_dependencia_estoque(self, cliente, estoque, disponivel, situacao):
        """Objetivo: Verificar que o health check do serviço de pedidos informa se o estoque está disponível.
        Técnica: Partição de equivalência (estoque online/offline) com dublê
        Requisitos: RF-P05
        """
        estoque.disponivel = disponivel
        resposta = cliente.get("/health")
        assert resposta.status_code == 200
        assert resposta.get_json() == {"servico": "pedidos", "status": "ok",
                                       "dependencias": {"estoque": situacao}}


class TestCatalogoApi:
    def test_catalogo_retorna_produtos_do_estoque(self, cliente):
        """Objetivo: Verificar que o catálogo exposto pelo serviço de pedidos vem do estoque.
        Técnica: Dublê de teste (fake)
        Requisitos: RF-P01
        """
        resposta = cliente.get("/api/catalogo")
        assert resposta.status_code == 200
        assert [p["sku"] for p in resposta.get_json()] == ["MON-001", "MOU-001", "TEC-001"]

    def test_catalogo_com_estoque_fora_do_ar_retorna_503(self, cliente, estoque):
        """Objetivo: Verificar que, com o estoque indisponível, o catálogo responde 503 com código ESTOQUE_INDISPONIVEL.
        Técnica: Injeção de falha com dublê
        Requisitos: RF-P01, RN-P06
        """
        estoque.disponivel = False
        resposta = cliente.get("/api/catalogo")
        assert resposta.status_code == 503
        assert resposta.get_json()["codigo"] == "ESTOQUE_INDISPONIVEL"


class TestCriarPedidoApi:
    def test_post_pedido_valido_retorna_201_com_totais(self, cliente):
        """Objetivo: Verificar que um pedido válido retorna 201 com status, itens, desconto e total.
        Técnica: Partição de equivalência (classe válida) e contrato HTTP
        Requisitos: RF-P02, RN-P03, RNF01
        """
        resposta = cliente.post("/api/pedidos", json=PEDIDO)
        assert resposta.status_code == 201
        corpo = resposta.get_json()
        assert (corpo["id"], corpo["status"], corpo["subtotal"], corpo["desconto"], corpo["total"]) == (
            1, "CONFIRMADO", "500.00", "25.00", "475.00")

    @pytest.mark.parametrize("corpo", [{"cliente": "Maria", "itens": []}, {"itens": PEDIDO["itens"]}, None])
    def test_post_pedido_invalido_retorna_400(self, cliente, corpo):
        """Objetivo: Verificar que pedido sem itens, sem cliente ou sem corpo JSON retorna 400.
        Técnica: Partição de equivalência (classes inválidas)
        Requisitos: RN-P01, RNF01
        """
        resposta = cliente.post("/api/pedidos", json=corpo) if corpo is not None else \
            cliente.post("/api/pedidos", data="xyz", content_type="text/plain")
        assert resposta.status_code == 400
        assert resposta.get_json()["codigo"] == "DADOS_INVALIDOS"

    @pytest.mark.parametrize("itens, status, codigo", [
        ([{"sku": "MOU-001", "quantidade": 6}], 409, "ESTOQUE_INSUFICIENTE"),
        ([{"sku": "NAO-EXISTE", "quantidade": 1}], 422, "PRODUTO_INEXISTENTE"),
    ])
    def test_recusas_do_estoque_viram_status_http_adequados(self, cliente, itens, status, codigo):
        """Objetivo: Verificar que saldo insuficiente gera 409 e produto inexistente gera 422.
        Técnica: Tabela de decisão (erro → status HTTP)
        Requisitos: RN-P04, RNF01
        """
        resposta = cliente.post("/api/pedidos", json={"cliente": "Maria", "itens": itens})
        assert resposta.status_code == status
        assert resposta.get_json()["codigo"] == codigo

    def test_estoque_indisponivel_retorna_503(self, cliente, estoque):
        """Objetivo: Verificar que, com o estoque fora do ar, a criação de pedido responde 503.
        Técnica: Injeção de falha com dublê
        Requisitos: RN-P06
        """
        estoque.disponivel = False
        resposta = cliente.post("/api/pedidos", json=PEDIDO)
        assert resposta.status_code == 503

    def test_resposta_invalida_do_estoque_retorna_502(self, estoque):
        """Objetivo: Verificar que uma resposta fora do contrato vinda do estoque gera 502 Bad Gateway.
        Técnica: Dublê de teste (stub que lança exceção)
        Requisitos: RN-P06
        """
        def baixar_com_contrato_violado(itens):
            raise RespostaInvalidaEstoque("formato inesperado")

        estoque.baixar = baixar_com_contrato_violado
        resposta = criar_app(ServicoPedidos(estoque)).test_client().post("/api/pedidos", json=PEDIDO)
        assert resposta.status_code == 502
        assert resposta.get_json()["codigo"] == "RESPOSTA_INVALIDA_ESTOQUE"


class TestConsultaECancelamentoApi:
    def test_listar_e_consultar_pedido(self, cliente):
        """Objetivo: Verificar a listagem de pedidos e a consulta por id via API.
        Técnica: Teste de rota (caixa-preta)
        Requisitos: RF-P03
        """
        cliente.post("/api/pedidos", json=PEDIDO)
        assert [p["id"] for p in cliente.get("/api/pedidos").get_json()] == [1]
        resposta = cliente.get("/api/pedidos/1")
        assert resposta.status_code == 200
        assert resposta.get_json()["cliente"] == "Maria Souza"

    def test_consultar_pedido_inexistente_retorna_404(self, cliente):
        """Objetivo: Verificar que consultar um id inexistente retorna 404 com código PEDIDO_NAO_ENCONTRADO.
        Técnica: Partição de equivalência (classe inválida)
        Requisitos: RF-P03, RNF01
        """
        resposta = cliente.get("/api/pedidos/999")
        assert resposta.status_code == 404
        assert resposta.get_json()["codigo"] == "PEDIDO_NAO_ENCONTRADO"

    def test_cancelar_pedido_retorna_200_e_segunda_vez_409(self, cliente, estoque):
        """Objetivo: Verificar que o primeiro cancelamento retorna 200 (CANCELADO) e o segundo 409 (transição inválida).
        Técnica: Teste de transição de estados via API
        Requisitos: RF-P04, RN-P05
        """
        cliente.post("/api/pedidos", json=PEDIDO)
        primeira = cliente.post("/api/pedidos/1/cancelamento")
        segunda = cliente.post("/api/pedidos/1/cancelamento")
        assert (primeira.status_code, primeira.get_json()["status"]) == (200, "CANCELADO")
        assert (segunda.status_code, segunda.get_json()["codigo"]) == (409, "TRANSICAO_INVALIDA")
        assert estoque.saldo("TEC-001") == 10


class TestErrosGenericos:
    def test_rota_inexistente_e_metodo_nao_permitido_em_json(self, cliente):
        """Objetivo: Verificar que rota desconhecida (404) e método não suportado (405) retornam JSON padronizado.
        Técnica: Partição de equivalência (classes inválidas)
        Requisitos: RNF01
        """
        assert cliente.get("/nao/existe").get_json()["codigo"] == "ROTA_INEXISTENTE"
        resposta = cliente.delete("/api/pedidos")
        assert (resposta.status_code, resposta.get_json()["codigo"]) == (405, "METODO_NAO_PERMITIDO")

    def test_erro_de_negocio_nao_mapeado_retorna_400(self, estoque):
        """Objetivo: Garantir que um erro de negócio genérico (sem status específico) é convertido em 400.
        Técnica: Dublê de teste (stub do serviço) para forçar o caminho de erro
        Requisitos: RNF01
        """

        class ServicoComFalha(ServicoPedidos):
            def listar_pedidos(self):
                raise ErroPedido("falha genérica")

        resposta = criar_app(ServicoComFalha(estoque)).test_client().get("/api/pedidos")
        assert resposta.status_code == 400
        assert resposta.get_json() == {"erro": "falha genérica", "codigo": "ERRO_PEDIDO"}


class TestConfiguracaoEInicializacao:
    def test_servico_padrao_le_url_e_timeout_do_ambiente(self, monkeypatch):
        """Objetivo: Verificar que a URL e o timeout do estoque são lidos das variáveis ESTOQUE_URL e ESTOQUE_TIMEOUT.
        Técnica: Configuração por ambiente (monkeypatch)
        Requisitos: RNF03, RNF05
        """
        monkeypatch.setenv("ESTOQUE_URL", "http://estoque:9000/")
        monkeypatch.setenv("ESTOQUE_TIMEOUT", "0.5")
        cliente_estoque = criar_servico_padrao().cliente_estoque
        assert (cliente_estoque.url_base, cliente_estoque.timeout) == ("http://estoque:9000", 0.5)

    def test_app_sem_servico_injetado_usa_configuracao_padrao(self, monkeypatch):
        """Objetivo: Verificar que, sem variáveis de ambiente, o app aponta para o estoque em http://127.0.0.1:5001 com timeout de 3 s.
        Técnica: Verificação de configuração padrão
        Requisitos: RNF03, RNF05
        """
        monkeypatch.delenv("ESTOQUE_URL", raising=False)
        monkeypatch.delenv("ESTOQUE_TIMEOUT", raising=False)
        cliente_estoque = criar_app().config["SERVICO_PEDIDOS"].cliente_estoque
        assert (cliente_estoque.url_base, cliente_estoque.timeout) == (URL_ESTOQUE_PADRAO, 3.0)

    def test_main_usa_host_e_porta_das_variaveis_de_ambiente(self, monkeypatch):
        """Objetivo: Verificar que o servidor é iniciado com host e porta definidos por variáveis de ambiente.
        Técnica: Dublê de teste (mock de Flask.run) e configuração por ambiente
        Requisitos: RNF05
        """
        chamadas = []
        monkeypatch.setattr(Flask, "run", lambda self, **kw: chamadas.append(kw))
        monkeypatch.setenv("PEDIDOS_HOST", "0.0.0.0")
        monkeypatch.setenv("PEDIDOS_PORTA", "7002")
        principal.main()
        assert chamadas == [{"host": "0.0.0.0", "port": 7002, "threaded": True}]

    def test_execucao_como_modulo_usa_porta_padrao_5002(self, monkeypatch):
        """Objetivo: Verificar que "python -m pedidos_service" sobe o servidor na porta padrão 5002.
        Técnica: Dublê de teste (mock de Flask.run)
        Requisitos: RNF05
        """
        chamadas = []
        monkeypatch.setattr(Flask, "run", lambda self, **kw: chamadas.append(kw))
        monkeypatch.delenv("PEDIDOS_HOST", raising=False)
        monkeypatch.delenv("PEDIDOS_PORTA", raising=False)
        monkeypatch.delitem(sys.modules, "pedidos_service.__main__", raising=False)
        runpy.run_module("pedidos_service", run_name="__main__")
        assert chamadas == [{"host": "127.0.0.1", "port": 5002, "threaded": True}]
