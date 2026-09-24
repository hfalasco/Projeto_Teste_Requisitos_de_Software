"""Testes unitários da camada HTTP do Serviço de Estoque (Flask test client, sem rede)."""

import runpy
import sys

import pytest
from flask import Flask

import estoque_service.__main__ as principal
from estoque_service.app import criar_app
from estoque_service.dominio import ErroEstoque
from estoque_service.servico import ServicoEstoque


@pytest.fixture
def cliente():
    app = criar_app()
    app.testing = True
    cliente = app.test_client()
    cliente.post("/api/produtos", json={"sku": "TEC-001", "nome": "Teclado", "preco": "250.00",
                                        "quantidade": 10, "estoque_minimo": 3})
    return cliente


class TestSaude:
    def test_health_informa_servico_ativo(self, cliente):
        """Objetivo: Verificar que o endpoint de saúde responde 200 com status ok.
        Técnica: Teste de rota (caixa-preta)
        Requisitos: RNF01
        """
        resposta = cliente.get("/health")
        assert resposta.status_code == 200
        assert resposta.get_json() == {"servico": "estoque", "status": "ok"}


class TestProdutosApi:
    def test_post_produto_valido_retorna_201_com_produto(self, cliente):
        """Objetivo: Verificar que o cadastro via API retorna 201 e o produto normalizado.
        Técnica: Partição de equivalência (classe válida) e contrato HTTP
        Requisitos: RF-E01, RNF01
        """
        resposta = cliente.post("/api/produtos", json={"sku": "mou-001", "nome": "Mouse", "preco": 120})
        assert resposta.status_code == 201
        assert resposta.get_json()["sku"] == "MOU-001"
        assert resposta.get_json()["preco"] == "120.00"

    def test_post_produto_invalido_retorna_400_padronizado(self, cliente):
        """Objetivo: Verificar que dados inválidos retornam 400 com corpo de erro padronizado (erro + codigo).
        Técnica: Partição de equivalência (classe inválida) e contrato de erro
        Requisitos: RN-E03, RNF01
        """
        resposta = cliente.post("/api/produtos", json={"sku": "ABC", "nome": "X", "preco": -1})
        assert resposta.status_code == 400
        assert resposta.get_json()["codigo"] == "DADOS_INVALIDOS"
        assert "maior que zero" in resposta.get_json()["erro"]

    def test_post_produto_duplicado_retorna_409(self, cliente):
        """Objetivo: Verificar que cadastrar SKU já existente retorna 409 Conflict.
        Técnica: Partição de equivalência (classe inválida: duplicidade)
        Requisitos: RN-E01
        """
        resposta = cliente.post("/api/produtos", json={"sku": "TEC-001", "nome": "X", "preco": 1})
        assert resposta.status_code == 409
        assert resposta.get_json()["codigo"] == "PRODUTO_JA_CADASTRADO"

    @pytest.mark.parametrize("corpo, tipo", [("nao e json", "text/plain"), ("[1, 2]", "application/json")])
    def test_corpo_que_nao_e_objeto_json_retorna_400(self, cliente, corpo, tipo):
        """Objetivo: Garantir que corpos não-JSON ou JSON que não é objeto são rejeitados com 400.
        Técnica: Partição de equivalência (entrada malformada)
        Requisitos: RNF01
        """
        resposta = cliente.post("/api/produtos", data=corpo, content_type=tipo)
        assert resposta.status_code == 400
        assert resposta.get_json()["codigo"] == "DADOS_INVALIDOS"

    def test_get_lista_e_consulta_por_sku(self, cliente):
        """Objetivo: Verificar a listagem de produtos e a consulta individual por SKU (em minúsculas).
        Técnica: Teste de rota (caixa-preta)
        Requisitos: RF-E02
        """
        assert [p["sku"] for p in cliente.get("/api/produtos").get_json()] == ["TEC-001"]
        resposta = cliente.get("/api/produtos/tec-001")
        assert resposta.status_code == 200
        assert resposta.get_json()["quantidade"] == 10

    def test_get_produto_inexistente_retorna_404(self, cliente):
        """Objetivo: Verificar que consultar um SKU inexistente retorna 404 com código PRODUTO_NAO_ENCONTRADO.
        Técnica: Partição de equivalência (classe inválida)
        Requisitos: RF-E02, RNF01
        """
        resposta = cliente.get("/api/produtos/NAO-EXISTE")
        assert resposta.status_code == 404
        assert resposta.get_json()["codigo"] == "PRODUTO_NAO_ENCONTRADO"

    def test_post_entrada_atualiza_saldo(self, cliente):
        """Objetivo: Verificar que a entrada via API retorna o produto com saldo atualizado.
        Técnica: Partição de equivalência (classe válida)
        Requisitos: RF-E03
        """
        resposta = cliente.post("/api/produtos/TEC-001/entradas", json={"quantidade": 5})
        assert resposta.status_code == 200
        assert resposta.get_json()["quantidade"] == 15

    def test_post_entrada_com_quantidade_zero_retorna_400(self, cliente):
        """Objetivo: Verificar que uma entrada com quantidade 0 é rejeitada com 400.
        Técnica: Análise de valor limite (mínimo-1)
        Requisitos: RF-E03, RN-E04
        """
        resposta = cliente.post("/api/produtos/TEC-001/entradas", json={"quantidade": 0})
        assert resposta.status_code == 400

    def test_get_reposicao_lista_produtos_no_minimo(self, cliente):
        """Objetivo: Verificar que o endpoint de reposição lista os produtos cujo saldo atingiu o mínimo.
        Técnica: Análise de valor limite (saldo = mínimo)
        Requisitos: RF-E06, RN-E05
        """
        assert cliente.get("/api/produtos/reposicao").get_json() == []
        cliente.post("/api/estoque/baixas", json={"itens": [{"sku": "TEC-001", "quantidade": 7}]})
        assert [p["sku"] for p in cliente.get("/api/produtos/reposicao").get_json()] == ["TEC-001"]


class TestBaixaEDevolucaoApi:
    def test_post_baixa_retorna_itens_com_preco(self, cliente):
        """Objetivo: Verificar o contrato da baixa em lote (itens com nome, preço, quantidade e saldo).
        Técnica: Verificação de contrato de integração (provedor)
        Requisitos: RF-E04, RN-P02
        """
        resposta = cliente.post("/api/estoque/baixas", json={"itens": [{"sku": "TEC-001", "quantidade": 4}]})
        assert resposta.status_code == 200
        assert resposta.get_json() == {"itens": [
            {"sku": "TEC-001", "nome": "Teclado", "preco": "250.00", "quantidade": 4, "saldo": 6}]}

    def test_post_baixa_sem_saldo_retorna_409_com_detalhes(self, cliente):
        """Objetivo: Verificar que falta de saldo retorna 409 com sku, disponível e solicitado no corpo.
        Técnica: Análise de valor limite (saldo+1) e contrato de erro
        Requisitos: RN-E04, RNF01
        """
        resposta = cliente.post("/api/estoque/baixas", json={"itens": [{"sku": "TEC-001", "quantidade": 11}]})
        assert resposta.status_code == 409
        corpo = resposta.get_json()
        assert corpo["codigo"] == "ESTOQUE_INSUFICIENTE"
        assert (corpo["sku"], corpo["disponivel"], corpo["solicitado"]) == ("TEC-001", 10, 11)

    def test_post_baixa_de_produto_inexistente_retorna_404(self, cliente):
        """Objetivo: Verificar que a baixa de SKU inexistente retorna 404.
        Técnica: Partição de equivalência (classe inválida)
        Requisitos: RF-E04
        """
        resposta = cliente.post("/api/estoque/baixas", json={"itens": [{"sku": "NAO-EXISTE", "quantidade": 1}]})
        assert resposta.status_code == 404

    def test_post_devolucao_retorna_produtos_atualizados(self, cliente):
        """Objetivo: Verificar que a devolução via API retorna os produtos com saldo atualizado.
        Técnica: Partição de equivalência (classe válida)
        Requisitos: RF-E05
        """
        resposta = cliente.post("/api/estoque/devolucoes", json={"itens": [{"sku": "TEC-001", "quantidade": 2}]})
        assert resposta.status_code == 200
        assert resposta.get_json()["itens"][0]["quantidade"] == 12


class TestErrosGenericos:
    def test_rota_inexistente_retorna_404_em_json(self, cliente):
        """Objetivo: Verificar que rotas desconhecidas retornam 404 no formato JSON padronizado.
        Técnica: Partição de equivalência (classe inválida)
        Requisitos: RNF01
        """
        resposta = cliente.get("/rota/inexistente")
        assert resposta.status_code == 404
        assert resposta.get_json()["codigo"] == "ROTA_INEXISTENTE"

    def test_metodo_nao_permitido_retorna_405_em_json(self, cliente):
        """Objetivo: Verificar que um método HTTP não suportado retorna 405 no formato JSON padronizado.
        Técnica: Partição de equivalência (classe inválida)
        Requisitos: RNF01
        """
        resposta = cliente.delete("/api/produtos")
        assert resposta.status_code == 405
        assert resposta.get_json()["codigo"] == "METODO_NAO_PERMITIDO"

    def test_erro_de_negocio_nao_mapeado_retorna_400(self):
        """Objetivo: Garantir que um erro de negócio genérico (sem status específico) é convertido em 400.
        Técnica: Dublê de teste (stub do serviço) para forçar o caminho de erro
        Requisitos: RNF01
        """

        class ServicoComFalha(ServicoEstoque):
            def listar(self):
                raise ErroEstoque("falha genérica")

        resposta = criar_app(ServicoComFalha()).test_client().get("/api/produtos")
        assert resposta.status_code == 400
        assert resposta.get_json() == {"erro": "falha genérica", "codigo": "ERRO_ESTOQUE"}


class TestInicializacao:
    def test_main_usa_host_e_porta_das_variaveis_de_ambiente(self, monkeypatch):
        """Objetivo: Verificar que o servidor é iniciado com host e porta definidos por variáveis de ambiente.
        Técnica: Dublê de teste (mock de Flask.run) e configuração por ambiente
        Requisitos: RNF05
        """
        chamadas = []
        monkeypatch.setattr(Flask, "run", lambda self, **kw: chamadas.append(kw))
        monkeypatch.setenv("ESTOQUE_HOST", "0.0.0.0")
        monkeypatch.setenv("ESTOQUE_PORTA", "7001")
        principal.main()
        assert chamadas == [{"host": "0.0.0.0", "port": 7001, "threaded": True}]

    def test_execucao_como_modulo_usa_porta_padrao_5001(self, monkeypatch):
        """Objetivo: Verificar que "python -m estoque_service" sobe o servidor na porta padrão 5001.
        Técnica: Dublê de teste (mock de Flask.run)
        Requisitos: RNF05
        """
        chamadas = []
        monkeypatch.setattr(Flask, "run", lambda self, **kw: chamadas.append(kw))
        monkeypatch.delenv("ESTOQUE_HOST", raising=False)
        monkeypatch.delenv("ESTOQUE_PORTA", raising=False)
        monkeypatch.delitem(sys.modules, "estoque_service.__main__", raising=False)
        runpy.run_module("estoque_service", run_name="__main__")
        assert chamadas == [{"host": "127.0.0.1", "port": 5001, "threaded": True}]
