"""Infraestrutura dos testes de integração.

As duas aplicações são iniciadas como **processos independentes**
(``python -m estoque_service`` e ``python -m pedidos_service``), cada uma na
sua própria porta TCP, exatamente como em produção. O Serviço de Pedidos é
configurado pela variável ESTOQUE_URL para conversar com o Serviço de Estoque
por HTTP. Nenhum dublê é usado aqui.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
import requests

RAIZ_DO_PROJETO = Path(__file__).resolve().parents[2]


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ProcessoServico:
    """Sobe um serviço em um processo separado e aguarda o /health responder."""

    def __init__(self, modulo: str, variavel_porta: str, pasta_logs: Path, ambiente: dict | None = None):
        self.modulo = modulo
        self.porta = porta_livre()
        self.url = f"http://127.0.0.1:{self.porta}"
        self._ambiente = {**os.environ, variavel_porta: str(self.porta), **(ambiente or {})}
        self._log = pasta_logs / f"{modulo}-{self.porta}.log"
        self._processo: subprocess.Popen | None = None
        self._arquivo_log = None

    def iniciar(self, tempo_limite: float = 15.0) -> "ProcessoServico":
        self._arquivo_log = self._log.open("w")
        self._processo = subprocess.Popen(
            [sys.executable, "-m", self.modulo],
            cwd=RAIZ_DO_PROJETO,
            env=self._ambiente,
            stdout=self._arquivo_log,
            stderr=subprocess.STDOUT,
        )
        limite = time.monotonic() + tempo_limite
        while time.monotonic() < limite:
            if self._processo.poll() is not None:
                raise RuntimeError(f"{self.modulo} encerrou ao iniciar:\n{self._log.read_text()}")
            try:
                if requests.get(f"{self.url}/health", timeout=3).status_code == 200:
                    return self
            except requests.RequestException:
                time.sleep(0.1)
        self.parar()
        raise RuntimeError(f"{self.modulo} não respondeu em {tempo_limite}s")

    def parar(self) -> None:
        if self._processo and self._processo.poll() is None:
            self._processo.terminate()
            try:
                self._processo.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._processo.kill()
                self._processo.wait()
        if self._arquivo_log:
            self._arquivo_log.close()


@pytest.fixture(scope="session")
def pasta_logs(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("logs_servicos")


@pytest.fixture(scope="session")
def estoque(pasta_logs):
    """Serviço de Estoque real, compartilhado pelos testes (cada teste usa SKUs próprios)."""
    servico = ProcessoServico("estoque_service", "ESTOQUE_PORTA", pasta_logs).iniciar()
    yield servico
    servico.parar()


@pytest.fixture(scope="session")
def pedidos(estoque, pasta_logs):
    """Serviço de Pedidos real, apontando para o Serviço de Estoque via ESTOQUE_URL."""
    servico = ProcessoServico("pedidos_service", "PEDIDOS_PORTA", pasta_logs,
                              {"ESTOQUE_URL": estoque.url}).iniciar()
    yield servico
    servico.parar()


@pytest.fixture
def iniciar_servico(pasta_logs):
    """Fábrica para testes que precisam de instâncias exclusivas (ex.: derrubar o estoque)."""
    iniciados: list[ProcessoServico] = []

    def _iniciar(modulo: str, variavel_porta: str, ambiente: dict | None = None) -> ProcessoServico:
        servico = ProcessoServico(modulo, variavel_porta, pasta_logs, ambiente).iniciar()
        iniciados.append(servico)
        return servico

    yield _iniciar
    for servico in iniciados:
        servico.parar()


@pytest.fixture
def novo_sku():
    """Gera SKUs únicos para isolar os dados de cada teste no estoque compartilhado."""

    def _novo(prefixo: str = "IT") -> str:
        return f"{prefixo}-{uuid.uuid4().hex[:8].upper()}"

    return _novo


@pytest.fixture
def cadastrar_produto(estoque, novo_sku):
    """Cadastra um produto no Serviço de Estoque real e devolve o SKU."""

    def _cadastrar(preco="100.00", quantidade=10, estoque_minimo=0, url=None) -> str:
        sku = novo_sku()
        resposta = requests.post(f"{url or estoque.url}/api/produtos", json={
            "sku": sku, "nome": f"Produto {sku}", "preco": preco,
            "quantidade": quantidade, "estoque_minimo": estoque_minimo,
        }, timeout=5)
        assert resposta.status_code == 201, resposta.text
        return sku

    return _cadastrar
