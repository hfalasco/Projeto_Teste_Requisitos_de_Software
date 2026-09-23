"""Permite executar o serviço com: python -m pedidos_service"""

import os

from pedidos_service.app import criar_app


def main() -> None:
    host = os.environ.get("PEDIDOS_HOST", "127.0.0.1")
    porta = int(os.environ.get("PEDIDOS_PORTA", "5002"))
    criar_app().run(host=host, port=porta, threaded=True)


if __name__ == "__main__":
    main()
