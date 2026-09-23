"""Demonstração funcional das duas aplicações (evidências para o relatório).

* ``demonstrar_api``  - executa um roteiro de chamadas HTTP e registra requisições e respostas.
* ``demonstrar_interface`` - usa o Playwright para operar as interfaces web das duas
  aplicações lado a lado, gravando o vídeo da execução e capturas de tela.

As aplicações são iniciadas como processos reais (``python -m ...``) nas portas 5001 e 5002.
"""

from __future__ import annotations

import contextlib
import functools
import html
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
PORTA_ESTOQUE, PORTA_PEDIDOS = 5001, 5002
URL_ESTOQUE = f"http://127.0.0.1:{PORTA_ESTOQUE}"
URL_PEDIDOS = f"http://127.0.0.1:{PORTA_PEDIDOS}"
LARGURA, ALTURA, ALTURA_LEGENDA, ZOOM = 1600, 900, 104, 1.15


# ---------------------------------------------------------------------------
# Processos das aplicações
# ---------------------------------------------------------------------------


class Servico:
    def __init__(self, modulo: str, ambiente: dict, url: str):
        self.modulo, self.url = modulo, url
        self._ambiente = {**os.environ, **ambiente}
        self._processo: subprocess.Popen | None = None

    def iniciar(self) -> "Servico":
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", int(self.url.rsplit(":", 1)[1]))) == 0:
                raise SystemExit(f"A porta de {self.url} já está em uso; encerre o processo que a ocupa.")
        self._processo = subprocess.Popen([sys.executable, "-m", self.modulo], cwd=RAIZ, env=self._ambiente,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(150):
            try:
                if requests.get(f"{self.url}/health", timeout=3).ok:
                    return self
            except requests.RequestException:
                time.sleep(0.1)
        raise SystemExit(f"{self.modulo} não iniciou.")

    def parar(self) -> None:
        if self._processo and self._processo.poll() is None:
            self._processo.terminate()
            self._processo.wait(timeout=10)


@contextlib.contextmanager
def aplicacoes_no_ar():
    estoque = Servico("estoque_service", {"ESTOQUE_PORTA": str(PORTA_ESTOQUE)}, URL_ESTOQUE).iniciar()
    pedidos = Servico("pedidos_service", {"PEDIDOS_PORTA": str(PORTA_PEDIDOS), "ESTOQUE_URL": URL_ESTOQUE},
                      URL_PEDIDOS).iniciar()
    try:
        yield estoque, pedidos
    finally:
        pedidos.parar()
        estoque.parar()


# ---------------------------------------------------------------------------
# Demonstração via API (registro de requisições e respostas)
# ---------------------------------------------------------------------------

PRODUTOS = [
    {"sku": "TEC-001", "nome": "Teclado mecânico", "preco": "250.00", "quantidade": 10, "estoque_minimo": 3},
    {"sku": "MOU-001", "nome": "Mouse sem fio", "preco": "120.00", "quantidade": 5, "estoque_minimo": 2},
    {"sku": "MON-001", "nome": "Monitor 27 polegadas", "preco": "1200.00", "quantidade": 2, "estoque_minimo": 1},
]


def demonstrar_api(destino: Path) -> list[dict]:
    """Executa o roteiro via HTTP e salva o registro em ``destino`` (texto). Retorna as interações."""
    interacoes: list[dict] = []

    def chamar(titulo, metodo, url, corpo=None):
        resposta = requests.request(metodo, url, json=corpo, timeout=10)
        interacoes.append({"titulo": titulo, "metodo": metodo, "url": url, "corpo": corpo,
                           "status": resposta.status_code, "motivo": resposta.reason,
                           "resposta": resposta.json()})
        return resposta

    with aplicacoes_no_ar():
        chamar("Saúde do Serviço de Estoque", "GET", f"{URL_ESTOQUE}/health")
        for produto in PRODUTOS:
            chamar(f"Cadastro do produto {produto['sku']} no Estoque", "POST", f"{URL_ESTOQUE}/api/produtos", produto)
        chamar("Pedidos verifica a dependência (Estoque online)", "GET", f"{URL_PEDIDOS}/health")
        chamar("Catálogo exibido pelo Pedidos (vem do Estoque)", "GET", f"{URL_PEDIDOS}/api/catalogo")
        chamar("Pedido com subtotal R$ 620,00 → desconto de 5%", "POST", f"{URL_PEDIDOS}/api/pedidos",
               {"cliente": "Maria Souza", "itens": [{"sku": "TEC-001", "quantidade": 2},
                                                   {"sku": "MOU-001", "quantidade": 1}]})
        chamar("Saldos no Estoque após o pedido (baixa automática)", "GET", f"{URL_ESTOQUE}/api/produtos")
        chamar("Pedido acima do saldo → recusado (409)", "POST", f"{URL_PEDIDOS}/api/pedidos",
               {"cliente": "Carlos Lima", "itens": [{"sku": "MON-001", "quantidade": 5}]})
        chamar("Pedido com produto inexistente → 422", "POST", f"{URL_PEDIDOS}/api/pedidos",
               {"cliente": "Carlos Lima", "itens": [{"sku": "XYZ-999", "quantidade": 1}]})
        chamar("Pedido com quantidade acima do limite (101) → 400", "POST", f"{URL_PEDIDOS}/api/pedidos",
               {"cliente": "Carlos Lima", "itens": [{"sku": "TEC-001", "quantidade": 101}]})
        chamar("Pedido de R$ 1.200,00 → desconto de 10%", "POST", f"{URL_PEDIDOS}/api/pedidos",
               {"cliente": "Carlos Lima", "itens": [{"sku": "MON-001", "quantidade": 1}]})
        chamar("Produtos que precisam de reposição (saldo ≤ mínimo)", "GET", f"{URL_ESTOQUE}/api/produtos/reposicao")
        chamar("Cancelamento do pedido 1", "POST", f"{URL_PEDIDOS}/api/pedidos/1/cancelamento")
        chamar("Segundo cancelamento do pedido 1 → 409", "POST", f"{URL_PEDIDOS}/api/pedidos/1/cancelamento")
        chamar("Saldos no Estoque após o cancelamento (itens devolvidos)", "GET", f"{URL_ESTOQUE}/api/produtos")

    linhas = []
    for n, i in enumerate(interacoes, 1):
        linhas += [f"### {n}. {i['titulo']}", f">>> {i['metodo']} {i['url']}"]
        if i["corpo"] is not None:
            linhas.append(json.dumps(i["corpo"], ensure_ascii=False))
        linhas += [f"<<< {i['status']} {i['motivo']}", json.dumps(i["resposta"], ensure_ascii=False, indent=2), ""]
    destino.write_text("\n".join(linhas), encoding="utf-8")
    return interacoes


# ---------------------------------------------------------------------------
# Páginas auxiliares do "palco" usado na gravação
# ---------------------------------------------------------------------------

PALCO = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Demonstração</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: #0f172a; font-family: "Segoe UI", system-ui, sans-serif; overflow: hidden; }
  #legenda { height: __ALT__px; padding: 18px 28px; display: flex; gap: 18px; align-items: center; color: #f8fafc; }
  #numero { flex: none; width: 58px; height: 58px; border-radius: 14px; background: #facc15; color: #0f172a;
            font-size: 28px; font-weight: 800; display: grid; place-items: center; }
  #titulo { font-size: 25px; font-weight: 700; }
  #texto { font-size: 16px; color: #cbd5e1; margin-top: 4px; }
  #conteudo { position: absolute; top: __ALT__px; left: 0; right: 0; bottom: 0; display: flex; gap: 10px; padding: 0 10px 10px; }
  .janela { flex: 1; position: relative; border-radius: 10px; overflow: hidden; background: #fff; }
  .barra { height: 34px; background: #e2e8f0; display: flex; align-items: center; gap: 8px; padding: 0 12px;
           font: 13px/1 ui-monospace, Menlo, Consolas, monospace; color: #334155; }
  .barra b { width: 10px; height: 10px; border-radius: 50%; background: #cbd5e1; display: inline-block; }
  .barra span { background: #fff; border-radius: 6px; padding: 5px 10px; flex: 1; }
  iframe { position: absolute; top: 34px; left: 0; border: 0; background: #fff; transform: scale(__ZOOM__);
           transform-origin: 0 0; width: calc(100% / __ZOOM__); height: calc((100% - 34px) / __ZOOM__); }
  #unica { display: none; }
  #unica iframe { transform: none; width: 100%; height: calc(100% - 34px); }
  #cartao { position: absolute; inset: 0; background: radial-gradient(circle at 30% 20%, #1e3a8a, #0f172a 70%);
            color: #f8fafc; display: none; flex-direction: column; justify-content: center; padding: 0 120px; }
  #cartao h1 { font-size: 46px; margin: 0 0 18px; } #cartao p { font-size: 22px; color: #cbd5e1; margin: 6px 0; }
  #cartao .destaque { color: #facc15; font-weight: 700; }
</style></head><body>
<div id="legenda"><div id="numero">▶</div><div><div id="titulo"></div><div id="texto"></div></div></div>
<div id="conteudo">
  <div class="janela" id="janela-estoque"><div class="barra"><b></b><b></b><b></b><span>__URL_E__/  ·  Aplicação 1</span></div>
    <iframe id="frame-estoque" src="__URL_E__/"></iframe></div>
  <div class="janela" id="janela-pedidos"><div class="barra"><b></b><b></b><b></b><span>__URL_P__/  ·  Aplicação 2</span></div>
    <iframe id="frame-pedidos" src="__URL_P__/"></iframe></div>
  <div class="janela" id="unica"><div class="barra"><b></b><b></b><b></b><span id="rotulo-unica"></span></div>
    <iframe id="frame-unica"></iframe></div>
</div>
<div id="cartao"></div>
<script>
  function legenda(numero, titulo, texto) {
    document.getElementById("numero").textContent = numero;
    document.getElementById("titulo").textContent = titulo;
    document.getElementById("texto").textContent = texto || "";
  }
  function modoUnico(url, rotulo) {
    document.getElementById("janela-estoque").style.display = "none";
    document.getElementById("janela-pedidos").style.display = "none";
    document.getElementById("unica").style.display = "block";
    document.getElementById("rotulo-unica").textContent = rotulo;
    document.getElementById("frame-unica").src = url;
  }
  function cartao(conteudo) {
    const c = document.getElementById("cartao");
    c.innerHTML = conteudo; c.style.display = conteudo ? "flex" : "none";
  }
</script></body></html>"""


def pagina_terminal(comando: str, saida: str, titulo: str) -> str:
    """Renderiza a saída real do pytest como um terminal (usada no vídeo e no PDF)."""
    linhas = []
    for linha in saida.splitlines():
        texto = html.escape(linha)
        if " PASSED" in linha or re.search(r"\b\d+ passed\b", linha):
            texto = re.sub(r"(PASSED|\d+ passed)", r'<span class="ok">\1</span>', texto)
        if "FAILED" in linha or "ERROR" in linha:
            texto = f'<span class="erro">{texto}</span>'
        if linha.startswith(("TOTAL", "Required test coverage")) or linha.startswith("="):
            texto = f"<strong>{texto}</strong>"
        texto = re.sub(r"\b100%", '<span class="ok">100%</span>', texto)
        linhas.append(texto)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{html.escape(titulo)}</title>
<style>body {{ margin: 0; background: #0b1020; color: #e2e8f0; font: 13.5px/1.45 "DejaVu Sans Mono", Consolas, monospace; }}
pre {{ margin: 0; padding: 18px 22px; white-space: pre-wrap; word-break: break-all; }}
.prompt {{ color: #93c5fd; }} .ok {{ color: #4ade80; font-weight: 700; }} .erro {{ color: #f87171; }}
strong {{ color: #fff; }}</style></head><body><pre><span class="prompt">$ {html.escape(comando)}</span>
{chr(10).join(linhas)}</pre></body></html>"""


class ServidorEstatico:
    """Servidor HTTP simples para o palco e as páginas de evidência."""

    def __init__(self, pasta: Path):
        manipulador = functools.partial(_ManipuladorSilencioso, directory=str(pasta))
        self._servidor = ThreadingHTTPServer(("127.0.0.1", 0), manipulador)
        self.url = f"http://127.0.0.1:{self._servidor.server_port}"
        threading.Thread(target=self._servidor.serve_forever, daemon=True).start()

    def parar(self):
        self._servidor.shutdown()
        self._servidor.server_close()


class _ManipuladorSilencioso(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


# ---------------------------------------------------------------------------
# Demonstração via interface web (vídeo + capturas)
# ---------------------------------------------------------------------------


def demonstrar_interface(evidencias: Path, gravar_video: bool, destino_video: Path | None = None) -> dict[str, Path]:
    """Opera as duas interfaces web lado a lado. Retorna as capturas geradas (nome -> arquivo)."""
    from playwright.sync_api import sync_playwright

    capturas_dir = evidencias / "capturas"
    capturas_dir.mkdir(parents=True, exist_ok=True)
    capturas: dict[str, Path] = {}
    ritmo = 1.0 if gravar_video else 0.25
    atraso_digitacao = 55 if gravar_video else 5

    pasta_palco = Path(tempfile.mkdtemp(prefix="palco_"))
    (pasta_palco / "index.html").write_text(
        PALCO.replace("__ALT__", str(ALTURA_LEGENDA)).replace("__ZOOM__", str(ZOOM)).replace("__URL_E__", URL_ESTOQUE).replace("__URL_P__", URL_PEDIDOS),
        encoding="utf-8")
    for nome, comando, titulo in [
        ("saida_testes_unitarios", "pytest tests/unit -v --cov --cov-report=term-missing --cov-fail-under=90",
         "Testes unitários"),
        ("saida_testes_integracao", "pytest tests/integration -v", "Testes de integração"),
    ]:
        saida = (evidencias / f"{nome}.txt").read_text(encoding="utf-8")
        (pasta_palco / f"{nome}.html").write_text(pagina_terminal(comando, saida, titulo), encoding="utf-8")
    if (evidencias / "cobertura_html").exists():
        shutil.copytree(evidencias / "cobertura_html", pasta_palco / "cobertura_html")
    servidor = ServidorEstatico(pasta_palco)
    pasta_video = Path(tempfile.mkdtemp(prefix="video_"))

    with aplicacoes_no_ar() as (estoque_proc, _), sync_playwright() as p:
        navegador = p.chromium.launch()
        opcoes = {"viewport": {"width": LARGURA, "height": ALTURA}, "device_scale_factor": 2}
        if gravar_video:
            opcoes.update(record_video_dir=str(pasta_video), record_video_size={"width": LARGURA, "height": ALTURA})
        contexto = navegador.new_context(**opcoes)
        pagina = contexto.new_page()
        pagina.goto(f"{servidor.url}/index.html")
        estoque = pagina.frame_locator("#frame-estoque")
        pedidos = pagina.frame_locator("#frame-pedidos")

        def esperar(segundos: float):
            pagina.wait_for_timeout(int(segundos * 1000 * ritmo))

        def legenda(numero, titulo, texto=""):
            pagina.evaluate("([n, t, x]) => legenda(n, t, x)", [str(numero), titulo, texto])

        def destacar(locator):
            locator.evaluate("""el => { el.scrollIntoView({block: 'nearest'});
                el.animate([{boxShadow: '0 0 0 5px rgba(250,204,21,1)'}, {boxShadow: '0 0 0 14px rgba(250,204,21,0)'}],
                           {duration: 1300, iterations: 2}); }""")

        def digitar(locator, texto):
            destacar(locator)
            locator.fill("")
            locator.press_sequentially(texto, delay=atraso_digitacao)

        def clicar(locator):
            destacar(locator)
            esperar(0.5)
            locator.click()

        def capturar(nome, alvo=None):
            arquivo = capturas_dir / f"{nome}.png"
            if alvo is None:
                pagina.screenshot(path=str(arquivo), clip={"x": 0, "y": ALTURA_LEGENDA, "width": LARGURA,
                                                           "height": ALTURA - ALTURA_LEGENDA})
            else:
                pagina.locator(alvo).screenshot(path=str(arquivo))
            capturas[nome] = arquivo

        # Abertura ------------------------------------------------------------
        pagina.evaluate("""cartao(`<p class="destaque">Trabalho Parcial · Teste e Requisitos de Software</p>
            <h1>Serviço de Estoque + Serviço de Pedidos</h1>
            <p>Aplicação 1: API de Estoque (porta 5001)</p><p>Aplicação 2: API de Pedidos (porta 5002)</p>
            <p>As duas rodam em processos separados e se comunicam por HTTP/JSON.</p>`)""")
        esperar(5)
        pagina.evaluate("cartao('')")
        legenda("▶", "As duas aplicações em execução",
                "Esquerda: Serviço de Estoque (Aplicação 1). Direita: Serviço de Pedidos (Aplicação 2), que consome o Estoque.")
        esperar(3.5)

        # 1. Cadastro de produtos ----------------------------------------------
        legenda(1, "Cadastro de produtos no Serviço de Estoque",
                "POST /api/produtos: SKU, nome, preço, saldo inicial e estoque mínimo")
        for produto in PRODUTOS:
            digitar(estoque.locator("#sku"), produto["sku"])
            digitar(estoque.locator("#nome"), produto["nome"])
            digitar(estoque.locator("#preco"), produto["preco"])
            digitar(estoque.locator("#quantidade"), str(produto["quantidade"]))
            digitar(estoque.locator("#estoque_minimo"), str(produto["estoque_minimo"]))
            clicar(estoque.locator("#btn-cadastrar"))
            estoque.locator(f'tr[data-sku="{produto["sku"]}"]').wait_for()
            esperar(1)
        esperar(1)
        capturar("01_produtos_cadastrados")

        # 2. Catálogo -----------------------------------------------------------
        legenda(2, "O Serviço de Pedidos obtém o catálogo do Estoque via HTTP",
                "GET /api/catalogo no Pedidos → GET /api/produtos no Estoque (preços e saldos em tempo real)")
        pedidos.locator('#produto option[value="MON-001"]').wait_for(state="attached")
        destacar(pedidos.locator("#produto"))
        esperar(3.5)

        # 3. Pedido com 5% ------------------------------------------------------
        legenda(3, "Pedido com desconto de 5% (subtotal R$ 620,00 ≥ R$ 500,00)",
                "O Pedidos reserva os itens no Estoque (POST /api/estoque/baixas) e usa o preço informado por ele")
        digitar(pedidos.locator("#cliente"), "Maria Souza")
        for sku, quantidade in [("TEC-001", "2"), ("MOU-001", "1")]:
            pedidos.locator("#produto").select_option(sku)
            digitar(pedidos.locator("#quantidade"), quantidade)
            clicar(pedidos.locator("#btn-adicionar"))
        clicar(pedidos.locator("#btn-finalizar"))
        pedidos.locator("#mensagem.ok").wait_for()
        esperar(2.5)

        # 4. Estoque atualizado ---------------------------------------------------
        legenda(4, "O Estoque foi atualizado automaticamente",
                "Teclado: 10 → 8 · Mouse: 5 → 4 (baixa feita pela Aplicação 2 na Aplicação 1)")
        estoque.locator('tr[data-sku="TEC-001"] .saldo', has_text="8").wait_for()
        destacar(estoque.locator('tr[data-sku="TEC-001"]'))
        destacar(estoque.locator('tr[data-sku="MOU-001"]'))
        esperar(3.5)
        capturar("02_pedido_5_por_cento_e_baixa")

        # 5. Saldo insuficiente ---------------------------------------------------
        legenda(5, "Regra de negócio: saldo insuficiente → pedido recusado (HTTP 409)",
                "5 monitores solicitados, apenas 2 em estoque: nenhum item é baixado e nenhum pedido é criado")
        digitar(pedidos.locator("#cliente"), "Carlos Lima")
        pedidos.locator("#produto").select_option("MON-001")
        digitar(pedidos.locator("#quantidade"), "5")
        clicar(pedidos.locator("#btn-adicionar"))
        clicar(pedidos.locator("#btn-finalizar"))
        pedidos.locator("#mensagem.erro").wait_for()
        destacar(pedidos.locator("#mensagem"))
        esperar(3.5)
        capturar("03_pedido_recusado_409", "#janela-pedidos")

        # 6. Pedido com 10% ---------------------------------------------------------
        legenda(6, "Pedido acima de R$ 1.000,00 recebe 10% de desconto",
                "1 monitor de R$ 1.200,00 → total R$ 1.080,00")
        clicar(pedidos.locator(".chip button").first)
        pedidos.locator("#produto").select_option("MON-001")
        digitar(pedidos.locator("#quantidade"), "1")
        clicar(pedidos.locator("#btn-adicionar"))
        clicar(pedidos.locator("#btn-finalizar"))
        pedidos.locator("#mensagem.ok").wait_for()
        esperar(2.5)

        # 7. Alerta de reposição ------------------------------------------------------
        legenda(7, "Alerta de reposição no Estoque",
                "Monitor chegou ao estoque mínimo (saldo 1 ≤ mínimo 1) → situação \"Repor\"")
        estoque.locator('tr[data-sku="MON-001"] .badge.repor').wait_for()
        destacar(estoque.locator('tr[data-sku="MON-001"]'))
        esperar(3.5)
        capturar("04_pedido_10_por_cento_e_reposicao")

        # 8. Cancelamento ---------------------------------------------------------------
        legenda(8, "Cancelamento: os itens do pedido #1 voltam para o Estoque",
                "POST /api/pedidos/1/cancelamento → POST /api/estoque/devolucoes (Teclado 8 → 10, Mouse 4 → 5)")
        clicar(pedidos.locator('button[data-cancelar="1"]'))
        pedidos.locator('tr[data-id="1"] .badge.CANCELADO').wait_for()
        estoque.locator('tr[data-sku="TEC-001"] .saldo', has_text="10").wait_for()
        destacar(estoque.locator('tr[data-sku="TEC-001"]'))
        destacar(estoque.locator('tr[data-sku="MOU-001"]'))
        esperar(3.5)
        capturar("05_cancelamento_devolve_estoque")

        # 9. Estoque fora do ar ---------------------------------------------------------
        legenda(9, "Resiliência: o Serviço de Estoque é desligado",
                "O Pedidos detecta a indisponibilidade e recusa novos pedidos com HTTP 503, sem registrar nada")
        estoque_proc.parar()
        pedidos.locator("#saude-estoque.off").wait_for(timeout=15000)
        destacar(pedidos.locator(".status"))
        esperar(2)
        digitar(pedidos.locator("#cliente"), "Ana Costa")
        pedidos.locator("#produto").select_option("MOU-001")
        digitar(pedidos.locator("#quantidade"), "1")
        clicar(pedidos.locator("#btn-adicionar"))
        clicar(pedidos.locator("#btn-finalizar"))
        pedidos.locator("#mensagem.erro").wait_for()
        destacar(pedidos.locator("#mensagem"))
        esperar(4)
        capturar("06_estoque_fora_do_ar_503", "#janela-pedidos")

        # 10-12. Evidências dos testes --------------------------------------------------
        legenda(10, "Testes unitários: execução e cobertura",
                "pytest + pytest-cov: todos os testes passando e cobertura de linhas e ramos acima de 90%")
        pagina.evaluate("([u, r]) => modoUnico(u, r)",
                        [f"{servidor.url}/saida_testes_unitarios.html", "Terminal · pytest tests/unit"])
        quadro = pagina.wait_for_selector("#frame-unica").content_frame()
        quadro.wait_for_load_state()
        esperar(2)
        altura = quadro.evaluate("document.body.scrollHeight")
        passos = 40
        for i in range(1, passos + 1):
            quadro.evaluate(f"window.scrollTo(0, {altura * i / passos})")
            esperar(0.18)
        esperar(4)

        if (pasta_palco / "cobertura_html").exists():
            legenda(11, "Relatório HTML de cobertura (coverage.py)",
                    "Cobertura por arquivo das duas aplicações, incluindo ramos (branch coverage)")
            pagina.evaluate("([u, r]) => modoUnico(u, r)",
                            [f"{servidor.url}/cobertura_html/index.html", "htmlcov/index.html"])
            esperar(6)

        legenda(12, "Testes de integração entre as duas aplicações",
                "Cada teste sobe o Estoque e o Pedidos em processos separados e verifica a comunicação HTTP real")
        pagina.evaluate("([u, r]) => modoUnico(u, r)",
                        [f"{servidor.url}/saida_testes_integracao.html", "Terminal · pytest tests/integration -v"])
        esperar(7)

        # Encerramento -------------------------------------------------------------------
        resumo = json.loads((evidencias / "resumo.json").read_text(encoding="utf-8"))
        pagina.evaluate("c => cartao(c)", f"""<p class="destaque">Resultado</p>
            <h1>{resumo['unitarios']['aprovados']} testes unitários · {resumo['integracao']['aprovados']} testes de integração</h1>
            <p>Todos passando · cobertura dos testes unitários: <span class="destaque">{resumo['cobertura']['total']}%</span>
            (meta: 90%)</p><p>Documentação dos testes, matriz de rastreabilidade e evidências no relatório PDF.</p>""")
        esperar(5)

        video = pagina.video
        contexto.close()
        navegador.close()
        if gravar_video and video and destino_video:
            converter_para_mp4(Path(video.path()), destino_video)

    servidor.parar()
    shutil.rmtree(pasta_palco, ignore_errors=True)
    shutil.rmtree(pasta_video, ignore_errors=True)
    return capturas


def converter_para_mp4(origem: Path, destino: Path) -> None:
    import imageio_ffmpeg

    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(origem),
                    "-c:v", "libx264", "-preset", "slow", "-crf", "22", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(destino)], check=True)


def capturar_pagina(url: str, destino: Path, largura: int = 1280, altura: int = 800, pagina_inteira=False) -> Path:
    """Tira uma captura de tela de uma página (usado para os relatórios HTML)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": largura, "height": altura}, device_scale_factor=2)
        pagina.goto(url)
        pagina.wait_for_load_state("networkidle")
        pagina.screenshot(path=str(destino), full_page=pagina_inteira)
        navegador.close()
    return destino
