# Redesign 2.0 — interface PRM

Em 08/10/2026, a interface recebeu uma nova camada visual em `app/static/css/prm-v2.css`, carregada depois do CSS existente. O objetivo é dar consistência de produto SaaS às áreas já operacionais, sem mudar contratos da API, tabelas ou dados publicados.

## O que mudou

- Identidade neutra PRM com acentos por empresa: Portwell (`#7DC240`), Choice (`#35A9D6`) e SAG (`#005ED3`), baseados nos temas de datasheet locais. As empresas próprias permanecem em destaque; concorrentes seguem em posição secundária.
- Login, navegação lateral, cabeçalho, cards, tabelas, formulários e dashboard foram harmonizados. A navegação compacta e os temas claro/escuro são persistidos localmente no navegador.
- Digitalização ganhou etapas navegáveis, resumo contextual do produto, prévia ampliada de fotos e visualização de PDF por página com zoom. Os controles existentes de análise, revisão, aprovação e geração continuam ligados às rotas anteriores.
- Há ajustes responsivos para desktop, tablet e celular, link para saltar ao conteúdo e respeito à preferência de movimento reduzido.

Os sites [Portwell](https://portwell.com.br/), [Choice](https://www.choicetech.com.br/) e [SAG](https://sag.ind.br/) foram usados como referências institucionais. O acesso direto automatizado a algumas páginas falhou; por isso, o projeto **não afirma** que os tons acima sejam os tons oficiais dos sites. Os acentos são os já definidos nos temas de datasheet do repositório.

## Implementação e preservação

- A nova camada é CSS/HTML/JavaScript local, sem biblioteca visual externa.
- IDs de formulários, chamadas de API, permissões, dados de catálogos e fluxo WooCommerce não foram modificados para o redesign.
- A marca composta usada no login e no cabeçalho é o arquivo já presente em `app/static/brand-lockup.png`.
- A troca de tema guarda apenas a preferência de interface em `localStorage`; não toca dados de produto.

## Verificação

- `node --check app/static/js/ui.js` e `node --check app/static/js/digitalizacao.js`.
- `.venv\Scripts\python.exe -X utf8 -B -m pytest -q`: 92 testes aprovados, 3 avisos preexistentes.
- Captura local da tela de login em 390 e 360 CSS px; em 360 px, `scrollWidth=innerWidth=360`, sem rolagem horizontal. A ferramenta `scripts/visual_smoke.cjs` captura uma URL local com Chrome DevTools Protocol, sem transmitir credenciais.

Ainda é necessária uma revisão visual autenticada e humana das telas com dados reais, em especial o fluxo completo da Digitalização, antes de considerar a experiência final aprovada. Não houve publicação, push ou alteração de banco nesta etapa.

## Refinamento do tema escuro — 09/10/2026

O tema escuro agora tem uma única camada específica, `app/static/css/prm-dark.css`, carregada após os estilos compartilhados. Ela centraliza as cores semânticas de fundo, sidebar, card, superfície elevada, input, borda, texto, ação e estados. As regras escuras antigas de `prm-v2.css` foram removidas para evitar dois conjuntos contraditórios de tokens.

Foram corrigidos sidebar/header, filtros do catálogo, cards, tabelas, campos nativos, botões, mensagens e as superfícies internas da Digitalização (upload, fotos, Claude, revisão, pacote e cadastro). Logos pretas ficam sobre uma pequena superfície branca; imagens de produto e páginas de PDF não recebem filtro nem inversão. Um ajuste compartilhado permite que os botões do cadastro quebrem linha no celular e que as textareas ocupem o painel; ele também melhora o tema claro.

Verificação visual: login real do aplicativo e comparação direta estática; dashboard, catálogo e estados de Digitalização renderizados com **dados sintéticos** por `scripts/dark_visual_preview.py`, sem autenticação, API ou escrita no banco. Capturas locais ignoradas pelo Git cobriram 320, 390, 768, 1024 e 1440 px, temas claro e escuro, upload, revisão, PDF, cadastro, tabela e modal. O alternador foi clicado no navegador: a preferência mudou, ficou no `localStorage` e persistiu após recarga. Pares principais de texto/superfície foram medidos com contraste de 5,72:1 a 16,01:1; isso não substitui uma auditoria WCAG completa de cada estado dinâmico.

Pendente: revisão autenticada com produtos e documentos reais, inclusive estados de erro da API, opções nativas dos sistemas operacionais e combinações de dados longos. Não houve alteração de backend, banco, loja ou publicação.
