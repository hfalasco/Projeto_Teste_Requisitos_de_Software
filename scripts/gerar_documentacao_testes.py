"""Gera a documentação dos casos de teste e a matriz de rastreabilidade.

Lê a docstring padronizada de cada teste (Objetivo / Técnica / Requisitos),
conta os casos parametrizados via ``pytest --collect-only`` e, se existirem,
incorpora os resultados dos relatórios JUnit em ``entrega/evidencias``.

Uso:  python scripts/gerar_documentacao_testes.py
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, OrderedDict
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DOCS = RAIZ / "docs"
EVIDENCIAS = RAIZ / "entrega" / "evidencias"
ARQUIVO_REQUISITOS = DOCS / "02-requisitos.md"

GRUPOS = [
    # (pasta, prefixo do ID, nível, aplicação)
    ("tests/unit/estoque", "UT-E", "Unitário", "Aplicação 1: Estoque"),
    ("tests/unit/pedidos", "UT-P", "Unitário", "Aplicação 2: Pedidos"),
    ("tests/integration", "IT", "Integração", "Estoque + Pedidos"),
]

ORDEM_ARQUIVOS = ["test_dominio.py", "test_repositorio_e_servico.py", "test_cliente_estoque.py",
                  "test_servico_e_repositorio.py", "test_api.py"]
TITULO_NIVEL = {"Unitário": "Testes unitários", "Integração": "Testes de integração"}

VERIFICACOES_ESPECIAIS = {
    "RNF02": "Verificado pela execução de `pytest --cov --cov-fail-under=90` (seção de evidências).",
}


@dataclass
class CasoDeTeste:
    id: str
    arquivo: str
    classe: str
    funcao: str
    nivel: str
    aplicacao: str
    objetivo: str
    tecnica: str
    requisitos: list[str]
    casos: int = 1
    aprovados: int = 0
    executados: int = 0

    @property
    def chave(self) -> str:
        return f"{self.arquivo}::{self.classe}::{self.funcao}" if self.classe else f"{self.arquivo}::{self.funcao}"

    @property
    def resultado(self) -> str:
        if not self.executados:
            return "Não executado"
        if self.aprovados == self.executados:
            return f"✔ Passou ({self.aprovados}/{self.executados})"
        return f"✘ Falhou ({self.executados - self.aprovados}/{self.executados})"


def carregar_requisitos() -> "OrderedDict[str, str]":
    requisitos: OrderedDict[str, str] = OrderedDict()
    for linha in ARQUIVO_REQUISITOS.read_text(encoding="utf-8").splitlines():
        achado = re.match(r"^\|\s*(R[FN]{1,2}-?[EP]?\d{2})\s*\|\s*(.+?)\s*\|$", linha)
        if achado:
            requisitos[achado.group(1)] = achado.group(2)
    return requisitos


def ler_docstring(no: ast.FunctionDef, arquivo: str) -> tuple[str, str, list[str]]:
    texto = ast.get_docstring(no) or ""
    campos = {}
    for linha in texto.splitlines():
        chave, _, valor = linha.strip().partition(":")
        if chave in ("Objetivo", "Técnica", "Requisitos"):
            campos[chave] = valor.strip()
    if not campos.get("Objetivo"):
        raise SystemExit(f"ERRO: {arquivo}::{no.name} não documenta o campo 'Objetivo'.")
    requisitos = [r.strip() for r in campos.get("Requisitos", "").split(",") if r.strip()]
    return campos["Objetivo"], campos.get("Técnica", ""), requisitos


def coletar_contagem_parametrizada() -> Counter:
    saida = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "tests"],
        cwd=RAIZ, capture_output=True, text=True, check=True,
    ).stdout
    contagem: Counter = Counter()
    for linha in saida.splitlines():
        if "::" in linha:
            contagem[linha.split("[")[0].strip()] += 1
    return contagem


def carregar_resultados_junit() -> dict[str, list[bool]]:
    resultados: dict[str, list[bool]] = {}
    for xml in sorted(EVIDENCIAS.glob("junit-*.xml")):
        for caso in ET.parse(xml).getroot().iter("testcase"):
            partes = caso.get("classname", "").split(".")
            # classname = tests.unit.estoque.test_dominio.TestClasse
            if partes and partes[-1].startswith("Test"):
                modulo, classe = partes[:-1], partes[-1]
            else:
                modulo, classe = partes, ""
            arquivo = "/".join(modulo) + ".py"
            funcao = caso.get("name", "").split("[")[0]
            chave = f"{arquivo}::{classe}::{funcao}" if classe else f"{arquivo}::{funcao}"
            passou = not any(filho.tag in ("failure", "error", "skipped") for filho in caso)
            resultados.setdefault(chave, []).append(passou)
    return resultados


def coletar_casos() -> list[CasoDeTeste]:
    requisitos_validos = carregar_requisitos()
    contagem = coletar_contagem_parametrizada()
    resultados = carregar_resultados_junit()
    casos: list[CasoDeTeste] = []
    for pasta, prefixo, nivel, aplicacao in GRUPOS:
        sequencia = 0
        arquivos = sorted((RAIZ / pasta).glob("test_*.py"), key=lambda a: (
            ORDEM_ARQUIVOS.index(a.name) if a.name in ORDEM_ARQUIVOS else len(ORDEM_ARQUIVOS), a.name))
        for arquivo in arquivos:
            relativo = arquivo.relative_to(RAIZ).as_posix()
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            funcoes = []
            for no in arvore.body:
                if isinstance(no, ast.ClassDef) and no.name.startswith("Test"):
                    funcoes += [(no.name, f) for f in no.body
                                if isinstance(f, ast.FunctionDef) and f.name.startswith("test_")]
                elif isinstance(no, ast.FunctionDef) and no.name.startswith("test_"):
                    funcoes.append(("", no))
            for classe, funcao in funcoes:
                sequencia += 1
                objetivo, tecnica, requisitos = ler_docstring(funcao, relativo)
                desconhecidos = [r for r in requisitos if r not in requisitos_validos]
                if desconhecidos:
                    raise SystemExit(f"ERRO: {relativo}::{funcao.name} cita requisitos inexistentes: {desconhecidos}")
                caso = CasoDeTeste(
                    id=f"{prefixo}{sequencia:02d}", arquivo=relativo, classe=classe, funcao=funcao.name,
                    nivel=nivel, aplicacao=aplicacao, objetivo=objetivo, tecnica=tecnica,
                    requisitos=requisitos,
                )
                caso.casos = contagem.get(caso.chave, 1)
                execucoes = resultados.get(caso.chave, [])
                caso.executados, caso.aprovados = len(execucoes), sum(execucoes)
                casos.append(caso)
    return casos


def _celula(texto: str) -> str:
    return texto.replace("|", "\\|")


def gerar_markdown_casos(casos: list[CasoDeTeste]) -> str:
    linhas = [
        "# Casos de teste",
        "",
        "> Documento gerado automaticamente por `scripts/gerar_documentacao_testes.py` a partir das "
        "*docstrings* dos testes. O campo **Casos** indica quantas execuções o teste gera "
        "(testes parametrizados executam uma vez por conjunto de dados).",
        "",
        "## Resumo",
        "",
        "| Nível | Aplicação | Funções de teste | Casos executados | Resultado |",
        "|---|---|---|---|---|",
    ]
    for _, prefixo, nivel, aplicacao in GRUPOS:
        grupo = [c for c in casos if c.id.startswith(prefixo) and c.id[len(prefixo)].isdigit()]
        executados = sum(c.executados for c in grupo)
        aprovados = sum(c.aprovados for c in grupo)
        resultado = f"{aprovados}/{executados} aprovados" if executados else "Não executado"
        linhas.append(f"| {nivel} | {aplicacao} | {len(grupo)} | {sum(c.casos for c in grupo)} | {resultado} |")
    linhas.append(f"| **Total** | | **{len(casos)}** | **{sum(c.casos for c in casos)}** | |")

    for _, prefixo, nivel, aplicacao in GRUPOS:
        grupo = [c for c in casos if c.id.startswith(prefixo) and c.id[len(prefixo)].isdigit()]
        linhas += ["", f"## {TITULO_NIVEL[nivel]}: {aplicacao}"]
        for arquivo in dict.fromkeys(c.arquivo for c in grupo):
            linhas += [
                "", f"### `{arquivo}`", "",
                "| ID | Teste | Objetivo | Técnica | Requisitos | Casos | Resultado |",
                "|---|---|---|---|---|---|---|",
            ]
            for c in (c for c in grupo if c.arquivo == arquivo):
                teste = f"`{c.funcao}`" + (f"<br><small>{c.classe}</small>" if c.classe else "")
                linhas.append(
                    f"| {c.id} | {teste} | {_celula(c.objetivo)} | {_celula(c.tecnica)} | "
                    f"{', '.join(c.requisitos)} | {c.casos} | {c.resultado} |"
                )
    return "\n".join(linhas) + "\n"


def montar_matriz(casos: list[CasoDeTeste]) -> list[dict]:
    matriz = []
    for requisito, descricao in carregar_requisitos().items():
        relacionados = [c for c in casos if requisito in c.requisitos]
        matriz.append({
            "requisito": requisito,
            "descricao": descricao,
            "unitarios": [c.id for c in relacionados if c.nivel == "Unitário"],
            "integracao": [c.id for c in relacionados if c.nivel == "Integração"],
            "especial": VERIFICACOES_ESPECIAIS.get(requisito, ""),
        })
    return matriz


def gerar_markdown_matriz(casos: list[CasoDeTeste]) -> str:
    matriz = montar_matriz(casos)
    cobertos = sum(1 for m in matriz if m["unitarios"] or m["integracao"] or m["especial"])
    linhas = [
        "# Matriz de rastreabilidade (requisito × teste)",
        "",
        "> Documento gerado automaticamente por `scripts/gerar_documentacao_testes.py`. "
        "Os IDs referem-se ao catálogo em `04-casos-de-teste.md`.",
        "",
        f"**{cobertos} de {len(matriz)} requisitos** possuem verificação automatizada.",
        "",
        "| Requisito | Descrição | Testes unitários | Testes de integração |",
        "|---|---|---|---|",
    ]
    for m in matriz:
        unitarios = ", ".join(m["unitarios"]) or "n/a"
        integracao = ", ".join(m["integracao"]) or "n/a"
        if m["especial"]:
            unitarios = m["especial"] if unitarios == "n/a" else f"{unitarios}. {m['especial']}"
        linhas.append(f"| **{m['requisito']}** | {_celula(m['descricao'])} | {unitarios} | {integracao} |")
    return "\n".join(linhas) + "\n"


def main() -> None:
    casos = coletar_casos()
    (DOCS / "04-casos-de-teste.md").write_text(gerar_markdown_casos(casos), encoding="utf-8")
    (DOCS / "05-matriz-de-rastreabilidade.md").write_text(gerar_markdown_matriz(casos), encoding="utf-8")
    sem_teste = [m["requisito"] for m in montar_matriz(casos)
                 if not (m["unitarios"] or m["integracao"] or m["especial"])]
    print(f"{len(casos)} funções de teste documentadas ({sum(c.casos for c in casos)} casos).")
    if sem_teste:
        raise SystemExit(f"ERRO: requisitos sem teste: {sem_teste}")
    print("Todos os requisitos possuem pelo menos um teste.")


if __name__ == "__main__":
    main()
