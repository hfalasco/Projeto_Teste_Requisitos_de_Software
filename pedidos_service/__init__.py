"""Aplicação 2 - Serviço de Pedidos.

API REST de vendas. Para cada pedido consulta e reserva os produtos no
Serviço de Estoque (Aplicação 1) via HTTP, calcula descontos e controla o
ciclo de vida do pedido (confirmado/cancelado).
"""

from pedidos_service.app import criar_app

__all__ = ["criar_app"]
