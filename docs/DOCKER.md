# Docker do PRM — ambiente isolado

## Segurança e arquitetura

O padrão é **homologação local**, não substituição do Windows. O PRM Windows/porta 8000, o PostgreSQL nativo `prm_mvp` e todos os arquivos em `data/` continuam intocados. Nenhum volume é preenchido com dados atuais automaticamente.

| Serviço | Execução | Persistência |
| --- | --- | --- |
| `gateway` | Nginx, `127.0.0.1:8001`; única entrada HTTP | Configuração read-only, sem dados/segredos |
| `api` | FastAPI interno, acessível pelo gateway | Volumes compartilhados abaixo |
| `db` | PostgreSQL 18, banco `prm_docker`, sem porta publicada | `postgres` em `/var/lib/postgresql` |
| `worker-registration` | Cadastro via API existente | `store-publish` |
| `worker-removal` | Remoção existente (depende do PR funcional) | `store-publish` |
| `worker-datasheets` | Datasheets em lote existentes | `datasheet-batches`, `products` |
| `worker-alerts` | Alertas, sem análise IA | PostgreSQL isolado, `meetings` |
| `migrate` | Manual; recusa banco diferente de `db/prm_docker` | Schema somente do banco isolado |

Volumes adicionais: `integrations`, `imports`, `exports`, `analysis`, `backups`, `tools`, `photos`. Todos recebem prefixo do projeto Compose. A imagem não contém dados, filas, `.env`, backups ou credenciais. O `.env` não é injetado nos serviços; suas chaves de lojas/IA não são usadas. A senha `local-test-only` pertence somente ao banco de teste sem porta publicada: nunca usar em produção.

A rede da aplicação é `internal: true`: API, banco e workers não acessam WooCommerce ou IA externa. Somente o gateway participa também da rede de entrada, sem credenciais ou volumes de dados. Não há chamadas pagas, grants ou publicações. Não habilitar serviços externos alterando somente uma variável; isso exige uma nova homologação autorizada. Playwright continua no código legado, mas não é instalado na imagem. Node.js e transcrição ASR não fazem parte desta imagem.

Workers são opt-in (`--profile workers`). O wrapper Linux limita o banco a `db/prm_docker` e aplica `flock` por worker/volume; o worker de alertas mantém também seu advisory lock PostgreSQL. Não compartilhar queues com Windows nem aumentar réplicas. Cookies Docker têm nomes distintos dos cookies Windows.

## Iniciar no PowerShell

Requisitos: Docker Desktop com containers Linux e Compose >= 2.24.4. Execute na raiz do clone.

Se o Windows bloquear scripts, execute somente o script revisado com política temporária do processo (não altera a política do sistema): `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/docker/prm.ps1 build`. Troque `build` pela ação desejada nos comandos abaixo.

```powershell
.\scripts\docker\prm.ps1 build
.\scripts\docker\prm.ps1 init   # migra SOMENTE o novo banco prm_docker
.\scripts\docker\prm.ps1 up
.\scripts\docker\prm.ps1 health
.\scripts\docker\prm.ps1 test
```

Abra http://127.0.0.1:8001. O banco é novo: contas e catálogos do Windows não são copiados. Cadastre dados sintéticos pelo procedimento existente de bootstrap do PRM antes de testar módulos autenticados. Não confundir health HTTP 200 com catálogo/usuários migrados.

**Dependência de versionamento:** `scripts/store_removal_worker.py` e módulos recentes de remoção/publicação ainda eram alterações funcionais não versionadas no início da infraestrutura. Não foram apropriados pelo commit Docker. Em checkout sem essa dependência, `up` recusa ativar todos os workers. Para validar o restante: `docker compose up -d --wait gateway worker-registration worker-datasheets worker-alerts`. Integre o PR funcional revisado antes de exigir os quatro workers num clone limpo.

```powershell
.\scripts\docker\prm.ps1 logs -Service api
.\scripts\docker\prm.ps1 workers
.\scripts\docker\prm.ps1 restart
.\scripts\docker\prm.ps1 down  # preserva volumes; NÃO usa -v
```

Para atualizar código da imagem: `build` seguido de `up` (recria serviços cuja imagem mudou). Para desenvolvimento: `up -Dev` após `init`; somente `app/`, `scripts/`, `tests/`, `migrations/`, `config/` são bind mounts read-only da API, com reload. Workers continuam usando a imagem: reconstruir ao alterar seu código. Nunca monte `.env`, disco inteiro ou `data/` do Windows.

Para clones paralelos: use `-Project prm-kaue` ou `-Project prm-arthur` em **todos** os comandos. Defina `$env:PRM_DOCKER_PORT='8002'` no segundo clone. Portas 8000/5432 do host não são usadas pelos containers.

## Verificar conexão com o PostgreSQL Windows sem escrever

`compose.windows.yaml` é exclusivamente um override para consulta de conectividade, não um modo de migração/publicação. Reaproveita `PRM_DATABASE_URL` do `.env` local, troca localhost por `host.docker.internal` no entrypoint e força `default_transaction_read_only=on` via libpq. Não carrega outras credenciais. Não iniciar workers neste modo. O SQL de health é `SELECT 1`.

```powershell
# Pare apenas a API Docker para liberar 8001; não pare o PRM Windows.
docker compose stop gateway api
docker compose -p prm-windows-check -f compose.yaml -f compose.windows.yaml up -d --no-deps api
Invoke-RestMethod http://127.0.0.1:8001/api/v1/health/ready
docker compose -p prm-windows-check -f compose.yaml -f compose.windows.yaml down
docker compose up -d gateway
```

Não publique `docker compose config` sem `--quiet` ou `docker inspect`: esses comandos podem revelar a URL com credenciais neste override. Um futuro modo operacional sobre `prm_mvp` exige plano de corte, backup e parada coordenada de workers Windows; não está ativado.

## Dados, backup e recuperação

- O journal do produto **16321** permanece no Windows (`data/store_publish/jobs.sqlite3`). O Docker não contém esse histórico e não deve executar o rollback daquele envio.
- Não migrar SQLite com escritores ativos. Uma migração futura exige parar produtores/consumidores, backup consistente via SQLite, verificar integridade/hashes, cópia explícita para volume novo e validação, nunca sobrepor filas automaticamente.
- `scripts/docker/prm.ps1 backup` para escritores Docker e faz backup frio dos arquivos no volume `backups`. Não reinicia automaticamente; não inclui PostgreSQL. Extraia com `docker compose cp api:/app/data/backups ./backups-docker` após criar o diretório local.
- PostgreSQL isolado: `docker compose exec db pg_dump -U prm -d prm_docker -Fc -f /tmp/prm-docker.dump`; depois `docker compose cp db:/tmp/prm-docker.dump ./backups-docker/prm-docker.dump`. Esse comando não acessa `prm_mvp`. Para restore, use outro projeto/volume e valide antes de substituir qualquer ambiente.
- Não executar `down -v`, `docker volume prune` ou remover volumes durante uso normal. Logs têm rotação 10 MB x 5; auditorias de aplicação persistem em volumes, não dependem desses logs.

## CI e limites

GitHub Actions: `tests` (Python 3.14), `docker` (build, pytest sem rede, migrations/health isolados), `security` (Gitleaks histórico). Sem deploy, sem secrets, sem upload de banco/artefatos privados. Testes de UI usam auditorias sintéticas; testes de catálogos/transcrição privada ausentes são explicitamente ignorados, não considerados homologação desses dados.

Resultados efetivamente executados e pendências em [INFRA_STATUS.md](INFRA_STATUS.md). Fluxo de PR em [CONTRIBUTING.md](../CONTRIBUTING.md).
