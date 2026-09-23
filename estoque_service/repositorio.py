"""Repositório em memória dos produtos (substituível por um banco de dados)."""

from __future__ import annotations

from estoque_service.dominio import Produto, ProdutoJaCadastrado, ProdutoNaoEncontrado


class RepositorioProdutosEmMemoria:
    def __init__(self):
        self._produtos: dict[str, Produto] = {}

    def adicionar(self, produto: Produto) -> None:
        if produto.sku in self._produtos:
            raise ProdutoJaCadastrado(produto.sku)
        self._produtos[produto.sku] = produto

    def obter(self, sku: str) -> Produto:
        try:
            return self._produtos[sku]
        except KeyError:
            raise ProdutoNaoEncontrado(sku) from None

    def listar(self) -> list[Produto]:
        return sorted(self._produtos.values(), key=lambda p: p.sku)

    def __len__(self) -> int:
        return len(self._produtos)
