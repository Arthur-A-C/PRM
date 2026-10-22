# Resolução de imagens em pasta

Acesso: **Digitalização → Resolução de imagens** (`/digitalizacao/resolucao-imagens`),
somente gestores/desenvolvedores.

Converte todas as fotos (JPG, JPEG, PNG, WEBP) de uma pasta e, por padrão, das subpastas para
um quadrado exato (padrão **1500 × 1500 px**), com a imagem inteira proporcional e centralizada
sobre fundo branco — nunca esticada. Nome, extensão e formato são mantidos. PDFs, ZIPs, desenhos
3D e outros documentos não são tocados.

## Uso

1. Clique em **Selecionar pasta** (ou cole o caminho completo) e escolha a pasta principal,
   por exemplo `...\Produtos`.
2. Ajuste **Incluir subpastas** e a **Resolução**; "Mover imagens antigas para Backup-fotos"
   é obrigatório.
3. **Ver prévia**: pastas, imagens, quantas faltam converter, quantas já foram convertidas pelo
   PRM, espaço necessário e livre.
4. Marque a confirmação e clique em **Converter imagens**. Acompanhe concluídas, ignoradas e
   erros; **Parar** interrompe com segurança após o arquivo atual.
5. **Restaurar backups** devolve os originais ao lugar.

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

O PRM processa as pastas no próprio servidor. Por padrão só aceita pastas dentro da pasta do
usuário que executa o servidor. Para outras unidades/pastas, configure no `.env`:

```dotenv
PRM_IMAGE_TOOL_ROOTS=C:\Users\PW\Documents;D:\Fotos
```

Reinicie o servidor após alterar. Pastas de rede só funcionam se o processo do servidor tiver
acesso de leitura e gravação a elas.
