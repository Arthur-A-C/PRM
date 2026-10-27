# Remoção de arquivos por cargo — 23/10/2026

Acesso: **Digitalização → Remoção de arquivos** (`/digitalizacao/remocao-arquivos`).
Regra central em `store_removal_production.py`:

```python
ALLOWED_STORE_ROLES = {"gestor", "desenvolvedor"}
```

Usuários ativos desses cargos, pertencentes à organização `PRM_STORE_ORGANIZATION_ID`,
podem aprovar, executar e restaurar nas lojas Choice, SAG e Portwell, inclusive a própria
operação. As permissões efetivas são `approve/execute/restore/admin: true`, independentemente
de registros na tabela antiga. Vendedores e demais perfis recebem 403.

Este acesso é exclusivo da remoção. Cadastro, publicação e outros serviços continuam com
suas políticas e grants anteriores. Credenciais permanecem separadas por loja.

## Fluxo atual

1. Escolher empresa, modo e até 500 SKUs; aceitar texto ou CSV/XLSX, preservando zeros.
2. Gerar Dry Run: leitura de SKU exato, ID, principal, galeria, documentos WCDA,
   estado atual/proposto, payloads, arquivos preservados e bloqueios. Nunca cria produto.
3. Revisar e aprovar. A aprovação registra usuário, data e hash do Dry Run.
4. Confirmar digitando `EXECUTAR <N> <LOJA>` (por exemplo, `EXECUTAR 1 CHOICE`).
5. O worker revalida organização/destino, empresa, SKU, produto, modo, hash,
   confirmação e identidade atual do executor/aprovador no PostgreSQL.
6. Conferir capacidades WordPress, capturar e verificar backup, reler o produto e
   checar novamente a autorização antes da escrita.
7. Desvincular somente os arquivos previstos e reler WooCommerce/WordPress.
   Só concluir quando estado e campos protegidos corresponderem ao esperado.
8. Consultar auditoria, baixar relatório/backup, reconferir ou restaurar pela mesma tela.

Não exige staging, SKU liberado previamente, chave de ativação de produção, CLI,
grant temporário, cadastro manual de permissões ou segunda pessoa. Essas configurações
antigas **não são um freio de emergência** para o fluxo novo.

Login, CSRF, organização, aprovação, confirmação, backup, auditoria e releitura permanecem
obrigatórios. Cargo recebido do navegador nunca autoriza escrita: o worker consulta a
identidade persistida, inclusive depois do backup e antes de cada escrita/upload de recuperação.
Mudança de cargo, desativação, organização diferente, fila alterada ou hash inválido bloqueiam.

## Modos e campos enviados

| Modo | Desvincula | Preserva | Gravação |
|---|---|---|---|
| Tudo | principal, galeria, documentos | dados comerciais | WooCommerce `images: []` e WCDA `[]` |
| Galeria | fotos secundárias | principal/documentos | WooCommerce `images: [{id: principal}]` |
| Documentos | entradas WCDA | imagens | WooCommerce `meta_data`, apenas `_wcda_arquivos` com ID existente |
| Principal | imagem principal | galeria/documentos | WordPress `featured_media: 0` |

A WooCommerce promove `images[0]` a principal; por isso remover apenas a principal usa
`POST wp/v2/product/{id}` e a leitura consulta `featured_media`. Galeria não é promovida.
Não há DELETE nem exclusão física da biblioteca. SKU, ID, preço, estoque, publicação, nome,
descrições, categorias, atributos e metadados de outros plugins não são enviados.
Novas prévias incluem também hash dos campos protegidos para detectar mudanças desde o Dry Run.

## Registro da remoção e restauração

Desde 26/10/2026 não há cópia física: imagens e documentos ficam salvos nos servidores da empresa.
Antes de cada remoção o PRM grava e confere (SHA-256 do manifesto) o registro do estado anterior:
principal, galeria, entradas `_wcda_arquivos` e, quando possível, os metadados de cada mídia (ID, URL,
MIME, título, alt). Nada é baixado: arquivo ausente, link quebrado ou host antigo nunca bloqueiam a
remoção. Vale para Choice, SAG e Portwell. `PRM_REMOVAL_BACKUP_*` deixou de ser usado.

Persistência: `data/store_publish/removal_backups/<org>/<loja>/<SKU>/<hash>/` (manifesto, no volume
`store-publish`); backups antigos com arquivos continuam conferidos e baixáveis, mas não são reenviados.

Restaurar exige `RESTAURAR <N> <LOJA>`, identidade válida, registro verificado e produto ainda no estado
pós-remoção. Revincula os IDs originais que ainda existem na biblioteca; mídia apagada depois é listada
(`media_missing`) e não é reenviada. Entradas WCDA voltam exatamente como estavam. Nova releitura antes de
associar impede sobrescrever mudanças concorrentes.
Resposta perdida no upload não causa reenvio cego. A CLI antiga de restauração foi aposentada;
solicite pela interface autenticada, e o worker processa a fila normal.

## Estados e auditoria

Estados visíveis: Dry Run pronto, Aprovado/Pronto para executar, Executando, Concluído,
Bloqueado, Erro e Restaurado. Resultado incerto exige Reconferir, sem regravar automaticamente.
A interface exibe o `detail` real do FastAPI, inclusive listas de erros de validação.

`role_authorized` registra ação, executor, aprovador, hash e `self_approved`.
`role_verified` registra revalidações do worker. Aprovação, backup, envio, verificação,
restauração e recusas operacionais têm eventos próprios; históricos legados são mantidos.

Pausar/cancelar age entre itens, sem interromper a requisição do item em andamento.
Restaurações ainda na fila voltam a um estado restaurável e exigem nova confirmação.
Reprocessar só refaz prévias de erros seguros; itens com possível escrita precisam de reconferência.

## Compatibilidade e banco

Nenhuma migration nova ou destrutiva. Tabelas antigas e logs são preservados.
`store_operation_permissions`, ambientes, grants e `PRM_REMOVAL_PRODUCTION_ALLOWED`
não autorizam nem bloqueiam a remoção role-v1; funções legadas permanecem para histórico/
compatibilidade. `PRM_PUBLISH_*` e `store_publish_grant.py` seguem protegendo outros módulos.

Endpoints antigos de ativação/quatro olhos e alteração de permissões respondem 410,
sem modificar configurações. Consultas de lojas/permissões mostram o acesso efetivo por cargo.
Lotes antigos enfileirados sem confirmação `role-v1` são bloqueados: refazer prévia/reaprovar
e confirmar; não liberar automaticamente uma operação antiga. Backups e journals continuam disponíveis.
Evitar versões antigas e novas de API/worker operando a mesma fila simultaneamente.

## Testes sem lojas reais

```powershell
docker build -t prm:removal-roles-test .
docker run --rm --network none prm:removal-roles-test python -m pytest -q -rs
node --test tests/js/store-file-removal.test.cjs
docker compose --profile workers config --quiet
docker compose -f compose.yaml -f compose.dev.yaml config --quiet
```

Mocks cobrem os dois cargos × três lojas × quatro modos, self-approval, revogação durante
backup, hash/escopo/confirmacão adulterados, SKU, CSRF, isolamento, backup ausente/inválido,
concorrência, restauração e preservação de campos. Nenhum teste envia escrita real.
Node é apenas ferramenta de testes da interface, não dependência do container runtime.

## Docker: implantação posterior, não executada nesta entrega

API, PostgreSQL, gateway e quatro workers permanecem no Compose sem mudanças.
Para ambiente de desenvolvimento isolado sem credenciais, usar nome/porta exclusivos:

```powershell
$env:PRM_DOCKER_PORT = "8012"
docker compose -p prm-remocao-review build api
docker compose -p prm-remocao-review up -d --wait db
docker compose -p prm-remocao-review --profile tools run --rm migrate
docker compose -p prm-remocao-review --profile workers up -d --wait
```

Não executar esses comandos contra o ambiente ativo sem revisar nome, porta e volumes.
Os volumes desse projeto novo começam vazios; não importar dados automaticamente.

Atualização do ambiente existente exige revisão/integração da branch e janela autorizada:
aguardar itens em andamento, pausar filas e guardar backups do PostgreSQL e `store-publish`.
Usar **os mesmos arquivos Compose/overlays e configurações locais já usados na implantação**,
incluindo `compose.integracoes.yaml` se aplicável (não versionado neste worktree).
Reconstruir imagem e recriar somente API e worker-removal com a mesma versão.
Manter um único worker por fila. Não executar `down -v`, trocar nome do projeto existente,
substituir volumes ou copiar credenciais para o repositório.

HTTP local continua aceito; TLS é recomendado para qualquer acesso remoto.
Chamadas às lojas continuam exclusivamente HTTPS. Confirmar login e Testar conexão antes
de uma operação real autorizada. O flag legado de produção não desativa este novo fluxo:
para suspensão operacional, pausar a fila/serviço de remoção; mudar cargo ou desativar usuário
é revalidado antes das escritas.

## Limites conhecidos

- APIs remotas não oferecem transação entre releitura e escrita: há uma janela residual de
  concorrência. Releitura posterior detecta divergência; não é feita correção destrutiva automática.
- Upload de recuperação pode deixar mídia não associada se ocorrer conflito posterior; auditar
  e revisar, nunca excluir automaticamente.
- Cache da loja pode produzir estado incerto; usar Reconferir.
- CDN não autorizada, backup ausente e caminhos Windows excessivamente longos podem bloquear.
- O fallback Playwright foi preservado; não é executado por este módulo.
