# Handoff para o Codex — profissionalização do ambiente (Docker, GitHub, CI/CD)

Data: 22/10/2026. Autor: sessão Claude Code interrompida a pedido do usuário (limite de uso).
Pedido original: Docker + Compose, GitHub organizado, fluxo por branches/PR, CI/CD, scripts de
operação e validação completa, **sem reescrever o PRM** e **sem alterar dados reais/banco**.

> Nada foi commitado, nada foi enviado ao GitHub nesta etapa e nenhuma loja foi alterada.
> Não execute `git reset`, `git clean`, `docker compose down -v` nem push sem revisar este documento.

---

## 1. Estado do Git (no momento da interrupção)

- Repositório: `C:\Users\PW\Documents\PRM`, remote `origin = https://github.com/Arthur-A-C/PRM.git`.
  - **Privado**: API anônima do GitHub responde 404; `git ls-remote` autenticado funciona.
- Branch atual: `cadastro-api-arquivos` (rastreia `origin/cadastro-api-arquivos`, commit `9b594c7`).
- `main` local = `origin/main` = `28b7c13` ("Atualizacao_dashboard"). Total: 11 commits em todos os branches.
- Identidade configurada no repositório: `Kaue-Borges <kaue.borges0803@gmail.com>`.
- Ferramenta `gh` (GitHub CLI) **não está instalada**; nenhuma regra/ruleset foi aplicada no GitHub.
- **Há ~70 arquivos modificados/não rastreados não commitados**, de várias entregas anteriores
  desta sessão (todas testadas, suíte local 563 aprovados antes da etapa Docker):
  - Liberação de uso único/auditoria/rollback do Cadastro via API (`store_publish_grant.py`,
    `scripts/homologation_grant.py`, `scripts/store_registration_rollback.py`, testes `test_homologation_grant.py`, `test_publish_audit.py`).
  - Datasheet do fornecedor fora da exportação (`datasheet_batches.py`, `digitalization_storage.py`, `registration_package.py`, Cadastro via API).
  - Digitalização e Publicação em Lote (`app/services/batch_publication.py`, `app/routers/batch_publication.py`, template/JS/CSS `batch*`, `docs/PUBLICACAO_EM_LOTE.md`, `tests/test_batch_publication.py`).
  - Front-end de Cards e Planner (`_meeting_pages.html`, `_planner.html`, `meetings.css`, `cards-page.css`, `meetings.js`).
  - Resolução de imagens em pasta (`app/services/image_resolution.py`, `app/routers/image_resolution.py`, template/JS/CSS `image*`, `docs/RESOLUCAO_IMAGENS.md`, `tests/test_image_resolution.py`; `fit_square` em `registration_package.py`).
  - Remoção de arquivos de produtos (`app/services/store_file_removal.py`, `app/routers/store_file_removal.py`, template/JS/CSS `store-file-removal*`, `scripts/store_removal_worker.py`, `scripts/store_removal_restore.py`, `docs/REMOCAO_ARQUIVOS.md`, `tests/test_store_file_removal.py`; leitura `product/<id>` em `store_http.py`).
  - Documentação: `README.md`, `CHANGELOG.md`, `docs/STATUS.md`, `docs/CADASTRO_API_STAGING.md`, `docs/API.md`, etc.
- **Arquivos modificados que NÃO foram feitos por esta sessão** (autor desconhecido — confirmar com
  Kaue/Arthur antes de commitar): `app/routers/meetings.py`, `app/services/meeting_activities.py`,
  `app/services/meeting_deadlines.py`, `app/services/meeting_demo.py`, `tests/test_meeting_pipeline.py`,
  `scripts/cards_assignment_smoke.cjs`, `scripts/install_test_cards.py` (novo).
  - O `shell.html` tinha a versão `meetings.js?v=20261022-test-cards` (de outra pessoa); foi trocada para `20261022-ui`.

## 2. Arquivos criados/alterados NESTA etapa (Docker/GitHub)

| Arquivo | Estado | Conteúdo |
|---|---|---|
| `.dockerignore` | criado | Exclui `.git`, `.env*` (exceto `.env.example`), `.venv*`, `data/` (7,2 GB), backups/dumps, `*.sqlite3`, `docs`, `*.md` (exceto README), `scripts/*.cjs`, compose/Dockerfile. |
| `Dockerfile` | criado | Multi-stage `python:3.14-slim-bookworm` (base → deps com venv em `/opt/venv` + `pip check` → runtime). `tzdata` + `fonts-dejavu-core`. Usuário não-root `prm` (uid/gid 1000). Cria `data/*` com dono `prm` para volumes nomeados herdarem. `EXPOSE 8000`. `ENTRYPOINT docker/entrypoint.sh`, `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers`. |
| `docker/entrypoint.sh` | criado | Se `PRM_DATABASE_URL` aponta para `127.0.0.1/localhost/::1`, troca o host por `PRM_DOCKER_DB_HOST` (padrão `host.docker.internal`); não imprime a URL; `exec "$@"`. |
| `.gitattributes` | alterado | Mantém `* text=auto` e força LF em `*.sh`, `docker/**` e `Dockerfile` (evita CRLF quebrar o entrypoint no Linux). |
| `requirements.txt` | alterado | **Acrescentados** `opencv-python-headless==5.0.0.93` e `pypdf==6.19.0` (ver §4). |
| `docs/HANDOFF_CODEX.md` | criado | Este documento. |

**Ainda não criados** (ver §6): `compose.yaml`, override de desenvolvimento, scripts PowerShell,
`.github/workflows/ci.yml`, template de PR, CODEOWNERS, ruleset, `.gitleaksignore`, ajustes no
`.gitignore`, README de infraestrutura, `docs/DOCKER.md`, `docs/FLUXO_GIT.md`.

## 3. Auditoria realizada (somente leitura)

- **Servidor**: `app.main:app` (FastAPI). Monta `app/static` e lê `.env` por caminho relativo → processo deve iniciar na raiz (`WORKDIR /app`). Health: `GET /api/v1/health/live` e `GET /api/v1/health/ready` (`SELECT 1`; 503 sem banco). Porta padrão 8000 (`scripts/run-web.ps1`). `app/remote_preview.py` é outro ASGI (exige `PRM_PREVIEW_BASIC_PASSWORD`) — não usar no Docker.
- **Banco**: somente PostgreSQL (`app/db.py` rejeita outros esquemas). Instância **nativa do Windows**: serviço `postgresql-x64-18` (Running/Automatic), escuta `0.0.0.0:5432`, banco `prm_mvp` (`PRM_DATABASE_URL=postgresql+psycopg://…@127.0.0.1:5432/prm_mvp`). Alembic: `alembic.ini`, `migrations/` (12 revisões; banco já em `20261021_0011` segundo STATUS). **Não migrar/alterar sem backup.**
  - Teste feito: container `postgres:18-alpine` → `pg_isready -h host.docker.internal` = *accepting connections*; conexão com usuário inexistente chegou à etapa de senha ⇒ **o `pg_hba.conf` já aceita conexões do Docker (origem 192.168.65.x)**. Não é preciso alterá-lo.
- **SQLite (filas)**: `data/store_publish/jobs.sqlite3` (cadastro, remoção, journal, auditoria, grants), `data/datasheet_batches/queue.sqlite3`, `data/integrations/connections.sqlite3`. Usam `BEGIN IMMEDIATE`, sem WAL/busy_timeout. API e workers escrevem simultaneamente.
- **Workers** (todos via `sys.executable` com processos filhos e watchdog):
  - `scripts/store_registration_worker.py` (`--once`, `--batch`+`--sku`) → `jobs.sqlite3`.
  - `scripts/store_removal_worker.py` (mesmo padrão) → `jobs.sqlite3`.
  - `scripts/datasheet_batch_worker.py` (`--once`, `--cleanup [--apply]`, SIGTERM) → `queue.sqlite3`; usa Anthropic (custo).
  - `python -m scripts.meeting_worker --stage alerts|analysis|cards|transcription|text` (`pg_try_advisory_lock`, uma instância por etapa no banco). `alerts` estava ativo em produção; `analysis/cards` usam IA paga; `transcription` exige `requirements-asr.txt` (faster-whisper/ctranslate2/av) e modelos em `data/meetings/models`.
  - Scripts só de desenvolvimento: `public_preview.py` (cloudflared.exe, Windows), `workspace_preview.py`.
- **Dependências**: `requirements.txt` (FastAPI, SQLAlchemy, psycopg, anthropic, pymupdf, pillow, numpy, reportlab…). `requirements-asr.txt` opcional. **Playwright não é importado** (só citado em comentários; automação antiga fica fora do repo em `Documents/arquivos-prm/automação cadastro`). Node: só 5 scripts `.cjs` de smoke visual (Edge via CDP), não usados em runtime.
- **Variáveis lidas direto de `os.environ`** (não estão todas no `.env.example`): `ANTHROPIC_API_KEY`, `DATASHEET_MODEL`, `PRM_PRODUCT_STORAGE_ROOT` (absoluto), `PRM_IMAGE_TOOL_ROOTS` (`;`, padrão `Path.home()`), `PRM_REGISTRATION_{CHOICE,SAG,PORTWELL}_ROOT`, `PRM_WOO_EXPORTS_ZIP`, `QWEN_*`/`DASHSCOPE_API_KEY`. `StoreSettings` lê `ROOT/.env`; no container as variáveis devem vir do `env_file`.
- **Caminhos Windows no código**: `datasheet_core.py` (fallback `C:/Windows/Fonts`; as fontes DejaVu estão em `app/services/assets/fonts`), `scripts/backup_database.py` e `restore_staging.py` (`pg_dump.exe`), `scripts/audit_registration_sources.py` (`C:/Users/PW/Downloads`), `public_preview.py` (cloudflared.exe). Nenhum afeta a aplicação no container; backup no Docker deve usar imagem `postgres:18` com `pg_dump`.
- **Dados**: `data/` = 7,2 GB (`analysis` 5,9 GB, `backups` 492 MB, `meetings` 465 MB, `imports` 311 MB, `tools` 53 MB, `exports` 19 MB, `products` 12 MB, `store_publish` 3,3 MB). Logs: apenas stdout (sem arquivos).
- **Segredos**: gitleaks 8.28 (container, repo montado read-only, `--log-opts=--all`, 11 commits): **2 achados, ambos falsos positivos** — `app/static/js/catalog-selection.js:2` (chave de localStorage) e `tests/test_security.py:14` (senha fictícia de teste), commit `86589ee`. Fingerprints para `.gitleaksignore`:
  - `86589ee32d72170376fc21278bf77603180acab9:app/static/js/catalog-selection.js:generic-api-key:2`
  - `86589ee32d72170376fc21278bf77603180acab9:tests/test_security.py:generic-api-key:14`
  - `.env` nunca foi rastreado; `.gitignore` já cobre `.env*`, `data/*` sensíveis, `chrome-profile*`, `.venv*`.

## 4. Comandos executados e resultados

| Comando | Resultado |
|---|---|
| `docker --version` / `docker compose version` / `docker info` | Docker 29.9.2, Compose v5.6.0, Docker Desktop. |
| `git remote -v`, `git branch -a -vv`, `git ls-remote --heads origin` | ver §1. |
| `curl https://api.github.com/repos/Arthur-A-C/PRM` | 404 (privado). |
| Leitura do `.env` (só nomes e host/porta/banco, sem segredos) | 29 chaves; DB em `127.0.0.1:5432/prm_mvp`. |
| Processos/portas Windows | Nenhum PRM rodando; só PostgreSQL em 5432. Porta 8000 livre no momento (servidor Windows parado). |
| `docker run postgres:18-alpine pg_isready -h host.docker.internal` | accepting connections; pg_hba aceita origem Docker. |
| gitleaks (histórico completo) | 2 falsos positivos (acima). |
| `docker build -t prm:local .` (1ª versão do requirements) | **Sucesso**. Imagem 826 MB, Python 3.14.9, usuário `prm` uid 1000, sem `.env`/`*.sqlite3`/`*.dump` na imagem, `/app` = 9,4 MB. |
| `docker run --rm --entrypoint python prm:local -m pytest -q` | **Falhou na coleta**: `ModuleNotFoundError: pypdf` em `tests/test_digitalization_storage.py`. |
| Varredura de imports × imagem | Faltavam: `pypdf` (testes + `qwen.py`), `cv2` (opcional em `datasheet_core.py`, mas altera o resultado da limpeza de imagens), `openai` (só `qwen.py`, não usado pelo app), `av`/`faster_whisper` (ASR opcional). Local tinha `pypdf 6.19.0`, `opencv-python-headless 5.0.0.93`, `openai 3.19.2` instalados à mão. |
| Acréscimo de `opencv-python-headless==5.0.0.93` e `pypdf==6.19.0` ao `requirements.txt` | **Gravado**; o rebuild + testes seguintes foram **interrompidos pelo usuário — não executados**. |

Suíte local (Windows, `.venv`) antes desta etapa: **563 passed, 3 warnings**.

## 5. O que funciona / o que está incompleto

Funciona:
- Imagem Docker construída (antes do acréscimo das 2 dependências), sem segredos, não-root.
- Conectividade container → PostgreSQL do Windows (`host.docker.internal:5432`).
- Entrypoint que corrige o host do banco sem editar o `.env`.

Incompleto:
1. Rebuild com o `requirements.txt` atualizado e **suíte completa dentro do container** (verificar se `opencv-python-headless==5.0.0.93` tem wheel manylinux para cp314; se não, usar a versão disponível mais próxima ou Python 3.13).
2. `compose.yaml`, override de desenvolvimento, scripts PowerShell, CI, regras do GitHub, documentação, commits e push.
3. Validação completa (healthcheck, páginas, workers, persistência após recriar, portas, lojas intactas).

## 6. Próximos passos recomendados (projeto já decidido nesta sessão)

### 6.1 `compose.yaml`
- Serviços, todos com `image: prm:local` (build `.`), `env_file: .env`, `restart: unless-stopped`, logging `json-file` com `max-size: 10m`, `max-file: 5`, `extra_hosts: ["host.docker.internal:host-gateway"]`:
  - `api`: CMD padrão; `ports: "127.0.0.1:${PRM_DOCKER_PORT:-8080}:8000"` (**não usar 8000** para não conflitar com o servidor Windows); healthcheck com Python/urllib em `http://127.0.0.1:8000/api/v1/health/live` (a imagem slim não tem curl).
  - `worker-registration`: `python scripts/store_registration_worker.py`.
  - `worker-removal`: `python scripts/store_removal_worker.py`.
  - `worker-datasheets`: `python scripts/datasheet_batch_worker.py` (IA só roda quando um lote é iniciado na interface).
  - `worker-alerts`: `python -m scripts.meeting_worker --stage alerts` (protegido por advisory lock; **não rodar junto com o worker de alertas do Windows**).
  - Perfil opcional `meetings-ai` (`analysis`, `cards`; transcrição só com imagem ASR) e perfil `tools` (`migrate`: `alembic upgrade head`, **somente manual após backup**).
  - Perfil opcional `db` (`postgres:18` com volume próprio) para desenvolvimento isolado/CI; `PRM_DOCKER_DB_HOST=db`.
- Volumes:
  - **Nomeados** (SQLite + escrita concorrente): `prm-store-publish:/app/data/store_publish`, `prm-datasheet-batches:/app/data/datasheet_batches`, `prm-integrations:/app/data/integrations`, `prm-meetings:/app/data/meetings`.
  - **Bind mounts** (arquivos, sem SQLite): `./data/products`, `./data/imports`, `./data/exports`, `./data/analysis`, `./data/backups` → `/app/data/...`.
  - Pastas de fotos para Resolução de imagens: bind mount explícito `${PRM_HOST_PHOTOS_DIR:-./data/fotos}:/mnt/prm-fotos` e `PRM_IMAGE_TOOL_ROOTS=/mnt/prm-fotos` no `environment` (nunca o disco inteiro; `Z:` mapeado não é visto pelo Docker Desktop — copiar para pasta local ou usar caminho UNC compartilhado no Docker Desktop, documentar).
  - `PRM_PRODUCT_STORAGE_ROOT=/app/data/products` no `environment` (o valor do `.env`, se houver, é caminho Windows).
- **Atenção**: os volumes nomeados começam **vazios**. A fila/journal/grants reais (incluindo o histórico do envio real do produto 16321 e o journal necessário para rollback) continuam em `data/store_publish/jobs.sqlite3` do Windows. Rollback desse envio deve ser feito pelo ambiente Windows, ou copiar o arquivo para o volume com o PRM parado (script de seed com cópia, nunca bind mount compartilhado).

### 6.2 Override de desenvolvimento (`compose.dev.yaml`)
- Bind mount de `./app`, `./scripts`, `./tests`, `./migrations`, `./config` e `uvicorn --reload` apenas para `api`.

### 6.3 Scripts PowerShell (`scripts/docker/prm.ps1`)
- Subcomandos: `up`, `down` (sem `-v`), `restart`, `rebuild` (`build` + `up -d --force-recreate`), `logs [serviço]`, `ps`/`workers`, `test` (`docker compose run --rm --entrypoint python api -m pytest -q`), `health`, `backup` (volumes nomeados via `docker run --rm -v vol:/v:ro -v ./backups-docker:/b alpine tar` + `pg_dump` via `postgres:18-alpine` contra `host.docker.internal` gravando em `data/backups`).

### 6.4 Git/GitHub
- `.gitignore`: acrescentar `backups-docker/`, `data/fotos/`, `*.dump`, `*.sqlite3`, `pytest-cache-files-*` (já), `.env.docker`.
- `.gitleaksignore` com os 2 fingerprints da §3.
- `.github/workflows/ci.yml` (sem segredos, sem integrações reais): jobs `tests` (Python 3.14, `pip install -r requirements.txt`, `pip check`, `python -m compileall -q app scripts`, `python -c "import app.main"`, `pytest -q`), `docker` (build da imagem + `docker compose config`), `security` (gitleaks com `fetch-depth: 0`; opcional `pip-audit`). Não chamar Anthropic/WooCommerce (testes já usam mocks).
- `.github/pull_request_template.md`, `.github/CODEOWNERS` (`* @Kaue-Borges @Arthur-A-C` — confirmar usernames), `CONTRIBUTING.md`.
- Ruleset da `main` (aplicar pela UI: Settings → Rules → Rulesets, ou `gh api`): bloquear exclusão e force push, exigir PR com 1 aprovação, descartar aprovações após novo push, exigir status checks `tests`, `docker`, `security` e branch atualizada. Exportar o JSON em `.github/rulesets/main.json`.
- Fluxo: `main` estável; `feature/kaue-*`, `feature/arthur-*`, `fix/*`; PR obrigatório com revisão do outro desenvolvedor.
- Mesma máquina: **dois clones separados** (não worktrees compartilhando credenciais), p. ex. `Documents/PRM-kaue` e `Documents/PRM-arthur`, cada um com `.env`, `.venv`, `COMPOSE_PROJECT_NAME` (`prm-kaue`/`prm-arthur`) e `PRM_DOCKER_PORT` próprios; identidade por repositório (`git config user.name/user.email`) e credencial separada por usuário na URL do remote (`https://Kaue-Borges@github.com/Arthur-A-C/PRM.git`, `https://Arthur-A-C@github.com/...`) com Git Credential Manager.
- Commits sugeridos (revisar a autoria dos arquivos de reuniões antes):
  1. Entregas de aplicação já testadas (dividir por área conforme §1).
  2. `build: Docker, Compose e scripts de operação`.
  3. `ci: GitHub Actions, gitleaks e templates de PR`.
  4. `docs: README, Docker e fluxo Git`.
  - Branch de destino sugerida: `feature/kaue-docker-infra` (a partir do estado atual), PR para `main`. Push só após validar e conferir o destino.

### 6.5 Validação pendente
1. `docker build` + pytest no container (Linux) — esperar 563 aprovados (alguns testes pulam sem `data/imports` e arquivos de `C:/Users/PW/Downloads`).
2. `docker compose up -d`; `health/live` e `health/ready` (ready exige o banco do Windows).
3. Páginas: `/login`, `/`, `/digitalizacao`, `/digitalizacao/cadastro-api`, `/digitalizacao/remocao-arquivos`, `/digitalizacao/resolucao-imagens`, `/digitalizacao/publicacao-lote`, `/cards`, `/planner`.
4. `docker compose ps` com todos os workers `running`; logs sem erro.
5. Persistência: criar um lote de teste, `docker compose up -d --force-recreate`, conferir que continua.
6. Portas: Docker em `127.0.0.1:8080`; servidor Windows em 8000.
7. Lojas: nenhuma gravação (política `PRM_PUBLISH_ENABLED=false`, grants só via CLI, allowlist = Choice/119002000072/16321).
8. Segredos: gitleaks no histórico + `git diff --cached` antes do push.

## 7. Riscos e configurações pendentes

- **SQLite em bind mount Windows** → risco de corrupção/locks; manter volumes nomeados. Nunca rodar workers Windows e Docker sobre o mesmo arquivo SQLite.
- **Banco compartilhado**: Docker e Windows usam o mesmo `prm_mvp`. Não rodar o `worker-alerts` dos dois lados (advisory lock evita duplicidade, mas um ficará ocioso). Migrações só manuais, com `pg_dump` antes.
- **Python 3.14**: confirmar wheels Linux para todas as versões fixadas (opencv/pypdf recém-adicionados).
- **`PRM_IMAGE_TOOL_ROOTS`/`PRM_PRODUCT_STORAGE_ROOT`/`PRM_REGISTRATION_*_ROOT`** com caminhos Windows no `.env` não funcionam no container; sobrescrever no `environment` do Compose.
- **Unidade Z:** não acessível diretamente pelo container.
- **Cookie**: `PRM_SESSION_COOKIE_SECURE=false` adequado só em `127.0.0.1`.
- **`.env` contém credenciais reais** das lojas (WooCommerce/WordPress) e Anthropic: não copiar para a imagem nem para o repositório (já protegido por `.gitignore`/`.dockerignore`).
- **Dependências não declaradas** encontradas (`pypdf`, `opencv`, `openai`): o ambiente Windows funcionava por pacotes instalados manualmente.
- Arquivos de reuniões modificados por autor desconhecido (§1) precisam de confirmação antes de commit.
- Pendência funcional anterior: o datasheet do fornecedor já está publicado no produto 16321 (WCDA). Opções: rollback + reenvio, ou remoção de um documento específico (não implementada).
