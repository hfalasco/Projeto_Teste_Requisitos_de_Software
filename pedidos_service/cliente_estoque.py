"""Cliente HTTP do Serviço de Estoque (ponto de integração entre as aplicações)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import requests

from pedidos_service.dominio import (
    DadosInvalidos,
    ErroPedido,
    EstoqueIndisponivel,
    EstoqueInsuficiente,
    ProdutoInexistente,
    RespostaInvalidaEstoque,
)

TIMEOUT_PADRAO = 3.0

ERRO_POR_CODIGO = {
    "ESTOQUE_INSUFICIENTE": EstoqueInsuficiente,
    "PRODUTO_NAO_ENCONTRADO": ProdutoInexistente,
    "DADOS_INVALIDOS": DadosInvalidos,
}


class ClienteEstoque:
    """Traduz chamadas HTTP em chamadas de método e erros HTTP em exceções."""

    def __init__(self, url_base: str, timeout: float = TIMEOUT_PADRAO, sessao=None):
        self.url_base = url_base.rstrip("/")
        self.timeout = timeout
        self._sessao = sessao or requests.Session()

    def _requisitar(self, metodo: str, caminho: str, corpo: dict | None = None):
        try:
            resposta = self._sessao.request(
                metodo, f"{self.url_base}{caminho}", json=corpo, timeout=self.timeout
            )
        except requests.Timeout as exc:
            raise EstoqueIndisponivel(
                "O Serviço de Estoque não respondeu dentro do tempo limite."
            ) from exc
        except requests.RequestException as exc:
            raise EstoqueIndisponivel(
                "Não foi possível conectar ao Serviço de Estoque."
            ) from exc

        if resposta.status_code >= 500:
            raise EstoqueIndisponivel(
                f"O Serviço de Estoque falhou (HTTP {resposta.status_code})."
            )
        try:
            dados = resposta.json()
        except ValueError:
            raise RespostaInvalidaEstoque(
                "O Serviço de Estoque retornou uma resposta que não é JSON."
            ) from None
        if resposta.status_code >= 400:
            raise self._converter_erro(resposta.status_code, dados)
        return dados

    @staticmethod
    def _converter_erro(status: int, dados) -> ErroPedido:
        dados = dados if isinstance(dados, dict) else {}
        mensagem = dados.get("erro") or f"Erro HTTP {status} no Serviço de Estoque."
        classe = ERRO_POR_CODIGO.get(dados.get("codigo"))
        if classe is None:
            return RespostaInvalidaEstoque(
                f"Erro inesperado do Serviço de Estoque (HTTP {status}): {mensagem}"
            )
        return classe(mensagem)

    def listar_produtos(self) -> list[dict]:
        dados = self._requisitar("GET", "/api/produtos")
        if not isinstance(dados, list):
            raise RespostaInvalidaEstoque("Catálogo recebido em formato inesperado.")
        return dados

    def baixar(self, itens: list[dict]) -> list[dict]:
        """Reserva (baixa) os itens no estoque e devolve nome e preço vigentes."""
        dados = self._requisitar("POST", "/api/estoque/baixas", {"itens": itens})
        try:
            return [
                {
                    "sku": item["sku"],
                    "nome": item["nome"],
                    "quantidade": int(item["quantidade"]),
                    "preco": Decimal(item["preco"]),
                }
                for item in dados["itens"]
            ]
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise RespostaInvalidaEstoque(
                "Resposta de baixa do estoque em formato inesperado."
            ) from None

    def devolver(self, itens: list[dict]) -> None:
        self._requisitar("POST", "/api/estoque/devolucoes", {"itens": itens})

    def esta_disponivel(self) -> bool:
        try:
            self._requisitar("GET", "/health")
        except ErroPedido:
            return False
        return True
