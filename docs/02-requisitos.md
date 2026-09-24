# Especificação de requisitos

Os requisitos foram levantados antes da implementação e cada um recebeu um identificador único. Esses identificadores aparecem no campo **Requisitos** de cada caso de teste e na **matriz de rastreabilidade**, o que permite verificar que todo requisito é coberto por pelo menos um teste.

Convenção: **RF** = requisito funcional, **RN** = regra de negócio, **RNF** = requisito não funcional. O sufixo **E** indica o Serviço de Estoque e **P** o Serviço de Pedidos.

## Aplicação 1: Serviço de Estoque

### Requisitos funcionais

| ID | Descrição |
|---|---|
| RF-E01 | Cadastrar produto com SKU, nome, preço, quantidade inicial e estoque mínimo. |
| RF-E02 | Listar os produtos e consultar um produto pelo SKU. |
| RF-E03 | Registrar entrada (reposição) de mercadoria em um produto. |
| RF-E04 | Baixar (reservar) itens em lote, informando nome e preço vigente de cada item. |
| RF-E05 | Devolver itens ao estoque (estorno de pedido cancelado). |
| RF-E06 | Listar os produtos que precisam de reposição. |
| RF-E07 | Oferecer uma interface de linha de comando (menu no terminal) para cadastrar, listar, registrar entradas e consultar a reposição, exibindo os erros da API ao usuário. |

### Regras de negócio

| ID | Descrição |
|---|---|
| RN-E01 | O SKU é obrigatório, único, tem de 3 a 20 caracteres (A–Z, 0–9 e hífen, sem começar com hífen) e é normalizado para maiúsculas. |
| RN-E02 | O nome é obrigatório e tem no máximo 100 caracteres. |
| RN-E03 | O preço deve ser numérico, maior que zero e no máximo R$ 1.000.000,00, arredondado para 2 casas (half-up). |
| RN-E04 | Quantidades por operação são inteiras entre 1 e 10.000. O saldo nunca fica negativo e a capacidade máxima por produto é 100.000 unidades. |
| RN-E05 | Um produto precisa de reposição quando o saldo é menor ou igual ao estoque mínimo. |
| RN-E06 | Baixas e devoluções em lote são atômicas (tudo ou nada), aceitam até 50 itens e somam SKUs repetidos. |

## Aplicação 2: Serviço de Pedidos

### Requisitos funcionais

| ID | Descrição |
|---|---|
| RF-P01 | Exibir o catálogo de produtos, obtido do Serviço de Estoque. |
| RF-P02 | Criar pedido informando cliente e itens (SKU e quantidade). |
| RF-P03 | Listar os pedidos e consultar um pedido pelo número. |
| RF-P04 | Cancelar pedido, devolvendo os itens ao Serviço de Estoque. |
| RF-P05 | Informar a saúde do serviço e a disponibilidade do Serviço de Estoque. |
| RF-P06 | Oferecer uma interface de linha de comando (menu no terminal) para ver o catálogo, criar, listar e cancelar pedidos e consultar a situação dos serviços. |

### Regras de negócio

| ID | Descrição |
|---|---|
| RN-P01 | O cliente é obrigatório (3 a 80 caracteres). O pedido tem de 1 a 20 produtos distintos, com quantidade inteira de 1 a 100 por produto. Itens com o mesmo SKU são agrupados. |
| RN-P02 | O preço unitário é sempre o informado pelo Serviço de Estoque (fonte da verdade), nunca o enviado pelo cliente. |
| RN-P03 | Desconto progressivo sobre o subtotal: 0% abaixo de R$ 500,00, 5% de R$ 500,00 a R$ 999,99 e 10% a partir de R$ 1.000,00, arredondado para 2 casas. |
| RN-P04 | O pedido só é confirmado se o estoque reservar todos os itens. Se houver falta de saldo ou produto inexistente, nenhum pedido é registrado. |
| RN-P05 | Somente pedidos CONFIRMADOS podem ser cancelados. Os itens são devolvidos ao estoque antes da mudança de status, e se o estoque estiver indisponível o pedido permanece CONFIRMADO. |
| RN-P06 | Falhas de comunicação com o estoque (conexão recusada, timeout, erro 5xx) resultam em HTTP 503, e respostas fora do contrato resultam em HTTP 502. |

## Requisitos não funcionais (ambas as aplicações)

| ID | Descrição |
|---|---|
| RNF01 | As APIs seguem o estilo REST com JSON. Erros usam o formato padronizado `{"erro", "codigo"}` e códigos HTTP adequados. |
| RNF02 | Os testes unitários devem cobrir pelo menos 90% do código (linhas e ramos), verificado automaticamente. |
| RNF03 | Chamadas do Pedidos ao Estoque têm tempo limite configurável (padrão de 3 segundos). |
| RNF04 | Operações simultâneas não podem deixar o estoque negativo nem devolver itens em duplicidade (thread-safety). |
| RNF05 | Portas, endereços e a URL do estoque são configuráveis por variáveis de ambiente. |
