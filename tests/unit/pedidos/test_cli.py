"""Testes unitários da interface de linha de comando do Serviço de Pedidos."""

import builtins
import runpy
import sys
from unittest.mock import Mock

import pytest
import requests

from pedidos_service.app import criar_app
from pedidos_service.cli import TerminalPedidos, moeda
from pedidos_service.servico import ServicoPedidos
from tests.unit.pedidos.dubles import EstoqueFalso
from tests.unit.terminal_falso import SessaoFlask, roteiro

PEDIDO_MARIA = ["2", "Maria Souza", "TEC-001", "2", "MOU-001", "1", ""]


@pytest.fixture
def estoque():
    return EstoqueFalso()


def executar(estoque, *linhas, sessao=None):
    """Roda o menu com as linhas digitadas e devolve o texto exibido."""
    sessao = sessao or SessaoFlask(criar_app(ServicoPedidos(estoque)))
    saida = []
    TerminalPedidos("http://pedidos.teste", entrada=roteiro(*linhas), saida=saida.append, sessao=sessao).executar()
    return "\n".join(saida)


class TestCatalogo:
    def test_catalogo_mostra_produtos_do_estoque(self, estoque):
        """Objetivo: Verificar que a opção de catálogo lista os produtos vindos do Estoque com preço e quantidade disponível.
        Técnica: Teste de caixa-preta da CLI com fakes (Flask em memória + estoque falso)
        Requisitos: RF-P06, RF-P01
        """
        texto = executar(estoque, "1", "0")
        assert "MON-001    Monitor                    R$ 1.200,00           2" in texto
        assert texto.endswith("Até logo!")

    def test_catalogo_vazio(self, estoque):
        """Objetivo: Verificar a mensagem exibida quando o Estoque não tem produtos cadastrados.
        Técnica: Análise de valor limite (lista vazia)
        Requisitos: RF-P06, RF-P01
        """
        estoque.produtos.clear()
        assert "O catálogo está vazio." in executar(estoque, "1", "0")

    def test_catalogo_com_estoque_fora_do_ar(self, estoque):
        """Objetivo: Verificar que a indisponibilidade do Estoque chega ao usuário como erro HTTP 503 com mensagem clara.
        Técnica: Injeção de falha com dublê
        Requisitos: RF-P06, RN-P06
        """
        estoque.disponivel = False
        texto = executar(estoque, "1", "0")
        assert "ERRO (HTTP 503): Não foi possível conectar ao Serviço de Estoque." in texto


class TestPedidos:
    def test_criar_pedido_mostra_itens_desconto_e_total(self, estoque):
        """Objetivo: Verificar que o pedido digitado item a item é confirmado e exibido com itens, desconto de 5% e total.
        Técnica: Teste de caixa-preta da CLI (fluxo principal)
        Requisitos: RF-P06, RF-P02, RN-P03
        """
        texto = executar(estoque, *PEDIDO_MARIA, "0")
        assert "OK: pedido confirmado!" in texto
        assert "Pedido #1 - Maria Souza - CONFIRMADO" in texto
        assert "   TEC-001    Teclado                    2 x    R$ 250,00 =     R$ 500,00" in texto
        assert "Subtotal R$ 620,00 | Desconto 5% (-R$ 31,00) | TOTAL R$ 589,00" in texto

    def test_quantidade_invalida_ignora_item(self, estoque):
        """Objetivo: Verificar que um item com quantidade não numérica é ignorado e que um pedido sem itens é recusado pela API (400).
        Técnica: Partição de equivalência (classes inválidas)
        Requisitos: RF-P06, RN-P01
        """
        texto = executar(estoque, "2", "Maria Souza", "TEC-001", "dois", "", "0")
        assert "ERRO: informe um número inteiro; item ignorado." in texto
        assert "ERRO (HTTP 400): O pedido deve conter pelo menos um item." in texto

    def test_pedido_sem_saldo_e_recusado(self, estoque):
        """Objetivo: Verificar que um pedido acima do saldo é recusado com HTTP 409 e o saldo do estoque não muda.
        Técnica: Análise de valor limite (saldo+1) via CLI
        Requisitos: RF-P06, RN-P04
        """
        texto = executar(estoque, "2", "Carlos Lima", "MON-001", "3", "", "0")
        assert "ERRO (HTTP 409)" in texto
        assert estoque.saldo("MON-001") == 2

    def test_listar_pedidos(self, estoque):
        """Objetivo: Verificar a listagem vazia e, depois de um pedido abaixo de R$ 500,00, a indicação "sem desconto".
        Técnica: Análise de valor limite (lista vazia) e partição (faixa sem desconto)
        Requisitos: RF-P06, RF-P03, RN-P03
        """
        texto = executar(estoque, "3", "2", "Ana Costa", "MOU-001", "1", "", "3", "0")
        assert "Nenhum pedido registrado." in texto
        assert "Subtotal R$ 120,00 | Desconto sem desconto | TOTAL R$ 120,00" in texto

    def test_cancelar_pedido(self, estoque):
        """Objetivo: Verificar o cancelamento pelo menu, a devolução ao estoque e a recusa de um segundo cancelamento (409).
        Técnica: Teste de transição de estados via CLI
        Requisitos: RF-P06, RF-P04, RN-P05
        """
        texto = executar(estoque, *PEDIDO_MARIA, "4", "1", "4", "1", "0")
        assert "OK: pedido #1 cancelado; itens devolvidos ao Estoque." in texto
        assert "ERRO (HTTP 409): O pedido 1 não pode ser cancelado (status CANCELADO)." in texto
        assert estoque.saldo("TEC-001") == 10

    @pytest.mark.parametrize("numero, mensagem", [("abc", "ERRO: informe o número do pedido."),
                                                  ("99", "ERRO (HTTP 404): Pedido 99 não encontrado.")])
    def test_cancelar_numero_invalido_ou_inexistente(self, estoque, numero, mensagem):
        """Objetivo: Verificar as mensagens para número de pedido não numérico e para pedido inexistente.
        Técnica: Partição de equivalência (classes inválidas)
        Requisitos: RF-P06, RF-P04
        """
        assert mensagem in executar(estoque, "4", numero, "0")


class TestSituacaoEFalhas:
    @pytest.mark.parametrize("disponivel, texto_estoque", [(True, "ok"), (False, "indisponivel")])
    def test_situacao_dos_servicos(self, estoque, disponivel, texto_estoque):
        """Objetivo: Verificar que a opção de situação mostra o estado do Pedidos e do Estoque (online/offline).
        Técnica: Partição de equivalência (estoque disponível/indisponível)
        Requisitos: RF-P06, RF-P05
        """
        estoque.disponivel = disponivel
        texto = executar(estoque, "5", "0")
        assert "Serviço de Pedidos: ok" in texto
        assert f"Serviço de Estoque: {texto_estoque}" in texto

    def test_opcao_invalida_e_fim_de_entrada(self, estoque):
        """Objetivo: Verificar que uma opção inexistente é avisada e que o fim da entrada encerra o programa.
        Técnica: Partição de equivalência (opção inválida) e valor limite (fim da entrada)
        Requisitos: RF-P06
        """
        texto = executar(estoque, "7")
        assert "Opção inválida." in texto
        assert texto.endswith("Até logo!")

    def test_servidor_de_pedidos_fora_do_ar(self, estoque):
        """Objetivo: Verificar que, sem o servidor de pedidos, cada opção informa a falha de conexão sem encerrar a CLI.
        Técnica: Injeção de falha com dublê (mock que lança ConnectionError)
        Requisitos: RF-P06
        """
        sessao = Mock(spec=requests.Session)
        sessao.request.side_effect = requests.ConnectionError()
        texto = executar(estoque, "1", "2", "Ana", "", "3", "4", "1", "5", "0", sessao=sessao)
        assert texto.count("ERRO: não foi possível conectar ao Serviço de Pedidos em http://pedidos.teste.") == 5


class TestFormatacaoEInicializacao:
    def test_moeda_no_formato_brasileiro(self):
        """Objetivo: Verificar a formatação de valores em reais usada nos resumos de pedido.
        Técnica: Partição de equivalência
        Requisitos: RF-P06
        """
        assert (moeda("1080"), moeda("31.5")) == ("R$ 1.080,00", "R$ 31,50")

    def test_execucao_como_modulo_usa_url_do_ambiente(self, monkeypatch, capsys):
        """Objetivo: Verificar que "python -m pedidos_service.cli" usa a URL de PEDIDOS_URL e encerra ao fim da entrada.
        Técnica: Configuração por ambiente e dublê de input
        Requisitos: RF-P06, RNF05
        """
        monkeypatch.setenv("PEDIDOS_URL", "http://outro-host:9002")
        monkeypatch.setattr(builtins, "input", roteiro())
        monkeypatch.delitem(sys.modules, "pedidos_service.cli", raising=False)
        runpy.run_module("pedidos_service.cli", run_name="__main__")
        assert "SERVIÇO DE PEDIDOS  (http://outro-host:9002)" in capsys.readouterr().out
