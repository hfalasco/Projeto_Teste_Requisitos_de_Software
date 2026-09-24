"""Interface de linha de comando (terminal) do Serviço de Pedidos.

Menu interativo que opera a API REST de pedidos. Uso (com os servidores no ar):

    python -m pedidos_service.cli

A URL da API vem da variável PEDIDOS_URL (padrão http://127.0.0.1:5002).
"""

from __future__ import annotations

import os
from decimal import Decimal

import requests

URL_PADRAO = "http://127.0.0.1:5002"
TIMEOUT = 10

MENU = """
==================================================
  SERVIÇO DE PEDIDOS  ({url})
==================================================
  1) Ver catálogo (produtos do Estoque)
  2) Criar pedido
  3) Listar pedidos
  4) Cancelar pedido
  5) Situação dos serviços
  0) Sair"""


def moeda(valor) -> str:
    texto = f"{Decimal(str(valor)):,.2f}"
    return "R$ " + texto.replace(",", "_").replace(".", ",").replace("_", ".")


class TerminalPedidos:
    """Menu de pedidos. Entrada, saída e sessão HTTP são injetáveis (testes)."""

    def __init__(self, url: str, entrada=input, saida=print, sessao=None):
        self.url = url.rstrip("/")
        self._entrada = entrada
        self._saida = saida
        self._sessao = sessao or requests.Session()

    # ------------------------------------------------------------------ HTTP
    def _chamar(self, metodo: str, caminho: str, corpo: dict | None = None):
        """Faz a chamada HTTP; devolve o JSON ou None (após exibir o erro)."""
        try:
            resposta = self._sessao.request(metodo, f"{self.url}{caminho}", json=corpo, timeout=TIMEOUT)
        except requests.RequestException:
            self._saida(f"ERRO: não foi possível conectar ao Serviço de Pedidos em {self.url}.")
            return None
        dados = resposta.json()
        if resposta.status_code >= 400:
            self._saida(f"ERRO (HTTP {resposta.status_code}): {dados.get('erro', 'falha desconhecida')}")
            return None
        return dados

    # ---------------------------------------------------------------- saída
    def _resumo(self, pedido: dict) -> None:
        self._saida(f"Pedido #{pedido['id']} - {pedido['cliente']} - {pedido['status']}")
        for item in pedido["itens"]:
            self._saida(f"   {item['sku']:<10} {item['nome'][:24]:<24} {item['quantidade']:>3} x "
                        f"{moeda(item['preco_unitario']):>12} = {moeda(item['total']):>13}")
        desconto = (f"{pedido['percentual_desconto']}% (-{moeda(pedido['desconto'])})"
                    if pedido["percentual_desconto"] else "sem desconto")
        self._saida(f"   Subtotal {moeda(pedido['subtotal'])} | Desconto {desconto} | "
                    f"TOTAL {moeda(pedido['total'])}")

    # -------------------------------------------------------------- opções
    def catalogo(self) -> None:
        produtos = self._chamar("GET", "/api/catalogo")
        if produtos is None:
            return
        if not produtos:
            self._saida("O catálogo está vazio.")
            return
        self._saida(f"{'SKU':<10} {'NOME':<24} {'PREÇO':>13} {'DISPONÍVEL':>11}")
        self._saida("-" * 61)
        for p in produtos:
            self._saida(f"{p['sku']:<10} {p['nome'][:24]:<24} {moeda(p['preco']):>13} {p['quantidade']:>11}")

    def criar_pedido(self) -> None:
        cliente = self._entrada("Cliente: ")
        itens = []
        self._saida("Informe os itens (SKU em branco para finalizar).")
        while True:
            sku = self._entrada("  SKU: ").strip()
            if not sku:
                break
            texto = self._entrada("  Quantidade: ").strip()
            try:
                itens.append({"sku": sku, "quantidade": int(texto)})
            except ValueError:
                self._saida("  ERRO: informe um número inteiro; item ignorado.")
        pedido = self._chamar("POST", "/api/pedidos", {"cliente": cliente, "itens": itens})
        if pedido:
            self._saida("OK: pedido confirmado!")
            self._resumo(pedido)

    def listar(self) -> None:
        pedidos = self._chamar("GET", "/api/pedidos")
        if pedidos is None:
            return
        if not pedidos:
            self._saida("Nenhum pedido registrado.")
        for pedido in pedidos:
            self._resumo(pedido)

    def cancelar(self) -> None:
        numero = self._entrada("Número do pedido: ").strip()
        if not numero.isdigit():
            self._saida("ERRO: informe o número do pedido.")
            return
        pedido = self._chamar("POST", f"/api/pedidos/{numero}/cancelamento")
        if pedido:
            self._saida(f"OK: pedido #{pedido['id']} cancelado; itens devolvidos ao Estoque.")

    def situacao(self) -> None:
        saude = self._chamar("GET", "/health")
        if saude:
            self._saida(f"Serviço de Pedidos: {saude['status']}")
            self._saida(f"Serviço de Estoque: {saude['dependencias']['estoque']}")

    def executar(self) -> None:
        acoes = {"1": self.catalogo, "2": self.criar_pedido, "3": self.listar, "4": self.cancelar,
                 "5": self.situacao}
        try:
            while True:
                self._saida(MENU.format(url=self.url))
                opcao = self._entrada("Opção: ").strip()
                if opcao == "0":
                    break
                acao = acoes.get(opcao)
                if acao is None:
                    self._saida("Opção inválida.")
                else:
                    self._saida("")
                    acao()
        except EOFError:
            pass
        self._saida("Até logo!")


def main() -> None:
    TerminalPedidos(os.environ.get("PEDIDOS_URL", URL_PADRAO)).executar()


if __name__ == "__main__":
    main()
