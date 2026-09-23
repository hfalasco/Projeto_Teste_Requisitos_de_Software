"""Casos de uso do Serviço de Estoque."""

from __future__ import annotations

import threading

from estoque_service.dominio import (
    DadosInvalidos,
    Produto,
    validar_quantidade,
    validar_sku,
)
from estoque_service.repositorio import RepositorioProdutosEmMemoria

MAXIMO_ITENS_POR_LOTE = 50


def normalizar_itens(itens) -> dict[str, int]:
    """Valida uma lista de itens [{sku, quantidade}] e agrupa SKUs repetidos."""
    if not isinstance(itens, list) or not itens:
        raise DadosInvalidos("Informe uma lista 'itens' com pelo menos um item.")
    if len(itens) > MAXIMO_ITENS_POR_LOTE:
        raise DadosInvalidos(
            f"Um lote pode ter no máximo {MAXIMO_ITENS_POR_LOTE} itens."
        )
    agrupados: dict[str, int] = {}
    for item in itens:
        if not isinstance(item, dict):
            raise DadosInvalidos("Cada item deve ser um objeto com 'sku' e 'quantidade'.")
        sku = validar_sku(item.get("sku"))
        quantidade = validar_quantidade(item.get("quantidade"))
        agrupados[sku] = agrupados.get(sku, 0) + quantidade
    for quantidade in agrupados.values():
        validar_quantidade(quantidade)
    return agrupados


class ServicoEstoque:
    """Orquestra as operações de estoque garantindo exclusão mútua.

    Um único lock protege as operações de escrita, de modo que pedidos
    simultâneos nunca deixem o saldo negativo (RNF04).
    """

    def __init__(self, repositorio: RepositorioProdutosEmMemoria | None = None):
        self._repositorio = repositorio or RepositorioProdutosEmMemoria()
        self._lock = threading.Lock()

    def cadastrar(self, dados) -> Produto:
        produto = Produto.criar(dados)
        with self._lock:
            self._repositorio.adicionar(produto)
        return produto

    def listar(self) -> list[Produto]:
        return self._repositorio.listar()

    def obter(self, sku) -> Produto:
        return self._repositorio.obter(validar_sku(sku))

    def registrar_entrada(self, sku, quantidade) -> Produto:
        with self._lock:
            produto = self.obter(sku)
            produto.adicionar(quantidade)
        return produto

    def baixar(self, itens) -> list[dict]:
        """Retira itens do estoque de forma atômica (tudo ou nada) - RN-E06.

        Retorna, para cada item, o nome e o preço vigente, que o Serviço de
        Pedidos utiliza como fonte da verdade (RN-P02).
        """
        agrupados = normalizar_itens(itens)
        with self._lock:
            produtos = {sku: self.obter(sku) for sku in agrupados}
            # 1ª fase: verifica todos os saldos antes de alterar qualquer um
            for sku, quantidade in agrupados.items():
                produtos[sku].validar_saida(quantidade)
            # 2ª fase: efetiva a baixa
            for sku, quantidade in agrupados.items():
                produtos[sku].remover(quantidade)
        return [
            {
                "sku": sku,
                "nome": produtos[sku].nome,
                "preco": f"{produtos[sku].preco:.2f}",
                "quantidade": quantidade,
                "saldo": produtos[sku].quantidade,
            }
            for sku, quantidade in agrupados.items()
        ]

    def devolver(self, itens) -> list[Produto]:
        """Devolve itens ao estoque (estorno de um pedido cancelado) - RF-E05."""
        agrupados = normalizar_itens(itens)
        with self._lock:
            produtos = [self.obter(sku) for sku in agrupados]
            for produto in produtos:
                produto.validar_entrada(agrupados[produto.sku])
            for produto in produtos:
                produto.adicionar(agrupados[produto.sku])
        return produtos

    def produtos_para_reposicao(self) -> list[Produto]:
        return [p for p in self._repositorio.listar() if p.precisa_reposicao]
