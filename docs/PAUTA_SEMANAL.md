# Pauta Semanal de Desenvolvimento

Acesso: **Reuniões → Pauta Semanal** (`/reunioes/pauta-semanal`), somente gestores e desenvolvedores
da organização. Vendedores não veem a seção nem a API.

Toda sexta-feira, no horário configurado, o PRM prepara um rascunho com o que aconteceu de segunda a
sexta (fuso `America/Sao_Paulo`): commits, pull requests, issues e tarefas do Planner. A equipe revisa,
edita, acrescenta assuntos e decisões, aprova, exporta em PDF e arquiva. As pautas anteriores ficam
pesquisáveis.

## De onde vêm os dados

| Fonte | O que é lido | O que nunca é lido |
|---|---|---|
| GitHub `Arthur-A-C/PRM` | Metadados: PRs (abertos, integrados, fechados), commits por branch (primeira linha da mensagem), issues, responsáveis, rótulos, resultado das verificações (Checks) e comparação de commits | Conteúdo de arquivos, diffs, patches, segredos, Actions secrets |
| Planner do PRM | Tarefas aprovadas/publicadas da organização: concluídas na semana, em andamento, bloqueadas/aguardando, vencidas e com prazo na próxima semana; quantidade de alterações na semana | Transcrições, evidências e propostas não aprovadas; cards de demonstração |

Cada item mostra a origem com link (PR, commit, issue ou card do PRM). Commits que pertencem a um PR
aparecem só dentro do PR; cada evidência entra em **uma** seção.

## Situação: nunca confundir código com entrega

| Situação | Quando |
|---|---|
| Código em branch, sem PR | Commits da semana em branch sem pull request |
| PR aberto / em rascunho | Pull request aberto |
| PR fechado sem integração | Fechado sem merge |
| **Integrado na main — implantação não confirmada** | PR integrado (ou commit direto na main) |
| **Implantado** | Somente se o commit configurado como em produção (`PRM_DEPLOYED_COMMIT`) contém o commit de merge, conferido pela API de comparação do GitHub |
| CI aprovado / com falhas / em andamento | Resultado das verificações do PR. **Testes aprovados não significam entrega** |

Sem `PRM_DEPLOYED_COMMIT`, nada aparece como implantado e a pauta avisa. PRs integrados sem prova de
implantação geram a decisão "Implantação dos PRs integrados".

Seções: Implantado em produção (comprovado) · Integrado na main · Em revisão · Em desenvolvimento ·
Bugs corrigidos (rótulo bug/fix ou título `fix:`/`corrige`, sempre com a situação exata) · Testes e CI ·
Concluído no Planner · Em andamento no Planner · Issues encerradas · PRs encerrados sem integração ·
Pendências · Decisões necessárias · Planejamento da próxima semana · Contribuições por pessoa.

**Decisões necessárias** são derivadas de evidência: PRs integrados aguardando implantação, PRs abertos
sem revisor ou há 3+ dias, CI falhando, issues com rótulo de decisão/pergunta, tarefas bloqueadas ou
aguardando parceiro. As decisões tomadas na reunião são registradas manualmente.

**Contribuições por pessoa** contam somente itens em que a pessoa aparece na evidência (autor ou
responsável). Para unir o login do GitHub ao nome no PRM, preencha "Nomes das pessoas" na configuração
(`Kaue-Borges = Kauê`).

## Inteligência artificial (opcional)

Usa a mesma integração Anthropic das Reuniões (`PRM_MEETING_AI_MODEL`, limites `PRM_MEETING_AI_*`) e pode
ser desligada por organização. A IA recebe somente título, situação, pessoas e rótulos de cada item já
classificado (sem código, diffs, credenciais ou e-mails) e devolve um texto por chave. Cada texto é
verificado antes de ser aceito:

- item inexistente é descartado;
- afirmação de implantação/produção em item que não está implantado é recusada ("implantação não
  confirmada" e "aguarda deploy" não contam como afirmação);
- número de PR/issue que não está na evidência é recusado.

Texto recusado volta para a redação por regras; o resumo segue as mesmas regras. Sem IA (desligada, sem
modelo configurado, fora do ar ou resposta inválida), a pauta é gerada só por regras, com o motivo
indicado na tela.

## Edição, nova geração e ciclo de vida

- **Gerar ou atualizar pauta** coleta de novo e mantém tudo o que foi feito por pessoas: textos editados,
  itens ocultos, resumo editado e anotações. Se a situação de um item editado mudou (por exemplo, o PR foi
  integrado), o item mostra o aviso para revisar o texto; a situação exibida segue sempre a evidência.
- **Anotações**: assuntos, observações e decisões registradas, com autor e horário.
- **Aprovar** congela a pauta (editar exige **Reabrir**). Gerar novamente uma pauta aprovada pede
  confirmação e a devolve para rascunho. **Arquivar** deixa somente leitura; **Desarquivar** volta para rascunho.
- Edições simultâneas: a segunda gravação com versão antiga é recusada ("recarregue antes de salvar").
- **Histórico de alterações**: geração, nova geração, edições, anotações, aprovação, arquivamento e
  exportação, com autor (ou "Agendamento automático").
- **Exportar PDF**: itens visíveis, situação, pessoas, links de origem, anotações e autoria.

## Rascunho automático

O worker de alertas (`scripts/meeting_worker.py --stage alerts`, serviço `worker-alerts`) verifica a cada
minuto. No dia e horário configurados (padrão: sexta 08:00, `America/Sao_Paulo`) prepara o rascunho da
semana uma vez por dia. Pautas aprovadas ou arquivadas nunca são alteradas pelo agendamento; edições
humanas são preservadas. Falhas são registradas sem interromper os alertas.

## Configuração do servidor

```dotenv
# Token fine-grained, somente o repositório Arthur-A-C/PRM, somente leitura:
#   Metadata: read · Contents: read (lista de commits) · Pull requests: read · Issues: read · Checks/Commit statuses: read
PRM_GITHUB_TOKEN=
PRM_GITHUB_REPOSITORY=Arthur-A-C/PRM
# Commit que está rodando em produção, atualizado a cada implantação. Vazio = nada é considerado implantado.
PRM_DEPLOYED_COMMIT=
```

O token fica só no backend (`api` e `worker-alerts`); nunca aparece em respostas, pautas, PDF ou logs.
"Testar acesso ao GitHub" avisa se for um token clássico com escopos amplos. Mensagens de commit e títulos
passam por remoção de padrões de segredo (tokens, chaves, senhas em URL) antes de serem guardados.

## Implantação

1. Backup do PostgreSQL.
2. `docker compose run --rm migrate` (migração `20261023_0013`, somente tabelas novas).
3. Definir `PRM_GITHUB_TOKEN` (e, quando houver, `PRM_DEPLOYED_COMMIT`) no arquivo de ambiente do servidor
   para `api` e `worker-alerts`; recriar somente esses dois serviços.
4. Abrir a Pauta Semanal, ajustar a configuração e usar "Testar acesso ao GitHub".

Sem token, a pauta funciona apenas com o Planner e avisa que o GitHub não está configurado.

## Limitações

- Até 30 branches e até 30 PRs detalhados por semana (commits, checks e prova de implantação); acima disso
  a pauta avisa que a lista foi limitada.
- "Implantado" depende de `PRM_DEPLOYED_COMMIT` estar atualizado; o PRM não descobre sozinho o que roda no servidor.
- Bugs são identificados por rótulos e prefixos de título; itens sem essa marcação aparecem na seção da sua situação.
- A geração manual roda na requisição (coleta + IA); com IA lenta pode levar alguns segundos.
