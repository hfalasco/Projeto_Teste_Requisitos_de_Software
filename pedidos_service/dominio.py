"""Entidades, validações e exceções de negócio do Serviço de Pedidos."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

# Limites das regras de negócio (usados nos testes de valor limite)
CLIENTE_TAMANHO_MINIMO = 3
CLIENTE_TAMANHO_MAXIMO = 80
MAXIMO_ITENS_DISTINTOS = 20
QUANTIDADE_MAXIMA_POR_ITEM = 100
FAIXA_DESCONTO_5 = Decimal("500.00")
FAIXA_DESCONTO_10 = Decimal("1000.00")
CENTAVOS = Decimal("0.01")
SKU_PADRAO = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,19}$")


class ErroPedido(Exception):
    """Classe base de todos os erros de negócio do serviço de pedidos."""

    codigo = "ERRO_PEDIDO"


class DadosInvalidos(ErroPedido):
    codigo = "DADOS_INVALIDOS"


class PedidoNaoEncontrado(ErroPedido):
    codigo = "PEDIDO_NAO_ENCONTRADO"

    def __init__(self, id_pedido: int):
        super().__init__(f"Pedido {id_pedido} não encontrado.")
        self.id_pedido = id_pedido


class TransicaoInvalida(ErroPedido):
    codigo = "TRANSICAO_INVALIDA"


# --- Erros originados na integração com o Serviço de Estoque -----------------


class ProdutoInexistente(ErroPedido):
    codigo = "PRODUTO_INEXISTENTE"


class EstoqueInsuficiente(ErroPedido):
    codigo = "ESTOQUE_INSUFICIENTE"


class EstoqueIndisponivel(ErroPedido):
    codigo = "ESTOQUE_INDISPONIVEL"


class RespostaInvalidaEstoque(ErroPedido):
    codigo = "RESPOSTA_INVALIDA_ESTOQUE"


class StatusPedido(str, Enum):
    CONFIRMADO = "CONFIRMADO"
    CANCELADO = "CANCELADO"


def arredondar(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def taxa_desconto(subtotal: Decimal) -> Decimal:
    """RN-P03: desconto progressivo por faixa de subtotal."""
    if subtotal >= FAIXA_DESCONTO_10:
        return Decimal("0.10")
    if subtotal >= FAIXA_DESCONTO_5:
        return Decimal("0.05")
    return Decimal("0")


def calcular_desconto(subtotal: Decimal) -> Decimal:
    return arredondar(subtotal * taxa_desconto(subtotal))


def validar_cliente(valor) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise DadosInvalidos("O campo 'cliente' é obrigatório.")
    cliente = " ".join(valor.split())
    if not CLIENTE_TAMANHO_MINIMO <= len(cliente) <= CLIENTE_TAMANHO_MAXIMO:
        raise DadosInvalidos(
            f"O nome do cliente deve ter entre {CLIENTE_TAMANHO_MINIMO} e "
            f"{CLIENTE_TAMANHO_MAXIMO} caracteres."
        )
    return cliente


def validar_sku(valor) -> str:
    if not isinstance(valor, str) or not SKU_PADRAO.match(valor.strip().upper()):
        raise DadosInvalidos(f"SKU inválido: {valor!r}.")
    return valor.strip().upper()


def validar_quantidade(valor) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise DadosInvalidos("A quantidade de cada item deve ser um número inteiro.")
    if not 1 <= valor <= QUANTIDADE_MAXIMA_POR_ITEM:
        raise DadosInvalidos(
            f"A quantidade de cada item deve estar entre 1 e {QUANTIDADE_MAXIMA_POR_ITEM}."
        )
    return valor


def validar_itens(itens) -> list[dict]:
    """RN-P01: valida os itens e agrupa SKUs repetidos (mantendo a ordem)."""
    if not isinstance(itens, list) or not itens:
        raise DadosInvalidos("O pedido deve conter pelo menos um item.")
    agrupados: dict[str, int] = {}
    for item in itens:
        if not isinstance(item, dict):
            raise DadosInvalidos("Cada item deve ser um objeto com 'sku' e 'quantidade'.")
        sku = validar_sku(item.get("sku"))
        agrupados[sku] = agrupados.get(sku, 0) + validar_quantidade(item.get("quantidade"))
    if len(agrupados) > MAXIMO_ITENS_DISTINTOS:
        raise DadosInvalidos(
            f"O pedido pode ter no máximo {MAXIMO_ITENS_DISTINTOS} produtos distintos."
        )
    return [
        {"sku": sku, "quantidade": validar_quantidade(quantidade)}
        for sku, quantidade in agrupados.items()
    ]


def validar_solicitacao(dados) -> tuple[str, list[dict]]:
    if not isinstance(dados, dict):
        raise DadosInvalidos("O corpo da requisição deve ser um objeto JSON.")
    return validar_cliente(dados.get("cliente")), validar_itens(dados.get("itens"))


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ItemPedido:
    sku: str
    nome: str
    quantidade: int
    preco_unitario: Decimal

    @property
    def total(self) -> Decimal:
        return arredondar(self.preco_unitario * self.quantidade)

    def para_dict(self) -> dict:
        return {
            "sku": self.sku,
            "nome": self.nome,
            "quantidade": self.quantidade,
            "preco_unitario": f"{self.preco_unitario:.2f}",
            "total": f"{self.total:.2f}",
        }


@dataclass
class Pedido:
    id: int
    cliente: str
    itens: list[ItemPedido]
    criado_em: datetime = field(default_factory=agora_utc)
    status: StatusPedido = StatusPedido.CONFIRMADO
    cancelado_em: datetime | None = None

    @property
    def subtotal(self) -> Decimal:
        return arredondar(sum((item.total for item in self.itens), Decimal("0")))

    @property
    def desconto(self) -> Decimal:
        return calcular_desconto(self.subtotal)

    @property
    def total(self) -> Decimal:
        return self.subtotal - self.desconto

    def garantir_cancelavel(self) -> None:
        """RN-P05: somente pedidos confirmados podem ser cancelados."""
        if self.status is not StatusPedido.CONFIRMADO:
            raise TransicaoInvalida(
                f"O pedido {self.id} não pode ser cancelado (status {self.status.value})."
            )

    def cancelar(self, momento: datetime | None = None) -> None:
        self.garantir_cancelavel()
        self.status = StatusPedido.CANCELADO
        self.cancelado_em = momento or agora_utc()

    def para_dict(self) -> dict:
        return {
            "id": self.id,
            "cliente": self.cliente,
            "status": self.status.value,
            "itens": [item.para_dict() for item in self.itens],
            "subtotal": f"{self.subtotal:.2f}",
            "percentual_desconto": int(taxa_desconto(self.subtotal) * 100),
            "desconto": f"{self.desconto:.2f}",
            "total": f"{self.total:.2f}",
            "criado_em": self.criado_em.isoformat(),
            "cancelado_em": self.cancelado_em.isoformat() if self.cancelado_em else None,
        }
