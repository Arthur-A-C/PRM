# Níveis de acesso — 21/10/2026

## Matriz vigente

| Área | Desenvolvedor | Gestor | Vendedor |
|---|---|---|---|
| Catálogos publicados e comparação de características | Sim | Sim | Sim |
| Reuniões, cards, planner e alertas | Sim | Sim | Sim, com os vínculos de autoria/responsabilidade existentes |
| Dados internos, procedência e qualidade da importação | Sim | Sim | Não |
| Dashboard operacional, importações e digitalização | Sim | Sim | Não |
| Integrações de lojas e cadastro via API | Sim | Sim | Não |
| Criação de contas na própria organização | Sim | Sim | Não |

Gestor e desenvolvedor podem acessar os módulos administrativos e criar contas dos três níveis. Desde a atualização de remoção de 22/10/2026, **não possuem permissões operacionais idênticas**: desenvolvedor ativo pode aprovar, executar e restaurar suas próprias remoções com dispensa auditada de quatro olhos; gestor depende de permissões por loja e outro aprovador autorizado. A administração dos ambientes de remoção exige concessão explícita. Consulte [Remoção de arquivos](REMOCAO_ARQUIVOS.md). Isso não remove as restrições de organização, titularidade dos lotes, CSRF, configuração ou homologação das lojas. Vendedor é redirecionado de `/` e `/comparador` para `/catalogos`; a comparação de produtos selecionados continua disponível. Calendário e alertas fazem parte de reuniões/cards.

As duas contas existentes foram convertidas de gestor para desenvolvedor no banco `prm_mvp`, sem trocar senha, organização, ID ou sessão. Não foram criados usuários fictícios no banco oficial.

## Links para criar contas

Na instalação local:

- <http://127.0.0.1:8000/contas/criar/desenvolvedor>
- <http://127.0.0.1:8000/contas/criar/gestor>
- <http://127.0.0.1:8000/contas/criar/vendedor>

Também disponíveis em **Gestão**. Estes são formulários administrativos, não convites públicos. Faça login com desenvolvedor ou gestor, abra o link e informe nome, e-mail e senha de no mínimo seis caracteres. A conta recebe o nível da rota e a organização do administrador autenticado; o cliente não pode escolher outro tenant. A senha é armazenada com Argon2 e não é retornada. E-mail duplicado retorna 409; CSRF inválido e vendedor retornam 403. Anônimo é encaminhado ao login no GET; POST exige autenticação.

`127.0.0.1` é o computador onde o PRM está rodando. Para acessar por outro computador, substitua a origem por um endereço de PRM já publicado/autorizado. Nenhum túnel ou deploy público foi criado nesta etapa.

## Implementação e migração

- `app/models/identity.py`: `User.role`, constraint `ck_users_role_allowed`; organização permanece em `users.organization_id`.
- `app/services/access.py`: papéis e allowlist de módulos do vendedor; negação por padrão para papéis desconhecidos. Navegação filtrada e remoção de procedência de importação nas respostas de produtos/comparações legadas.
- `app/dependencies.py` / `app/main.py`: guard aplicado aos routers protegidos, inclusive GETs/downloads de digitalização; esconder o menu não é o único controle.
- `app/routers/accounts.py`: formulários protegidos de criação. As verificações antigas de gestor foram ampliadas para desenvolvedor em serviços, routers, templates e seleção de curador do script de reuniões.
- `20261021_0010`: amplia apenas a constraint de papéis. Ramificação a partir de `20261009_0008` permite não aplicar a migração de reuniões pendente. `20261021_0011` une os ramos sem DDL adicional e mantém um único head futuro.
- `scripts/configure_access_levels.py`: por padrão somente audita. `--apply` executa a revisão **0010** e promove somente IDs ativos explicitamente fornecidos, vinculados à organização indicada, na mesma transação. Não promove todos os gestores automaticamente. Downgrade destrutivo é bloqueado.

Exemplo de auditoria, substituindo por IDs efetivamente consultados no ambiente:

```powershell
.\.venv\Scripts\python.exe scripts/configure_access_levels.py --organization UUID_ORGANIZACAO --user UUID_USUARIO
```

Na entrega dos níveis, `prm_mvp` ficou em `20261021_0010`, com duas contas desenvolvedor. Na etapa seguinte de cards/alertas (21/10/2026), foram aplicadas `20261016_0009` e a união `20261021_0011`; essa é a última revisão oficial registrada naquela etapa. O head hoje disponível no repositório é `20261023_0014`; sua aplicação no destino não foi confirmada na revisão documental de 23/10/2026. Nenhum dado de staging foi copiado. Consulte `CARDS_E_ALERTAS.md` para o agendador e os limites da publicação.

## Verificação

Testes com SQLite temporário e mocks: criação nos três níveis por gestor/desenvolvedor, hash da senha, isolamento de organização, duplicidade, CSRF, anônimo, restrição por URL e API, menus e procedência. Testes de reuniões mantêm autoria, responsabilidade e isolamento existentes. Nenhuma chamada de escrita às lojas.

Servidor local reiniciado com autorização do operador em 21/10/2026, na origem `http://127.0.0.1:8000`. Os três links retornaram HTTP 303 para `/login` quando acessados sem sessão (antes retornavam 404); login retornou HTTP 200. Formulários autenticados e criação foram testados com banco temporário, sem cadastrar usuários reais extras.
