"""Aplicação 1 - Serviço de Estoque.

API REST responsável pelo cadastro de produtos e pelo controle de saldo
(entradas, baixas e devoluções). É consumida pelo Serviço de Pedidos.
"""

from estoque_service.app import criar_app

__all__ = ["criar_app"]
