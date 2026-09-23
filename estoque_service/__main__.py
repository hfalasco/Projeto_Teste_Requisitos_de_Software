"""Permite executar o serviço com: python -m estoque_service"""

import os

from estoque_service.app import criar_app


def main() -> None:
    host = os.environ.get("ESTOQUE_HOST", "127.0.0.1")
    porta = int(os.environ.get("ESTOQUE_PORTA", "5001"))
    criar_app().run(host=host, port=porta, threaded=True)


if __name__ == "__main__":
    main()
