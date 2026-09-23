"""Casos de uso do Serviço de Pedidos."""

from __future__ import annotations

import threading
from typing import Callable

from pedidos_service.dominio import (
    ItemPedido,
    Pedido,
    agora_utc,
    validar_solicitacao,
)
from pedidos_service.repositorio import RepositorioPedidosEmMemoria


class ServicoPedidos:
    """Regras de aplicação; o estoque é acessado apenas via ``cliente_estoque``.

    As dependências (cliente do estoque, repositório e relógio) são injetadas
    no construtor, o que permite substituí-las por dublês nos testes unitários.
    """

    def __init__(
        self,
        cliente_estoque,
        repositorio: RepositorioPedidosEmMemoria | None = None,
        relogio: Callable = agora_utc,
    ):
        self._estoque = cliente_estoque
        self._repositorio = repositorio or RepositorioPedidosEmMemoria()
        self._relogio = relogio
        self._lock_cancelamento = threading.Lock()

    @property
    def cliente_estoque(self):
        return self._estoque

    def catalogo(self) -> list[dict]:
        return self._estoque.listar_produtos()

    def estoque_disponivel(self) -> bool:
        return self._estoque.esta_disponivel()

    def criar_pedido(self, dados) -> Pedido:
        cliente, itens = validar_solicitacao(dados)
        # RN-P02/RN-P04: o estoque reserva tudo ou nada e informa o preço vigente
        reservados = self._estoque.baixar(itens)
        itens_pedido = [
            ItemPedido(
                sku=item["sku"],
                nome=item["nome"],
                quantidade=item["quantidade"],
                preco_unitario=item["preco"],
            )
            for item in reservados
        ]
        return self._repositorio.criar(cliente, itens_pedido, self._relogio())

    def listar_pedidos(self) -> list[Pedido]:
        return self._repositorio.listar()

    def obter_pedido(self, id_pedido: int) -> Pedido:
        return self._repositorio.obter(id_pedido)

    def cancelar_pedido(self, id_pedido: int) -> Pedido:
        """RN-P05: devolve os itens ao estoque e só então marca como cancelado.

        Se o estoque estiver indisponível a exceção se propaga e o pedido
        permanece CONFIRMADO, mantendo os dois serviços consistentes.
        """
        pedido = self._repositorio.obter(id_pedido)
        with self._lock_cancelamento:
            pedido.garantir_cancelavel()
            self._estoque.devolver(
                [{"sku": item.sku, "quantidade": item.quantidade} for item in pedido.itens]
            )
            pedido.cancelar(self._relogio())
        return pedido
