# Central operacional PRM — entrega visual de 15/10/2026

## Conceito e escopo

Interface industrial-tech original: base azul-grafite, superfícies neutras, acentos verde/teal, indicadores compactos e hierarquia por contexto. Portwell, Choice e SAG aparecem primeiro. As logos continuam usando a imagem original, sem recriação, recoloração ou inversão no tema escuro.

Esta entrega altera somente apresentação e testes/documentação. Não muda endpoints, autenticação, permissões, modelos, pipeline, regras de comparação, integrações, arquivos de produtos ou banco. Trabalha na pasta oficial `C:\Users\PW\Documents\PRM`; alterações anteriores não relacionadas foram preservadas.

## Dashboard

- Cabeçalho, navegação lateral e ícones SVG próprios; recolhimento, menu mobile, tema persistido e horário de Brasília.
- Contexto por empresa, busca real no catálogo, cards de empresas selecionáveis e densidade persistida no navegador.
- Indicadores calculados do snapshot publicado: registros analisados, portfólio próprio visível, produtos com atributos e família pendente. O portfólio próprio é explicitamente um indicador do grupo; os outros três acompanham o contexto escolhido.
- Três visões: **Panorama**, **Atributos & compatibilidade** e **Qualidade & origem**. `/comparador` abre atributos; `/importacoes` abre qualidade; `/` abre panorama. Abas operáveis por teclado com setas, Home/End e relações ARIA.
- Gráfico de composição ECO/Dimensional com links para os registros em famílias próprias, sem família própria e com classificação pendente. O gráfico mede registros em famílias, não número de famílias nem equivalência integral de produtos.
- Análises atuais de SO, memória, armazenamento, USB e procedência permanecem acessíveis nas abas; nenhum dado histórico reaparece.
- Ações rápidas e atalhos para etapas da Digitalização. Última fotografia identificada por data e run ID. Catálogo público diferenciado das contagens analíticas que incluem itens internos.
- SAG não tem catálogo neste snapshot: mostra estado vazio explícito, não números fictícios. Busca com contexto SAG continua geral; a mensagem esclarece que a empresa participa apenas do workspace de digitalização nesta fotografia.
- Claude/WooCommerce ficam **Sem telemetria**. Não há endpoint de resumo operacional/saúde; não foram inventadas filas, atividades recentes ou estados online. Os links de catálogo continuam respeitando sua visão pública.

Fonte preservada: `74f1f8e8300912677e8f49f4`, **89.693 registros / 500.016 observações**, 89.651 registros públicos e 3.741 próprios públicos. Não houve recálculo ou publicação de um novo snapshot.

## Digitalização e temas

- Mesmo padrão visual do dashboard, etapas fixas durante rolagem em telas largas, contexto do produto recolhível, campos organizados, área de upload ampliada e espaço maior para a prévia do PDF.
- Preservados os IDs, scripts de análise/aprovação/geração, recuperação de execuções, ações de imagens, pacote e cadastro. A seleção de empresa mantém a cor contextual e a logo real.
- Claro: superfícies brancas e fundo cinza frio, bordas discretas e contraste de conteúdo. Escuro: superfícies grafite em níveis, acentos claros e estados selecionados distintos; regras genéricas antigas de botões não sobrescrevem as novas abas/cards.
- Logos, imagens e documentos não são invertidos. O card SAG usa proporção própria para não cortar a marca. Campos longos de procedência quebram linha; tabelas largas têm rolagem interna.
- Adaptação até 320 px, indicadores em duas colunas em tablet/mobile, navegação recolhida no celular e redução de movimento conforme preferência do sistema.

## Arquivos desta entrega

Alterados:

- `app/templates/base.html`: inclusão versionada do CSS novo, preservando a ordem dos estilos existentes.
- `app/templates/shell.html`: estrutura compartilhada e integração do novo dashboard/JS.
- `app/templates/digitalizacao.html`: título, controle de contexto e identificador do painel; hooks existentes preservados.
- `docs/STATUS.md` e `CHANGELOG.md`: registro da entrega.

Criados:

- `app/templates/_operations_dashboard.html`: central operacional com dados reais.
- `app/templates/_workspace_icons.html`: ícones SVG reutilizáveis, sem dependência externa.
- `app/static/css/workspace.css`: tokens, componentes, temas, layout e responsividade.
- `app/static/js/workspace.js`: filtros locais, abas, densidade, relógio e painel de contexto; não escreve na API.
- `tests/test_operations_workspace.py`: cinco casos parametrizados/independentes de regressão de apresentação.
- `scripts/workspace_preview.py`: prévia somente leitura em loopback, sem montar a API ou consultar banco.
- `scripts/workspace_visual_smoke.cjs`: testes Chrome DevTools sem dependências npm; capturas e relatório local.
- `docs/WORKSPACE_VISUAL.md`: este documento.

`_current_dashboard.html` permanece no repositório, mas não é mais incluído nas rotas atuais. Outros arquivos sujos no Git antes desta tarefa pertencem às implementações anteriores e não devem ser descartados.

## Validação e reprodução

- **178 testes pytest aprovados**, três avisos preexistentes (Starlette/AnyIO e estilo ausente em duas planilhas).
- Smoke somente leitura no `prm_mvp`: **14 rotas HTML/API aprovadas**, reconciliação de contagens/atributos/filtros e isolamento entre organizações.
- Chrome headless: **20 combinações** de dashboard/Digitalização × claro/escuro × larguras 1440, 1280, 768, 390 e 320 px. **296 verificações**, sem exceções JavaScript não tratadas e sem transbordamento horizontal da página nos estados testados, inclusive tabela de qualidade aberta.
- Exercitados filtros/cards, pesquisa contextual, concorrente, abas por clique/teclado, densidade, menu mobile, seleção das três empresas, campos/contexto ao vivo e recolhimento do painel. Galeria testada em desktop/mobile nos dois temas: adicionar duas imagens locais, trocar principal, girar, ampliar e remover. Nenhum upload à API.
- Alternância claro/escuro e persistência após recarregamento também conferidas no navegador. Capturas de desktop, tablet, mobile, mapa competitivo e galeria inspecionadas visualmente.
- Evidências locais em `data/exports/visual-workspace-20261015/`, incluindo `report.json`; ignoradas pelo Git. São prévias, não prints de uma sessão autenticada do usuário. Imagens da galeria são fixtures locais, não produtos publicados.

No diretório oficial:

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m scripts.smoke_refined_catalogs --target production --run-id 74f1f8e8300912677e8f49f4
.venv/Scripts/python.exe -m scripts.workspace_preview --manifest data/analysis/staging/refined/74f1f8e8300912677e8f49f4/run_manifest.json
```

Com a prévia em `127.0.0.1:8871` e um Chrome de teste isolado, headless, com depuração em `127.0.0.1:9225`:

```powershell
node scripts/workspace_visual_smoke.cjs data/exports/visual-workspace-20261015
node scripts/visual_smoke.cjs http://127.0.0.1:8871/ 1440 1000 data/exports/visual-workspace-20261015/theme.png light verify-toggle
```

Nunca exponha a prévia/porta de depuração publicamente; não é um servidor de produção. O script de prévia não possui POST nem rotas da API e não substitui o servidor autenticado.

## Limites e próximos passos

Não foram executadas chamadas pagas ao Claude, publicação WooCommerce ou geração/aprovação real de novos PDFs/pacotes nesta validação visual. Esses fluxos mantêm backend/scripts e testes existentes; ainda é recomendável uma homologação operacional autenticada com um produto de teste autorizado.

Evoluções úteis: endpoint autenticado de resumo das execuções por organização, telemetria de integrações, fila/atividade real, verificação de acessibilidade mais ampla e testes em navegadores/dispositivos físicos adicionais. Não mostrar esses dados como existentes antes de implementá-los.

Não houve push/deploy remoto nem reinício do servidor PRM existente. Para ver a atualização, recarregar a página; se o processo mantém templates em cache ou atende outra pasta, reiniciá-lo apontando para o diretório oficial. CSS/JS novos têm versão `20261015-1`.
