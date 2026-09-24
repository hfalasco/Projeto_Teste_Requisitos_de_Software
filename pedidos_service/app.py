"""Camada HTTP (Flask) do Serviço de Pedidos."""

from __future__ import annotations

import os

from flask import Flask, jsonify, request

from pedidos_service.cliente_estoque import TIMEOUT_PADRAO, ClienteEstoque
from pedidos_service.dominio import (
    DadosInvalidos,
    ErroPedido,
    EstoqueIndisponivel,
    EstoqueInsuficiente,
    PedidoNaoEncontrado,
    ProdutoInexistente,
    RespostaInvalidaEstoque,
    TransicaoInvalida,
)
from pedidos_service.servico import ServicoPedidos

URL_ESTOQUE_PADRAO = "http://127.0.0.1:5001"

STATUS_POR_ERRO = {
    DadosInvalidos: 400,
    PedidoNaoEncontrado: 404,
    EstoqueInsuficiente: 409,
    TransicaoInvalida: 409,
    ProdutoInexistente: 422,
    RespostaInvalidaEstoque: 502,
    EstoqueIndisponivel: 503,
}


def criar_servico_padrao() -> ServicoPedidos:
    """Monta o serviço real a partir das variáveis de ambiente (RNF05)."""
    url = os.environ.get("ESTOQUE_URL", URL_ESTOQUE_PADRAO)
    timeout = float(os.environ.get("ESTOQUE_TIMEOUT", TIMEOUT_PADRAO))
    return ServicoPedidos(ClienteEstoque(url, timeout=timeout))


def criar_app(servico: ServicoPedidos | None = None) -> Flask:
    """Application factory: permite injetar um serviço (útil nos testes)."""
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    servico = servico or criar_servico_padrao()
    app.config["SERVICO_PEDIDOS"] = servico

    @app.errorhandler(ErroPedido)
    def tratar_erro_negocio(erro: ErroPedido):
        corpo = {"erro": str(erro), "codigo": erro.codigo}
        return jsonify(corpo), STATUS_POR_ERRO.get(type(erro), 400)

    @app.errorhandler(404)
    def rota_nao_encontrada(_erro):
        return jsonify({"erro": "Recurso não encontrado.", "codigo": "ROTA_INEXISTENTE"}), 404

    @app.errorhandler(405)
    def metodo_nao_permitido(_erro):
        return jsonify({"erro": "Método não permitido.", "codigo": "METODO_NAO_PERMITIDO"}), 405

    @app.get("/health")
    def saude():
        estoque_ok = servico.estoque_disponivel()
        return jsonify(
            {
                "servico": "pedidos",
                "status": "ok",
                "dependencias": {"estoque": "ok" if estoque_ok else "indisponivel"},
            }
        )

    @app.get("/api/catalogo")
    def catalogo():
        return jsonify(servico.catalogo())

    @app.get("/api/pedidos")
    def listar_pedidos():
        return jsonify([p.para_dict() for p in servico.listar_pedidos()])

    @app.post("/api/pedidos")
    def criar_pedido():
        pedido = servico.criar_pedido(request.get_json(silent=True))
        return jsonify(pedido.para_dict()), 201

    @app.get("/api/pedidos/<int:id_pedido>")
    def obter_pedido(id_pedido):
        return jsonify(servico.obter_pedido(id_pedido).para_dict())

    @app.post("/api/pedidos/<int:id_pedido>/cancelamento")
    def cancelar_pedido(id_pedido):
        return jsonify(servico.cancelar_pedido(id_pedido).para_dict())

    return app
