"""Repositório em memória dos pedidos."""

from __future__ import annotations

import itertools
import threading
from datetime import datetime

from pedidos_service.dominio import ItemPedido, Pedido, PedidoNaoEncontrado


class RepositorioPedidosEmMemoria:
    def __init__(self):
        self._pedidos: dict[int, Pedido] = {}
        self._sequencia = itertools.count(1)
        self._lock = threading.Lock()

    def criar(self, cliente: str, itens: list[ItemPedido], criado_em: datetime) -> Pedido:
        with self._lock:
            pedido = Pedido(
                id=next(self._sequencia), cliente=cliente, itens=itens, criado_em=criado_em
            )
            self._pedidos[pedido.id] = pedido
        return pedido

    def obter(self, id_pedido: int) -> Pedido:
        try:
            return self._pedidos[id_pedido]
        except KeyError:
            raise PedidoNaoEncontrado(id_pedido) from None

    def listar(self) -> list[Pedido]:
        return sorted(self._pedidos.values(), key=lambda p: p.id, reverse=True)
