# SVG na resolução de imagens — 23/10/2026

## Renderização

SVG é tratado como imagem e sempre entregue como PNG. A renderização usa `resvg-py` 0.5.0 (resvg em Rust, licença MIT; wheels próprias para Windows e Linux, sem biblioteca de sistema).

Não usamos CairoSVG porque ele depende da libcairo, ausente na imagem Docker e no Windows. O PyMuPDF, já instalado, ignora `<style>`/classes, `<symbol>`, herança de gradientes e padrões. Por isso, SVGs exportados pelo Illustrator saíam pretos ou incompletos.

O resvg não tem carregador de rede nem executa scripts. As fontes são somente a DejaVu do projeto, sem varrer fontes do sistema, então o resultado é igual no Windows e no Docker.

## Sanitização

A sanitização fica em `app/services/safe_svg.py` e acontece antes de qualquer parser XML:

- **Removido:**
  - `<?xml ...?>` e demais instruções de processamento, inclusive `xml-stylesheet`;
  - comentários e DOCTYPE, sem baixar o DTD público;
  - metadados e atributos de editores (Inkscape, Sodipodi, Adobe);
  - `xml:base`.
- **Expandido como texto:** entidades internas do DOCTYPE, como `&ns_svg;` do Illustrator, com no máximo 4 níveis e 4 KB cada.
- **Elementos e atributos ativos removidos:**
  - `<script>`, `foreignObject`, `iframe` e animações (`set`/`animate`);
  - eventos `on*`;
  - `javascript:`.
- **Referências:**
  - `href` só é mantido se apontar para `#id` interno, ou para `data:image/(png|jpeg|gif|webp)` em `<image>`/`<feImage>`;
  - qualquer outro `href` é removido: http/https, `file:`, caminhos locais, SVG embutido.
- **CSS:** `@import`, `@font-face` e qualquer `url()` que não seja `#id` são removidos, tanto em `<style>` quanto em `style=""`.
- **Falha só daquele arquivo** (o lote continua):
  - entidade externa (`SYSTEM`/`PUBLIC`) ou de parâmetro (`%`);
  - entidades recursivas;
  - XML truncado;
  - raiz diferente de `<svg>`;
  - mais de 20 MiB;
  - mais de 100.000 elementos ou profundidade acima de 128.

O manifesto registra a lista do que foi removido, no campo `sanitized`.

## Saída

1. `foto.svg` vira `foto.png` no mesmo diretório, com a resolução escolhida, proporcional, centralizado e com fundo branco.
2. O SVG original vai para `Backup-fotos` e não permanece na pasta convertida.

**Colisão de nomes.** Um `foto.png` que já existia nunca é sobrescrito: ele segue a regra das outras imagens (redimensionado no lugar, com backup). O SVG vira `foto-svg.png`, ou `foto-svg-2.png` e assim por diante. A criação é exclusiva (hard link ou rename sem substituir).

**Manifesto.** `.prm-resolucao.json` registra para cada SVG:

- `source`;
- `output`;
- `converted_from: "svg"`;
- `renamed`;
- `sanitized`;
- `original_sha256`/`output_sha256`;
- `backup`.

A restauração devolve o SVG e remove apenas o PNG gerado, se ele não tiver sido alterado.

## Lote e prévia

- Um SVG que não pode ser convertido gera uma linha de erro, por exemplo `arquivo.svg — Erro ao converter SVG: motivo; original mantido.`. O lote segue para o próximo arquivo.
- O resumo final mostra: Processados, Convertidos, SVG convertidos, Ignorados e Erros.
- No envio pelo navegador, o SVG é aceito só pela extensão e pela assinatura. O conteúdo é tratado na conversão, para que um SVG ruim não bloqueie o envio inteiro.
- Na prévia, o SVG conta como imagem válida e aparece em miniatura via `<img>`. O navegador o desenha como imagem estática, sem scripts e sem recursos externos.
