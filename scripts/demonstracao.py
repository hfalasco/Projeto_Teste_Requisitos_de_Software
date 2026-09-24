"""Demonstração funcional das duas aplicações (evidências para o relatório).

* ``demonstrar_api``  - executa um roteiro de chamadas HTTP e registra requisições e respostas.
* ``demonstrar_terminal``  - abre quatro terminais reais (bash em pseudo-terminais,
  exibidos com xterm.js), digita os comandos que um usuário digitaria (subir os dois
  servidores, usar as duas CLIs e rodar os testes) e grava o vídeo com o Playwright.

As aplicações são iniciadas como processos reais (``python -m ...``) nas portas 5001 e 5002.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import functools
import json
import os
import pty
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
PORTA_ESTOQUE, PORTA_PEDIDOS = 5001, 5002
URL_ESTOQUE = f"http://127.0.0.1:{PORTA_ESTOQUE}"
URL_PEDIDOS = f"http://127.0.0.1:{PORTA_PEDIDOS}"
LARGURA, ALTURA, ALTURA_LEGENDA = 1600, 900, 92
VENDOR = RAIZ / "scripts" / "vendor" / "xterm"


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
# Terminais reais para a gravação (bash em pseudo-terminal + WebSocket)
# ---------------------------------------------------------------------------


def _ambiente_do_terminal() -> dict:
    venv = RAIZ / ".venv"
    ambiente = {k: v for k, v in os.environ.items() if k not in ("PROMPT_COMMAND", "COLUMNS", "LINES")}
    caminho = ambiente.get("PATH", "")
    if (venv / "bin").exists():
        caminho = f"{venv / 'bin'}:{caminho}"
        ambiente["VIRTUAL_ENV"] = str(venv)
    ambiente.update(PATH=caminho, TERM="xterm-256color", LANG="C.UTF-8", LC_ALL="C.UTF-8", HISTFILE="/dev/null",
                    PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1",
                    PS1=r"\[\e[2m\](.venv)\[\e[0m\] \[\e[1;32m\]aluno@projeto\[\e[0m\]:\[\e[1;34m\]~/Projeto\[\e[0m\]$ ")
    return ambiente


class ServidorDeTerminais:
    """Servidor WebSocket: cada conexão ganha um bash real ligado a um pseudo-terminal."""

    def __init__(self):
        self.porta = _porta_livre()
        self.sessoes: list[int] = []
        self._pronto = threading.Event()
        self._laco: asyncio.AbstractEventLoop | None = None
        threading.Thread(target=self._rodar, daemon=True).start()
        self._pronto.wait(10)

    def _rodar(self):
        import websockets

        self._laco = asyncio.new_event_loop()
        asyncio.set_event_loop(self._laco)

        async def iniciar():
            self._servidor = await websockets.serve(self._atender, "127.0.0.1", self.porta, max_size=None)

        self._laco.run_until_complete(iniciar())
        self._pronto.set()
        self._laco.run_forever()

    async def _atender(self, conexao, *_):
        pid, descritor = pty.fork()
        if pid == 0:  # processo filho: vira o bash do terminal
            os.chdir(RAIZ)
            os.execvpe("bash", ["bash", "--noprofile", "--norc", "-i"], _ambiente_do_terminal())
        self.sessoes.append(pid)
        laco = asyncio.get_running_loop()
        fila: asyncio.Queue = asyncio.Queue()

        def ler():
            try:
                dados = os.read(descritor, 65536)
            except OSError:
                dados = b""
            fila.put_nowait(dados)
            if not dados:
                laco.remove_reader(descritor)

        laco.add_reader(descritor, ler)

        async def enviar():
            while (dados := await fila.get()):
                await conexao.send(dados.decode("utf-8", "replace"))

        tarefa = asyncio.ensure_future(enviar())
        try:
            async for mensagem in conexao:
                if mensagem.startswith("\x00resize:"):
                    colunas, linhas = map(int, mensagem.split(":")[1].split("x"))
                    fcntl.ioctl(descritor, termios.TIOCSWINSZ, struct.pack("HHHH", linhas, colunas, 0, 0))
                else:
                    os.write(descritor, mensagem.encode())
        finally:
            tarefa.cancel()

    def encerrar(self):
        """Encerra todos os processos iniciados nos terminais (servidores inclusive)."""
        for sessao in self.sessoes:
            for entrada in Path("/proc").iterdir():
                if entrada.name.isdigit():
                    with contextlib.suppress(OSError):
                        if os.getsid(int(entrada.name)) == sessao:
                            os.kill(int(entrada.name), signal.SIGKILL)
        if self._laco:
            self._laco.call_soon_threadsafe(self._laco.stop)


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PALCO = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Demonstração</title>
<link rel="stylesheet" href="xterm.css">
<script src="xterm.js"></script><script src="addon-fit.js"></script>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: #0f172a; font-family: "Segoe UI", "DejaVu Sans", sans-serif; overflow: hidden; }
  #legenda { height: __ALT__px; padding: 14px 24px; display: flex; gap: 16px; align-items: center; color: #f8fafc; }
  #numero { flex: none; width: 54px; height: 54px; border-radius: 12px; background: #facc15; color: #0f172a;
            font-size: 26px; font-weight: 800; display: grid; place-items: center; }
  #titulo { font-size: 24px; font-weight: 700; } #texto { font-size: 15.5px; color: #cbd5e1; margin-top: 3px; }
  #grade { position: absolute; top: __ALT__px; left: 0; right: 0; bottom: 0; padding: 0 8px 8px; display: grid;
           gap: 8px; grid-template-columns: 1fr 1fr; grid-template-rows: 30fr 70fr; }
  .painel { display: flex; flex-direction: column; border-radius: 8px; overflow: hidden; background: #0b1020;
            border: 2px solid #1e293b; transition: border-color .3s; min-height: 0; }
  .painel.ativo { border-color: #facc15; }
  .painel.oculto { display: none; }
  #grade.maximizado { grid-template-columns: 1fr; grid-template-rows: 1fr; }
  .titulo { height: 28px; flex: none; background: #1e293b; color: #e2e8f0; font: 600 13px/28px "DejaVu Sans", sans-serif;
            padding: 0 12px; display: flex; gap: 8px; align-items: center; }
  .titulo i { width: 10px; height: 10px; border-radius: 50%; background: #475569; display: inline-block; }
  .titulo span { color: #94a3b8; font-weight: 400; }
  .term { flex: 1; min-height: 0; padding: 4px 0 0 6px; }
  #cartao { position: absolute; inset: 0; background: radial-gradient(circle at 30% 20%, #1e3a8a, #0f172a 70%);
            color: #f8fafc; display: none; flex-direction: column; justify-content: center; padding: 0 120px; z-index: 5; }
  #cartao h1 { font-size: 44px; margin: 0 0 18px; } #cartao p { font-size: 22px; color: #cbd5e1; margin: 6px 0; }
  #cartao .destaque { color: #facc15; font-weight: 700; } #cartao code { color: #facc15; }
</style></head><body>
<div id="legenda"><div id="numero">▶</div><div><div id="titulo"></div><div id="texto"></div></div></div>
<div id="grade">
  <div class="painel" id="p1"><div class="titulo"><i></i><i></i><i></i>Terminal 1 <span>· Aplicação 1: servidor do Estoque</span></div><div class="term"></div></div>
  <div class="painel" id="p2"><div class="titulo"><i></i><i></i><i></i>Terminal 2 <span>· Aplicação 2: servidor de Pedidos</span></div><div class="term"></div></div>
  <div class="painel" id="p3"><div class="titulo"><i></i><i></i><i></i>Terminal 3 <span>· CLI do Estoque (usuário)</span></div><div class="term"></div></div>
  <div class="painel" id="p4"><div class="titulo"><i></i><i></i><i></i>Terminal 4 <span>· CLI de Pedidos (usuário)</span></div><div class="term"></div></div>
</div>
<div id="cartao"></div>
<script>
  const terminais = {}, ajustes = {}, conexoes = {};
  for (const id of ["p1", "p2", "p3", "p4"]) {
    const term = new Terminal({ fontFamily: '"DejaVu Sans Mono", monospace', fontSize: id < "p3" ? 12.5 : 14,
      lineHeight: 1.12, cursorBlink: true, scrollback: 5000,
      theme: { background: "#0b1020", foreground: "#e2e8f0", cursor: "#facc15" } });
    const ajuste = new FitAddon.FitAddon();
    term.loadAddon(ajuste);
    term.open(document.querySelector(`#${id} .term`));
    const ws = new WebSocket("ws://127.0.0.1:__PORTA__/" + id);
    ws.onmessage = e => term.write(e.data);
    term.onData(d => ws.readyState === 1 && ws.send(d));
    ws.onopen = () => { ajuste.fit(); ws.send(`\\x00resize:${term.cols}x${term.rows}`); };
    terminais[id] = term; ajustes[id] = ajuste; conexoes[id] = ws;
  }
  function reajustar() {
    for (const id in terminais) {
      if (document.getElementById(id).classList.contains("oculto")) continue;
      ajustes[id].fit();
      conexoes[id].send(`\\x00resize:${terminais[id].cols}x${terminais[id].rows}`);
    }
  }
  function focar(id) {
    document.querySelectorAll(".painel").forEach(p => p.classList.toggle("ativo", p.id === id));
    terminais[id].focus();
  }
  function maximizar(id) {
    document.querySelectorAll(".painel").forEach(p => p.classList.toggle("oculto", id && p.id !== id));
    document.getElementById("grade").classList.toggle("maximizado", !!id);
    setTimeout(reajustar, 50);
  }
  function textoDe(id) {
    const b = terminais[id].buffer.active, linhas = [];
    for (let i = 0; i < b.length; i++) linhas.push(b.getLine(i).translateToString(true));
    return linhas.join("\\n");
  }
  function linhaAtual(id) {
    const b = terminais[id].buffer.active;
    return b.getLine(b.baseY + b.cursorY).translateToString(true);
  }
  function legenda(numero, titulo, texto) {
    document.getElementById("numero").textContent = numero;
    document.getElementById("titulo").textContent = titulo;
    document.getElementById("texto").textContent = texto || "";
  }
  function cartao(conteudo) {
    const c = document.getElementById("cartao");
    c.innerHTML = conteudo; c.style.display = conteudo ? "flex" : "none";
  }
</script></body></html>"""


class ServidorEstatico:
    """Servidor HTTP simples para o palco e os arquivos do xterm.js."""

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
# Roteiro do vídeo
# ---------------------------------------------------------------------------


def demonstrar_terminal(evidencias: Path, gravar_video: bool, destino_video: Path | None = None) -> dict[str, Path]:
    """Executa o roteiro nos terminais reais. Retorna as capturas geradas (nome -> arquivo)."""
    from playwright.sync_api import sync_playwright

    for porta in (PORTA_ESTOQUE, PORTA_PEDIDOS):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", porta)) == 0:
                raise SystemExit(f"A porta {porta} já está em uso; encerre o processo que a ocupa.")

    capturas_dir = evidencias / "capturas"
    capturas_dir.mkdir(parents=True, exist_ok=True)
    capturas: dict[str, Path] = {}
    ritmo = 1.0 if gravar_video else 0.2
    atraso = 38 if gravar_video else 2

    terminais = ServidorDeTerminais()
    pasta_palco = Path(tempfile.mkdtemp(prefix="palco_"))
    (pasta_palco / "index.html").write_text(
        PALCO.replace("__ALT__", str(ALTURA_LEGENDA)).replace("__PORTA__", str(terminais.porta)), encoding="utf-8")
    for arquivo in ("xterm.js", "xterm.css", "addon-fit.js"):
        shutil.copy(VENDOR / arquivo, pasta_palco / arquivo)
    servidor = ServidorEstatico(pasta_palco)
    pasta_video = Path(tempfile.mkdtemp(prefix="video_"))

    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch()
            opcoes = {"viewport": {"width": LARGURA, "height": ALTURA}, "device_scale_factor": 2}
            if gravar_video:
                opcoes.update(record_video_dir=str(pasta_video), record_video_size={"width": LARGURA, "height": ALTURA})
            contexto = navegador.new_context(**opcoes)
            pagina = contexto.new_page()
            pagina.goto(f"{servidor.url}/index.html")
            for painel in ("p1", "p2", "p3", "p4"):
                pagina.wait_for_function("id => textoDe(id).includes('aluno@projeto')", arg=painel, timeout=15000)

            def esperar(segundos: float):
                pagina.wait_for_timeout(int(segundos * 1000 * ritmo))

            def legenda(numero, titulo, texto=""):
                pagina.evaluate("([n, t, x]) => legenda(n, t, x)", [str(numero), titulo, texto])

            def aguardar(painel: str, trecho: str, ocorrencias: int = 1, tempo: float = 60):
                pagina.wait_for_function(
                    "([id, t, n]) => textoDe(id).split(t).length - 1 >= n", arg=[painel, trecho, ocorrencias],
                    timeout=tempo * 1000)

            def contar(painel: str, trecho: str) -> int:
                return pagina.evaluate("([id, t]) => textoDe(id).split(t).length - 1", [painel, trecho])

            def digitar(painel: str, texto: str, pausa: float = 0.35):
                pagina.evaluate("id => focar(id)", painel)
                pagina.keyboard.type(texto, delay=atraso)
                esperar(pausa)
                pagina.keyboard.press("Enter")

            def responder(painel: str, *respostas: str):
                """Responde às perguntas da CLI, esperando cada prompt aparecer antes de digitar."""
                for resposta in respostas:
                    pagina.wait_for_function("id => linhaAtual(id).trimEnd().endsWith(':')", arg=painel,
                                             timeout=30000)
                    digitar(painel, resposta, 0.2)
                    esperar(0.25)

            def opcao(painel: str, numero: str, *respostas: str):
                antes = contar(painel, "Opção:")
                digitar(painel, numero)
                responder(painel, *respostas)
                aguardar(painel, "Opção:", antes + 1)

            def capturar(nome: str):
                arquivo = capturas_dir / f"{nome}.png"
                pagina.screenshot(path=str(arquivo), clip={"x": 0, "y": ALTURA_LEGENDA, "width": LARGURA,
                                                           "height": ALTURA - ALTURA_LEGENDA})
                capturas[nome] = arquivo

            # Abertura --------------------------------------------------------------
            pagina.evaluate("""cartao(`<p class="destaque">Trabalho Parcial · Teste e Requisitos de Software</p>
                <h1>Serviço de Estoque + Serviço de Pedidos</h1>
                <p>Duas aplicações back-end (APIs REST em Python/Flask) operadas pelo terminal.</p>
                <p>Terminais 1 e 2: os servidores · Terminais 3 e 4: as interfaces de linha de comando (CLI)</p>`)""")
            esperar(5)
            pagina.evaluate("cartao('')")

            # 1-2. Servidores -----------------------------------------------------------
            legenda(1, "Terminal 1: subindo a Aplicação 1 (Serviço de Estoque)",
                    "python -m estoque_service → API REST na porta 5001")
            digitar("p1", "python -m estoque_service")
            aguardar("p1", "Running on")
            esperar(2)
            legenda(2, "Terminal 2: subindo a Aplicação 2 (Serviço de Pedidos)",
                    "python -m pedidos_service → API REST na porta 5002, que chama o Estoque em http://127.0.0.1:5001")
            digitar("p2", "python -m pedidos_service")
            aguardar("p2", "Running on")
            esperar(2)

            # 3. Cadastro pela CLI do Estoque ----------------------------------------------
            legenda(3, "Terminal 3: CLI do Estoque, cadastro de produtos",
                    "Cada opção do menu faz uma chamada HTTP; o log do Terminal 1 mostra POST /api/produtos → 201")
            digitar("p3", "python -m estoque_service.cli")
            aguardar("p3", "Opção:")
            esperar(1)
            for produto in PRODUTOS:
                opcao("p3", "2", produto["sku"], produto["nome"], produto["preco"].replace(".", ","),
                      str(produto["quantidade"]), str(produto["estoque_minimo"]))
                esperar(0.6)
            opcao("p3", "1")
            esperar(2.5)
            capturar("01_produtos_cadastrados")

            # 4. Catálogo pela CLI de Pedidos --------------------------------------------------
            legenda(4, "Terminal 4: CLI de Pedidos, o catálogo vem do Estoque",
                    "GET /api/catalogo no Pedidos (Terminal 2) gera GET /api/produtos no Estoque (Terminal 1)")
            digitar("p4", "python -m pedidos_service.cli")
            aguardar("p4", "Opção:")
            esperar(1)
            opcao("p4", "1")
            esperar(3)

            # 5. Pedido com 5% ---------------------------------------------------------------
            legenda(5, "Pedido com desconto de 5% (subtotal R$ 620,00 ≥ R$ 500,00)",
                    "O Pedidos reserva os itens no Estoque: veja POST /api/estoque/baixas no Terminal 1")
            opcao("p4", "2", "Maria Souza", "TEC-001", "2", "MOU-001", "1", "")
            esperar(3)
            legenda(5, "O saldo foi baixado no Estoque",
                    "Terminal 3, opção 1: Teclado 10 → 8 e Mouse 5 → 4")
            opcao("p3", "1")
            esperar(3)
            capturar("02_pedido_5_por_cento_e_baixa")

            # 6. Saldo insuficiente --------------------------------------------------------------
            legenda(6, "Regra de negócio: saldo insuficiente → pedido recusado (HTTP 409)",
                    "5 monitores pedidos, apenas 2 em estoque: nada é baixado e nenhum pedido é criado")
            opcao("p4", "2", "Carlos Lima", "MON-001", "5", "")
            esperar(3.5)
            capturar("03_pedido_recusado_409")

            # 7. Pedido com 10% e reposição -------------------------------------------------------
            legenda(7, "Pedido de R$ 1.200,00 recebe 10% de desconto",
                    "E o Monitor chega ao estoque mínimo: a opção 4 do Estoque mostra o alerta REPOR")
            opcao("p4", "2", "Carlos Lima", "MON-001", "1", "")
            esperar(2)
            opcao("p3", "4")
            esperar(3)
            capturar("04_pedido_10_por_cento_e_reposicao")

            # 8. Cancelamento ------------------------------------------------------------------
            legenda(8, "Cancelamento: os itens do pedido #1 voltam para o Estoque",
                    "POST /api/pedidos/1/cancelamento → POST /api/estoque/devolucoes (Teclado 8 → 10, Mouse 4 → 5)")
            opcao("p4", "4", "1")
            esperar(1.5)
            opcao("p3", "1")
            esperar(3)
            capturar("05_cancelamento_devolve_estoque")

            # 9. Queda do Estoque ----------------------------------------------------------------
            legenda(9, "Resiliência: o servidor do Estoque é desligado (Ctrl+C no Terminal 1)",
                    "O Pedidos continua no ar, informa a indisponibilidade e recusa pedidos com HTTP 503")
            pagina.evaluate("id => focar(id)", "p1")
            esperar(0.8)
            pagina.keyboard.press("Control+C")
            aguardar("p1", "aluno@projeto", 2)
            esperar(1)
            opcao("p4", "5")
            esperar(1.5)
            opcao("p4", "2", "Ana Costa", "MOU-001", "1", "")
            esperar(3.5)
            capturar("06_estoque_fora_do_ar_503")

            # 10-11. Testes ---------------------------------------------------------------------
            legenda(10, "Testes unitários com cobertura (pytest + pytest-cov)",
                    "Meta da atividade: pelo menos 90% de cobertura; o comando falha se a meta não for atingida")
            digitar("p3", "0")
            aguardar("p3", "Até logo!")
            pagina.evaluate("maximizar('p3')")
            esperar(0.8)
            digitar("p3", "clear")
            esperar(0.3)
            digitar("p3", "pytest tests/unit --cov --cov-report=term-missing --cov-fail-under=90 -q")
            aguardar("p3", "Required test coverage", tempo=120)
            aguardar("p3", "passed in", tempo=60)
            esperar(6)
            capturar("07_testes_unitarios_terminal")

            legenda(11, "Testes de integração entre as duas aplicações",
                    "Cada teste sobe o Estoque e o Pedidos em processos separados e verifica a comunicação HTTP real")
            digitar("p3", "clear")
            esperar(0.3)
            digitar("p3", "pytest tests/integration -v")
            aguardar("p3", "passed in", tempo=180)
            esperar(7)
            capturar("08_testes_integracao_terminal")

            # Encerramento -----------------------------------------------------------------------
            resumo = json.loads((evidencias / "resumo.json").read_text(encoding="utf-8"))
            pagina.evaluate("c => cartao(c)", f"""<p class="destaque">Resultado</p>
                <h1>{resumo['unitarios']['aprovados']} testes unitários · {resumo['integracao']['aprovados']} testes de integração</h1>
                <p>Todos passando · cobertura dos testes unitários:
                <span class="destaque">{resumo['cobertura']['total']}%</span> (meta: 90%)</p>
                <p>Documentação, objetivo de cada teste e evidências no relatório PDF.</p>""")
            esperar(5)

            video = pagina.video
            contexto.close()
            navegador.close()
            if gravar_video and video and destino_video:
                converter_para_mp4(Path(video.path()), destino_video)
    finally:
        terminais.encerrar()
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
