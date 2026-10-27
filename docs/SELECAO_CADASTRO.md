# Seleção em massa no cadastro — 23/10/2026

Checkout PRM-remocao-cargos, branch fix/remocao-autorizacao-cargos. Alteração de interface apenas: store-registration.js e store_registration.html. Nenhuma regra do backend ou worker alterada.

Checkbox no cabeçalho seleciona itens em review (aprovados ou não), excluindo blockers, needs_refresh, disabled e requires_manual_review. Segundo clique limpa a seleção. Estado parcial usa indeterminate; contador acompanha seleção individual e polling. Transição de pronto para inelegível limpa a seleção anterior, sem selecionar itens que acabaram de ficar prontos. Seleção individual de erros continua disponível para refazer prévia/restaurar, não sendo incluída automaticamente.

Seleção interna do Dry Run e seleção da linha usam o mesmo estado, evitando aprovação oculta após desmarcar. Aprovar usa somente selecionados ainda não aprovados; enviar usa somente selecionados aprovados. Nenhuma dessas ações é disparada pelo checkbox.

Testes JavaScript: 4 passaram, cobrindo seleção/limpeza, exclusões, contador, seleção individual e subconjuntos de aprovação/envio. Build Docker aprovado. Testes de regressão usam MockTransport e container sem rede.

Deploy: overlay compose.selecao-cadastro.yaml após os overlays existentes, alterando somente api para prm:cadastro-selecao-20261023. Workers, banco e volumes preservados. Recarregar navegador com Ctrl+F5. Rollback: recriar apenas API sem esse último overlay.
