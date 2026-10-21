# WooCommerce e WordPress — etapa de leitura

Evolução posterior: [cadastro preparado para staging](CADASTRO_API_STAGING.md).

Atualização de 21/10/2026: [contrato candidato de `_wcda_arquivos`, Dry Run e homologação controlada](WCDA_HOMOLOGACAO.md). A estrutura foi observada nas três lojas; a gravação e o reconhecimento pelo plugin continuam não homologados. Nenhum PUT real foi executado.
Diagnósticos desta página continuam somente leitura; publicador separado bloqueia
as três lojas em uso e aguarda contrato de documentos.

Implementação local em 20/10/2026. **WooCommerce e WordPress autenticados nas três lojas em 20/10/2026 às 13:57 (São Paulo). Escrita e uploads não homologados.**
O usuário optou por preencher as credenciais diretamente no `.env`.

## Configuração e acesso

Copie os blocos de integrações do `.env.example` para o `.env` real, sem substituir
as outras configurações. Os nomes são:

| Empresa | URL | Variáveis privadas |
|---|---|---|
| Choice | `https://choicetech.com.br` | `CHOICE_WC_KEY`, `CHOICE_WC_SECRET`, `CHOICE_WP_USER`, `CHOICE_WP_APP_PASSWORD` |
| SAG | `https://sagloja.devsplcomunic.com.br` | `SAG_WC_KEY`, `SAG_WC_SECRET`, `SAG_WP_USER`, `SAG_WP_APP_PASSWORD` |
| Portwell | `https://portwell.com.br` | `PORTWELL_WC_KEY`, `PORTWELL_WC_SECRET`, `PORTWELL_WP_USER`, `PORTWELL_WP_APP_PASSWORD` |

URLs configuráveis por `CHOICE_WC_URL`, `SAG_WC_URL`, `PORTWELL_WC_URL`.
Não acrescente `/wp-json`, usuário, senha ou query string. Não use credenciais
Frenet nem a senha comum de login do WordPress. A senha deve ser de aplicativo.
Senhas com espaços podem ser colocadas entre aspas no `.env`.

Configure `PRM_STORE_ORGANIZATION_ID` com o UUID da organização PRM autorizada.
Um administrador do banco pode consultá-lo, somente leitura:

```sql
SELECT id, name FROM organizations;
```

Não é o ID da loja, do usuário WordPress ou de um produto. Somente gestores PRM
dessa organização podem acessar os diagnósticos. O bloqueio padrão, quando o UUID
não está configurado, é intencional; outro tenant não recebe acesso às credenciais
globais da instalação.
O mesmo vínculo passou a proteger a prévia WooCommerce já existente no cadastro;
exportação CSV local e automação Playwright não foram trocadas.

- `PRM_STORE_TIMEOUT_SECONDS=20`: timeout por operação; conexão limitada a 10s.
- `PRM_STORE_STATUS_DIR=data/integrations`: últimos diagnósticos sanitizados em
  SQLite local, separados por organização/empresa. Nenhum segredo é persistido.
- Variáveis do processo prevalecem sobre `.env`. O serviço lê configurações novas
  por chamada, mas reiniciar o servidor evita valores antigos já carregados no
  ambiente por outro componente.
- Aliases legados `PRM_WOO_{EMPRESA}_URL/KEY/SECRET` continuam suportados. Use o novo
  padrão e não mantenha dois conjuntos conflitantes; nomes novos têm preferência.

Após reiniciar, abra **Integrações WooCommerce**, `/integracoes-woocommerce`,
e use **Testar conexão** em cada card. Os resultados das duas APIs e o horário do
último teste permanecem disponíveis após recarregar a página.

Diagnóstico no terminal, na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe scripts/check_store_connections.py
.\.venv\Scripts\python.exe scripts/check_store_connections.py --company choice
# Opcional: somente respostas anônimas, SEM comprovar autenticação
.\.venv\Scripts\python.exe scripts/check_store_connections.py --public
```

O CLI não se passa por um usuário PRM nem grava histórico na interface. O teste pela
interface registra o diagnóstico e exige sessão gestor + organização autorizada +
CSRF. Credenciais nunca são passadas como argumentos da linha de comando.

## Implementação reutilizada e segurança

O cliente `registration_woo_api.WooClient` existente foi ampliado, não substituído
por uma segunda aplicação. Mantém prévia de produto, categorias e atributos; agora
há consulta paginada, detalhes por ID e busca exata por SKU com detecção de
ambiguidade. `WordPressClient` fornece identidade e leitura de mídia.

O transporte compartilhado permite somente endpoints GET específicos. Não possui
operação de publicação, upload ou exclusão. Autenticação Basic em header HTTPS:
Consumer Key/Secret para WooCommerce; usuário/senha de aplicativo para WordPress,
conforme a [documentação WooCommerce](https://woocommerce.github.io/woocommerce-rest-api-docs/)
e a [documentação WordPress](https://developer.wordpress.org/rest-api/using-the-rest-api/authentication/).

TLS permanece validado. Redirecionamentos não são seguidos; nunca se envia segredo
em query string. Proxies de ambiente estão desativados neste transporte; se a rede
exigir proxy corporativo, a configuração deve ser revisada explicitamente, sem
desabilitar a validação do certificado.

Respostas e logs não incluem headers de autenticação, corpos de erro da loja,
e-mails de usuários, valores de metadata ou documentos. Objetos de credenciais
têm repr oculto e Settings usa SecretStr. Erros 401, 403, 404, 429, 5xx, TLS,
timeout, comunicação, resposta HTML e redirecionamento têm mensagens sanitizadas.
Limite de resposta: 4 MiB. Sem retries automáticos nesta etapa.

`.env`, `.env.*` (exceto `.env.example`), `*.env`, `credenciais*.json`,
`credentials*.json`, `secrets*.json` e perfis de automação foram adicionados/
confirmados no `.gitignore`. Nenhum arquivo real de credenciais estava rastreado
entre esses padrões na verificação. Isso não é auditoria integral do histórico Git:
segredos eventualmente publicados no passado precisam de revogação, não só ignore.

## Critérios dos testes

**WooCommerce**

1. GET `/wp-json/wc/v3/products?context=edit&per_page=1&_fields=id,meta_data`
   com credenciais. Exige lista JSON válida.
2. Controle sem autenticação do mesmo recurso protegido, retornando somente IDs.
3. Só confirma autenticação quando a consulta autenticada funciona e a anônima é
   recusada com 401/403. Se responder publicamente, o resultado é inconclusivo.
4. Leitura confirmada não comprova permissão de escrita da chave.

**WordPress**

1. GET `/wp-json/wp/v2/users/me?context=edit&_fields=id,capabilities`.
2. Exige identidade válida, não um índice REST público.
3. GET `/wp-json/wp/v2/media?context=edit&per_page=1&_fields=id`, separado da
   autenticação da conta.
4. Exibe somente capacidades selecionadas: `read`, `upload_files`,
   `edit_products`, `manage_woocommerce`. Pode haver autenticação válida com acesso
   à mídia negado. Capacidade ausente no objeto é tratada como não concedida;
   objeto de capacidades ausente é desconhecido.

Capacidades declaradas não comprovam upload bem-sucedido nem MIME permitido. PNG,
JPG/JPEG, WebP, PDF, ZIP e formatos adicionais continuam **não homologados**.
Plugins, filtros e políticas de segurança podem restringi-los. Nenhum bloqueio é
contornado.

## Resultados reais em 20/10/2026

**Último teste, após correção das senhas de aplicativo:** HTTP 200 autenticado nas
duas APIs das três lojas. Leitura de produtos WooCommerce confirmada com controle
anônimo recusado; identidade WordPress e acesso de leitura à mídia confirmados.
As três contas declararam `read`, `upload_files`, `edit_products` e
`manage_woocommerce`. Nenhum upload ou escrita foi executado; restrições de formatos
e contrato de atualização de `_wcda_arquivos` permanecem pendentes.
`PRM_STORE_ORGANIZATION_ID` ainda vazio impede uso da interface até configuração.

**Histórico anterior (superado pela correção das senhas):**

Atualização após preenchimento do `.env`: WooCommerce retornou HTTP 200 autenticado
nas três lojas, com controle anônimo recusado. WordPress retornou HTTP 401 e código
`incorrect_password` nas três, confirmado por `scripts/check_wordpress_auth.py`.
Conferir usuário e senha de aplicativo específicos de cada instalação. O vínculo
`PRM_STORE_ORGANIZATION_ID` ainda estava vazio e precisa ser preenchido para a UI.
`_wcda_arquivos` apareceu como lista na amostra de metadata de um produto por loja;
isso confirma somente exposição em leitura, não contrato de gravação.

Registro anterior, **antes do preenchimento das credenciais**:

| Loja | WooCommerce anônimo | WordPress anônimo | Autenticação com credenciais |
|---|---|---|---|
| Choice | HTTP 401 | HTTP 401 | Não executada: credenciais ausentes |
| SAG | HTTP 401 | HTTP 401 | Não executada: credenciais ausentes |
| Portwell | HTTP 401 | HTTP 401 | Não executada: credenciais ausentes |

Foram seis GETs reais sem Authorization nas URLs do documento. 401 é esperado
nessa sonda e **não significa que uma chave configurada falhou**, pois nenhuma foi
enviada. A consulta local de configuração retornou `not_configured`,
`attempted=false` e `authenticated=false` nas seis verificações.

Na sonda anterior não havia permissões reais confirmadas. Nenhum produto, mídia, plugin ou configuração
das lojas foi alterado. Resultados de testes simulados não preenchem este gate.

## Auditoria do script fornecido e `wcda_arquivos`

O anexo `bb098790-1270-4ced-a1a6-da38ea0e56aa/Pasted text.txt` foi lido integralmente.
Contém o dashboard Flask/Playwright antigo. Nenhum frontend Flask foi copiado e a
automação atual não foi removida/executada.

Mapeamento para a próxima etapa:

| Regra do script | Reuso/preparação no PRM |
|---|---|
| CSV/XLSX, SKU/CIGAM e zeros iniciais | serviços `registration_sheets`, `registration_woo_csv`; regressões existentes preservadas |
| Pasta com nome exato do SKU | `registration_files.find_product_folder`, rejeitando ambiguidade |
| Principal `_variante`, imagens numeradas, galeria | `registration_files.classify_files` |
| Datasheet, manual, desenho 3D, certificado | classificação existente + `store_registration_plan.prepare_files` |
| Uma categoria: nome genérico; várias: descrição individual | planejamento puro de labels, com sufixo para duplicatas |
| Produto existente pelo SKU exato | `WooClient.find_by_sku`, sem atualização |
| Confirmar persistência após salvar | gate futuro: releitura REST e comparação, ainda sem escrita |
| Lote/erros | preservar fila persistente PRM; não copiar thread/estado Flask em memória |

Diferenças que exigem decisão na próxima etapa: script antigo aceita SVG/GIF como
imagem, enquanto descoberta PRM restringe imagens a PNG/JPG/JPEG/WebP; regra antiga
de `Fotos/` escolhe a última imagem não-`front`, enquanto PRM usa ordenação
determinística/manifesto. Não ampliar formatos ou trocar principal silenciosamente
durante a migração. Testar esses casos com pastas reais antes de substituir automação.

Evidência do campo: `add_download_file` localiza
`input[name^="wcda_arquivos"][name$="[label]"]`; a confirmação procura outros
inputs `wcda_arquivos[index][...]` preenchidos. Isso comprova **nomes de formulário**,
não o nome da chave no banco, serialização, attachment ID versus URL nem contrato
REST. O script não contém PHP de salvamento ou schema do plugin.

O teste WooCommerce procura apenas as chaves `wcda_arquivos` e `_wcda_arquivos` em
`meta_data` de uma amostra de até um produto, registrando só chave/tipo, nunca valor.
Ausência na amostra não prova inexistência. Presença não prova suporte a escrita.
Na primeira sonda sem credenciais, a inspeção não ocorreu. No teste autenticado
posterior, `_wcda_arquivos` foi encontrado como lista nas três amostras; ainda falta
inspecionar o contrato do plugin para qualquer escrita.

Antes de qualquer atualização:

1. Obter o PHP/plugin que registra o metabox e salva os campos, ou acesso autorizado
   somente leitura ao schema/metadata de produto conhecido com downloads.
2. Determinar chave exata, formato, sanitização, validação de attachments e filtros.
3. Conferir exposição REST registrada. Metadados não aparecem automaticamente em
   todo endpoint; registro/schema e permissões importam, conforme
   [extensão da REST API WordPress](https://developer.wordpress.org/rest-api/extending-the-rest-api/modifying-responses/).
4. Se necessário, propor plugin/endpoint específico (não instalado nesta etapa):
   autenticação WordPress por aplicativo, `permission_callback` verificando
   `current_user_can('edit_post', product_id)`, schema estrito, somente o campo
   aprovado, attachments válidos da loja, validação de MIME/tamanho, auditoria sem
   segredos, idempotência e controle de versão para evitar sobrescrita concorrente.
   Nunca expor escrita arbitrária de metadata.
5. Homologar em staging uploads, preservação da galeria/downloads anteriores,
   atualização parcial por ID obtido de SKU exato e releitura pós-gravação.

`store_registration_plan` produz um plano local, não um payload `wcda_arquivos`
inventado. O mapeamento permanece bloqueado até conhecer o schema real.

## Arquivos e contratos

Novos: `store_config.py`, `store_http.py`, `wordpress_api.py`,
`store_connections.py`, `store_registration_plan.py` em `app/services`;
`app/routers/store_integrations.py`; template/CSS/JS `store_integrations.html`,
`store-integrations.css`, `store-integrations.js`; CLI `scripts/check_store_connections.py`;
`tests/test_store_integrations.py` e este guia.

Modificados: cliente `registration_woo_api.py`, `app/main.py`, `app/routers/pages.py`, `app/routers/registration.py`,
`base.html`, `shell.html`, `.env.example`, `.gitignore`, contratos visuais de teste,
README/API/STATUS/CHANGELOG. `.env` real e automação Playwright preservados.

API PRM:

- `GET /api/v1/integracoes/lojas`: últimos resultados sanitizados, sem conexão remota.
- `POST /api/v1/integracoes/lojas/{choice|sag|portwell}/testar`: diagnósticos GET nas
  lojas e persistência local do resultado; exige `X-CSRF-Token`.

Não há endpoints para gravar produtos, mídias ou configurações. Não houve deploy
ou commit automático. Consulte `STATUS.md` para execução de testes e pendências.
