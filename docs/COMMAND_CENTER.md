# PRM 4.0 — Industrial Command Center

Dashboard (`/`, também `/comparador` e `/importacoes` com outra aba inicial) e shell compartilhado.

## Arquivos

| Arquivo | Papel |
|---|---|
| `app/templates/_operations_dashboard.html` | Composição: barra operacional, status da base, centro de operações, portfólio, abas Atributos/Qualidade |
| `app/templates/_attribute_analysis.html` | Widgets de SO e interpretação de atributos |
| `app/templates/shell.html`, `_workspace_icons.html` | Sidebar compacta, cabeçalho, Operational Clock, ícones |
| `app/static/css/command-center.css` | Tokens `--cc-*` (claro/escuro), shell e componentes; carregado por último |
| `app/static/js/workspace.js` | Shell em todas as páginas: relógio, contexto da Digitalização, menu |
| `app/static/js/command-center.js` | Somente no dashboard: filtros, gráficos SVG, tabela, feed, atualização |
| `app/services/operations_overview.py`, `app/routers/operations.py` | Leitura dos registros de digitalização (`GET /api/v1/operations/overview`, gestores) |

## Fontes de dados

- **Portfólio**: snapshot refinado publicado (`refined_analysis`, `current_analysis`). Sem histórico.
- **Operações**: `record.json` das execuções em `PRM_PRODUCT_STORAGE_ROOT/_runs/`. Etapas registradas: rascunho (análise técnica + datasheet), aprovação e pacote validado (pasta CIGAM + ZIP). CSV, WooCommerce e falhas **não são persistidos** e aparecem como "sem registro persistido".
- O período filtra execuções pela data de criação. O status filtra tabela, fila, feed, pipeline e gráfico. Os indicadores mostram a distribuição por status. Empresas concorrentes não têm operações.
- O gráfico principal mostra **acumulados no período**, com o valor do dia no tooltip. Acima de 120 dias, agrega por semana.

## Cores

Identidade: Portwell `#7DC240`, Choice `#35A9D6`, SAG `#005ED3` (temas de datasheet). Semântica dos gráficos: azul = grupo/datasheets, laranja = concorrente, verde-água = sobreposição/aprovações, violeta = pacotes, cinza = pendente. Pares validados com o validador da skill `dataviz` nas superfícies `#ffffff` e `#121a23`. O cinza "pendente" é neutro de propósito e sempre acompanha rótulo e tabela.

## Prévia visual

```powershell
.\.venv\Scripts\python.exe -m scripts.workspace_preview --manifest data/analysis/staging/refined/<RUN>/summary.json --port 8873 --operations-root <pasta com _runs>
```

Sem `--operations-root`, usa o armazenamento configurado. A prévia serve só GETs e não usa banco nem sessão.

## Limites

- Logos: arquivos individuais em `app/static/brand/` (ver `scripts/extract_brand_logos.py`).
- Login e catálogo herdam os tokens, mas não foram redesenhados.
- Sem telemetria real de Claude/WooCommerce. Os status exibidos são declarativos.
