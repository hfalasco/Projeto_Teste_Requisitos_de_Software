"""Camada HTTP (Flask) do Serviço de Estoque."""

from __future__ import annotations

from flask import Flask, jsonify, request

from estoque_service.dominio import (
    DadosInvalidos,
    ErroEstoque,
    EstoqueInsuficiente,
    ProdutoJaCadastrado,
    ProdutoNaoEncontrado,
)
from estoque_service.servico import ServicoEstoque

STATUS_POR_ERRO = {
    DadosInvalidos: 400,
    ProdutoNaoEncontrado: 404,
    ProdutoJaCadastrado: 409,
    EstoqueInsuficiente: 409,
}


def _corpo_json() -> dict:
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        raise DadosInvalidos("O corpo da requisição deve ser um objeto JSON.")
    return corpo


def criar_app(servico: ServicoEstoque | None = None) -> Flask:
    """Application factory: permite injetar um serviço (útil nos testes)."""
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    servico = servico or ServicoEstoque()
    app.config["SERVICO_ESTOQUE"] = servico

    @app.errorhandler(ErroEstoque)
    def tratar_erro_negocio(erro: ErroEstoque):
        corpo = {"erro": str(erro), "codigo": erro.codigo}
        if isinstance(erro, EstoqueInsuficiente):
            corpo.update(
                sku=erro.sku, disponivel=erro.disponivel, solicitado=erro.solicitado
            )
        return jsonify(corpo), STATUS_POR_ERRO.get(type(erro), 400)

    @app.errorhandler(404)
    def rota_nao_encontrada(_erro):
        return jsonify({"erro": "Recurso não encontrado.", "codigo": "ROTA_INEXISTENTE"}), 404

    @app.errorhandler(405)
    def metodo_nao_permitido(_erro):
        return jsonify({"erro": "Método não permitido.", "codigo": "METODO_NAO_PERMITIDO"}), 405

    @app.get("/health")
    def saude():
        return jsonify({"servico": "estoque", "status": "ok"})

    @app.get("/api/produtos")
    def listar_produtos():
        return jsonify([p.para_dict() for p in servico.listar()])

    @app.post("/api/produtos")
    def cadastrar_produto():
        produto = servico.cadastrar(_corpo_json())
        return jsonify(produto.para_dict()), 201

    @app.get("/api/produtos/reposicao")
    def produtos_para_reposicao():
        return jsonify([p.para_dict() for p in servico.produtos_para_reposicao()])

    @app.get("/api/produtos/<sku>")
    def obter_produto(sku):
        return jsonify(servico.obter(sku).para_dict())

    @app.post("/api/produtos/<sku>/entradas")
    def registrar_entrada(sku):
        produto = servico.registrar_entrada(sku, _corpo_json().get("quantidade"))
        return jsonify(produto.para_dict())

    @app.post("/api/estoque/baixas")
    def baixar_itens():
        itens = servico.baixar(_corpo_json().get("itens"))
        return jsonify({"itens": itens})

    @app.post("/api/estoque/devolucoes")
    def devolver_itens():
        produtos = servico.devolver(_corpo_json().get("itens"))
        return jsonify({"itens": [p.para_dict() for p in produtos]})

    return app
