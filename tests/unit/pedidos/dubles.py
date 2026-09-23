"""Dublês de teste (test doubles) usados pelos testes unitários do Serviço de Pedidos.

* ``EstoqueFalso`` é um *fake*: implementação simplificada e em memória do
  ``ClienteEstoque``, que também funciona como *spy* (registra as chamadas).
* ``RespostaFalsa`` é um *stub* de ``requests.Response`` com status e corpo
  pré-definidos.
"""

from decimal import Decimal

from pedidos_service.dominio import EstoqueIndisponivel, EstoqueInsuficiente, ProdutoInexistente


class EstoqueFalso:
    def __init__(self):
        self.produtos = {
            "TEC-001": {"nome": "Teclado", "preco": Decimal("250.00"), "quantidade": 10},
            "MOU-001": {"nome": "Mouse", "preco": Decimal("120.00"), "quantidade": 5},
            "MON-001": {"nome": "Monitor", "preco": Decimal("1200.00"), "quantidade": 2},
        }
        self.disponivel = True
        self.chamadas = []

    def _verificar_disponibilidade(self):
        if not self.disponivel:
            raise EstoqueIndisponivel("Não foi possível conectar ao Serviço de Estoque.")

    def listar_produtos(self):
        self._verificar_disponibilidade()
        return [
            {"sku": sku, "nome": p["nome"], "preco": f"{p['preco']:.2f}", "quantidade": p["quantidade"]}
            for sku, p in sorted(self.produtos.items())
        ]

    def baixar(self, itens):
        self._verificar_disponibilidade()
        self.chamadas.append(("baixar", itens))
        for item in itens:
            if item["sku"] not in self.produtos:
                raise ProdutoInexistente(f"Produto '{item['sku']}' não encontrado.")
            if item["quantidade"] > self.produtos[item["sku"]]["quantidade"]:
                raise EstoqueInsuficiente(f"Estoque insuficiente para '{item['sku']}'.")
        for item in itens:
            self.produtos[item["sku"]]["quantidade"] -= item["quantidade"]
        return [
            {"sku": item["sku"], "nome": self.produtos[item["sku"]]["nome"],
             "quantidade": item["quantidade"], "preco": self.produtos[item["sku"]]["preco"]}
            for item in itens
        ]

    def devolver(self, itens):
        self._verificar_disponibilidade()
        self.chamadas.append(("devolver", itens))
        for item in itens:
            self.produtos[item["sku"]]["quantidade"] += item["quantidade"]

    def esta_disponivel(self):
        return self.disponivel

    def saldo(self, sku):
        return self.produtos[sku]["quantidade"]


class RespostaFalsa:
    def __init__(self, status_code=200, dados=None, json_invalido=False):
        self.status_code = status_code
        self._dados = dados
        self._json_invalido = json_invalido

    def json(self):
        if self._json_invalido:
            raise ValueError("corpo não é JSON")
        return self._dados
