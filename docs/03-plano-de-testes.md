# Plano e estratégia de testes

## Objetivo

Demonstrar, com evidências automatizadas, que as duas aplicações atendem aos requisitos especificados:

* individualmente, com **testes unitários** que cobrem pelo menos 90% do código (meta atingida: 100% de linhas e de ramos);
* em conjunto, com **testes de integração** que exercitam a comunicação HTTP real entre o Serviço de Pedidos e o Serviço de Estoque.

## Níveis de teste

| Nível | Pasta | O que é testado | Isolamento | Ferramentas |
|---|---|---|---|---|
| Unitário | `tests/unit/estoque/` | Domínio, repositório, serviço, rotas HTTP e CLI do Estoque | Sem rede: Flask *test client* e objetos em memória | pytest, pytest-cov |
| Unitário | `tests/unit/pedidos/` | Domínio, repositório, serviço, cliente HTTP, rotas e CLI do Pedidos | O Serviço de Estoque é substituído por **dublês de teste** | pytest, unittest.mock, pytest-cov |
| Integração | `tests/integration/` | As duas aplicações rodando juntas (inclusive usadas pelas CLIs, como um usuário no terminal) | Nenhum dublê: cada aplicação roda em **seu próprio processo**, em portas TCP reais | pytest, subprocess, requests |

### Por que os testes de integração usam processos separados

A fixture `ProcessoServico` (`tests/integration/conftest.py`) executa `python -m estoque_service` e `python -m pedidos_service` como processos do sistema operacional, cada um em uma porta livre. O Pedidos recebe a URL do Estoque pela variável `ESTOQUE_URL`, como aconteceria em produção. Com isso os testes validam, além da lógica, a **configuração**, a **serialização JSON**, os **códigos HTTP** e o comportamento diante de **falhas reais de rede**: processo derrubado, porta fechada e servidor que não responde.

## Técnicas de projeto de casos de teste aplicadas

| Técnica | Onde foi aplicada (exemplos) |
|---|---|
| **Partição de equivalência** | Classes válidas/inválidas de SKU, nome, preço, quantidade, cliente e corpo JSON. |
| **Análise de valor limite** | SKU com 2/3/20/21 caracteres. Preço 0,00/0,01/1.000.000,00/1.000.000,01. Quantidade 0/1/100/101 e 0/1/10.000/10.001. Desconto em 499,99/500,00/999,99/1.000,00. Estoque mínimo (saldo = mínimo ± 1). Capacidade máxima + 1. Lote com 50/51 itens e pedido com 20/21 produtos. |
| **Tabela de decisão** | Tradução de cada código de erro do estoque (409, 404, 400, 4xx desconhecido, 5xx) na exceção e no status HTTP do Pedidos. |
| **Transição de estados** | Pedido `CONFIRMADO → CANCELADO` (válida) e `CANCELADO → CANCELADO` (inválida, 409). |
| **Dublês de teste** | *Stub* (`RespostaFalsa`), *Mock* (`unittest.mock.Mock` com verificação de chamadas), *Fake* e *Spy* (`EstoqueFalso`, estoque em memória que registra as chamadas). Nas CLIs, `SessaoFlask` (fake de `requests.Session` que encaminha as chamadas ao app em memória) e `roteiro` (simula o usuário digitando). |
| **Injeção de falhas** | Timeout, conexão recusada, erro 5xx, JSON inválido e contrato violado (unitário). Porta fechada, servidor mudo e queda do processo do Estoque (integração). |
| **Teste de concorrência** | 30 baixas simultâneas (unitário) e 25 pedidos e 10 cancelamentos simultâneos via HTTP (integração), com `threading.Barrier`. |
| **Injeção de dependência** | Relógio, repositório e cliente de estoque injetados no `ServicoPedidos`. Serviço injetado no `criar_app()`. |

Todos os testes seguem o padrão **AAA (Arrange, Act, Assert)** e são **independentes entre si**: cada teste cria seus próprios dados, e nos testes de integração cada teste usa SKUs únicos gerados com `uuid`.

## Documentação dos testes

Cada função de teste possui uma *docstring* padronizada com três campos:

```python
def test_baixa_e_atomica_quando_um_item_nao_tem_saldo(self, servico):
    """Objetivo: Garantir que, se um item do lote não tem saldo, nenhum item é baixado (tudo ou nada).
    Técnica: Teste de transação/atomicidade com valor limite (saldo+1)
    Requisitos: RN-E06, RN-P04
    """
```

O script `scripts/gerar_documentacao_testes.py` lê essas *docstrings* e gera automaticamente o catálogo de casos de teste (`docs/04-casos-de-teste.md`) e a matriz de rastreabilidade (`docs/05-matriz-de-rastreabilidade.md`), com o resultado da última execução. O script **falha** se algum teste não tiver objetivo documentado ou citar um requisito inexistente, o que mantém documentação e código sincronizados.

## Critérios de aceitação

| Critério | Como é verificado |
|---|---|
| 100% dos testes unitários e de integração passando | Saída do pytest e relatórios HTML/JUnit |
| Cobertura dos testes unitários ≥ 90% (linhas + ramos) | `pytest --cov --cov-fail-under=90` (o comando falha se a meta não for atingida) |
| Todo requisito coberto por pelo menos um teste | Matriz de rastreabilidade |

## Ambiente de teste

* Python 3.11 (compatível com 3.10+), Linux ou Windows
* pytest 8.3, pytest-cov 5.0 (coverage.py 7), pytest-html 4.1
* Serviços executados localmente em `127.0.0.1` com portas escolhidas dinamicamente

## Como executar os testes

```bash
pip install -r requirements-dev.txt

# Testes unitários + relatório de cobertura (falha se < 90%)
pytest tests/unit --cov --cov-report=term-missing --cov-report=html --cov-fail-under=90

# Testes de integração (sobem as duas aplicações automaticamente)
pytest tests/integration -v

# Tudo
pytest
```

O relatório HTML de cobertura é gerado em `htmlcov/index.html`.
