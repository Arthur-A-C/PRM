# Infraestrutura — 22/10/2026

## Escopo e autoria

- Handoff Claude lido integralmente; base `cadastro-api-arquivos` em `9b594c7`.
- Worktree inicial com 76 caminhos alterados/não versionados. Alterações funcionais existentes, inclusive reuniões/cards, preservadas e não incluídas nos commits de infraestrutura.
- `requirements.txt` e `.gitattributes` tinham apenas alterações de infraestrutura do handoff. Dockerfile/entrypoint preservados e complementados com Compose, guardas, scripts e CI.
- README e STATUS têm alterações de terceiros: staging somente dos novos blocos de infraestrutura, sem apropriar o restante.

## Resultados locais confirmados

- Build Python 3.14 multi-stage com `pypdf` e `opencv-python-headless`: OK.
- Primeira suíte Linux: 536 passed, 24 skipped, 3 failed por dependência de fixtures locais. Corrigidos testes de dashboard para auditorias sintéticas e detecção de diretório de fixtures vazio (sem copiar dados privados).
- Suíte completa Linux após ajustes: **540 passed, 26 skipped, 1 warning**. Skips de catálogos/transcrições privados e do arquivo Compose deliberadamente excluído da imagem. Aviso de depreciação AnyIO/Starlette.
- Contratos de Compose no host: **2 passed, 1 skipped** (flock somente Linux, exercitado na suíte do container).
- Compose base, dev e override Windows validados com `config --quiet`.
- API, PostgreSQL isolado, gateway e quatro workers iniciados. Logs sem erros de aplicação; health live/ready HTTP 200, incluindo acesso do host à porta 8001.
- Migrações até `20261021_0011` executadas **somente em `prm_docker`**.
- Probe sintético verificado após recriação dos containers: PostgreSQL, SQLite e dez volumes de arquivos preservados. Não inseriu trabalhos de publicação ou IA nas filas.
- Imagem executa sem root, sem `.env`, SQLite ou dumps embutidos. Testes executados sem rede/segredos; runtime app/workers em rede interna.
- Nenhuma gravação WooCommerce, chamada paga de IA, cópia de dados Windows ou alteração do journal do produto 16321. Nenhuma ação sobre serviço/porta 8000.
- Conexão nativa confirmada por container temporário em 8002: `prm_mvp`, `transaction_read_only=on`, readiness HTTP 200. O container de verificação foi removido; seus volumes vazios foram preservados. `docker compose exec` não executa entrypoint automaticamente: a verificação SQL foi repetida passando por `sh docker/entrypoint.sh`, que adapta localhost para o host Windows.
- Worker duplicado recusado com a mensagem de lock; tentativa de conexão TCP externa da API bloqueada pela rede interna.
- Gitleaks 8.28.0 executado sem rede, montando apenas `.git`/ignore (não `.env`); nenhum segredo encontrado nos commits examinados. Dois fingerprints históricos de testes/chave localStorage foram mantidos como exceções específicas do handoff.

## GitHub e limites

- `Arthur-A-C/PRM`: `private: true`, verificado pela API autenticada com credencial Git local; tokens não exibidos. Colaboradores confirmados: Arthur-A-C (admin), Kaue-Borges (write).
- Actions preparado: `tests`, `docker`, `security`; template PR, CODEOWNERS, CONTRIBUTING e JSON da proteção da main. Sem deploy de produção.
- **Proteção da main bloqueada pelo plano GitHub:** consultas de rulesets e branch protection retornaram HTTP 403, “Upgrade to GitHub Pro or make this repository public to enable this feature.” Repositório permanece privado. O JSON não foi apresentado como proteção ativa; proprietário precisa habilitar plano compatível e aplicar o ruleset.
- Worker de remoção e funcionalidades recentes permanecem como dependência de PR funcional: não foram incluídos em commits de infraestrutura. Os quatro workers foram testados no worktree local; clone limpo da branch de infraestrutura ainda depende desse PR para remoção. CI explicita essa ausência e testa os outros três.
- Publicação/CI remoto e verificação do checkout limpo: resultados registrados na continuação desta auditoria, não inferidos do build local.
- Checkout somente dos commits (sem módulos funcionais locais): build aprovado, **425 passed, 26 skipped, 1 warning** no container. A diferença para 540 é a suíte funcional ainda não commitada, não uma perda silenciosa de testes da CI.

Operação e comandos: [DOCKER.md](DOCKER.md). Fluxo Git: [CONTRIBUTING.md](../CONTRIBUTING.md).
