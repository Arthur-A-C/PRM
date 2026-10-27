# Ativação local da remoção por cargo — 23/10/2026

Autorizada pelo usuário após os testes. Endpoint local:
`http://localhost:8001/digitalizacao/remocao-arquivos`.

## Implantação efetiva

- Projeto Docker: `prm-docker`; API/worker-removal usam `prm:removal-roles-20261023`.
- Imagem testada: `sha256:5c69d97a387bc6d191b7c78a7965ebde93e5398bfb868d6303fd847842b98a09`.
- Base Compose/configuração: `C:\Users\PW\Documents\PRM\compose.yaml`, intacta.
- Overlay: `C:\Users\PW\Documents\PRM-remocao-cargos\compose.remocao-cargos.yaml`.
- Sem build a partir do checkout compartilhado, sem mudança na tag `prm:local`, sem migrations.
- Credenciais/variáveis conferidas sem exposição; mesmos 11 volumes por serviço.
- API e worker-removal recriados; PostgreSQL, gateway, registration, datasheets e alerts mantiveram
  seus IDs. O ambiente `prm-kaue` da porta 8002 não foi alterado.
- Nenhum commit, push ou merge. O código continua na branch local `fix/remocao-autorizacao-cargos`.

**Atenção:** não usar apenas o Compose original para recriar esses serviços até integrar o código.
Sem o overlay, a imagem `prm:local` antiga será selecionada. Não remover este worktree/overlay
enquanto fizer parte da configuração ativa; depois da integração, ajustar o procedimento de deploy.

Comando usado, para referência (não é necessário executar novamente):

```powershell
docker compose --project-directory C:\Users\PW\Documents\PRM -p prm-docker -f C:\Users\PW\Documents\PRM\compose.yaml -f C:\Users\PW\Documents\PRM-remocao-cargos\compose.remocao-cargos.yaml --profile workers up -d --no-deps --no-build --pull never --wait --wait-timeout 60 api worker-removal
```

## Backup e retorno

Backups privados, fora do repositório:
`C:\Users\PW\Documents\PRM-deploy-backups\removal-20261023`.

- `prm_docker.dump`: pg_dump custom, 115867 bytes; listado por pg_restore sem restaurar.
- `store-publish.tar.gz`: fila, journal e arquivos do volume, 6617 bytes; arquivo TAR conferido.
- Imagem anterior: `prm:before-removal-roles-20261023`, baseada em
  `sha256:c162c0e3427c9bea8372cf9925f065ac0f59f0840149a93470dd1bc4e406f58d`.

Retorno requer nova decisão operacional: pausar fila, aguardar item ativo e revisar operações
pendentes; versões antigas não entendem a autorização role-v1. Não restaurar banco/fila
automaticamente, pois isso descartaria alterações posteriores e poderia repetir operações.
Se necessário retornar apenas o código, usar o mesmo comando com
`compose.remocao-cargos.rollback.yaml` no lugar de `compose.remocao-cargos.yaml`.
O overlay de retorno não foi executado. Nunca usar `down -v`.

## Verificações após ativação

- `/api/v1/health/ready`: HTTP 200, `status: ok`, `database: available`.
- `/api/v1/remocao-arquivos/ambientes` sem login: HTTP 401.
- JavaScript servido inclui autorização por cargo e helper de estados dos botões.
- Processo carregado reconhece `gestor` e `desenvolvedor`, três lojas, `four_eyes: false`.
- Worker iniciado e lock exclusivo adquirido.
- Fila antes/depois: `done: 1`, `error: 8`, `review: 4`; nenhum item pendente foi executado.
- Grants legados mantidos: `consumed: 1`, `issued: 1`; não usados pela remoção nova.
- Nenhum teste destrutivo, upload, remoção ou chamada de IA. A operação pela interface exige
  login real, revisão, aprovação e confirmação do usuário; testes de produção não foram simulados.

Para testar: abrir a URL, atualizar com Ctrl+F5 e usar gestor/desenvolvedor. Nos itens antigos com
erro, Refazer Dry Run antes de aprovar e executar. Confirmar que o backup está disponível e que
os arquivos propostos são exatamente os desejados. Flag legado de produção não bloqueia este fluxo.

Observação preexistente: `prm-kaue-worker-alerts-1` já reiniciava antes desta implantação;
não foi investigado ou alterado por estar fora do escopo.
