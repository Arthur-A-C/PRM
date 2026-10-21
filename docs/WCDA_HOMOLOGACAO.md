# Documentos adicionais — contrato candidato e homologação

Atualizado em 21/10/2026. **Nenhuma escrita nas lojas foi executada.** A orientação da SPLComunic para tentar `_wcda_arquivos` é uma hipótese de integração, não uma confirmação de persistência/renderização nem autorização para teste em produção. As três origens atuais, inclusive o domínio de desenvolvimento da SAG, são produção.

## Auditoria realizada somente com GET

Consultados produtos existentes pela WooCommerce REST API autenticada, sem imprimir credenciais:

| Loja | Produto | SKU retornado | ID do metadado | Documentos | HTTP |
| --- | --- | --- | --- | --- | --- |
| Choice | 6260 | codmaterialaqui | 92930 | 1 | 200 |
| SAG | 5667 | 230010000099 | 103183 | 4 | 200 |
| Portwell | 5546 | 315003000084 | 88345 | 1 | 200 |

O SKU de Choice parece provisório: é somente uma amostra de leitura, **não** um alvo escolhido para homologação. Os IDs acima foram observados, não criados. A amostra não representa todos os produtos das lojas.

Nas três lojas, `meta_data` contém um objeto com `id`, `key: "_wcda_arquivos"` e `value` como lista JSON. Cada documento observado tem exatamente quatro campos string:

| Campo | Interpretação observada |
| --- | --- |
| `label` | Texto de apresentação/nome do documento |
| `url` | URL pública do arquivo |
| `filename` | Nome do arquivo com extensão |
| `filesize` | Tamanho formatado, como `421.1 KB`, `1.09 MB`; não é tamanho inteiro em bytes |

Não foi encontrado ID individual de documento nem campo de ordenação. O ID é do **metadado inteiro**, não de um arquivo da biblioteca WordPress. Preservamos a posição na lista; a ordem efetiva no frontend ainda deve ser conferida. Não adicionamos `attachment_id`, `id` ou outros campos inventados aos documentos.

Choice: um datasheet KL3-SS-Z, `kl3-ss-z-datasheet-.pdf`, `421.1 KB`. SAG: manual de pareamento (`635.3 KB`), manual Série R (`1.09 MB`), certificado Anatel (`86.7 KB`) e certificado de categoria (`1.22 MB`). Portwell: um datasheet, com URL no domínio legado e `filesize` vazio. **O vazio existente e a URL antiga são preservados**, não corrigidos automaticamente.

## Payload e Dry Run

Endpoint candidato: `PUT /wp-json/wc/v3/products/{id}`. O corpo contém somente `meta_data`, com **um** item: ID observado, chave `_wcda_arquivos` e lista original completa seguida dos documentos novos reais. Outros metadados não são enviados.

Abaixo está o corpo exato da prévia **sem adição** de Portwell, obtido do produto 5546. É uma fotografia real para inspeção, **não um teste de escrita nem um payload com documento novo**. Nenhum PUT foi enviado:

```json
{
  "meta_data": [
    {
      "id": 88345,
      "key": "_wcda_arquivos",
      "value": [
        {
          "label": "Datasheet PPC-19Ri56200UA – Painel PC Industrial 19\" Touch Resistivo Intel Core i5-6200U 8GB DDR3L SSD 128GB Wi-Fi",
          "url": "https://portwellloja.devsplcomunic.com.br/wp-content/uploads/2026/03/Painel-PC-VISION-19.pdf",
          "filename": "Painel-PC-VISION-19.pdf",
          "filesize": ""
        }
      ]
    }
  ]
}
```

Ainda falta indicar o documento novo real para produzir o payload final de adição. Não usamos URL fictícia, valores de exemplo ou lista vazia para essa finalidade.

Comandos de **somente leitura**, na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe scripts/preview_wcda_update.py --company portwell --product-id 5546
.\.venv\Scripts\python.exe scripts/preview_wcda_update.py --company sag --sku 230010000099
```

Para preparar uma adição, acrescente `--documents caminho/do/arquivo.json`, contendo uma lista dos documentos reais nos quatro campos acima. Isso **continua sem escrever**, mesmo com documentos informados. A prévia retorna endpoint, método proposto, payload, contagens e hashes. URLs com tokens/credenciais e campos desconhecidos são ocultados, com `redacted_paths` e `payload_is_exact: false`; o plano interno mantém os valores originais. Não registre o plano bruto em logs públicos. A CLI não retorna headers nem credenciais.

## Serviço implementado e limites

- `app/services/store_document_update.py`: plano imutável em memória, preservação integral dos documentos existentes/ordem/campos extras, seleção por SKU exato e ID confirmado.
- Duplicação por URL e quatro campos iguais é ignorada; mesma URL com informações diferentes, ou mesmo nome/label em outra URL, exige reconciliação. Não há download nem comprovação de conteúdo por hash nesta etapa: arquivos iguais com nomes e URLs diferentes ainda precisam de verificação.
- `known_media_document` aceita mídia WordPress com ID confirmado e usa `source_url`; não insere ID da mídia na estrutura do plugin. Não faz upload.
- Novos documentos exigem quatro campos não vazios e URL HTTPS estável sem credenciais/query/fragmento. Metadado ausente, duplicado, serializado ou lista vazia são bloqueados no primeiro teste, pois precisamos de um estado anterior recuperável.
- `verify_document_update` exige identidade, ID do metadado, lista final exata, prefixo dos documentos antigos preservado e ausência de mudanças nos outros metadados/campos conhecidos. Persistência REST **não** significa frontend ou plugin verificado.
- `simulate_update` executa GET → PUT mínimo → GET **exclusivamente com `httpx.MockTransport`**. Transportes reais são rejeitados; sem retry automático de PUT, inclusive em timeout. Um HTTP 200 que não persistiu os dados é falha de verificação.
- `rollback_payload` prepara restauração apenas se o estado atual coincidir com o pós-teste esperado; não realiza gravação.
- Nenhum endpoint público de escrita foi habilitado. O cadastro em lote mantém documentos bloqueados; este contrato candidato ainda não foi conectado a um executor real. Classificação de fotos/documentos, labels e regras herdadas do script original permanecem inalteradas. Playwright preservado.

## Homologação controlada, ainda NÃO autorizada

1. Empresa confirma por escrito **loja/origem, SKU exato, ID do produto, um documento real, label/URL/nome/tamanho, janela do teste e autorização de rollback**. Preferir documento já disponível na biblioteca, evitando upload; esta etapa não autoriza upload implicitamente.
2. Antes de qualquer futura escrita, preparar executor restrito a esse alvo e payload aprovado, com journal persistente e backup privado integral do produto/metadado/URLs anteriores, hashes e identidade da organização. O plano atual fica em memória; não é um journal de execução real.
3. Conferir produto e documentos atuais no frontend; guardar evidências. Repetir GET imediatamente antes do único PUT; qualquer divergência invalida a prévia. Combinar janela sem edição pela equipe: o GET prévio não é trava atômica nem elimina corrida de concorrência da API.
4. Enviar apenas `_wcda_arquivos` com a lista original mais o documento autorizado. Não atualizar preço, imagem, descrição nem outro metadado. Registrar status HTTP sem headers secretos ou corpo bruto de erro.
5. Fazer GET autenticado e verificar conteúdo completo, documentos anteriores e demais campos. Em timeout, consultar antes de qualquer ação: a requisição pode ter sido persistida. Não repetir PUT cegamente.
6. Verificar a página pública do produto, link/label do documento novo e todos os documentos anteriores, abertura dos arquivos e comportamento do plugin. Não encaminhar autenticação WooCommerce para URLs de arquivos ou outros hosts. Frontend/plugin ainda **não foram verificados** nesta etapa.

### Rollback

Guardar o valor original **antes** da atualização. Corpo de restauração: somente `meta_data` com o mesmo ID/chave e `value` original completo (não lista vazia). O corpo acima ilustra o estado original real da amostra Portwell, mas deverá ser capturado novamente para o alvo autorizado.

Reconsultar antes de restaurar; se houve edição concorrente ou estado inesperado, **não sobrescrever**: reconciliar com a equipe/SPLComunic. Com autorização explícita e estado compatível, enviar somente o corpo de restauração, reconsultar a API e conferir links/frontend antigos. Não excluir arquivos da biblioteca. O serviço apenas prepara esse corpo; nenhuma restauração real foi executada.

## O que ainda depende da SPLComunic

A [documentação oficial de produtos WooCommerce](https://developer.woocommerce.com/docs/apis/rest-api/v3/products) descreve atualização de produto e `meta_data`, mas não comprova o contrato do plugin `_wcda_arquivos`. O ID existente será usado como seletor do metadado, nunca criado ou renumerado. Aceitação da lista pelo servidor e reconhecimento pelo plugin precisam do teste autorizado.

| Resultado do futuro teste | Evidência / solicitação técnica |
| --- | --- |
| 401/403 | Status e código sanitizados; verificar permissões de edição, WAF e liberação da chave protegida |
| 400 | Confirmar schema de gravação, tipos, ID do metadado e sanitização esperada |
| 200 sem persistência | Confirmar se hooks/filtros descartam a chave ou se há outra forma de gravação obrigatória |
| Persistido sem aparecer no frontend | Confirmar leitura/renderização do plugin, cache, hooks pós-salvamento e campos auxiliares |
| Documentos antigos divergentes | Suspender, capturar estado e reconciliar antes de qualquer rollback |

Solicitar contrato de escrita e orientações de invalidação de cache/hooks; acesso ao PHP não é obrigatório se a SPL fornecer essas informações. **Ainda não é possível afirmar que um endpoint personalizado é necessário ou dispensável.** Se a API padrão persistir e o plugin renderizar corretamente, ela pode bastar; caso contrário, a SPL deverá liberar o fluxo padrão ou fornecer endpoint específico com autorização e contrato documentado.

## Testes

Execução em 21/10/2026: `.\.venv\Scripts\python.exe -m pytest -q --tb=short` — **384 aprovados**, sendo 36 do novo serviço, 3 avisos conhecidos de AnyIO/openpyxl. Nenhum PUT dos testes acessa rede.

Mocks cobrem os formatos observados das três lojas, append e ordem, campo antigo vazio, campos extras, deduplicação/conflitos, ausência de estruturas vazias, SKU exato, redaction, preflight, bloqueio de rede real, sucesso/erro/timeout/200 ignorado, alteração concorrente, preservação e rollback. Dados fictícios existem somente nos testes isolados, nunca enviados às lojas.
