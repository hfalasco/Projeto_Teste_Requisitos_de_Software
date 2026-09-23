"""Monta o relatório PDF da entrega (documentação + evidências) com o Chromium do Playwright."""

from __future__ import annotations

import base64
import html
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path

import markdown

RAIZ = Path(__file__).resolve().parents[1]
DOCS = RAIZ / "docs"

CSS = """
@page { size: A4; margin: 17mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Liberation Sans", Arial, sans-serif; font-size: 10.2pt; line-height: 1.45; color: #1f2937; margin: 0; }
h1 { font-size: 21pt; color: #0f3d56; margin: 0 0 14pt; padding-bottom: 6pt; border-bottom: 2.5pt solid #0f766e;
     break-before: page; }
h1.sem-quebra { break-before: auto; }
h2 { font-size: 13.5pt; color: #0f3d56; margin: 18pt 0 6pt; break-after: avoid; }
h3 { font-size: 11pt; color: #334155; margin: 13pt 0 5pt; break-after: avoid; }
h4 { font-size: 10pt; margin: 10pt 0 4pt; break-after: avoid; }
p, li { text-align: justify; }
a { color: #0f766e; text-decoration: none; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.3pt; background: #f1f5f9; padding: 0 2pt; border-radius: 2pt; }
pre { font-family: "DejaVu Sans Mono", monospace; font-size: 7.6pt; line-height: 1.38; background: #f8fafc;
      border: 0.6pt solid #cbd5e1; border-radius: 4pt; padding: 7pt 9pt; white-space: pre-wrap; word-break: break-word; }
pre code { background: none; padding: 0; font-size: inherit; }
pre.terminal { background: #0b1020; color: #e2e8f0; border: 0; break-inside: avoid; }
pre.terminal.longo { break-inside: auto; font-size: 6.5pt; }
pre { break-inside: avoid; }
p:has(+ pre), p:has(+ table), p:has(+ figure) { break-after: avoid; }
pre.terminal .ok { color: #4ade80; font-weight: bold; } pre.terminal .erro { color: #f87171; }
pre.terminal strong { color: #fff; } pre.terminal .prompt { color: #93c5fd; }
blockquote { margin: 8pt 0; padding: 5pt 10pt; border-left: 3pt solid #0f766e; background: #f0fdfa; color: #134e4a; }
blockquote p { margin: 2pt 0; }
table { width: 100%; border-collapse: collapse; margin: 6pt 0 10pt; font-size: 8.6pt; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { background: #0f3d56; color: #fff; text-align: left; padding: 4pt 5pt; font-weight: bold; }
td { padding: 3.5pt 5pt; border-bottom: 0.5pt solid #d6dde6; vertical-align: top; text-align: left; }
tbody tr:nth-child(even) td { background: #f5f8fb; }
td small { color: #64748b; font-size: 7.4pt; }
table.casos { font-size: 7.6pt; }
table.casos td:nth-child(1) { white-space: nowrap; font-weight: bold; color: #0f3d56; }
table.casos td:nth-child(2) code { font-size: 6.9pt; word-break: break-all; background: none; padding: 0; }
table.casos td:nth-child(6) { text-align: center; }
table.casos td:nth-child(7) { white-space: nowrap; color: #15803d; font-weight: bold; }
table.casos th:nth-child(1) { width: 7%; } table.casos th:nth-child(2) { width: 20%; }
table.casos th:nth-child(3) { width: 31%; } table.casos th:nth-child(4) { width: 17%; }
table.casos th:nth-child(5) { width: 9%; } table.casos th:nth-child(6) { width: 5%; }
table.cobertura td:nth-child(n+2), table.cobertura th:nth-child(n+2) { text-align: right; }
table.cobertura tr.total td { font-weight: bold; background: #e7f6ec; }
figure { margin: 10pt 0 14pt; break-inside: avoid; text-align: center; }
figure img { max-width: 100%; border: 0.6pt solid #cbd5e1; border-radius: 3pt; }
figcaption { font-size: 8.6pt; color: #475569; margin-top: 4pt; }
.cartoes { display: flex; gap: 8pt; margin: 8pt 0 12pt; }
.cartao { flex: 1; border: 0.8pt solid #99d5cc; background: #f0fdfa; border-radius: 5pt; padding: 8pt 9pt; }
.cartao .valor { font-size: 19pt; font-weight: bold; color: #0f766e; line-height: 1.1; }
.cartao .rotulo { font-size: 8.4pt; color: #334155; }
.marcador { font-size: 1pt; color: #fff; }
.sumario { list-style: none; padding: 0; margin: 0; }
.sumario li { display: flex; align-items: baseline; gap: 4pt; margin: 3pt 0; text-align: left; }
.sumario li.nivel1 { font-weight: bold; margin-top: 8pt; }
.sumario li.nivel2 { padding-left: 16pt; font-size: 9.6pt; }
.sumario .pontos { flex: 1; border-bottom: 0.8pt dotted #94a3b8; transform: translateY(-3pt); }
.api { break-inside: avoid; margin-bottom: 7pt; }
.api h4 { margin: 0 0 2pt; font-size: 9pt; }
.api pre { margin: 0; }
.status { display: inline-block; border-radius: 3pt; padding: 0 4pt; font-weight: bold; color: #fff; }
.status.s2 { background: #15803d; } .status.s4 { background: #b45309; } .status.s5 { background: #b91c1c; }
.aviso { border: 0.8pt solid #f59e0b; background: #fffbeb; padding: 6pt 9pt; border-radius: 4pt; }
svg text { font-family: "Liberation Sans", Arial, sans-serif; }
"""

CSS_CAPA = """
@page { size: A4; margin: 0; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font-family: "Liberation Sans", Arial, sans-serif; }
.capa { height: 297mm; width: 210mm; display: flex; flex-direction: column; padding: 26mm 22mm 20mm;
        background: linear-gradient(165deg, #0f3d56 0%, #0f3d56 50%, #ffffff 50.1%); color: #0f172a; }
.topo { color: #d1fae5; font-size: 12pt; letter-spacing: .4pt; }
.topo strong { color: #fff; font-size: 14pt; display: block; margin-bottom: 3pt; }
h1 { color: #fff; font-size: 36pt; margin: 24mm 0 6mm; line-height: 1.05; }
.sub { color: #e2e8f0; font-size: 15pt; line-height: 1.35; max-width: 150mm; }
.faixa { margin-top: 12mm; display: flex; gap: 6mm; }
.faixa div { background: #fff; border-radius: 4mm; padding: 5mm 6mm; flex: 1; box-shadow: 0 2mm 6mm rgba(15,23,42,.18); }
.faixa b { display: block; font-size: 20pt; color: #0f766e; } .faixa span { font-size: 10pt; color: #334155; }
.dados { margin-top: auto; font-size: 12pt; line-height: 1.7; }
.dados .rot { color: #64748b; font-size: 10pt; text-transform: uppercase; letter-spacing: .6pt; display: block; margin-top: 4mm; }
.rodape { margin-top: 10mm; font-size: 11pt; color: #334155; border-top: 1pt solid #cbd5e1; padding-top: 4mm; }
"""

DIAGRAMA_ARQUITETURA = """
<figure>
<svg viewBox="0 0 760 250" width="100%" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Arquitetura">
  <defs><marker id="seta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
    <path d="M0,0 L10,5 L0,10 z" fill="#334155"/></marker></defs>
  <rect x="10" y="95" width="120" height="60" rx="8" fill="#f1f5f9" stroke="#64748b"/>
  <text x="70" y="120" text-anchor="middle" font-size="13" font-weight="bold" fill="#1f2937">Usuário</text>
  <text x="70" y="138" text-anchor="middle" font-size="10.5" fill="#475569">navegador / HTTP</text>
  <rect x="215" y="20" width="220" height="92" rx="10" fill="#eef2ff" stroke="#4338ca" stroke-width="1.5"/>
  <text x="325" y="46" text-anchor="middle" font-size="14" font-weight="bold" fill="#312e81">Aplicação 2</text>
  <text x="325" y="66" text-anchor="middle" font-size="13" fill="#312e81">Serviço de Pedidos</text>
  <text x="325" y="86" text-anchor="middle" font-size="11" fill="#475569">Flask · porta 5002</text>
  <text x="325" y="102" text-anchor="middle" font-size="10" fill="#475569">pedidos, descontos, cancelamentos</text>
  <rect x="215" y="140" width="220" height="92" rx="10" fill="#ecfdf5" stroke="#0f766e" stroke-width="1.5"/>
  <text x="325" y="166" text-anchor="middle" font-size="14" font-weight="bold" fill="#134e4a">Aplicação 1</text>
  <text x="325" y="186" text-anchor="middle" font-size="13" fill="#134e4a">Serviço de Estoque</text>
  <text x="325" y="206" text-anchor="middle" font-size="11" fill="#475569">Flask · porta 5001</text>
  <text x="325" y="222" text-anchor="middle" font-size="10" fill="#475569">produtos, saldos, baixas, devoluções</text>
  <line x1="130" y1="115" x2="212" y2="72" stroke="#334155" stroke-width="1.4" marker-end="url(#seta)"/>
  <line x1="130" y1="135" x2="212" y2="180" stroke="#334155" stroke-width="1.4" marker-end="url(#seta)"/>
  <line x1="325" y1="112" x2="325" y2="137" stroke="#b45309" stroke-width="2.2" marker-end="url(#seta)"/>
  <rect x="470" y="40" width="280" height="172" rx="8" fill="#fffbeb" stroke="#f59e0b"/>
  <text x="484" y="62" font-size="12" font-weight="bold" fill="#92400e">Integração HTTP/JSON (Pedidos → Estoque)</text>
  <text x="484" y="86" font-size="11" fill="#1f2937">GET  /api/produtos: catálogo</text>
  <text x="484" y="106" font-size="11" fill="#1f2937">POST /api/estoque/baixas: reserva atômica</text>
  <text x="484" y="126" font-size="11" fill="#1f2937">POST /api/estoque/devolucoes: estorno</text>
  <text x="484" y="146" font-size="11" fill="#1f2937">GET  /health: disponibilidade</text>
  <text x="484" y="172" font-size="10.5" fill="#475569">Erros traduzidos: 409 → 409 · 404 → 422</text>
  <text x="484" y="190" font-size="10.5" fill="#475569">timeout / conexão / 5xx → 503 · contrato → 502</text>
  <line x1="437" y1="125" x2="468" y2="125" stroke="#f59e0b" stroke-dasharray="4 3"/>
</svg>
<figcaption>Figura 1: Visão geral da arquitetura. A Aplicação 2 consome a API REST da Aplicação 1.</figcaption>
</figure>
"""


def _imagem(caminho: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(caminho.read_bytes()).decode()


class Documento:
    """Acumula o HTML do corpo, numerando capítulos, seções e figuras."""

    def __init__(self):
        self.partes: list[str] = []
        self.sumario: list[tuple[int, str, str]] = []  # (nível, número+título, marcador)
        self.capitulo = 0
        self.secao = 0
        self.figura = 1  # a figura 1 é o diagrama de arquitetura
        self.apendice = 0

    def _marcador(self) -> str:
        return f"[[M{len(self.sumario):03d}]]"

    def capitulo_novo(self, titulo: str, apendice: bool = False) -> None:
        if apendice:
            self.apendice += 1
            numero = f"Apêndice {chr(64 + self.apendice)}:"
        else:
            self.capitulo += 1
            numero = f"{self.capitulo}"
        self.secao = 0
        rotulo = f"{numero} {titulo}"
        marcador = self._marcador()
        self.sumario.append((1, rotulo, marcador))
        self.partes.append(f'<h1>{html.escape(rotulo)}<span class="marcador">{marcador}</span></h1>')

    def secao_nova(self, titulo: str) -> None:
        self.secao += 1
        rotulo = f"{self.capitulo}.{self.secao} {titulo}"
        marcador = self._marcador()
        self.sumario.append((2, rotulo, marcador))
        self.partes.append(f'<h2>{html.escape(rotulo)}<span class="marcador">{marcador}</span></h2>')

    def html(self, trecho: str) -> None:
        self.partes.append(trecho)

    def figura_nova(self, caminho: Path, legenda: str, largura: str = "100%") -> None:
        self.figura += 1
        self.partes.append(
            f'<figure><img src="{_imagem(caminho)}" style="width:{largura}">'
            f"<figcaption>Figura {self.figura}: {html.escape(legenda)}</figcaption></figure>")

    def markdown(self, arquivo: Path, titulo: str) -> None:
        """Converte um documento Markdown de docs/ em um capítulo numerado."""
        texto = arquivo.read_text(encoding="utf-8")
        texto = re.sub(r"^# .*\n", "", texto, count=1)
        texto = re.sub(r"```mermaid.*?```", "[[DIAGRAMA]]", texto, flags=re.S)
        corpo = markdown.markdown(texto, extensions=["tables", "fenced_code", "sane_lists"])
        corpo = corpo.replace("<p>[[DIAGRAMA]]</p>", DIAGRAMA_ARQUITETURA)
        if "Teste | Objetivo" in texto:
            corpo = corpo.replace("<table>", '<table class="casos">')
        self.capitulo_novo(titulo)
        for pedaco in re.split(r"(<h2>.*?</h2>)", corpo):
            achado = re.fullmatch(r"<h2>(.*?)</h2>", pedaco)
            if achado:
                self.secao_nova(html.unescape(re.sub(r"<.*?>", "", achado.group(1))))
            else:
                self.html(pedaco)


def terminal(comando: str, saida: str, longo: bool = False) -> str:
    linhas = []
    for linha in saida.rstrip().splitlines():
        texto = html.escape(linha)
        texto = re.sub(r"(PASSED|\b\d+ passed\b)", r'<span class="ok">\1</span>', texto)
        if "FAILED" in linha or "ERROR" in linha:
            texto = f'<span class="erro">{texto}</span>'
        if linha.startswith(("TOTAL", "Required test coverage", "=")):
            texto = f"<strong>{texto}</strong>"
        linhas.append(texto)
    classe = "terminal longo" if longo else "terminal"
    return f'<pre class="{classe}"><span class="prompt">$ {html.escape(comando)}</span>\n' + "\n".join(linhas) + "</pre>"


def _trecho_cobertura(saida: str) -> str:
    """Extrai da saída do pytest apenas o bloco final (tabela de cobertura e resumo)."""
    inicio = saida.find("---------- coverage")
    return saida[inicio:] if inicio >= 0 else saida[-3000:]


def _cabecalho_sessao(saida: str) -> str:
    return "\n".join(saida.splitlines()[:9])


def tabela_cobertura(cobertura: dict) -> str:
    linhas = ['<table class="cobertura"><thead><tr><th>Arquivo</th><th>Instruções</th><th>Não executadas</th>'
              '<th>Ramos</th><th>Ramos parciais</th><th>Cobertura</th></tr></thead><tbody>']
    for arquivo, dados in sorted(cobertura["files"].items()):
        r = dados["summary"]
        linhas.append(f"<tr><td><code>{html.escape(arquivo)}</code></td><td>{r['num_statements']}</td>"
                      f"<td>{r['missing_lines']}</td><td>{r['num_branches']}</td><td>{r['num_partial_branches']}</td>"
                      f"<td>{r['percent_covered_display']}%</td></tr>")
    t = cobertura["totals"]
    linhas.append(f'<tr class="total"><td>TOTAL</td><td>{t["num_statements"]}</td><td>{t["missing_lines"]}</td>'
                  f'<td>{t["num_branches"]}</td><td>{t["num_partial_branches"]}</td>'
                  f'<td>{t["percent_covered_display"]}%</td></tr></tbody></table>')
    return "".join(linhas)


def bloco_api(n: int, interacao: dict) -> str:
    classe = f"s{str(interacao['status'])[0]}"
    requisicao = f"{interacao['metodo']} {interacao['url']}"
    if interacao["corpo"] is not None:
        requisicao += "\n" + json.dumps(interacao["corpo"], ensure_ascii=False)
    resposta = json.dumps(interacao["resposta"], ensure_ascii=False)
    return (f'<div class="api"><h4>{n}. {html.escape(interacao["titulo"])} '
            f'<span class="status {classe}">{interacao["status"]} {html.escape(interacao["motivo"])}</span></h4>'
            f"<pre>&gt;&gt;&gt; {html.escape(requisicao)}\n&lt;&lt;&lt; {html.escape(resposta)}</pre></div>")


def montar_corpo(meta: dict, resumo: dict, evidencias: Path, capturas: dict[str, Path],
                 interacoes: list[dict], cobertura: dict) -> Documento:
    doc = Documento()
    u, i, c = resumo["unitarios"], resumo["integracao"], resumo["cobertura"]
    casos_doc = resumo["documentacao"]

    # 1. Introdução ------------------------------------------------------------------
    doc.capitulo_novo("Introdução")
    doc.html(f"""
<p>Este relatório documenta o <strong>Trabalho Parcial</strong> da disciplina de {html.escape(meta['disciplina'])}.
Foram construídas <strong>duas aplicações</strong> em Python que simulam o back-office de uma loja de informática:
a <strong>Aplicação 1, Serviço de Estoque</strong>, que controla produtos e saldos, e a <strong>Aplicação 2,
Serviço de Pedidos</strong>, que registra vendas e depende do estoque para reservar mercadorias. As aplicações
rodam em processos separados e se comunicam por uma API REST (HTTP/JSON).</p>
<p>O trabalho foi guiado por requisitos: cada requisito funcional, regra de negócio e requisito não funcional
recebeu um identificador (Capítulo 3). Os testes foram projetados com técnicas de caixa-preta e caixa-branca
(partição de equivalência, análise de valor limite, tabela de decisão, transição de estados, dublês de teste
e injeção de falhas). Cada teste documenta seu objetivo e os requisitos que verifica, o que permite construir
a matriz de rastreabilidade do Capítulo 7.</p>
<div class="cartoes">
  <div class="cartao"><div class="valor">{u['aprovados']}/{u['total']}</div><div class="rotulo">testes unitários aprovados</div></div>
  <div class="cartao"><div class="valor">{c['total']}%</div><div class="rotulo">cobertura dos testes unitários (linhas + ramos; meta ≥ 90%)</div></div>
  <div class="cartao"><div class="valor">{i['aprovados']}/{i['total']}</div><div class="rotulo">testes de integração aprovados</div></div>
  <div class="cartao"><div class="valor">{resumo['requisitos']['cobertos']}/{resumo['requisitos']['total']}</div><div class="rotulo">requisitos com teste rastreado</div></div>
</div>""")
    doc.secao_nova("Atendimento ao enunciado da atividade")
    doc.html(f"""
<table><thead><tr><th style="width:27%">Item solicitado</th><th>Como foi atendido</th><th style="width:15%">Onde</th></tr></thead><tbody>
<tr><td>Duas aplicações em qualquer linguagem</td><td>Serviço de Estoque e Serviço de Pedidos, em Python 3 + Flask, executados como processos independentes que se comunicam por HTTP.</td><td>Cap. 2</td></tr>
<tr><td>Documentação sobre o que a aplicação faz</td><td>Arquitetura, funcionalidades, endpoints, regras de negócio, configuração e forma de execução de cada aplicação. Especificação de requisitos com {resumo['requisitos']['total']} itens identificados.</td><td>Cap. 2 e 3</td></tr>
<tr><td>Documentação sobre o objetivo de cada teste</td><td>{casos_doc['funcoes']} funções de teste ({casos_doc['casos']} casos executados), cada uma com <em>objetivo</em>, <em>técnica</em>, <em>requisitos verificados</em> e resultado.</td><td>Cap. 4 e 5</td></tr>
<tr><td>Testes unitários com cobertura de pelo menos 90%</td><td>{u['total']} testes unitários, com cobertura de <strong>{c['linhas']}% das linhas e {c['ramos']}% dos ramos</strong>. O comando usa <code>--cov-fail-under=90</code> e falha se a meta não for atingida.</td><td>Cap. 6.2</td></tr>
<tr><td>Testes de integração entre as aplicações</td><td>{i['total']} testes que sobem as duas aplicações em processos separados e verificam fluxos completos, atomicidade, concorrência e falhas de rede (queda, timeout, porta fechada).</td><td>Cap. 6.3</td></tr>
<tr><td>PDF com evidências</td><td>Este documento: saídas reais do pytest, relatórios de cobertura, capturas de tela e registro das chamadas HTTP.</td><td>Cap. 6</td></tr>
<tr><td>Código-fonte em RAR/ZIP</td><td><code>codigo_fonte.zip</code> (aplicações, testes, documentação e scripts).</td><td>Apêndice B</td></tr>
<tr><td>Vídeo da execução funcional</td><td><code>video_execucao.mp4</code>: as duas aplicações operando lado a lado, seguidas da execução dos testes.</td><td>Apêndice B</td></tr>
</tbody></table>""")

    # 2-5. Documentos em Markdown -------------------------------------------------------
    doc.markdown(DOCS / "01-aplicacoes.md", "Documentação das aplicações")
    doc.markdown(DOCS / "02-requisitos.md", "Especificação de requisitos")
    doc.markdown(DOCS / "03-plano-de-testes.md", "Plano e estratégia de testes")
    doc.markdown(DOCS / "04-casos-de-teste.md", "Casos de teste: objetivo de cada teste")

    # 6. Evidências ----------------------------------------------------------------------
    saida_unit = (evidencias / "saida_testes_unitarios.txt").read_text(encoding="utf-8")
    saida_int = (evidencias / "saida_testes_integracao.txt").read_text(encoding="utf-8")
    doc.capitulo_novo("Evidências de execução")
    doc.html(f"""<p>Todas as evidências abaixo foram produzidas automaticamente pelo script
<code>scripts/gerar_entrega.py</code> em <strong>{resumo['executado_em']}</strong>
(Python {resumo['ambiente']['python']}, {html.escape(resumo['ambiente']['sistema'])}). Os arquivos originais
(saídas de terminal, relatórios JUnit/HTML e relatório de cobertura) acompanham a entrega na pasta
<code>entrega/evidencias/</code>.</p>""")
    doc.secao_nova("Resumo")
    doc.html(f"""
<table><thead><tr><th>Suíte</th><th>Comando</th><th>Casos</th><th>Aprovados</th><th>Falhas</th><th>Tempo</th></tr></thead><tbody>
<tr><td>Unitários</td><td><code>pytest tests/unit --cov --cov-fail-under=90</code></td><td>{u['total']}</td><td>{u['aprovados']}</td><td>{u['falhas']}</td><td>{u['tempo']:.2f} s</td></tr>
<tr><td>Integração</td><td><code>pytest tests/integration</code></td><td>{i['total']}</td><td>{i['aprovados']}</td><td>{i['falhas']}</td><td>{i['tempo']:.2f} s</td></tr>
</tbody></table>
<div class="cartoes">
  <div class="cartao"><div class="valor">{c['linhas']}%</div><div class="rotulo">cobertura de linhas ({c['linhas_cobertas']}/{c['linhas_total']})</div></div>
  <div class="cartao"><div class="valor">{c['ramos']}%</div><div class="rotulo">cobertura de ramos ({c['ramos_cobertos']}/{c['ramos_total']})</div></div>
  <div class="cartao"><div class="valor">{c['total']}%</div><div class="rotulo">cobertura combinada (critério do coverage.py)</div></div>
</div>""")

    doc.secao_nova("Testes unitários e cobertura")
    doc.html("<p>Cobertura por arquivo das duas aplicações, obtida com <code>pytest-cov</code> "
             "(coverage.py com medição de ramos, <code>branch = true</code>):</p>")
    doc.html(tabela_cobertura(cobertura))
    doc.html("<p>Trecho final da saída do terminal (a saída completa, com cada teste, está no Apêndice A):</p>")
    doc.html(terminal("pytest tests/unit -v --cov --cov-report=term-missing --cov-fail-under=90",
                      _trecho_cobertura(saida_unit)))
    if "07_relatorio_cobertura" in capturas:
        doc.figura_nova(capturas["07_relatorio_cobertura"],
                        "Relatório HTML de cobertura gerado pelo coverage.py (entrega/evidencias/cobertura_html/index.html).")

    doc.secao_nova("Testes de integração")
    doc.html("<p>Saída completa da execução. Cada teste utiliza as duas aplicações reais, iniciadas como "
             "processos independentes (<code>python -m estoque_service</code> e <code>python -m pedidos_service</code>).</p>")
    doc.html(terminal("pytest tests/integration -v", saida_int))
    if "08_relatorio_integracao" in capturas:
        doc.figura_nova(capturas["08_relatorio_integracao"],
                        "Relatório pytest-html dos testes de integração (entrega/evidencias/relatorio-testes-integracao.html).")

    doc.secao_nova("Execução funcional pela interface web")
    doc.html("<p>Capturas feitas durante a gravação do vídeo. Na esquerda está o Serviço de Estoque e na direita "
             "o Serviço de Pedidos, ambos em execução nas portas 5001 e 5002.</p>")
    legendas = {
        "01_produtos_cadastrados": "Três produtos cadastrados no Estoque. O catálogo aparece automaticamente no Pedidos.",
        "02_pedido_5_por_cento_e_baixa": "Pedido de R$ 620,00 confirmado com 5% de desconto. O Estoque baixou 2 teclados e 1 mouse.",
        "03_pedido_recusado_409": "Pedido de 5 monitores recusado (saldo 2): HTTP 409, sem baixa parcial.",
        "04_pedido_10_por_cento_e_reposicao": "Pedido de R$ 1.200,00 com 10% de desconto. O monitor atingiu o mínimo e foi sinalizado para reposição.",
        "05_cancelamento_devolve_estoque": "Pedido #1 cancelado: os itens voltaram ao Estoque (Teclado 10, Mouse 5).",
        "06_estoque_fora_do_ar_503": "Com o Estoque desligado, o Pedidos indica a indisponibilidade e recusa o pedido com HTTP 503.",
    }
    for nome, legenda in legendas.items():
        if nome in capturas:
            largura = "78%" if nome in ("03_pedido_recusado_409", "06_estoque_fora_do_ar_503") else "100%"
            doc.figura_nova(capturas[nome], legenda, largura)

    doc.secao_nova("Execução funcional pela API (requisições e respostas)")
    doc.html("<p>Roteiro executado com a biblioteca <code>requests</code> contra as duas aplicações em execução. "
             "Linhas <code>&gt;&gt;&gt;</code> são requisições e linhas <code>&lt;&lt;&lt;</code> são as respostas "
             "reais recebidas (arquivo <code>entrega/evidencias/demonstracao_api.txt</code>).</p>")
    for n, interacao in enumerate(interacoes, 1):
        doc.html(bloco_api(n, interacao))

    # 7. Matriz --------------------------------------------------------------------------
    doc.markdown(DOCS / "05-matriz-de-rastreabilidade.md", "Matriz de rastreabilidade")

    # 8. Conclusão -----------------------------------------------------------------------
    doc.capitulo_novo("Conclusão")
    doc.html(f"""
<p>As duas aplicações atendem aos requisitos especificados, e isso é comprovado por evidências automatizadas e
reprodutíveis. Os <strong>{u['total']} testes unitários</strong> exercitam cada camada de forma isolada. Com o
uso de dublês (stub, mock, fake e spy) e de injeção de dependência, atingiram <strong>{c['linhas']}% de cobertura
de linhas e {c['ramos']}% de ramos</strong>, acima da meta de 90%. Os <strong>{i['total']} testes de integração</strong>
comprovam que as aplicações funcionam em conjunto em um cenário realista: processos separados, portas TCP reais
e falhas de rede provocadas de propósito.</p>
<p>Os testes de integração verificaram comportamentos que um teste unitário sozinho não garante: a baixa em lote
é atômica entre os serviços, o preço vem sempre do Estoque, pedidos simultâneos não vendem além do saldo,
cancelamentos simultâneos não devolvem itens em dobro e a queda do Estoque não deixa os dados inconsistentes.</p>
<p>A documentação dos testes é gerada a partir do próprio código, e a matriz de rastreabilidade liga cada
requisito aos testes que o verificam. Assim é possível responder, a qualquer momento, <em>"o que foi testado e
por quê?"</em>. Todos os {resumo['requisitos']['total']} requisitos possuem verificação automatizada.</p>""")

    # Apêndices ------------------------------------------------------------------------------
    doc.capitulo_novo("Saída completa dos testes unitários", apendice=True)
    doc.html(terminal("pytest tests/unit -v --cov --cov-report=term-missing --cov-fail-under=90", saida_unit,
                      longo=True))

    doc.capitulo_novo("Arquivos da entrega e execução", apendice=True)
    doc.html(f"""
<table><thead><tr><th style="width:36%">Arquivo</th><th>Conteúdo</th></tr></thead><tbody>
<tr><td><code>Relatorio_Trabalho_Parcial.pdf</code></td><td>Este relatório (documentação + evidências).</td></tr>
<tr><td><code>codigo_fonte.zip</code></td><td>Código-fonte completo: <code>estoque_service/</code>, <code>pedidos_service/</code>, <code>tests/</code>, <code>docs/</code>, <code>scripts/</code> e arquivos de configuração.</td></tr>
<tr><td><code>video_execucao.mp4</code></td><td>Vídeo da execução funcional: cadastro, pedidos com desconto, recusa por falta de saldo, alerta de reposição, cancelamento, queda do Estoque e execução dos testes com cobertura.</td></tr>
<tr><td><code>evidencias/saida_testes_*.txt</code></td><td>Saídas completas do terminal (pytest).</td></tr>
<tr><td><code>evidencias/relatorio-testes-*.html</code></td><td>Relatórios pytest-html (abrir no navegador).</td></tr>
<tr><td><code>evidencias/junit-*.xml</code></td><td>Resultados no formato JUnit (padrão de ferramentas de CI).</td></tr>
<tr><td><code>evidencias/cobertura_html/index.html</code></td><td>Relatório navegável de cobertura, linha a linha.</td></tr>
<tr><td><code>evidencias/capturas/</code></td><td>Capturas de tela usadas neste relatório.</td></tr>
<tr><td><code>evidencias/demonstracao_api.txt</code></td><td>Registro das requisições e respostas HTTP da demonstração.</td></tr>
</tbody></table>
<h3>Como reproduzir</h3>
<pre>python -m venv .venv &amp;&amp; source .venv/bin/activate      # Windows: .venv\\Scripts\\activate
pip install -r requirements-dev.txt
pytest tests/unit --cov --cov-report=term-missing --cov-report=html --cov-fail-under=90
pytest tests/integration -v
python -m estoque_service   # terminal 1 → http://127.0.0.1:5001
python -m pedidos_service   # terminal 2 → http://127.0.0.1:5002

# (opcional) regerar PDF, ZIP, vídeo e evidências:
pip install -r requirements-docs.txt &amp;&amp; playwright install chromium
python scripts/gerar_entrega.py</pre>
<p>Repositório: <a href="{html.escape(meta['repositorio'])}">{html.escape(meta['repositorio'])}</a></p>""")
    return doc


def html_corpo(doc: Documento, paginas: dict[str, int] | None) -> str:
    itens = []
    for nivel, rotulo, marcador in doc.sumario:
        pagina = paginas.get(marcador, "") if paginas else "00"
        itens.append(f'<li class="nivel{nivel}"><span>{html.escape(rotulo)}</span><span class="pontos"></span>'
                     f"<span>{pagina}</span></li>")
    sumario = f'<h1 class="sem-quebra">Sumário</h1><ul class="sumario">{"".join(itens)}</ul>'
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>{CSS}</style></head>'
            f"<body>{sumario}{''.join(doc.partes)}</body></html>")


def html_capa(meta: dict, resumo: dict) -> str:
    integrantes = "<br>".join(html.escape(n) for n in meta["integrantes"])
    instituicao = f"<strong>{html.escape(meta['instituicao'])}</strong>" if meta.get("instituicao") else ""
    u, i, c = resumo["unitarios"], resumo["integracao"], resumo["cobertura"]
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>{CSS_CAPA}</style></head><body>
<div class="capa">
  <div class="topo">{instituicao}{html.escape(meta['disciplina'])}</div>
  <h1>{html.escape(meta['titulo'])}</h1>
  <div class="sub">{html.escape(meta['subtitulo'])}</div>
  <div class="faixa">
    <div><b>{u['aprovados']}</b><span>testes unitários</span></div>
    <div><b>{c['total']}%</b><span>de cobertura</span></div>
    <div><b>{i['aprovados']}</b><span>testes de integração</span></div>
  </div>
  <div class="dados">
    <span class="rot">Professor</span>{html.escape(meta['professor'])}
    <span class="rot">Integrantes</span>{integrantes}
  </div>
  <div class="rodape">{html.escape(meta['local_e_data'])}</div>
</div></body></html>"""


RODAPE = """<div style="font-family: 'Liberation Sans', Arial, sans-serif; font-size: 7.5pt; color: #64748b;
width: 100%; padding: 0 16mm; display: flex; justify-content: space-between;">
<span>{titulo}</span><span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>"""


def gerar_pdf(destino: Path, meta: dict, resumo: dict, evidencias: Path, capturas: dict[str, Path],
              interacoes: list[dict]) -> None:
    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader, PdfWriter

    cobertura = json.loads((evidencias / "cobertura.json").read_text(encoding="utf-8"))
    doc = montar_corpo(meta, resumo, evidencias, capturas, interacoes, cobertura)
    rodape = RODAPE.format(titulo=html.escape(f"{meta['titulo']}: {meta['disciplina']}"))
    temporario = Path(tempfile.mkdtemp(prefix="relatorio_"))

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()

        def renderizar(conteudo: str, arquivo: Path, com_rodape: bool) -> None:
            (temporario / "pagina.html").write_text(conteudo, encoding="utf-8")
            pagina.goto((temporario / "pagina.html").as_uri())
            pagina.pdf(path=str(arquivo), format="A4", print_background=True, prefer_css_page_size=True,
                       display_header_footer=com_rodape, header_template="<span></span>",
                       footer_template=rodape if com_rodape else "<span></span>")

        # 1ª passagem: descobre a página de cada título pelos marcadores invisíveis
        corpo_pdf = temporario / "corpo.pdf"
        renderizar(html_corpo(doc, None), corpo_pdf, True)
        paginas: dict[str, int] = {}
        for numero, folha in enumerate(PdfReader(str(corpo_pdf)).pages, 1):
            texto = re.sub(r"\s+", "", folha.extract_text() or "")
            for _, _, marcador in doc.sumario:
                if marcador not in paginas and marcador in texto:
                    paginas[marcador] = numero
        # 2ª passagem: sumário com números de página
        renderizar(html_corpo(doc, paginas), corpo_pdf, True)
        capa_pdf = temporario / "capa.pdf"
        renderizar(html_capa(meta, resumo), capa_pdf, False)
        navegador.close()

    escritor = PdfWriter()
    for arquivo in (capa_pdf, corpo_pdf):
        for folha in PdfReader(str(arquivo)).pages:
            escritor.add_page(folha)
    escritor.add_metadata({"/Title": f"{meta['titulo']}: {meta['disciplina']}",
                           "/Author": ", ".join(meta["integrantes"]),
                           "/Subject": meta["subtitulo"],
                           "/CreationDate": datetime.now().strftime("D:%Y%m%d%H%M%S")})
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("wb") as saida:
        escritor.write(saida)
    faltando = [r for _, r, m in doc.sumario if m not in paginas]
    if faltando:
        print(f"Aviso: página não localizada no sumário para: {faltando}")
