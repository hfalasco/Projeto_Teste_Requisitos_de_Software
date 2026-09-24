"""Testes de integração entre a Aplicação 1 (Estoque) e a Aplicação 2 (Pedidos).

Cada teste exercita o sistema pela API pública dos serviços, que rodam em
processos separados e se comunicam por HTTP real (ver conftest.py).
"""

import os
import socket
import subprocess
import sys
import threading
import time

import pytest
import requests

from tests.integration.conftest import RAIZ_DO_PROJETO

pytestmark = pytest.mark.integracao

TIMEOUT = 10


def saldo(estoque, sku):
    return requests.get(f"{estoque.url}/api/produtos/{sku}", timeout=TIMEOUT).json()["quantidade"]


def criar_pedido(pedidos, itens, cliente="Cliente Integração"):
    return requests.post(f"{pedidos.url}/api/pedidos", json={"cliente": cliente, "itens": itens},
                         timeout=TIMEOUT)


class TestComunicacaoEntreServicos:
    def test_pedidos_reconhece_estoque_online(self, estoque, pedidos):
        """Objetivo: Verificar que os dois serviços sobem em processos distintos e que o health check do Pedidos confirma a comunicação com o Estoque.
        Técnica: Teste de integração (smoke test entre serviços)
        Requisitos: RF-P05, RNF05
        """
        assert requests.get(f"{estoque.url}/health", timeout=TIMEOUT).json()["status"] == "ok"
        saude = requests.get(f"{pedidos.url}/health", timeout=TIMEOUT).json()
        assert saude["dependencias"] == {"estoque": "ok"}

    def test_catalogo_do_pedidos_reflete_produtos_do_estoque(self, estoque, pedidos, cadastrar_produto):
        """Objetivo: Verificar que um produto cadastrado no Estoque aparece imediatamente no catálogo do Pedidos, com preço e saldo.
        Técnica: Teste de integração (consistência de dados entre serviços)
        Requisitos: RF-P01, RF-E01
        """
        sku = cadastrar_produto(preco="49.90", quantidade=7)
        catalogo = requests.get(f"{pedidos.url}/api/catalogo", timeout=TIMEOUT).json()
        produto = next(p for p in catalogo if p["sku"] == sku)
        assert (produto["preco"], produto["quantidade"]) == ("49.90", 7)


class TestCriacaoDePedido:
    def test_pedido_confirmado_baixa_saldo_no_estoque(self, estoque, pedidos, cadastrar_produto):
        """Objetivo: Verificar que um pedido confirmado no Pedidos reduz o saldo correspondente no Estoque.
        Técnica: Teste de integração (fluxo principal / caminho feliz)
        Requisitos: RF-P02, RF-E04
        """
        sku_a, sku_b = cadastrar_produto(quantidade=10), cadastrar_produto(quantidade=5)
        resposta = criar_pedido(pedidos, [{"sku": sku_a, "quantidade": 3}, {"sku": sku_b, "quantidade": 5}])
        assert resposta.status_code == 201
        assert resposta.json()["status"] == "CONFIRMADO"
        assert (saldo(estoque, sku_a), saldo(estoque, sku_b)) == (7, 0)

    def test_preco_do_pedido_vem_do_estoque(self, estoque, pedidos, cadastrar_produto):
        """Objetivo: Garantir que o preço unitário usado no pedido é o do Estoque, ignorando um preço enviado pelo cliente.
        Técnica: Teste de integração (fonte da verdade entre serviços)
        Requisitos: RN-P02
        """
        sku = cadastrar_produto(preco="80.00")
        resposta = criar_pedido(pedidos, [{"sku": sku, "quantidade": 1, "preco": "0.01"}])
        item = resposta.json()["itens"][0]
        assert (item["preco_unitario"], resposta.json()["total"]) == ("80.00", "80.00")

    @pytest.mark.parametrize("preco, quantidade, percentual, total", [
        ("499.99", 1, 0, "499.99"),
        ("250.00", 2, 5, "475.00"),
        ("1000.00", 1, 10, "900.00"),
    ])
    def test_desconto_progressivo_com_precos_reais_do_estoque(self, estoque, pedidos, cadastrar_produto,
                                                              preco, quantidade, percentual, total):
        """Objetivo: Verificar o desconto de 0%, 5% e 10% nas fronteiras das faixas usando preços cadastrados no Estoque.
        Técnica: Teste de integração com análise de valor limite
        Requisitos: RN-P03, RN-P02
        """
        sku = cadastrar_produto(preco=preco)
        corpo = criar_pedido(pedidos, [{"sku": sku, "quantidade": quantidade}]).json()
        assert (corpo["percentual_desconto"], corpo["total"]) == (percentual, total)

    def test_estoque_insuficiente_recusa_pedido_sem_baixa_parcial(self, estoque, pedidos, cadastrar_produto):
        """Objetivo: Garantir que, se um dos itens não tem saldo, o pedido é recusado (409) e nenhum item é baixado no Estoque.
        Técnica: Teste de integração (atomicidade entre serviços) com valor limite (saldo+1)
        Requisitos: RN-P04, RN-E06
        """
        sku_ok, sku_sem_saldo = cadastrar_produto(quantidade=10), cadastrar_produto(quantidade=2)
        resposta = criar_pedido(pedidos, [{"sku": sku_ok, "quantidade": 4}, {"sku": sku_sem_saldo, "quantidade": 3}])
        assert resposta.status_code == 409
        assert resposta.json()["codigo"] == "ESTOQUE_INSUFICIENTE"
        assert (saldo(estoque, sku_ok), saldo(estoque, sku_sem_saldo)) == (10, 2)

    def test_produto_inexistente_retorna_422_sem_alterar_estoque(self, estoque, pedidos, cadastrar_produto, novo_sku):
        """Objetivo: Verificar que um pedido com SKU que não existe no Estoque retorna 422 e não altera os demais saldos.
        Técnica: Teste de integração (propagação de erro entre serviços)
        Requisitos: RN-P04, RNF01
        """
        sku = cadastrar_produto(quantidade=10)
        resposta = criar_pedido(pedidos, [{"sku": sku, "quantidade": 1}, {"sku": novo_sku("NX"), "quantidade": 1}])
        assert resposta.status_code == 422
        assert resposta.json()["codigo"] == "PRODUTO_INEXISTENTE"
        assert saldo(estoque, sku) == 10

    def test_pedido_invalido_nao_altera_estoque(self, estoque, pedidos, cadastrar_produto):
        """Objetivo: Garantir que um pedido rejeitado na validação do Pedidos (quantidade 101) não gera nenhuma baixa no Estoque.
        Técnica: Teste de integração com valor limite (máximo+1)
        Requisitos: RN-P01
        """
        sku = cadastrar_produto(quantidade=200)
        resposta = criar_pedido(pedidos, [{"sku": sku, "quantidade": 101}])
        assert resposta.status_code == 400
        assert saldo(estoque, sku) == 200

    def test_entrada_no_estoque_libera_pedido_antes_recusado(self, estoque, pedidos, cadastrar_produto):
        """Objetivo: Verificar que, após registrar entrada no Estoque, um pedido antes recusado por falta de saldo passa a ser aceito.
        Técnica: Teste de integração (cenário de ponta a ponta)
        Requisitos: RF-E03, RF-P02, RN-P04
        """
        sku = cadastrar_produto(quantidade=1)
        assert criar_pedido(pedidos, [{"sku": sku, "quantidade": 3}]).status_code == 409
        requests.post(f"{estoque.url}/api/produtos/{sku}/entradas", json={"quantidade": 2}, timeout=TIMEOUT)
        assert criar_pedido(pedidos, [{"sku": sku, "quantidade": 3}]).status_code == 201
        assert saldo(estoque, sku) == 0

    def test_pedido_que_atinge_minimo_gera_alerta_de_reposicao(self, estoque, pedidos, cadastrar_produto):
        """Objetivo: Verificar que um pedido que leva o saldo ao estoque mínimo faz o produto aparecer na lista de reposição do Estoque.
        Técnica: Teste de integração com valor limite (saldo = mínimo)
        Requisitos: RN-E05, RF-E06
        """
        sku = cadastrar_produto(quantidade=5, estoque_minimo=2)

        def skus_para_reposicao():
            resposta = requests.get(f"{estoque.url}/api/produtos/reposicao", timeout=TIMEOUT)
            return [p["sku"] for p in resposta.json()]

        assert sku not in skus_para_reposicao()
        criar_pedido(pedidos, [{"sku": sku, "quantidade": 3}])
        assert sku in skus_para_reposicao()


class TestCancelamento:
    def test_cancelamento_devolve_itens_ao_estoque(self, estoque, pedidos, cadastrar_produto):
        """Objetivo: Verificar que cancelar um pedido no Pedidos devolve as quantidades ao Estoque.
        Técnica: Teste de integração (fluxo de compensação)
        Requisitos: RF-P04, RF-E05
        """
        sku = cadastrar_produto(quantidade=10)
        id_pedido = criar_pedido(pedidos, [{"sku": sku, "quantidade": 6}]).json()["id"]
        assert saldo(estoque, sku) == 4
        resposta = requests.post(f"{pedidos.url}/api/pedidos/{id_pedido}/cancelamento", timeout=TIMEOUT)
        assert resposta.json()["status"] == "CANCELADO"
        assert saldo(estoque, sku) == 10

    def test_cancelamento_duplicado_nao_devolve_em_dobro(self, estoque, pedidos, cadastrar_produto):
        """Objetivo: Garantir que cancelar o mesmo pedido duas vezes retorna 409 e o Estoque recebe a devolução só uma vez.
        Técnica: Teste de integração (transição de estado inválida)
        Requisitos: RN-P05
        """
        sku = cadastrar_produto(quantidade=10)
        id_pedido = criar_pedido(pedidos, [{"sku": sku, "quantidade": 6}]).json()["id"]
        url = f"{pedidos.url}/api/pedidos/{id_pedido}/cancelamento"
        assert requests.post(url, timeout=TIMEOUT).status_code == 200
        assert requests.post(url, timeout=TIMEOUT).status_code == 409
        assert saldo(estoque, sku) == 10


class TestConcorrencia:
    def test_pedidos_simultaneos_nao_vendem_alem_do_saldo(self, estoque, pedidos, cadastrar_produto):
        """Objetivo: Verificar que 25 pedidos simultâneos de 1 unidade sobre saldo 10 resultam em exatamente 10 confirmados e 15 recusados.
        Técnica: Teste de integração de concorrência (condição de corrida)
        Requisitos: RNF04, RN-P04
        """
        sku = cadastrar_produto(quantidade=10)
        status, barreira = [], threading.Barrier(25)

        def comprar():
            barreira.wait()
            status.append(criar_pedido(pedidos, [{"sku": sku, "quantidade": 1}]).status_code)

        threads = [threading.Thread(target=comprar) for _ in range(25)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert (status.count(201), status.count(409)) == (10, 15)
        assert saldo(estoque, sku) == 0

    def test_cancelamentos_simultaneos_devolvem_uma_unica_vez(self, estoque, pedidos, cadastrar_produto):
        """Objetivo: Garantir que 10 cancelamentos simultâneos do mesmo pedido resultam em 1 sucesso e devolução única ao Estoque.
        Técnica: Teste de integração de concorrência (condição de corrida)
        Requisitos: RNF04, RN-P05
        """
        sku = cadastrar_produto(quantidade=10)
        id_pedido = criar_pedido(pedidos, [{"sku": sku, "quantidade": 4}]).json()["id"]
        status, barreira = [], threading.Barrier(10)

        def cancelar():
            barreira.wait()
            status.append(requests.post(f"{pedidos.url}/api/pedidos/{id_pedido}/cancelamento",
                                        timeout=TIMEOUT).status_code)

        threads = [threading.Thread(target=cancelar) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert (status.count(200), status.count(409)) == (1, 9)
        assert saldo(estoque, sku) == 10


class TestFalhasDeComunicacao:
    def test_estoque_fora_do_ar_retorna_503(self, iniciar_servico):
        """Objetivo: Verificar que, sem o Estoque no ar, o Pedidos informa a indisponibilidade no health check e responde 503 ao catálogo e à criação de pedidos.
        Técnica: Teste de integração com injeção de falha (serviço dependente inacessível)
        Requisitos: RN-P06, RF-P05
        """
        porta_fechada = socket.socket()
        porta_fechada.bind(("127.0.0.1", 0))
        url_sem_servico = f"http://127.0.0.1:{porta_fechada.getsockname()[1]}"
        porta_fechada.close()
        pedidos = iniciar_servico("pedidos_service", "PEDIDOS_PORTA", {"ESTOQUE_URL": url_sem_servico})

        assert requests.get(f"{pedidos.url}/health", timeout=TIMEOUT).json()["dependencias"] == {
            "estoque": "indisponivel"}
        assert requests.get(f"{pedidos.url}/api/catalogo", timeout=TIMEOUT).status_code == 503
        resposta = criar_pedido(pedidos, [{"sku": "ABC-123", "quantidade": 1}])
        assert (resposta.status_code, resposta.json()["codigo"]) == (503, "ESTOQUE_INDISPONIVEL")
        assert requests.get(f"{pedidos.url}/api/pedidos", timeout=TIMEOUT).json() == []

    def test_estoque_que_nao_responde_gera_timeout_e_503(self, iniciar_servico):
        """Objetivo: Garantir que um Estoque que aceita a conexão mas não responde é abandonado após o timeout configurado (0,5 s), retornando 503.
        Técnica: Teste de integração com injeção de falha (latência / timeout)
        Requisitos: RNF03, RN-P06
        """
        with socket.socket() as servidor_mudo:
            servidor_mudo.bind(("127.0.0.1", 0))
            servidor_mudo.listen(50)
            url_mudo = f"http://127.0.0.1:{servidor_mudo.getsockname()[1]}"
            pedidos = iniciar_servico("pedidos_service", "PEDIDOS_PORTA",
                                      {"ESTOQUE_URL": url_mudo, "ESTOQUE_TIMEOUT": "0.5"})
            inicio = time.monotonic()
            resposta = criar_pedido(pedidos, [{"sku": "ABC-123", "quantidade": 1}])
            duracao = time.monotonic() - inicio
        assert resposta.status_code == 503
        assert "tempo limite" in resposta.json()["erro"]
        assert duracao < 3

    def test_queda_do_estoque_mantem_pedido_confirmado(self, iniciar_servico, cadastrar_produto):
        """Objetivo: Verificar que, se o Estoque cair depois da venda, o cancelamento responde 503 e o pedido continua CONFIRMADO (sem perda de consistência).
        Técnica: Teste de integração com injeção de falha (queda do processo do Estoque)
        Requisitos: RN-P05, RN-P06
        """
        estoque = iniciar_servico("estoque_service", "ESTOQUE_PORTA")
        pedidos = iniciar_servico("pedidos_service", "PEDIDOS_PORTA", {"ESTOQUE_URL": estoque.url})
        sku = cadastrar_produto(quantidade=5, url=estoque.url)
        id_pedido = criar_pedido(pedidos, [{"sku": sku, "quantidade": 2}]).json()["id"]

        estoque.parar()  # derruba o processo do Serviço de Estoque

        resposta = requests.post(f"{pedidos.url}/api/pedidos/{id_pedido}/cancelamento", timeout=TIMEOUT)
        assert resposta.status_code == 503
        pedido = requests.get(f"{pedidos.url}/api/pedidos/{id_pedido}", timeout=TIMEOUT).json()
        assert pedido["status"] == "CONFIRMADO"


def usar_cli(modulo: str, variavel_url: str, url: str, *linhas: str) -> str:
    """Executa a CLI como um usuário faria no terminal, digitando as linhas informadas."""
    processo = subprocess.run([sys.executable, "-m", modulo], input="\n".join(linhas) + "\n", text=True,
                              capture_output=True, timeout=30, cwd=RAIZ_DO_PROJETO,
                              env={**os.environ, variavel_url: url, "PYTHONIOENCODING": "utf-8"},
                              encoding="utf-8")
    assert processo.returncode == 0, processo.stderr
    return processo.stdout


class TestInterfaceDeLinhaDeComando:
    def test_fluxo_completo_pelas_duas_clis(self, estoque, pedidos, novo_sku):
        """Objetivo: Verificar o uso real pelo terminal: cadastro na CLI do Estoque, pedido na CLI do Pedidos e saldo atualizado visto novamente na CLI do Estoque.
        Técnica: Teste de integração ponta a ponta (CLI → API → outra API)
        Requisitos: RF-E07, RF-P06, RF-P02, RF-E04
        """
        sku = novo_sku("CLI")
        saida = usar_cli("estoque_service.cli", "ESTOQUE_URL", estoque.url,
                         "2", sku, "Teclado CLI", "250,00", "10", "3", "0")
        assert f"OK: produto {sku} cadastrado com saldo 10." in saida

        saida = usar_cli("pedidos_service.cli", "PEDIDOS_URL", pedidos.url,
                         "2", "Maria Souza", sku, "2", "", "0")
        assert "OK: pedido confirmado!" in saida
        assert "Subtotal R$ 500,00 | Desconto 5% (-R$ 25,00) | TOTAL R$ 475,00" in saida

        saida = usar_cli("estoque_service.cli", "ESTOQUE_URL", estoque.url, "1", "0")
        linha = next(linha for linha in saida.splitlines() if linha.startswith(sku))
        assert linha.split()[-3:] == ["8", "3", "OK"]

    def test_cli_de_pedidos_mostra_recusa_do_estoque(self, estoque, pedidos, cadastrar_produto):
        """Objetivo: Verificar que a recusa por falta de saldo, gerada no Estoque, chega ao usuário da CLI de Pedidos como HTTP 409.
        Técnica: Teste de integração com valor limite (saldo+1) propagado entre serviços
        Requisitos: RF-P06, RN-P04
        """
        sku = cadastrar_produto(quantidade=2)
        saida = usar_cli("pedidos_service.cli", "PEDIDOS_URL", pedidos.url, "2", "Carlos Lima", sku, "3", "", "0")
        assert f"ERRO (HTTP 409): Estoque insuficiente para '{sku}': disponível 2, solicitado 3." in saida
        assert saldo(estoque, sku) == 2
