# Trabalho Parcial: Serviço de Estoque + Serviço de Pedidos

Duas aplicações em **Python/Flask** que se comunicam por **HTTP/JSON**, com **testes unitários (100% de cobertura de linhas e ramos)** e **testes de integração entre as aplicações**.

| | Aplicação 1: Serviço de Estoque | Aplicação 2: Serviço de Pedidos |
|---|---|---|
| Pasta | [`estoque_service/`](estoque_service) | [`pedidos_service/`](pedidos_service) |
| Função | Cadastro de produtos e controle de saldo (entradas, baixas atômicas, devoluções, alerta de reposição) | Vendas: valida o pedido, reserva os itens no Estoque, aplica desconto progressivo e permite cancelar |
| Porta | 5001 | 5002 (chama o Estoque via `ESTOQUE_URL`) |
| Interface | `python -m estoque_service.cli` | `python -m pedidos_service.cli` |

## Entrega

| Item pedido | Arquivo |
|---|---|
| PDF com evidências e documentação | [`entrega/Relatorio_Trabalho_Parcial.pdf`](entrega/Relatorio_Trabalho_Parcial.pdf) |
| Código-fonte (ZIP) | [`entrega/codigo_fonte.zip`](entrega/codigo_fonte.zip) |
| Vídeo da execução funcional | [`entrega/video_execucao.mp4`](entrega/video_execucao.mp4) |
| Evidências brutas (saídas do pytest, JUnit, pytest-html, cobertura HTML, capturas) | [`entrega/evidencias/`](entrega/evidencias) |

## Documentação

1. [O que cada aplicação faz](docs/01-aplicacoes.md): arquitetura, endpoints, regras, configuração
2. [Especificação de requisitos](docs/02-requisitos.md): RF, RN e RNF com identificadores
3. [Plano e estratégia de testes](docs/03-plano-de-testes.md): níveis, técnicas, dublês, critérios
4. [Casos de teste: objetivo de cada teste](docs/04-casos-de-teste.md) *(gerado a partir das docstrings)*
5. [Matriz de rastreabilidade](docs/05-matriz-de-rastreabilidade.md) *(requisito × teste)*

## Resultados

| Suíte | Casos | Resultado |
|---|---|---|
| Testes unitários (`tests/unit`) | 256 | 256 aprovados · **cobertura 100%** (723/723 linhas, 148/148 ramos) |
| Testes de integração (`tests/integration`) | 21 | 21 aprovados (as duas aplicações em processos separados, inclusive via CLI) |

## Como executar

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# Servidores (terminais 1 e 2)
python -m estoque_service            # API em http://127.0.0.1:5001
python -m pedidos_service            # API em http://127.0.0.1:5002

# Interfaces de linha de comando (terminais 3 e 4)
python -m estoque_service.cli
python -m pedidos_service.cli

# Testes unitários + cobertura (falha se < 90%)
pytest tests/unit --cov --cov-report=term-missing --cov-report=html --cov-fail-under=90

# Testes de integração (sobem as duas aplicações automaticamente)
pytest tests/integration -v
```

### Regerar PDF, vídeo, ZIP e evidências

```bash
pip install -r requirements-docs.txt
playwright install chromium        # o vídeo usa terminais bash reais (Linux/macOS/WSL)
python scripts/gerar_entrega.py          # ou --sem-video para ser mais rápido
```

Nomes dos integrantes, disciplina e professor exibidos na capa do PDF ficam em [`docs/metadados.json`](docs/metadados.json).

## Estrutura

```
estoque_service/        Aplicação 1 (app.py, servico.py, dominio.py, repositorio.py, cli.py)
pedidos_service/        Aplicação 2 (app.py, servico.py, dominio.py, repositorio.py, cliente_estoque.py, cli.py)
tests/unit/estoque/     Testes unitários da Aplicação 1
tests/unit/pedidos/     Testes unitários da Aplicação 2 (com dublês do Estoque em dubles.py)
tests/integration/      Testes de integração (as duas aplicações como processos reais)
docs/                   Documentação
scripts/                Geração da documentação dos testes, do PDF, do vídeo e do ZIP
entrega/                Artefatos para entrega
```
