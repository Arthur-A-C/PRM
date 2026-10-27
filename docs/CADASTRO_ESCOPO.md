# Cadastro via API com escopo explícito — 26/10/2026

Checkout PRM-remocao-cargos, branch fix/remocao-autorizacao-cargos. Sem commits/push.

## Escopo
`{"gallery": bool, "documents": bool, "main": bool}` (pelo menos um verdadeiro), escolhido na importação
("O que deseja cadastrar?") e gravado por item em `plan.input.scope`. A API aceita `escopo=gallery,documents,main`
ou `all` e recusa importação sem escopo (422). `Jobs.create(scope=None)` mantém o plano anterior: usado pela
Geração em Lote e pelos lotes já existentes.

- Galeria: só imagens novas (hash), principal atual preservada; a imagem que o padrão da pasta destina à principal
  não entra na galeria sozinha. Produto sem principal + só galeria = bloqueado (a 1ª foto viraria principal sem escolha).
- Documentos: regra WCDA existente (ausente → criado; um válido → reutilizado; duplicado/inválido → bloqueado).
- Principal: escolhida por SKU no Dry Run (`POST /{lote}/principal {sku, sha256}`), entre as imagens daquele SKU;
  a sugestão da pasta é só rotulada. Estado `awaiting_main` até a escolha. Substituição: a principal anterior vai
  para a 2ª posição (galeria); nenhuma mídia é apagada. Imagem já vinculada na galeria é promovida sem novo upload.
- Nada novo para o escopo: estado `nothing` ("Sem alteração"), sem gravação, não é erro.

## Assinatura e worker
`dry_run.registration_scope` (escopo + principal escolhida) entra no hash do Dry Run e `scope_sha256` na binding
de autorização. Mudar escopo (`POST /{lote}/escopo`) ou principal refaz o Dry Run e descarta a aprovação. O worker
revalida (`check_scope`) antes de qualquer upload e monta a ordem de imagens com `scoped_order`: sem `main` a
principal não muda; sem `gallery` nada entra na galeria; sem `documents` o payload não leva `meta_data`.

## Deploy
Overlay `compose.cadastro-escopo.yaml` por último: api e worker-registration em `prm:cadastro-escopo-20261026b`
(inclui o backup SVG da remoção). Banco, volumes, gateway e worker-removal intactos. JS versionado
`?v=20261026-escopo`. Retorno: recriar os dois serviços sem este overlay.

Testes: tests/test_store_registration_scope.py (20), endpoint em test_store_registration_roles.py, JS 11/11.
Suíte do host 851 passam (13 falhas só de test_image_resolution_svg por falta do resvg no host); dentro da
imagem, sem rede, 287 testes relacionados passam incluindo esses.

## Padrão oficial de imagens — 26/10/2026
Pastas sem manifesto PRM, em lotes com escopo: `<SKU>_1.ext` = principal (detectada automaticamente, sem escolha
manual), `<SKU>_2.ext`, `_3`, … = galeria em ordem numérica (2, 3, 10). SKU comparado como texto exato (zeros à
esquerda preservados); extensão sem diferenciar maiúsculas (.jpg/.jpeg/.png/.webp; SVG/GIF são listados como não
enviados, pois o cadastro não os converte). Posição repetida (`_1.png` + `_1.jpg`) bloqueia o SKU. Sem `_1` com
Principal no escopo: "Foto principal não encontrada no padrão <SKU>_1.ext." e escolha manual no Dry Run (nunca `_2`
automaticamente). Nomes fora do padrão são listados e não classificados. Pacotes com manifesto PRM validado seguem a
ordem declarada no manifesto (principal escolhida no Dry Run), como antes.

`dry_run.image_rule` (principal, galeria ordenada com hash, duplicidades, fora do padrão) e
`files_inventory_sha256` (caminho + tamanho de todos os arquivos do SKU) entram no hash. O worker revalida a
classificação (`check_image_rule`) e, antes de qualquer upload, o inventário e o SHA-256 de cada arquivo planejado.

Deploy: overlay `compose.cadastro-padrao-sku.yaml` por último (api + worker-registration em
`prm:cadastro-padrao-sku-20261026`); JS `?v=20261026-padrao-sku`. Retorno: sem esse overlay (cadastro-escopo-20261026b).
Testes: tests/test_store_registration_naming.py (21); suíte do host 873 passam (13 falhas só do resvg ausente no host);
248 relacionados passam dentro da imagem sem rede; JS 12/12.
