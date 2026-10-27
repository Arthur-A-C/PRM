# Variáveis de ambiente

O PRM usa `pydantic-settings`: variáveis da classe `Settings` recebem o prefixo `PRM_`. Algumas integrações antigas (`ANTHROPIC_API_KEY`, `DATASHEET_MODEL` e credenciais das lojas) são lidas pelos serviços próprios e permanecem compatíveis. O arquivo `.env` é local, ignorado pelo Git e nunca deve ser copiado para a imagem Docker.

Use [.env.example](../.env.example) como referência. Os valores ali são exemplos vazios ou locais; nunca copie credenciais reais para documentação, logs, testes ou commits.

## Grupos de configuração

| Grupo | Prefixos principais | Finalidade |
|---|---|---|
| Core e banco | `PRM_DATABASE_URL`, `PRM_ENVIRONMENT`, `PRM_ORGANIZATION_*` | Banco PostgreSQL, ambiente e organização inicial |
| Autenticação | `PRM_SESSION_*`, `PRM_CSRF_*` | Cookies e validade de sessão |
| Catálogos | `PRM_CATALOG_*`, `PRM_MAX_IMPORT_ROWS` | Limites de CSV/XLS/XLSX e importação |
| Uploads | `PRM_UPLOAD_*` | Armazenamento temporário, chunks, quantidade e limite por arquivo |
| Digitalização | `PRM_PRODUCT_STORAGE_ROOT`, `PRM_BATCH_*` | Produtos finalizados e geração em lote |
| Datasheets | `ANTHROPIC_API_KEY`, `DATASHEET_MODEL` | Modelo e chave usados pelo fluxo de datasheets |
| Reuniões | `PRM_MEETING_*`, `PRM_AUDIO_*`, `PRM_ASR_*` | Transcrição, interpretação e retenção |
| Fornecedores | `PRM_SUPPLIER_STORAGE_DIR`, `PRM_SUPPLIER_AI_*` | CRM, coleta segura e IA de fornecedores |
| Lojas | `CHOICE_*`, `SAG_*`, `PORTWELL_*`, `PRM_STORE_*` | WooCommerce e WordPress, separados por loja |
| Cadastro | `PRM_PUBLISH_*`, `PRM_REGISTRATION_*` | Dry Run, filas e escopo de cadastro via API |
| Remoção | `PRM_REMOVAL_*` | Backup e limites do fluxo de remoção |
| GitHub | `PRM_GITHUB_*`, `PRM_DEPLOYED_COMMIT` | Pauta semanal e identificação do código implantado |

## Convenção de IA

Configurações de negócio ficam separadas por módulo:

- reuniões: `PRM_MEETING_AI_*`;
- fornecedores: `PRM_SUPPLIER_AI_*`;
- datasheets: nomes legados `ANTHROPIC_API_KEY` e `DATASHEET_MODEL`.

`PRM_SUPPLIER_AI_ALLOW_SHARED_KEY=false` é o padrão seguro. Quando ativada explicitamente, a IA de fornecedores pode reutilizar `ANTHROPIC_API_KEY`; o modelo continua sendo definido somente por `PRM_SUPPLIER_AI_MODEL`. Não existem variáveis oficiais `PRM_SUPPLIER_ANTHROPIC_*`.

Os três fluxos mantêm prompts, modelos, limites e contabilização próprios. A criação do cliente Anthropic ainda não está totalmente centralizada; isso foi preservado para não alterar os fluxos críticos durante a consolidação de 27/10/2026.

## Regras operacionais

- `PRM_DATABASE_URL` deve apontar explicitamente para o banco correto antes de migrations.
- Escrita em lojas não deve ser habilitada apenas por mudança de variável; exige o procedimento de Dry Run e autorização do módulo.
- API e worker correspondente precisam compartilhar os mesmos diretórios persistentes.
- `PRM_UPLOAD_MAX_FILE_MIB=1024` representa 1 GiB por arquivo; gateway e worker devem ter limite compatível.
- Em HTTPS, use `PRM_SESSION_COOKIE_SECURE=true`.
- Depois de alterar `.env`, reinicie apenas os processos que precisam reler a configuração.

## Verificação sem revelar segredos

Confira apenas presença e configuração, nunca valores:

```powershell
.\.venv\Scripts\python.exe -c "from app.config import get_settings; s=get_settings(); print(s.environment, bool(s.database_url))"
```

Para as lojas, use os diagnósticos autenticados já existentes e evite imprimir objetos de configuração completos. Consulte [INTEGRACOES_LOJAS.md](INTEGRACOES_LOJAS.md).
