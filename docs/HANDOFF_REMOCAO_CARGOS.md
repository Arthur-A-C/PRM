# Handoff — remoção por cargo (23/10/2026)

## Estado da entrega

Implementação concluída, testada e **ativada no Docker principal da porta 8001**, após autorização
explícita do usuário em 23/10/2026. Consulte `docs/DEPLOY_REMOCAO_CARGOS.md` para configuração e retorno.
Worktree: `C:\Users\PW\Documents\PRM-remocao-cargos`.
Branch: `fix/remocao-autorizacao-cargos`, base `origin/main@179c702` (PRs #4/#5 já integrados).
Sem novos commits, push ou merge. A versão está no servidor local, mas ainda não foi publicada no GitHub.

O usuário confirmou explicitamente no chat a autorização permanente **somente para remoção**:
gestores/desenvolvedores ativos, lojas da organização configurada, sem grants, liberação por SKU,
trava de produção ou segundo aprovador, mantendo login/CSRF/isolamento/Dry Run/confirmação/
backup/auditoria/verificação. A pausa anterior foi resolvida por essa confirmação.

## Concluído

- Regra central `ALLOWED_STORE_ROLES = {"gestor", "desenvolvedor"}`.
- Permissões approve/execute/restore/admin automáticas, sem concessões por loja.
- Worker sem gates legados: confirmação role-v1 vinculada à organização, origem, empresa, SKU,
  ID, modo, aprovador e hash; revalidação da identidade persistida antes das escritas.
- Backup verificado obrigatório, proteção de campos comerciais e concorrência inclusive durante
  backup/restauração; preservação de journal, auditoria, arquivos, tabelas e históricos.
- Aprovação/execução/restauração pela própria pessoa para ambos os cargos, auditadas.
- UI com estados simples, controles por estado e erros FastAPI legíveis (string/lista).
- CLI antiga de restauração aposentada, sem bypass; endpoints antigos de configuração retornam 410.
- Pausa/cancelamento de restauração mantém possibilidade de reconfirmar e recuperar.
- Documentação atualizada. Nenhuma migration necessária.
- `store_publish_grant.py` e demais publicadores revisados, mas **não alterados**.
  Grants continuam protegendo os outros módulos.

## Arquivos modificados

- `.env.example`: somente comentário sobre flag legado; nenhuma credencial.
- `app/models/store_operations.py`: comentários sobre registros históricos.
- `app/routers/store_file_removal.py`: cargo, CSRF, configuração aposentada, confirmação.
- `app/services/store_file_removal.py`: fila/worker, escopo, backup, concorrência e restauração.
- `app/services/store_removal_production.py`: autorização central e identidade persistida.
- `app/static/js/store-file-removal.js`: interface e helpers testáveis.
- `app/templates/store_file_removal.html`: controles simplificados.
- `app/templates/shell.html`: apenas versão de cache do JS de remoção; reuniões intocadas.
- `scripts/store_removal_worker.py`: descrição atualizada, execução existente preservada.
- `scripts/store_removal_restore.py`: CLI aposentada com orientação, sem abrir filas/banco.
- `tests/test_store_file_removal.py` e `tests/test_store_removal_production.py`: contrato novo.
- `docs/REMOCAO_ARQUIVOS.md`, `docs/API.md`, `docs/STATUS.md` e `CHANGELOG.md`.

Arquivos novos:

- `tests/test_store_removal_roles.py`: matriz cargo/loja/modo e regressões de segurança.
- `tests/js/store-file-removal.test.cjs`: erros e estados dos botões, sem navegador/rede.
- `tests/test_store_removal_ui.py`: chama testes Node quando disponível; skip no runtime.
- `docs/HANDOFF_REMOCAO_CARGOS.md`: este registro.

## Testes realizados

- Build exclusivo `prm:removal-roles-test`, aprovado; imagem estável `prm:local` não substituída.
- Primeira rodada focada: 68 passaram e 6 falharam em fixtures/expectativas legadas.
  Ajustes: active/permissões no mock, confirmação digitada e ausência esperada de grants.
- Rodada focada após ajustes e novas regressões: **126 passaram**, 1 aviso, 31,22 s.
- Suíte completa final em container descartável `--network none`, sem volumes/credenciais:
  **713 passaram, 27 ignorados, 1 aviso**, 75,83 s.
- Ignorados: 25 fixtures privadas, 1 arquivo Compose excluído da imagem, 1 Node ausente.
- Node no Windows: **4 testes passaram**. Primeira tentativa limitada pelo sandbox (spawn EPERM);
  execução autorizada posterior concluiu sem erro.
- `docker compose --profile workers config --quiet` e configuração de desenvolvimento: aprovadas.
- `git diff --check` e sintaxe JavaScript aprovados.
- Aviso preexistente AnyIO/Starlette (depreciação). Não houve teste real de loja nesta tarefa.

## Ambientes preservados e riscos

Na implementação/testes não houve deploy ou reinício. Na ativação posterior autorizada, somente
API e worker-removal foram recriados; backups e volumes existentes preservados, sem migrations.
Nenhuma chamada às lojas ou IA foi feita durante a implantação.
Nenhuma credencial copiada/exposta. O worktree original e os demais desenvolvedores
não foram alterados. PostgreSQL/gateway/demais workers mantiveram os mesmos containers.
Compose original preservado; imagem de API/worker-removal selecionada por overlay nesta branch.

O repositório foi informado como público na etapa anterior. Esta entrega não fez push
nem criou PR. Conferir novamente o destino antes de qualquer publicação.

Filas antigas sem confirmação role-v1 devem ser revisadas/reprocessadas e reconfirmadas.
Backups/journals antigos permanecem disponíveis; não misturar API e workers de versões diferentes.
Flag antigo `PRM_REMOVAL_PRODUCTION_ALLOWED=false` **não bloqueia a versão nova**.
Não usar esse flag como mecanismo de suspensão; pausar a fila/serviço, respeitando item em andamento.

Risco residual: APIs Woo/WordPress não possuem transação atômica com nossa releitura; concorrência
pode ocorrer entre GET e escrita. Conferência posterior detecta divergência. Upload de recuperação
pode deixar arquivo avulso se conflito surgir antes da associação; não apagar automaticamente.
Permissões reais da loja, CDN e espaço para backup ainda podem bloquear operações legitimamente.

## Próximos passos exatos

1. Revisar `git diff` e esta lista no worktree isolado. Comparar com main remota novamente antes
   de abrir PR, pois outro desenvolvedor segue trabalhando. Não tocar em arquivos dele.
2. Se for versionar, adicionar apenas os arquivos listados (não `git add .`), revisar segredos e
   criar commit coeso. Sem merge automático; confirmar publicação/PR conforme fluxo da equipe.
3. Após revisão/integração e autorização de implantação, seguir `docs/REMOCAO_ARQUIVOS.md`:
   aguardar itens ativos, backup, mesmos volumes/Compose/overlays, mesma versão em API/worker-removal.
   `compose.integracoes.yaml` é configuração local ausente deste worktree; não recriar credenciais.
4. Testar a interface implantada com cargo gestor/desenvolvedor e usuário sem acesso, começando
   por leitura/Dry Run. Qualquer remoção real exige autorização específica e confirmação da operação.
5. Nenhuma loja foi homologada em produção por estes testes com mocks; não declarar o contrário.
