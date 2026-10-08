# Digitalização persistente e pasta do produto

Atualizado em 08/10/2026. Este fluxo salva artefatos reais no backend antes de qualquer preparação para WooCommerce. Não há escrita automática em loja nem no CIGAM.

## Configuração

Por padrão, os arquivos ficam em `data/products/` no projeto (ignorado pelo Git). Para usar outro disco ou pasta de rede Windows, configure `PRM_PRODUCT_STORAGE_ROOT` com **caminho absoluto** no ambiente do processo, por exemplo `D:\PRM\Produtos`. Confirme permissões de leitura/escrita da conta que executa o servidor e inclua a pasta nos backups operacionais. Não aponte para a raiz de um disco ou para uma pasta compartilhada ampla sem definir permissões adequadas.

O Código CIGAM é usado **literalmente** como nome da pasta e do SKU. Zeros à esquerda permanecem. Espaços nas extremidades, caracteres proibidos pelo Windows e nomes reservados são rejeitados com erro; não há renomeação silenciosa. As empresas usam raízes separadas: `<raiz>/choice/<SKU>/`, `<raiz>/sag/<SKU>/` e `<raiz>/portwell/<SKU>/`.

## Fluxo

1. Na Digitalização, selecione empresa, código, nome, fotos e documentos. Escolha a principal e ordene as demais; a ordem visual vira a ordem persistida. Rotação, tamanho e qualidade JPEG são aplicados pelo backend aos arquivos reais.
2. Revise a análise e clique em **Gerar Datasheet**. O PDF da empresa e as fotos processadas são gravados sob `_runs/<id>/`; o navegador recebe o identificador da execução e exibe a prévia processada. O link de PDF passa a ler o arquivo salvo no servidor.
3. Revise o PDF. Em **Finalizar digitalização e gerar pacote**, o backend usa o rascunho salvo, acrescenta os documentos opcionais, monta uma pasta temporária, escreve `manifest.json`, gera um ZIP e testa sua integridade antes de mover a pasta para o destino final.
4. Só após a resposta validada ficam disponíveis **Baixar Pacote Completo**, descrição, prévia WooCommerce e geração de CSV. O CSV exige aprovação explícita e o backend revalida arquivos e ZIP antes de liberá-lo.

Estrutura da primeira versão:

```text
<raiz>/<empresa>/<SKU>/
  Fotos/
    <SKU>_variante.jpg
    <SKU>_foto2.jpg
    ...
  <SKU>_Datasheet.pdf
  <SKU>_Datasheet_Original.pdf   (se enviado)
  <SKU>_Desenho_3D.zip          (se enviado)
  <SKU>_Manual.pdf              (se enviado)
  <SKU>_Certificado.pdf         (se enviado)
  manifest.json
  <SKU>.zip
```

O ZIP interno contém a pasta `<SKU>/` e os artefatos finais, **sem** incluir o próprio ZIP. O manifesto contém empresa, SKU/CIGAM, nomes, caminhos absolutos da pasta/PDF/foto principal, imagens ordenadas, documentos, análise técnica, configurações de processamento, hashes SHA-256, horário UTC, ID, versão e status. A classificação de arquivos usa o manifesto quando ele existe; não decide a foto principal por ordem alfabética.

Uma pasta existente nunca é sobrescrita. O servidor retorna conflito; após confirmação do usuário, a nova versão fica em `<raiz>/<empresa>/_versions/<SKU>/<id>/<SKU>/`, mantendo o nome da pasta final exatamente igual ao código. O manifesto aponta para a versão usada. Alterar empresa, SKU, nome técnico, fotos ou análise invalida a execução no navegador e exige novo datasheet/pacote. Alterações comerciais posteriores (descrição, categorias, atributos) são revisadas separadamente, sem regenerar fotos/PDF.

O ID fica no campo **Identificador da execução** e no armazenamento local do navegador. Após recarregar a página, o PRM consulta o backend e recupera o datasheet ou pacote; também é possível informar o ID manualmente. Rascunhos são recuperáveis, mas arquivos opcionais ainda não finalizados devem ser reenviados. Para auditoria, a rota autenticada `GET /api/v1/digitalizacao/execucoes/<id>` retorna o registro. PDF, fotos e ZIP têm rotas autenticadas próprias. A Digitalização exige perfil `gestor` e CSRF nas operações de escrita.

## Validação e limites

Os testes verificam rotação real, PDF de Choice/SAG/Portwell, pasta e ZIP, recuperação em nova requisição, preservação de zeros, conflito/versionamento, foto principal via manifesto e bloqueio do CSV antes da finalização ou após corrupção do pacote. A geração/consulta de arquivos não grava em WooCommerce. O adaptador de upload e a automação Playwright continuam para a fase posterior, após validação das lojas e autorização explícita para escrita externa.

Não há limpeza automática de rascunhos nem política de retenção; planejar quota e backup antes de uso intensivo. O armazenamento é filesystem, não banco de dados. O teste em compartilhamento de rede real e o teste visual em dispositivo móvel ainda dependem do ambiente operacional.
