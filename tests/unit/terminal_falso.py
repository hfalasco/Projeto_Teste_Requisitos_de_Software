"""Dublês usados nos testes das interfaces de linha de comando (CLI).

* ``SessaoFlask`` é um *fake* de ``requests.Session``: encaminha as chamadas HTTP
  da CLI para o aplicativo Flask em memória (sem rede).
* ``roteiro`` simula o usuário digitando no terminal (substitui ``input``).
"""


class _Resposta:
    def __init__(self, status_code, dados):
        self.status_code = status_code
        self._dados = dados

    def json(self):
        return self._dados


class SessaoFlask:
    def __init__(self, app):
        self._cliente = app.test_client()
        self.chamadas = []

    def request(self, metodo, url, json=None, timeout=None):
        caminho = "/" + url.split("/", 3)[3]
        self.chamadas.append((metodo, caminho))
        resposta = self._cliente.open(caminho, method=metodo, json=json)
        return _Resposta(resposta.status_code, resposta.get_json())


def roteiro(*linhas):
    """Devolve uma função no lugar de ``input``; ao fim das linhas simula Ctrl+D (EOF)."""
    restantes = list(linhas)

    def _entrada(_prompt=""):
        if not restantes:
            raise EOFError
        return restantes.pop(0)

    return _entrada
