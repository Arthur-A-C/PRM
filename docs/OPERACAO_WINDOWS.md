# Operação no Windows

## Desenvolvimento local

Os scripts usam explicitamente `C:\PRM\.venv\Scripts\python.exe`, definem `C:\PRM` como diretório de trabalho e interrompem no primeiro erro. Veja o roteiro no `README.md`.

O bind padrão é `127.0.0.1`. Não altere para a rede interna nem crie regra de firewall sem aprovação do operador de rede. `--reload` é exclusivo para desenvolvimento.

## Serviço permanente

A configuração como serviço Windows ainda não foi executada. Na Fase 6 deve ser escolhido e validado um mecanismo aprovado (por exemplo, gerenciador de serviço corporativo), configurando:

- conta de serviço com privilégio mínimo;
- diretório de trabalho `C:\PRM`;
- variáveis via arquivo protegido, nunca na linha de comando;
- inicialização automática e recuperação após falha;
- logs com rotação e sem segredos;
- processos separados para web e worker.

Não dependa do VS Code nem de uma sessão RDP aberta.

## Backup

O comando abaixo cria um dump com data/hora em `data/backups`, sem colocar a senha na linha de comando ou nos logs:

```powershell
.\.venv\Scripts\python.exe -m scripts.backup_database
```

Em 2026-09-22 foi criado `data/backups/prm_mvp_20260922_134439.dump` antes da migração 0003. O arquivo tem 24.481.003 bytes e seu inventário custom/gzip, com 91 entradas, foi validado por `pg_restore --list`.

Antes da migração 0004 também foi criado `data/backups/prm_mvp_20260922_152540.dump`, com 24.487.679 bytes, SHA-256 `d2c5ad575cb37da52ac05047baa8ff552f7ab6d911a3f3ff88f229cf3b217717` e 107 entradas validadas por `pg_restore --list`.

Antes da migração 0005 foi criado `data/backups/prm_mvp_20260922_155755.dump`, com 24.497.125 bytes, SHA-256 `5ec6d8544670e66c40850cc08e16dd96bf1e0f2e8bd9f8cb696246d884425443` e 127 entradas validadas por `pg_restore --list`.

Antes da migração 0006 foi criado `data/backups/prm_mvp_20260922_163117.dump`, com 24.574.218 bytes, SHA-256 `99bf75f5cb896ca0e2601768cb9417df22b37d08da85877ad117090a9a2baa49` e 147 entradas validadas por `pg_restore --list`.

Antes da migração 0007 foi criado `data/backups/prm_mvp_20260923_150939.dump`, com 24.634.582 bytes, SHA-256 `7dd9ac098cbcdf97b8fe9cc88b484bbe7ae2eb2cda67bef68b7316ac394bea8a`; o inventário foi validado por `pg_restore --list`. Os arquivos XLSX tratados ficam em `data/imports/treated/` e, assim como os originais, não são versionados. Antes de publicar nova saída do pipeline, faça a prévia com `python -m scripts.import_pipeline_enrichment --company <codigo>` e confira a correspondência de códigos; `--commit` grava e recalcula as concorrentes.

A restauração ainda deve ser ensaiada em um banco separado; nunca use o banco operacional como ensaio. Mantenha também uma cópia íntegra das planilhas originais fora da máquina.
