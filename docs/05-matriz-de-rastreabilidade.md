# Matriz de rastreabilidade (requisito × teste)

> Documento gerado automaticamente por `scripts/gerar_documentacao_testes.py`. Os IDs referem-se ao catálogo em `04-casos-de-teste.md`.

**30 de 30 requisitos** possuem verificação automatizada.

| Requisito | Descrição | Testes unitários | Testes de integração |
|---|---|---|---|
| **RF-E01** | Cadastrar produto com SKU, nome, preço, quantidade inicial e estoque mínimo. | UT-E18, UT-E19, UT-E20, UT-E30, UT-E40, UT-E58, UT-E76 | IT02 |
| **RF-E02** | Listar os produtos e consultar um produto pelo SKU. | UT-E28, UT-E30, UT-E32, UT-E33, UT-E40, UT-E42, UT-E62, UT-E63, UT-E76 | n/a |
| **RF-E03** | Registrar entrada (reposição) de mercadoria em um produto. | UT-E22, UT-E44, UT-E45, UT-E46, UT-E64, UT-E65, UT-E79, UT-E80 | IT09 |
| **RF-E04** | Baixar (reservar) itens em lote, informando nome e preço vigente de cada item. | UT-E25, UT-E26, UT-E47, UT-E48, UT-E67, UT-E69, UT-P28 | IT03, IT18 |
| **RF-E05** | Devolver itens ao estoque (estorno de pedido cancelado). | UT-E53, UT-E54, UT-E55, UT-E70, UT-P29, UT-P50 | IT11 |
| **RF-E06** | Listar os produtos que precisam de reposição. | UT-E56, UT-E66, UT-E81 | IT10 |
| **RF-E07** | Oferecer uma interface de linha de comando (menu no terminal) para cadastrar, listar, registrar entradas e consultar a reposição, exibindo os erros da API ao usuário. | UT-E76, UT-E77, UT-E78, UT-E79, UT-E80, UT-E81, UT-E82, UT-E83, UT-E84, UT-E85 | IT18 |
| **RN-E01** | O SKU é obrigatório, único, tem de 3 a 20 caracteres (A–Z, 0–9 e hífen, sem começar com hífen) e é normalizado para maiúsculas. | UT-E01, UT-E02, UT-E03, UT-E04, UT-E18, UT-E31, UT-E41, UT-E42, UT-E43, UT-E60 | n/a |
| **RN-E02** | O nome é obrigatório e tem no máximo 100 caracteres. | UT-E05, UT-E06, UT-E07, UT-E08, UT-E18 | n/a |
| **RN-E03** | O preço deve ser numérico, maior que zero e no máximo R$ 1.000.000,00, arredondado para 2 casas (half-up). | UT-E09, UT-E10, UT-E11, UT-E12, UT-E13, UT-E18, UT-E59, UT-E77 | n/a |
| **RN-E04** | Quantidades por operação são inteiras entre 1 e 10.000. O saldo nunca fica negativo e a capacidade máxima por produto é 100.000 unidades. | UT-E14, UT-E15, UT-E16, UT-E17, UT-E23, UT-E24, UT-E26, UT-E27, UT-E39, UT-E45, UT-E55, UT-E65, UT-E68 | n/a |
| **RN-E05** | Um produto precisa de reposição quando o saldo é menor ou igual ao estoque mínimo. | UT-E21, UT-E48, UT-E56, UT-E66, UT-E81 | IT10 |
| **RN-E06** | Baixas e devoluções em lote são atômicas (tudo ou nada), aceitam até 50 itens e somam SKUs repetidos. | UT-E34, UT-E35, UT-E36, UT-E37, UT-E38, UT-E39, UT-E49, UT-E50, UT-E51, UT-E54 | IT06 |
| **RF-P01** | Exibir o catálogo de produtos, obtido do Serviço de Estoque. | UT-P27, UT-P37, UT-P49, UT-P55, UT-P56, UT-P71, UT-P72 | IT02 |
| **RF-P02** | Criar pedido informando cliente e itens (SKU e quantidade). | UT-P15, UT-P16, UT-P17, UT-P21, UT-P42, UT-P57, UT-P74 | IT03, IT09, IT18 |
| **RF-P03** | Listar os pedidos e consultar um pedido pelo número. | UT-P21, UT-P25, UT-P40, UT-P41, UT-P47, UT-P48, UT-P62, UT-P63, UT-P77 | n/a |
| **RF-P04** | Cancelar pedido, devolvendo os itens ao Serviço de Estoque. | UT-P22, UT-P23, UT-P29, UT-P50, UT-P53, UT-P64, UT-P78, UT-P79 | IT11 |
| **RF-P05** | Informar a saúde do serviço e a disponibilidade do Serviço de Estoque. | UT-P30, UT-P39, UT-P49, UT-P54, UT-P80 | IT01, IT15 |
| **RF-P06** | Oferecer uma interface de linha de comando (menu no terminal) para ver o catálogo, criar, listar e cancelar pedidos e consultar a situação dos serviços. | UT-P71, UT-P72, UT-P73, UT-P74, UT-P75, UT-P76, UT-P77, UT-P78, UT-P79, UT-P80, UT-P81, UT-P82, UT-P83, UT-P84 | IT18, IT19 |
| **RN-P01** | O cliente é obrigatório (3 a 80 caracteres). O pedido tem de 1 a 20 produtos distintos, com quantidade inteira de 1 a 100 por produto. Itens com o mesmo SKU são agrupados. | UT-P02, UT-P03, UT-P04, UT-P05, UT-P06, UT-P07, UT-P08, UT-P09, UT-P10, UT-P11, UT-P12, UT-P13, UT-P14, UT-P15, UT-P43, UT-P44, UT-P58, UT-P75 | IT08 |
| **RN-P02** | O preço unitário é sempre o informado pelo Serviço de Estoque (fonte da verdade), nunca o enviado pelo cliente. | UT-E47, UT-E67, UT-P28, UT-P38, UT-P42 | IT04, IT05 |
| **RN-P03** | Desconto progressivo sobre o subtotal: 0% abaixo de R$ 500,00, 5% de R$ 500,00 a R$ 999,99 e 10% a partir de R$ 1.000,00, arredondado para 2 casas. | UT-P01, UT-P18, UT-P19, UT-P20, UT-P57, UT-P74, UT-P77 | IT05 |
| **RN-P04** | O pedido só é confirmado se o estoque reservar todos os itens. Se houver falta de saldo ou produto inexistente, nenhum pedido é registrado. | UT-E49, UT-P31, UT-P43, UT-P45, UT-P59, UT-P76 | IT06, IT07, IT09, IT13, IT19 |
| **RN-P05** | Somente pedidos CONFIRMADOS podem ser cancelados. Os itens são devolvidos ao estoque antes da mudança de status, e se o estoque estiver indisponível o pedido permanece CONFIRMADO. | UT-P22, UT-P24, UT-P50, UT-P51, UT-P52, UT-P64, UT-P78 | IT12, IT14, IT17 |
| **RN-P06** | Falhas de comunicação com o estoque (conexão recusada, timeout, erro 5xx) resultam em HTTP 503, e respostas fora do contrato resultam em HTTP 502. | UT-P32, UT-P33, UT-P34, UT-P35, UT-P36, UT-P37, UT-P38, UT-P46, UT-P52, UT-P56, UT-P60, UT-P61, UT-P73 | IT15, IT16, IT17 |
| **RNF01** | As APIs seguem o estilo REST com JSON. Erros usam o formato padronizado `{"erro", "codigo"}` e códigos HTTP adequados. | UT-E20, UT-E28, UT-E29, UT-E38, UT-E57, UT-E58, UT-E59, UT-E61, UT-E63, UT-E68, UT-E71, UT-E72, UT-E73, UT-P14, UT-P16, UT-P17, UT-P21, UT-P25, UT-P31, UT-P57, UT-P58, UT-P59, UT-P63, UT-P65, UT-P66 | IT07 |
| **RNF02** | Os testes unitários devem cobrir pelo menos 90% do código (linhas e ramos), verificado automaticamente. | Verificado pela execução de `pytest --cov --cov-fail-under=90` (seção de evidências). | n/a |
| **RNF03** | Chamadas do Pedidos ao Estoque têm tempo limite configurável (padrão de 3 segundos). | UT-P26, UT-P27, UT-P34, UT-P67, UT-P68 | IT16 |
| **RNF04** | Operações simultâneas não podem deixar o estoque negativo nem devolver itens em duplicidade (thread-safety). | UT-E52 | IT13, IT14 |
| **RNF05** | Portas, endereços e a URL do estoque são configuráveis por variáveis de ambiente. | UT-E74, UT-E75, UT-E85, UT-P26, UT-P67, UT-P68, UT-P69, UT-P70, UT-P84 | IT01 |
