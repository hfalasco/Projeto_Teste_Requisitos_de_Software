"""Interface de linha de comando (terminal) do Serviço de Estoque.

Menu interativo que opera a API REST do estoque. Uso (com o servidor no ar):

    python -m estoque_service.cli

A URL da API vem da variável ESTOQUE_URL (padrão http://127.0.0.1:5001).
"""

from __future__ import annotations

import os
from decimal import Decimal

import requests

URL_PADRAO = "http://127.0.0.1:5001"
TIMEOUT = 5

MENU = """
==================================================
  SERVIÇO DE ESTOQUE  ({url})
==================================================
  1) Listar produtos
  2) Cadastrar produto
  3) Registrar entrada (reposição)
  4) Produtos que precisam de reposição
  0) Sair"""


def moeda(valor) -> str:
    texto = f"{Decimal(str(valor)):,.2f}"
    return "R$ " + texto.replace(",", "_").replace(".", ",").replace("_", ".")


class TerminalEstoque:
    """Menu do estoque. Entrada, saída e sessão HTTP são injetáveis (testes)."""

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
            self._saida(f"ERRO: não foi possível conectar ao Serviço de Estoque em {self.url}.")
            return None
        dados = resposta.json()
        if resposta.status_code >= 400:
            self._saida(f"ERRO (HTTP {resposta.status_code}): {dados.get('erro', 'falha desconhecida')}")
            return None
        return dados

    # ---------------------------------------------------------------- saída
    def _tabela(self, produtos: list[dict]) -> None:
        if not produtos:
            self._saida("Nenhum produto encontrado.")
            return
        self._saida(f"{'SKU':<10} {'NOME':<24} {'PREÇO':>13} {'SALDO':>6} {'MÍNIMO':>7}  SITUAÇÃO")
        self._saida("-" * 74)
        for p in produtos:
            situacao = "REPOR" if p["precisa_reposicao"] else "OK"
            self._saida(f"{p['sku']:<10} {p['nome'][:24]:<24} {moeda(p['preco']):>13} "
                        f"{p['quantidade']:>6} {p['estoque_minimo']:>7}  {situacao}")

    def _perguntar_inteiro(self, rotulo: str, padrao: int | None = None) -> int | None:
        texto = self._entrada(f"{rotulo}: ").strip()
        if texto == "" and padrao is not None:
            return padrao
        try:
            return int(texto)
        except ValueError:
            self._saida("ERRO: informe um número inteiro.")
            return None

    # -------------------------------------------------------------- opções
    def listar(self) -> None:
        produtos = self._chamar("GET", "/api/produtos")
        if produtos is not None:
            self._tabela(produtos)

    def cadastrar(self) -> None:
        sku = self._entrada("SKU: ")
        nome = self._entrada("Nome: ")
        preco = self._entrada("Preço (R$): ").strip().replace(",", ".")
        quantidade = self._perguntar_inteiro("Quantidade inicial [0]", 0)
        minimo = None if quantidade is None else self._perguntar_inteiro("Estoque mínimo [0]", 0)
        if minimo is None:
            return
        produto = self._chamar("POST", "/api/produtos", {"sku": sku, "nome": nome, "preco": preco,
                                                         "quantidade": quantidade, "estoque_minimo": minimo})
        if produto:
            self._saida(f"OK: produto {produto['sku']} cadastrado com saldo {produto['quantidade']}.")

    def registrar_entrada(self) -> None:
        sku = self._entrada("SKU: ").strip()
        quantidade = self._perguntar_inteiro("Quantidade")
        if quantidade is None:
            return
        produto = self._chamar("POST", f"/api/produtos/{sku}/entradas", {"quantidade": quantidade})
        if produto:
            self._saida(f"OK: {produto['sku']} agora tem {produto['quantidade']} unidades.")

    def reposicao(self) -> None:
        produtos = self._chamar("GET", "/api/produtos/reposicao")
        if produtos is not None:
            self._tabela(produtos)

    def executar(self) -> None:
        acoes = {"1": self.listar, "2": self.cadastrar, "3": self.registrar_entrada, "4": self.reposicao}
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
    TerminalEstoque(os.environ.get("ESTOQUE_URL", URL_PADRAO)).executar()


if __name__ == "__main__":
    main()
