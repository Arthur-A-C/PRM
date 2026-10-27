# Deploy e rollback

Este documento consolida o procedimento; os detalhes do ambiente isolado estão em [DOCKER.md](DOCKER.md) e a operação nativa em [OPERACAO_WINDOWS.md](OPERACAO_WINDOWS.md). Não há deploy automático no GitHub Actions.

## Composição suportada

`compose.yaml` é a base segura de desenvolvimento/homologação:

- `gateway`: Nginx na porta configurável do host (8001 por padrão);
- `api`: FastAPI;
- `db`: PostgreSQL 18 isolado;
- `worker-registration`, `worker-removal`, `worker-datasheets`, `worker-alerts`: opt-in pelo profile `workers`;
- `migrate`: execução manual pelo profile `tools`.

Volumes nomeados preservam PostgreSQL, filas e arquivos. Não use `docker compose down -v`, não compartilhe SQLite entre escritores e não copie automaticamente dados do Windows para volumes vazios.

`compose.dev.yaml` monta somente código-fonte read-only e habilita reload da API. `compose.windows.yaml` serve exclusivamente para validar, em modo somente leitura, a conexão ao PostgreSQL do Windows.

## Overlays funcionais históricos

Os overlays `compose.<funcionalidade>.yaml` registram imagens homologadas ou pontos de rollback de entregas incrementais. Eles não foram removidos nem consolidados em 27/10/2026 porque a equivalência operacional depende das imagens locais e da ordem usada em cada implantação.

Categorias encontradas:

- cadastro: `cadastro-*`, `selecao-cadastro`, `wcda-ausente`, `upload-grande`;
- remoção: `remocao-*` e overlays de rollback;
- imagens: `svg*`;
- catálogos: `catalogos-*`;
- fornecedores/design: `fornecedores*`, `design-system`.

Antes de aposentar um overlay, registre a imagem atualmente ativa e compare:

```powershell
docker compose -f compose.yaml -f compose.<antigo>.yaml config --quiet
docker compose -f compose.yaml -f compose.<novo>.yaml config --quiet
```

Compare serviços, imagens, variáveis, volumes, redes e comandos. Não publique a saída completa quando ela puder conter variáveis locais.

## Procedimento de entrega

1. Confirme branch, diff e ausência de segredos.
2. Execute a suíte Python e JavaScript sem rede externa.
3. Valide uma única head Alembic.
4. Faça backup do banco e dos volumes/filas afetados.
5. Construa uma imagem imutável com tag identificável; não use `latest` como evidência de versão.
6. Rode migrations manualmente antes da API, somente no banco confirmado.
7. Atualize primeiro os serviços necessários; evite reiniciar workers não relacionados.
8. Verifique health, logs, versão e operação em Dry Run.
9. Registre `PRM_DEPLOYED_COMMIT` com o SHA efetivamente implantado.

Comandos do ambiente Docker isolado:

```powershell
.\scripts\docker\prm.ps1 build
.\scripts\docker\prm.ps1 init
.\scripts\docker\prm.ps1 up
.\scripts\docker\prm.ps1 health
.\scripts\docker\prm.ps1 test
```

## Migrations

Nunca reescreva migrations aplicadas. Verifique antes do deploy:

```powershell
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Em 27/10/2026 existe uma única head: `20261027_0017` (`access_levels`). `upgrade head` modifica o banco e só deve ser executado depois de conferir a URL e o backup.

## Rollback

- Código: volte para a imagem imutável anterior, sem force push.
- Banco: migrations destrutivas não fazem parte do fluxo normal; restauração exige backup verificado e janela coordenada.
- Filas/arquivos: preserve os volumes e journals. Não restaure SQLite com workers ativos.
- Lojas: use o journal e o plano de rollback do módulo correspondente; não improvise payload inverso.

Overlays com sufixo `.rollback.yaml` são referências explícitas de imagens anteriores, não um comando completo de restauração. Confirme a compatibilidade do schema antes de usá-los.
