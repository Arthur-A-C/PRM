# Operação no Windows

## Desenvolvimento local

Os scripts usam explicitamente `C:\PRM\.venv\Scripts\python.exe`, definem `C:\PRM` como diretório de trabalho e interrompem no primeiro erro. Veja o roteiro no `README.md`.

O bind padrão é `127.0.0.1`. Não altere para a rede interna nem crie regra de firewall sem aprovação do operador de rede. `--reload` é exclusivo para desenvolvimento.

Se uma alteração de rota Python aparecer como HTTP 404 enquanto arquivos de estilo/JavaScript novos já aparecem, o servidor provavelmente está usando código carregado antes da alteração. No terminal em que o PRM está rodando, encerre-o com `Ctrl+C` e inicie novamente em `C:\PRM`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Em desenvolvimento, acrescente `--reload` para recarregar mudanças futuras. Não encerre processos pela porta sem confirmar que pertencem à instância do PRM. A página estática de compatibilidade da comparação direta funciona mesmo antes desse reinício; após ele, redireciona para a rota completa com atributos tratados.

## Serviço permanente

A configuração como serviço Windows ainda não foi executada. Na Fase 6 deve ser escolhido e validado um mecanismo aprovado (por exemplo, gerenciador de serviço corporativo), configurando:

- conta de serviço com privilégio mínimo;
- diretório de trabalho `C:\PRM`;
- variáveis via arquivo protegido, nunca na linha de comando;
- inicialização automática e recuperação após falha;
- logs com rotação e sem segredos;
- processos separados para web e worker.

Não dependa do VS Code nem de uma sessão RDP aberta.

## Prévia pública temporária para a equipe

Para testes externos pontuais, `scripts.public_preview` executa uma instância separada em `127.0.0.1:8002` com cookie de sessão `Secure`, uma senha HTTP Basic adicional e um Cloudflare Quick Tunnel HTTPS. Não abre porta de entrada no roteador ou firewall. O URL aleatório dura enquanto o processo e a conexão estiverem ativos; não é um endereço de produção nem estável. O tráfego passa pela infraestrutura da Cloudflare. Confirme autorização interna antes de compartilhar dados comerciais com terceiros.

O executável oficial `cloudflared.exe` deve estar em `data/tools/` (ignorado pelo Git). Na pasta `C:\PRM`, execute:

```powershell
.\.venv\Scripts\python.exe -m scripts.public_preview --duration-minutes 120
```

O comando mostra uma URL HTTPS, usuário `prm-preview` e senha aleatória da prévia **uma única vez**. Compartilhe URL e senha por canal restrito. Depois dessa primeira barreira, cada pessoa precisa entrar com uma conta individual do PRM; não compartilhe a senha do gestor. A política atual aceita no mínimo 6 caracteres, embora senhas mais longas sejam recomendadas, especialmente para gestores. Para cadastrar um colega como `vendedor`, com nome/e-mail/senha próprios, execute localmente:

```powershell
.\.venv\Scripts\python.exe -m scripts.create_team_tester
```

O processo encerra automaticamente o túnel e a instância remota após 15–240 minutos (120 por padrão). Para encerrar antes do prazo, em outro terminal:

```powershell
.\.venv\Scripts\python.exe -m scripts.stop_public_preview
```

Ao terminar os testes, desative a conta individual e revogue suas sessões:

```powershell
.\.venv\Scripts\python.exe -m scripts.deactivate_team_tester colega@empresa.com
```

`data/exports/public_preview_status.json` guarda apenas URL, prazo e identificadores dos processos enquanto a prévia está ativa; não guarda a senha. Essa pasta e o binário não são versionados. A prévia não substitui implantação permanente com domínio próprio, gestão de acesso corporativa, monitoramento e políticas de segurança.

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
