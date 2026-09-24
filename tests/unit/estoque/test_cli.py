"""Testes unitários da interface de linha de comando do Serviço de Estoque."""

import builtins
import runpy
import sys
from unittest.mock import Mock

import pytest
import requests

import estoque_service.cli as cli
from estoque_service.app import criar_app
from estoque_service.cli import TerminalEstoque, moeda
from tests.unit.terminal_falso import SessaoFlask, roteiro

TECLADO = ["2", "tec-001", "Teclado mecânico", "250,00", "10", "3"]


def executar(*linhas, sessao=None):
    """Roda o menu com as linhas digitadas e devolve (texto exibido, sessão)."""
    sessao = sessao or SessaoFlask(criar_app())
    saida = []
    TerminalEstoque("http://estoque.teste", entrada=roteiro(*linhas), saida=saida.append, sessao=sessao).executar()
    return "\n".join(saida), sessao


class TestMenu:
    def test_cadastrar_e_listar_produto(self):
        """Objetivo: Verificar que o usuário cadastra um produto pelo menu (preço com vírgula) e o vê na listagem formatada.
        Técnica: Teste de caixa-preta da CLI com fake HTTP (Flask em memória)
        Requisitos: RF-E07, RF-E01, RF-E02
        """
        texto, _ = executar(*TECLADO, "1", "0")
        assert "OK: produto TEC-001 cadastrado com saldo 10." in texto
        assert "TEC-001    Teclado mecânico             R$ 250,00     10       3  OK" in texto
        assert texto.endswith("Até logo!")

    def test_erro_da_api_e_exibido_ao_usuario(self):
        """Objetivo: Verificar que um erro de validação da API (preço negativo) é mostrado com o status HTTP e a mensagem.
        Técnica: Partição de equivalência (classe inválida) via CLI
        Requisitos: RF-E07, RN-E03
        """
        texto, _ = executar("2", "ABC", "Produto", "-5", "", "", "0")
        assert "ERRO (HTTP 400): O preço deve ser maior que zero." in texto

    def test_quantidade_nao_numerica_nao_chama_a_api(self):
        """Objetivo: Garantir que uma quantidade não numérica é recusada pela CLI antes de qualquer chamada HTTP.
        Técnica: Partição de equivalência (tipo inválido) e dublê espião
        Requisitos: RF-E07
        """
        texto, sessao = executar("2", "ABC", "Produto", "10", "dez", "0")
        assert "ERRO: informe um número inteiro." in texto
        assert sessao.chamadas == []

    def test_registrar_entrada(self):
        """Objetivo: Verificar a entrada de mercadoria pelo menu e a mensagem com o novo saldo.
        Técnica: Teste de caixa-preta da CLI
        Requisitos: RF-E07, RF-E03
        """
        texto, _ = executar(*TECLADO, "3", "TEC-001", "5", "0")
        assert "OK: TEC-001 agora tem 15 unidades." in texto

    @pytest.mark.parametrize("sku, quantidade, mensagem", [
        ("TEC-001", "x", "ERRO: informe um número inteiro."),
        ("NAO-EXISTE", "1", "ERRO (HTTP 404): Produto 'NAO-EXISTE' não encontrado."),
    ])
    def test_registrar_entrada_invalida(self, sku, quantidade, mensagem):
        """Objetivo: Verificar as mensagens para quantidade não numérica e para produto inexistente na entrada.
        Técnica: Partição de equivalência (classes inválidas)
        Requisitos: RF-E07, RF-E03
        """
        texto, _ = executar(*TECLADO, "3", sku, quantidade, "0")
        assert mensagem in texto

    def test_reposicao_lista_produtos_no_minimo(self):
        """Objetivo: Verificar que a opção de reposição mostra "Nenhum produto encontrado." e, com saldo no mínimo, a situação REPOR.
        Técnica: Análise de valor limite (saldo = mínimo) via CLI
        Requisitos: RF-E07, RF-E06, RN-E05
        """
        texto, _ = executar(*TECLADO, "4", "2", "MON-001", "Monitor", "1200", "1", "1", "4", "0")
        assert "Nenhum produto encontrado." in texto
        ultima_tabela = texto.rsplit("SITUAÇÃO", 1)[1]
        assert "MON-001    Monitor                    R$ 1.200,00      1       1  REPOR" in ultima_tabela
        assert "TEC-001" not in ultima_tabela

    def test_opcao_invalida_e_fim_de_entrada(self):
        """Objetivo: Verificar que uma opção inexistente é avisada e que o fim da entrada (Ctrl+D/Ctrl+Z) encerra o programa.
        Técnica: Partição de equivalência (opção inválida) e valor limite (fim da entrada)
        Requisitos: RF-E07
        """
        texto, _ = executar("9")
        assert "Opção inválida." in texto
        assert texto.endswith("Até logo!")

    def test_servidor_fora_do_ar(self):
        """Objetivo: Verificar que, sem o servidor do estoque, a CLI informa a falha de conexão em vez de encerrar com erro.
        Técnica: Injeção de falha com dublê (mock que lança ConnectionError)
        Requisitos: RF-E07
        """
        sessao = Mock(spec=requests.Session)
        sessao.request.side_effect = requests.ConnectionError()
        texto, _ = executar("1", "4", "0", sessao=sessao)
        assert texto.count("ERRO: não foi possível conectar") == 2
        assert "ERRO: não foi possível conectar ao Serviço de Estoque em http://estoque.teste." in texto


class TestFormatacaoEInicializacao:
    @pytest.mark.parametrize("valor, esperado", [("0.5", "R$ 0,50"), ("250.00", "R$ 250,00"),
                                                 ("1234567.5", "R$ 1.234.567,50")])
    def test_moeda_no_formato_brasileiro(self, valor, esperado):
        """Objetivo: Verificar a formatação de valores em reais (separador de milhar e vírgula decimal).
        Técnica: Partição de equivalência e valores limite de formatação
        Requisitos: RF-E07
        """
        assert moeda(valor) == esperado

    def test_execucao_como_modulo_usa_url_do_ambiente(self, monkeypatch, capsys):
        """Objetivo: Verificar que "python -m estoque_service.cli" usa a URL de ESTOQUE_URL e encerra ao fim da entrada.
        Técnica: Configuração por ambiente e dublê de input
        Requisitos: RF-E07, RNF05
        """
        monkeypatch.setenv("ESTOQUE_URL", "http://outro-host:9001/")
        monkeypatch.setattr(builtins, "input", roteiro())
        monkeypatch.delitem(sys.modules, "estoque_service.cli", raising=False)
        runpy.run_module("estoque_service.cli", run_name="__main__")
        saida = capsys.readouterr().out
        assert "SERVIÇO DE ESTOQUE  (http://outro-host:9001)" in saida
        assert cli.URL_PADRAO == "http://127.0.0.1:5001"
