# Resolução de imagens em pasta

Acesso: **Digitalização → Resolução de imagens** (`/digitalizacao/resolucao-imagens`),
somente gestores/desenvolvedores.

Converte todas as fotos (JPG, JPEG, PNG, WEBP) de uma pasta e, por padrão, das subpastas para
um quadrado exato (padrão **1500 × 1500 px**), com a imagem inteira proporcional e centralizada
sobre fundo branco — nunca esticada. Nome, extensão e formato são mantidos. PDFs, ZIPs, desenhos
3D e outros documentos não são tocados.

## Uso (pasta do seu computador — padrão)

1. Clique em **Selecionar pasta do computador** e escolha a pasta principal, por exemplo
   `...\Produtos`. Confira quantidade, tamanho, miniaturas e arquivos ignorados.
2. Ajuste **Incluir subpastas** e a **Resolução**; guardar os originais em `Backup-fotos` é
   obrigatório.
3. **Enviar e ver prévia**: a pasta é enviada ao servidor, com progresso e retomada, e a prévia
   mostra pastas, imagens, quantas faltam converter, quantas já foram convertidas pelo PRM, e o
   espaço necessário e livre.
4. Marque a confirmação e clique em **Converter imagens**. Acompanhe concluídas, ignoradas e
   erros; **Parar** interrompe com segurança após o arquivo atual.
5. **Baixar imagens convertidas (ZIP)** traz as imagens nas mesmas subpastas; **Baixar com
   Backup-fotos** inclui os originais. **Descartar arquivos do servidor** apaga a cópia.

O PRM converte uma cópia no servidor. Os arquivos do seu computador não são alterados; substitua-os
pelo conteúdo do ZIP quando quiser. Detalhes do envio: `docs/SELECAO_PASTAS_LOCAIS.md`.

## Uso (pasta no servidor — opcional)

Só aparece, em **Pasta no servidor do PRM (avançado)**, quando `PRM_IMAGE_TOOL_ROOTS` está
configurado. Nesse modo, as imagens são substituídas na própria pasta do servidor e **Restaurar
backups** devolve os originais ao lugar.

Resultado:

```text
Produtos/
  119002000072/foto1.jpg   (1500 × 1500)
  Backup-fotos/
    119002000072/foto1.jpg (original)
    .prm-resolucao.json    (registro da conversão)
```

## Segurança

- Para cada imagem: a nova versão é gerada em memória e gravada em arquivo temporário; o
  original é copiado para `Backup-fotos` (criação exclusiva, conferida por SHA-256) e só então
  o arquivo é substituído por `os.replace` (atômico). Uma falha mantém o original intacto e não
  deixa duas versões na pasta.
- Backup existente nunca é sobrescrito: se for idêntico é reaproveitado; se for diferente, o novo
  recebe nome versionado (`foto1.backup-2.jpg`).
- O registro `.prm-resolucao.json` permite retomar após interrupção e evita reconverter: um
  arquivo é ignorado quando é exatamente a saída gravada pelo PRM.
- A restauração confere o hash do backup e não sobrescreve imagens alteradas depois da conversão.
- `Backup-fotos`, links simbólicos e junctions não são percorridos. Erros são registrados por
  arquivo sem interromper o lote. Uma pasta por vez.

## Acesso do servidor

Somente para o modo de pasta no servidor. Sem `PRM_IMAGE_TOOL_ROOTS`, esse modo fica
desligado e o envio pelo navegador continua disponível. Para ativá-lo, configure no `.env`:

```dotenv
PRM_IMAGE_TOOL_ROOTS=C:\Users\PW\Documents;D:\Fotos
```

Reinicie o servidor após alterar. Pastas de rede só funcionam se o processo do servidor tiver
acesso de leitura e gravação a elas.
