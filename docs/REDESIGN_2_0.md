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
- A marca composta usada no login e no cabeçalho é o arquivo já presente em `app/static/img/brand-lockup.png`.
- A troca de tema guarda apenas a preferência de interface em `localStorage`; não toca dados de produto.

## Verificação

- `node --check app/static/js/ui.js` e `node --check app/static/js/digitalizacao.js`.
- `.venv\Scripts\python.exe -X utf8 -B -m pytest -q`: 92 testes aprovados, 3 avisos preexistentes.
- Captura local da tela de login em 390 e 360 CSS px; em 360 px, `scrollWidth=innerWidth=360`, sem rolagem horizontal. A ferramenta `scripts/visual_smoke.cjs` captura uma URL local com Chrome DevTools Protocol, sem transmitir credenciais.

Ainda é necessária uma revisão visual autenticada e humana das telas com dados reais, em especial o fluxo completo da Digitalização, antes de considerar a experiência final aprovada. Não houve publicação, push ou alteração de banco nesta etapa.
