# PRM

Product Relationship Manager: aplicação interna para analisar catálogos de produtos do grupo SAG, com foco nas ofertas da Choice Tech e da Portwell e comparação com concorrentes como a Eco Automação.

Este repositório contém o código e a documentação da primeira entrega (`0.1.0`). O [marco da entrega](docs/ENTREGA_0_1.md) resume o que funciona e seus limites; o [estado operacional](docs/STATUS.md) registra as verificações mais recentes.

## O que já funciona

- Login individual, sessões e páginas protegidas.
- Importação auditável de planilhas XLSX da Eco Automação, Portwell e Choice Tech, com prévia, validação e proteção contra reimportação idêntica.
- Dashboard e catálogo com busca, filtros, preços e origem de cada oferta. Nossas empresas aparecem primeiro nas listas.
- Análise automática do catálogo concorrente inteiro contra o portfólio próprio, com sugestões, candidatos, cobertura e posição nominal de preços.
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

## Verificações

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m scripts.reconcile_catalogs
```

O último conjunto verificado em 23/09/2026 teve 17 testes aprovados, migração `20260922_0006` e 35.786 ofertas no banco local. Esses números dependem dos catálogos importados e não aparecem em um banco recém-criado.

## Documentação

| Documento | Conteúdo |
|---|---|
| [Primeira entrega](docs/ENTREGA_0_1.md) | Escopo, evidências e limites do marco `0.1.0` |
| [Status](docs/STATUS.md) | Estado atual, contagens, verificações e próxima tarefa |
| [Arquitetura](docs/ARQUITETURA.md) | Módulos e decisões de persistência |
| [API](docs/API.md) | Rotas, autenticação e semântica das respostas |
| [Dados](docs/DADOS.md) | Fontes, importação, marcas e correspondência |
| [Operação no Windows](docs/OPERACAO_WINDOWS.md) | Execução local, backup e limites de implantação |
| [Backlog](docs/BACKLOG.md) | Trabalho concluído e pendente por fase |
| [Changelog](CHANGELOG.md) | Histórico funcional da versão |
| [Especificação original](PRM_ESPECIFICACAO_CODEX.md) | Objetivo e fases planejadas |

## Versionamento e dados locais

O código, as migrações, os testes e a documentação são versionados no GitHub. O [.gitignore](.gitignore) exclui `.env`, `.venv`, planilhas em `data/imports/`, exports e backups. O banco PostgreSQL também é local e não é recriado ao clonar o repositório. Antes de publicar uma alteração, confira os arquivos selecionados para o commit; mantenha `docs/STATUS.md` atualizado para facilitar a continuidade entre sessões.
