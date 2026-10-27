# PRM

## Docker e colaboração

Ambiente isolado na porta **8001**, preservando o PRM Windows: [guia Docker](docs/DOCKER.md), [resultados da infraestrutura](docs/INFRA_STATUS.md) e [fluxo de Pull Requests Kaue/Arthur](CONTRIBUTING.md). Sem deploy automático ou migração dos dados atuais.

Product Relationship Manager: aplicação interna para centralizar catálogos, comparação de produtos, digitalização/publicação em lojas, reuniões e gestão de fornecedores do grupo SAG. As empresas próprias permanecem em primeiro plano e concorrentes são tratados como origens separadas.

Este repositório contém o código e a documentação da primeira entrega (`0.1.0`). O [marco da entrega](docs/ENTREGA_0_1.md) resume o que funciona e seus limites; o [estado operacional](docs/STATUS.md) registra as verificações mais recentes.

A [nova base refinada](docs/CATALOGOS_REFINADOS.md), publicada em 09/10/2026, reúne os quatro arquivos atuais em snapshots separados do histórico: 89.693 registros e 500.016 observações de atributos. Catálogos abre a nova fotografia, com acesso ao histórico preservado. **Comparação técnica/cobertura dessa nova base ainda não foram homologadas**; os próximos gates estão documentados.

## O que já funciona

- [Níveis de acesso e contas](docs/NIVEIS_DE_ACESSO.md): desenvolvedor e gestor com permissões administrativas equivalentes, vendedor restrito a produtos e reuniões/cards. Criação de contas protegida em Gestão.
- [Fornecedores](docs/FORNECEDORES.md): CRM/Kanban por organização, responsável, ficha, contatos, interações, tarefas, documentos, histórico e enriquecimento opcional por IA com revisão humana.
- [Catálogos por origem](docs/CATALOGOS_ORIGENS.md): importação CSV/XLS/XLSX separando nossa base e concorrência, prévia, mapeamento, auditoria e publicação explícita do snapshot consumido pelo Comparador e pela Visão Geral.

- [Pauta Semanal de Desenvolvimento](docs/PAUTA_SEMANAL.md): pauta automática de sexta com commits, PRs, issues e Planner, situação comprovada (branch, PR, integrado, implantado), IA verificada, edição, aprovação, PDF e histórico.
- [Remoção de arquivos de produtos](docs/REMOCAO_ARQUIVOS.md): desvincula foto principal, galeria e/ou documentos WCDA de produtos existentes por SKU, com Dry Run, aprovação, auditoria e restauração; nunca exclui mídia nem altera dados comerciais.
- [Resolução de imagens em pasta](docs/RESOLUCAO_IMAGENS.md): converte as fotos de uma pasta e subpastas para 1500 × 1500 px com fundo branco, mantendo nomes e formatos, com originais em `Backup-fotos`, retomada e restauração.
- [Digitalização e Publicação em Lote](docs/PUBLICACAO_EM_LOTE.md): ZIP por SKU → datasheets → Dry Run → aprovação → imagens e documentos em produtos existentes, sem baixar/reenviar ZIP. Não gera nomes, descrições, categorias, atributos ou CSV. Lojas atuais bloqueadas sem liberação.
- [Cadastro via API — arquivos](docs/CADASTRO_API_STAGING.md): imagens e documentos `_wcda_arquivos` de produtos já existentes, a partir de ZIPs do PRM por SKU (CSV opcional). Dry Run, aprovação, journal, auditoria e releitura; dados comerciais continuam no fluxo CSV. Escrita nas lojas atuais bloqueada.
- [Documentos `_wcda_arquivos`](docs/WCDA_HOMOLOGACAO.md): estrutura observada nas três lojas, serviço de preparação, Dry Run, preservação de documentos, payload e plano de rollback. Sem escrita real; teste futuro exige autorização específica de loja/SKU.

- [Integrações WooCommerce e WordPress](docs/INTEGRACOES_LOJAS.md): diagnósticos autenticados somente leitura para as três lojas, restritos a gestores/desenvolvedores. Autenticação das seis APIs confirmada em 20/10/2026; escrita e contrato de documentos ainda não homologados. Playwright preservado.

- [Geração de Datasheets em Lote](docs/DATASHEETS_EM_LOTE.md): ZIP por pastas CIGAM/SKU (CSV opcional) ou modo CSV/PDFs anterior, prévia com inventário, fila persistente e exportação de PDFs/análises/fontes por empresa. Acesse `/digitalizacao/lotes`; requer iniciar o worker separado descrito no guia. Sem publicação automática nas lojas.

- Login individual, sessões e páginas protegidas.
- Importação auditável de planilhas XLSX da Eco Automação, Portwell e Choice Tech, com prévia, validação e proteção contra reimportação idêntica.
- Tratamento automático conservador de novos produtos (família, modelo e especificações detectáveis) e enriquecimento opcional com as saídas tratadas do `PRM_Pipeline`, sem perder as fontes originais.
- Dashboard com nossos catálogos em primeiro plano, cobertura do tratamento por empresa, funil de correspondência da concorrente e destaques nominais de preço; catálogo com busca por vários termos, filtros combináveis, origem de cada oferta e 100 produtos por página por padrão.
- Análise automática do catálogo concorrente inteiro contra o portfólio próprio, com sugestões, candidatos, cobertura e posição nominal de preços.
- Comparador com visualização de possíveis lacunas: marcas sem oferta própria identificada e famílias de produtos concorrentes sem candidato, com exemplos e listagem paginada para revisão.
- Retrato adicional de amplitude de famílias Choice + Portwell frente à Eco, gerado dos CSVs normalizados conciliados ao banco; a presença numa família não confirma equivalência de produtos.
- No catálogo, faixa de preço funciona também com “Todas as modalidades”. É possível selecionar de 2 a 8 produtos, inclusive entre páginas, para comparação direta de preços e características, separada da análise automática do concorrente.
- Para testes remotos pontuais da equipe, há uma prévia HTTPS temporária com senha adicional e login individual do PRM; veja [Operação no Windows](docs/OPERACAO_WINDOWS.md#prévia-pública-temporária-para-a-equipe).
- Marcas canônicas com aliases revisáveis; `ELFIN` e `NEW ELFIN SRL` são reconhecidas como a mesma marca, preservando o texto original da fonte.
- API `/api/v1`, migrações Alembic e testes automatizados.

As correspondências são sugestões para revisão humana. A cobertura exibida não representa equivalência comercial confirmada. Preços de modalidades diferentes são comparados apenas nominalmente.

## Executar localmente no Windows

Requisitos: Python 3.14, PostgreSQL e acesso à pasta do projeto. O banco operacional é PostgreSQL; o pgAdmin é apenas uma ferramenta de administração. A aplicação não depende de chave de IA nem de n8n.

No PowerShell, a partir da raiz do repositório:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite **somente o `.env` local** com a URL e a senha do seu banco. Não compartilhe nem publique esse arquivo. Em um ambiente novo, crie o banco e o usuário PostgreSQL antes da migração; em um ambiente existente, confira a URL para reutilizar o banco correto.

```powershell
.\.venv\Scripts\python.exe -m scripts.check_database
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m scripts.create_manager
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`scripts.check_database` confirma a conexão inclusive antes da primeira migração. `scripts.create_manager` é interativo e deve ser executado somente para criar um novo gestor. Abra `http://127.0.0.1:8000` para entrar. A API interativa fica em `http://127.0.0.1:8000/docs`.

Se sua política do PowerShell permitir, há atalhos em `scripts/*.ps1`. Os comandos acima funcionam sem executar arquivos `.ps1`.

## Carregar os catálogos

Os arquivos originais são dados locais e não acompanham o repositório. Coloque em `data/imports/` os arquivos `produtos_ecoautomacao.xlsx`, `produtos-portwell.xlsx` e `produtos-choice.xlsx`. Para cada empresa, faça a prévia antes da publicação:

```powershell
.\.venv\Scripts\python.exe -m scripts.import_catalog --company eco-automacao
.\.venv\Scripts\python.exe -m scripts.import_catalog --company eco-automacao --commit
```

Repita com `--company portwell` e `--company choice-tech`. A publicação nova recalcula as correspondências dos concorrentes. Se precisar executar essa análise separadamente:

```powershell
.\.venv\Scripts\python.exe -m scripts.analyze_catalog_matches --company eco-automacao --commit
```

Sem `--commit`, esses comandos fazem uma prévia e não gravam o lote ou uma nova análise. Detalhes sobre formato, regras e contagens das planilhas estão em [Dados](docs/DADOS.md).

Para aproveitar arquivos já tratados pelo pipeline, mantenha os XLSX originais em `data/imports/` e coloque `Produtos-Choice.xlsx`, `Produtos-Portwell.xlsx` e `Produtos-ECO.xlsx` em `data/imports/treated/`. Após publicar os lotes originais, execute a prévia e a associação por código externo:

```powershell
.\.venv\Scripts\python.exe -m scripts.import_pipeline_enrichment --company choice-tech
.\.venv\Scripts\python.exe -m scripts.import_pipeline_enrichment --company choice-tech --commit --skip-matching
.\.venv\Scripts\python.exe -m scripts.import_pipeline_enrichment --company portwell --commit --skip-matching
.\.venv\Scripts\python.exe -m scripts.import_pipeline_enrichment --company eco-automacao --commit
```

O último comando recalcula a análise; sem `--commit`, a operação é apenas uma prévia. Para qualquer importação futura de dados brutos, o tratamento automático ocorre antes da comparação. Quando houver uma nova saída tratada do pipeline, publique-a com esse mesmo comando para incorporar seus atributos adicionais. O ZIP externo não é executado pela aplicação; veja os limites em [Dados](docs/DADOS.md).

## Verificações

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --test tests/js/*.test.cjs
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m scripts.reconcile_catalogs
```

O último conjunto verificado em 23/09/2026 teve 21 testes aprovados, migração `20260923_0007` e 35.786 ofertas no banco local. Esses números dependem dos catálogos importados e não aparecem em um banco recém-criado.

## Documentação

| Documento | Conteúdo |
|---|---|
| [Primeira entrega](docs/ENTREGA_0_1.md) | Escopo, evidências e limites do marco `0.1.0` |
| [Status](docs/STATUS.md) | Estado atual, contagens, verificações e próxima tarefa |
| [Arquitetura](docs/ARQUITETURA.md) | Módulos e decisões de persistência |
| [Deploy e rollback](docs/DEPLOY.md) | Compose, migrations, entrega e recuperação |
| [Variáveis de ambiente](docs/ENV.md) | Configuração por módulo sem valores secretos |
| [API](docs/API.md) | Rotas, autenticação e semântica das respostas |
| [Dados](docs/DADOS.md) | Fontes, importação, marcas e correspondência |
| [Comparação normalizada](docs/COMPARACAO_NORMALIZADA.md) | Auditoria dos novos CSVs/XLSX, metodologia, limites e regeneração do retrato |
| [Operação no Windows](docs/OPERACAO_WINDOWS.md) | Execução local, backup e limites de implantação |
| [Backlog](docs/BACKLOG.md) | Trabalho concluído e pendente por fase |
| [Changelog](CHANGELOG.md) | Histórico funcional da versão |
| [Especificação original](PRM_ESPECIFICACAO_CODEX.md) | Objetivo e fases planejadas |

## Versionamento e dados locais

O código, as migrações, os testes e a documentação são versionados no GitHub. O [.gitignore](.gitignore) exclui `.env`, `.venv`, planilhas em `data/imports/`, exports e backups. O banco PostgreSQL também é local e não é recriado ao clonar o repositório. Antes de publicar uma alteração, confira os arquivos selecionados para o commit; mantenha `docs/STATUS.md` atualizado para facilitar a continuidade entre sessões.
