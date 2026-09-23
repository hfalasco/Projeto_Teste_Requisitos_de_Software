"""Entidades, validações e exceções de negócio do Serviço de Estoque."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Limites das regras de negócio (usados nos testes de valor limite)
SKU_PADRAO = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,19}$")
NOME_TAMANHO_MAXIMO = 100
PRECO_MAXIMO = Decimal("1000000.00")
QUANTIDADE_MAXIMA_OPERACAO = 10_000
CAPACIDADE_MAXIMA = 100_000
CENTAVOS = Decimal("0.01")


class ErroEstoque(Exception):
    """Classe base de todos os erros de negócio do estoque."""

    codigo = "ERRO_ESTOQUE"


class DadosInvalidos(ErroEstoque):
    codigo = "DADOS_INVALIDOS"


class ProdutoNaoEncontrado(ErroEstoque):
    codigo = "PRODUTO_NAO_ENCONTRADO"

    def __init__(self, sku: str):
        super().__init__(f"Produto '{sku}' não encontrado.")
        self.sku = sku


class ProdutoJaCadastrado(ErroEstoque):
    codigo = "PRODUTO_JA_CADASTRADO"

    def __init__(self, sku: str):
        super().__init__(f"Já existe um produto com o SKU '{sku}'.")
        self.sku = sku


class EstoqueInsuficiente(ErroEstoque):
    codigo = "ESTOQUE_INSUFICIENTE"

    def __init__(self, sku: str, disponivel: int, solicitado: int):
        super().__init__(
            f"Estoque insuficiente para '{sku}': disponível {disponivel}, "
            f"solicitado {solicitado}."
        )
        self.sku = sku
        self.disponivel = disponivel
        self.solicitado = solicitado


def validar_sku(valor) -> str:
    """Normaliza (maiúsculas, sem espaços nas pontas) e valida um SKU."""
    if not isinstance(valor, str):
        raise DadosInvalidos("O campo 'sku' é obrigatório e deve ser texto.")
    sku = valor.strip().upper()
    if not SKU_PADRAO.match(sku):
        raise DadosInvalidos(
            "SKU inválido: use de 3 a 20 caracteres entre letras, números e hífen, "
            "começando por letra ou número."
        )
    return sku


def validar_nome(valor) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise DadosInvalidos("O campo 'nome' é obrigatório.")
    nome = valor.strip()
    if len(nome) > NOME_TAMANHO_MAXIMO:
        raise DadosInvalidos(
            f"O nome deve ter no máximo {NOME_TAMANHO_MAXIMO} caracteres."
        )
    return nome


def validar_preco(valor) -> Decimal:
    """Aceita número ou texto numérico; retorna Decimal com 2 casas."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str, Decimal)):
        raise DadosInvalidos("O campo 'preco' deve ser numérico.")
    try:
        preco = Decimal(str(valor).strip())
    except InvalidOperation:
        raise DadosInvalidos("O campo 'preco' deve ser numérico.") from None
    if not preco.is_finite():
        raise DadosInvalidos("O campo 'preco' deve ser numérico.")
    preco = preco.quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    if preco <= 0:
        raise DadosInvalidos("O preço deve ser maior que zero.")
    if preco > PRECO_MAXIMO:
        raise DadosInvalidos(f"O preço deve ser no máximo {PRECO_MAXIMO}.")
    return preco


def validar_quantidade(valor, campo: str = "quantidade", minimo: int = 1) -> int:
    """Valida um inteiro no intervalo [minimo, QUANTIDADE_MAXIMA_OPERACAO]."""
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise DadosInvalidos(f"O campo '{campo}' deve ser um número inteiro.")
    if valor < minimo:
        raise DadosInvalidos(f"O campo '{campo}' deve ser no mínimo {minimo}.")
    if valor > QUANTIDADE_MAXIMA_OPERACAO:
        raise DadosInvalidos(
            f"O campo '{campo}' deve ser no máximo {QUANTIDADE_MAXIMA_OPERACAO}."
        )
    return valor


@dataclass
class Produto:
    sku: str
    nome: str
    preco: Decimal
    quantidade: int = 0
    estoque_minimo: int = 0

    @classmethod
    def criar(cls, dados) -> "Produto":
        """Cria um produto a partir de um dicionário (ex.: corpo JSON)."""
        if not isinstance(dados, dict):
            raise DadosInvalidos("Os dados do produto devem ser um objeto JSON.")
        return cls(
            sku=validar_sku(dados.get("sku")),
            nome=validar_nome(dados.get("nome")),
            preco=validar_preco(dados.get("preco")),
            quantidade=validar_quantidade(
                dados.get("quantidade", 0), "quantidade", minimo=0
            ),
            estoque_minimo=validar_quantidade(
                dados.get("estoque_minimo", 0), "estoque_minimo", minimo=0
            ),
        )

    @property
    def precisa_reposicao(self) -> bool:
        """Regra RN-E05: alerta quando o saldo atinge ou fica abaixo do mínimo."""
        return self.quantidade <= self.estoque_minimo

    def validar_entrada(self, quantidade: int) -> int:
        quantidade = validar_quantidade(quantidade)
        if self.quantidade + quantidade > CAPACIDADE_MAXIMA:
            raise DadosInvalidos(
                f"Capacidade máxima de armazenamento ({CAPACIDADE_MAXIMA}) excedida."
            )
        return quantidade

    def validar_saida(self, quantidade: int) -> int:
        quantidade = validar_quantidade(quantidade)
        if quantidade > self.quantidade:
            raise EstoqueInsuficiente(self.sku, self.quantidade, quantidade)
        return quantidade

    def adicionar(self, quantidade: int) -> None:
        self.quantidade += self.validar_entrada(quantidade)

    def remover(self, quantidade: int) -> None:
        self.quantidade -= self.validar_saida(quantidade)

    def para_dict(self) -> dict:
        return {
            "sku": self.sku,
            "nome": self.nome,
            "preco": f"{self.preco:.2f}",
            "quantidade": self.quantidade,
            "estoque_minimo": self.estoque_minimo,
            "precisa_reposicao": self.precisa_reposicao,
        }
