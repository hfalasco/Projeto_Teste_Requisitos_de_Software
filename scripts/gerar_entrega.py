"""Gera todos os artefatos da entrega na pasta ``entrega/``.

1. Executa os testes unitários (com cobertura) e de integração, salvando saídas e relatórios.
2. Atualiza a documentação dos casos de teste e a matriz de rastreabilidade.
3. Executa a demonstração funcional (API e interface web) e grava o vídeo.
4. Monta o relatório PDF com a documentação e as evidências.
5. Compacta o código-fonte em ZIP.

Uso:  python scripts/gerar_entrega.py [--sem-video]
Requer: pip install -r requirements-docs.txt  (e `playwright install chromium`)
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

import demonstracao  # noqa: E402
import gerar_documentacao_testes  # noqa: E402
import relatorio_pdf  # noqa: E402

ENTREGA = RAIZ / "entrega"
EVIDENCIAS = ENTREGA / "evidencias"


def etapa(texto: str) -> None:
    print(f"\n==> {texto}", flush=True)


def rodar_pytest(argumentos: list[str], nome: str) -> str:
    ambiente = {**os.environ, "COLUMNS": "110", "PYTHONIOENCODING": "utf-8"}
    processo = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *argumentos],
                              cwd=RAIZ, env=ambiente, capture_output=True, text=True, encoding="utf-8")
    saida = processo.stdout + processo.stderr
    (EVIDENCIAS / f"{nome}.txt").write_text(saida, encoding="utf-8")
    print("   " + saida.strip().splitlines()[-1])
    if processo.returncode != 0:
        raise SystemExit(f"Os testes falharam; veja {EVIDENCIAS / (nome + '.txt')}")
    return saida


def resumo_junit(arquivo: Path) -> dict:
    suite = ET.parse(arquivo).getroot()
    suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
    total = int(suite.get("tests"))
    falhas = int(suite.get("failures")) + int(suite.get("errors"))
    return {"total": total, "aprovados": total - falhas - int(suite.get("skipped")), "falhas": falhas,
            "tempo": float(suite.get("time"))}


def resumo_cobertura(arquivo: Path) -> dict:
    t = json.loads(arquivo.read_text(encoding="utf-8"))["totals"]

    def pct(parte, total):
        valor = 100 * parte / total if total else 100
        return f"{valor:.0f}" if valor == int(valor) else f"{valor:.1f}"

    return {"total": t["percent_covered_display"],
            "linhas": pct(t["covered_lines"], t["num_statements"]),
            "linhas_cobertas": t["covered_lines"], "linhas_total": t["num_statements"],
            "ramos": pct(t["covered_branches"], t["num_branches"]),
            "ramos_cobertos": t["covered_branches"], "ramos_total": t["num_branches"]}


def arquivos_do_projeto() -> list[str]:
    saida = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                           cwd=RAIZ, capture_output=True, text=True, check=True).stdout
    return sorted(a for a in set(saida.splitlines())
                  if not a.startswith("entrega/") and (RAIZ / a).is_file())


def criar_zip(destino: Path) -> int:
    arquivos = arquivos_do_projeto()
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zip_:
        for arquivo in arquivos:
            zip_.write(RAIZ / arquivo, f"{RAIZ.name}/{arquivo}")
    return len(arquivos)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sem-video", action="store_true", help="não grava o vídeo (mais rápido)")
    args = parser.parse_args()

    shutil.rmtree(EVIDENCIAS, ignore_errors=True)
    EVIDENCIAS.mkdir(parents=True)

    etapa("1/6 Testes unitários com cobertura")
    rodar_pytest(["tests/unit", "-v", "--cov", "--cov-report=term-missing",
                  f"--cov-report=html:{EVIDENCIAS / 'cobertura_html'}",
                  f"--cov-report=json:{EVIDENCIAS / 'cobertura.json'}", "--cov-fail-under=90",
                  f"--junitxml={EVIDENCIAS / 'junit-unitarios.xml'}",
                  f"--html={EVIDENCIAS / 'relatorio-testes-unitarios.html'}", "--self-contained-html"],
                 "saida_testes_unitarios")
    (EVIDENCIAS / "cobertura_html" / ".gitignore").unlink(missing_ok=True)

    etapa("2/6 Testes de integração")
    rodar_pytest(["tests/integration", "-v", f"--junitxml={EVIDENCIAS / 'junit-integracao.xml'}",
                  f"--html={EVIDENCIAS / 'relatorio-testes-integracao.html'}", "--self-contained-html"],
                 "saida_testes_integracao")

    etapa("3/6 Documentação dos casos de teste e matriz de rastreabilidade")
    gerar_documentacao_testes.main()
    casos = gerar_documentacao_testes.coletar_casos()
    matriz = gerar_documentacao_testes.montar_matriz(casos)
    resumo = {
        "executado_em": datetime.now().strftime("%d/%m/%Y às %H:%M"),
        "ambiente": {"python": platform.python_version(), "sistema": f"{platform.system()} {platform.release()}"},
        "unitarios": resumo_junit(EVIDENCIAS / "junit-unitarios.xml"),
        "integracao": resumo_junit(EVIDENCIAS / "junit-integracao.xml"),
        "cobertura": resumo_cobertura(EVIDENCIAS / "cobertura.json"),
        "documentacao": {"funcoes": len(casos), "casos": sum(c.casos for c in casos)},
        "requisitos": {"total": len(matriz),
                       "cobertos": sum(1 for m in matriz if m["unitarios"] or m["integracao"] or m["especial"])},
    }
    (EVIDENCIAS / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")

    etapa("4/6 Demonstração funcional (API, interface web e vídeo)")
    interacoes = demonstracao.demonstrar_api(EVIDENCIAS / "demonstracao_api.txt")
    capturas = demonstracao.demonstrar_interface(EVIDENCIAS, gravar_video=not args.sem_video,
                                                 destino_video=ENTREGA / "video_execucao.mp4")
    capturas["07_relatorio_cobertura"] = demonstracao.capturar_pagina(
        (EVIDENCIAS / "cobertura_html" / "index.html").as_uri(), EVIDENCIAS / "capturas" / "07_relatorio_cobertura.png",
        largura=1100, altura=760)
    capturas["08_relatorio_integracao"] = demonstracao.capturar_pagina(
        (EVIDENCIAS / "relatorio-testes-integracao.html").as_uri(),
        EVIDENCIAS / "capturas" / "08_relatorio_integracao.png", largura=1100, altura=900)

    etapa("5/6 Relatório PDF")
    meta = json.loads((RAIZ / "docs" / "metadados.json").read_text(encoding="utf-8"))
    relatorio_pdf.gerar_pdf(ENTREGA / "Relatorio_Trabalho_Parcial.pdf", meta, resumo, EVIDENCIAS, capturas,
                            interacoes)

    etapa("6/6 Código-fonte (ZIP)")
    total = criar_zip(ENTREGA / "codigo_fonte.zip")
    print(f"   {total} arquivos compactados")

    print("\nEntrega gerada em", ENTREGA)
    for arquivo in sorted(ENTREGA.iterdir()):
        if arquivo.is_file():
            print(f"   {arquivo.name:40s} {arquivo.stat().st_size / 1024:8.0f} KB")


if __name__ == "__main__":
    main()
