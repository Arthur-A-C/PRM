# Colaboração Kaue / Arthur

- `main`: estável; alterações por Pull Request, revisão do outro desenvolvedor e CI verde.
- Kaue: `feature/kaue-<assunto>`; Arthur: `feature/arthur-<assunto>`; correções: `fix/<assunto>`.
- Use clones separados, com identidade Git, `.env`, ambiente Python e credenciais próprias. Não compartilhe worktree suja.
- Antes de iniciar: `git status`, `git diff`, `git fetch origin`. Confirme a base do PR; uma branch funcional não equivale à `main`.
- Adicione caminhos específicos (`git add <arquivo>`); use staging por hunk para arquivos mistos. Não use `git add .`, reset/clean ou force push sobre trabalho compartilhado.
- Não versione dados privados, `.env`, mídias, SQLite, dumps, backups ou transcrições. Nunca coloque segredos em Actions.
- Execute `scripts/docker/prm.ps1 build` e `scripts/docker/prm.ps1 test`; documente skips dependentes de fixtures privadas.
- Cada clone deve ter projeto Compose e porta distintos: `-Project prm-kaue` / `-Project prm-arthur`, `PRM_DOCKER_PORT=8001` / `8002`. Compartilhar volume/fila é proibido.
- Consulte [Docker](docs/DOCKER.md). Não existe deploy automático de produção.

## Proteção da main

Contrato em `.github/rulesets/main.json`: PR, uma aprovação, revisão do último push, resolução de conversas, checks `tests`, `docker`, `security`, sem force push/exclusão.
O JSON preparado **não prova aplicação no GitHub**. Consulte o resultado da auditoria em `docs/INFRA_STATUS.md`.
Repositórios privados exigem plano compatível para enforcement ([GitHub](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)). Não tornar o PRM público para contornar essa restrição.
