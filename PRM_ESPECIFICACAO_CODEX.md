# PRM — Dashboard de inteligência de catálogos e colaboração

Versão da especificação: 1.0 • 22/09/2026

Documento de implementação para o Codex no VS Code. Idioma da aplicação: português do Brasil.

## 1. Instrução inicial ao agente de desenvolvimento

Implemente um protótipo funcional seguindo este documento, trabalhando na pasta local do projeto. Comece inspecionando os arquivos e dependências existentes, sem substituir trabalho anterior. Execute as fases em ordem, valide cada entrega e registre o progresso em `docs/STATUS.md`. Não se limite a apresentar um plano: produza código, migrações, telas, testes e instruções de execução.

O resultado deve ser uma aplicação real com persistência em PostgreSQL, não apenas uma maquete preenchida com dados fictícios. Implemente primeiro a importação, navegação visual e comparação; em seguida, cards e alertas. O projeto deve funcionar sem uma chave de IA e sem n8n configurado. Integrações externas são adaptadores opcionais.

Se faltarem credenciais, crie `.env.example`, continue o trabalho que não depende delas e explique exatamente o que o operador deve configurar. Não afirme que uma conexão ou integração foi testada se ela não foi. Não solicite senhas no chat nem as inclua em logs. Respeite instruções locais e permissões do ambiente.

### Como o usuário deve preparar o projeto

1. Colocar este documento em `C:\PRM\PRM_ESPECIFICACAO_CODEX.md`.
2. Colocar a planilha em `C:\PRM\data\imports\produtos_ecoautomacao.xlsx`.
3. Abrir `C:\PRM` no VS Code.
4. Pedir ao Codex: “Leia PRM_ESPECIFICACAO_CODEX.md, inspecione o ambiente existente e implemente o MVP por fases. Preserve o banco e arquivos existentes. Documente progresso, testes e pendências para continuidade.”

## 2. Objetivo e contexto confirmado

Criar um dashboard interno para comparar ofertas de produtos das empresas **Portwell**, **Choice Tech** e **Eco Automação**, explorar características e aplicações, produzir cards interativos compartilháveis e acompanhar compromissos individuais com supervisão do gestor.

Ambiente informado pelo usuário:

- Windows, em uma máquina simples da empresa, acessada remotamente.
- Pasta de trabalho prevista: `C:\PRM`.
- Python **3.14.7**, ambiente virtual `.venv`, dependências básicas instaladas e imports verificados pelo usuário.
- PostgreSQL e pgAdmin instalados; banco `prm_mvp`; usuário da aplicação `prm_app`.
- Host local previsto: `127.0.0.1`; porta padrão prevista: `5432`. Conferir a configuração real.
- n8n **Cloud**, com possibilidade de migração futura para hospedagem local.
- Modelos de IA acessados por APIs; nenhum modelo local nem GPU obrigatória.
- Até esta especificação, não há confirmação de API, dashboard, túnel HTTPS ou tabelas de domínio implementados.

O PostgreSQL é o armazenamento operacional. O pgAdmin é uma ferramenta administrativa. Vendedores e gestores usam o dashboard pelo navegador.

## 3. Diagnóstico da planilha recebida — fonte autoritativa inicial

Foi inspecionado o arquivo `produtos_ecoautomacao.xlsx`, com aproximadamente 6,54 MiB, uma aba chamada `Produtos`, 7.946 linhas incluindo cabeçalho e oito colunas.

**Atenção: embora a solicitação descreva um comparativo entre empresas, o arquivo recebido contém somente o catálogo da Eco Automação.** Todos os 7.945 links de produtos pertencem a `ecoautomacao.com.br`. Não há coluna de empresa, nem registros identificados como catálogos separados de Portwell ou Choice Tech. Criar os cadastros dessas duas empresas, mas manter seus catálogos vazios até importação ou cadastro real.

SHA-256 do arquivo inspecionado:

```text
1dbb6be1da1f7f89746638ff3214070e2ad9f6ff949321623a8b4cb393ccca5d
```

### 3.1 Dicionário de origem

| Coluna exata | Significado operacional | Destino proposto |
|---|---|---|
| `Codigo` | Código no catálogo da empresa ofertante | `offers.external_code`, sempre texto |
| `Nome` | Nome original do produto | `offers.name_raw` |
| `link` | Página do produto | `offers.source_url` |
| `Marca` | Marca/fabricante informado | `offers.brand_raw` e referência normalizada |
| `Preco_pix` | Valor numérico da modalidade Pix | Observação de preço `pix` |
| `Preco_cartao` | Valor numérico da modalidade cartão | Observação de preço `cartao` |
| `Estoque` | Situação textual anunciada | `availability_raw` + estado normalizado |
| `Descricao` | Texto livre com especificações, aplicações e conteúdo comercial | Texto original e texto tratado |

Não confundir empresa ofertante com fabricante. Por exemplo, uma oferta da Eco Automação pode ter marca Siemens. `Codigo` não é necessariamente o código do fabricante.

### 3.2 Perfil conferido

| Indicador bruto | Valor |
|---|---:|
| Registros de produto | 7.945 |
| Códigos distintos | 7.945 |
| URLs distintas | 7.945 |
| Marca ausente | 169 |
| Descrição ausente | 1 |
| Preço Pix positivo | 7.333 |
| Preço Pix zero | 612 |
| Preço cartão positivo | 7.333 |
| Preço cartão zero | 612 |
| `Em estoque` | 1.670 |
| `Fora de estoque` | 6.221 |
| `https://schema.org/BackOrder` | 54 |

Principais marcas no campo original: EATON 3.602; SIEMENS 3.066; BUSSMANN 244; REER 223; HUMMEL 173. São contagens de registros, não participação de mercado ou vendas.

A linha 2 contém código `4574`, nome `Produto teste`, preços zero e descrição aparentemente de teste. Preservar o registro na auditoria e propor sua exclusão dos indicadores por uma marcação reversível. Não excluir todos os nomes ou descrições que contenham a palavra “teste”: ela também ocorre em aplicações legítimas.

Existem resíduos como `_x000D_` e `&amp;nbsp;`. Limpar na versão de exibição, preservando o original.

### 3.3 O que não existe no arquivo

- Catálogos Portwell e Choice Tech e vínculos de equivalência entre produtos.
- Categoria, aplicação, protocolos e atributos técnicos em colunas estruturadas.
- Região comercial, UF, cidade ou cobertura de atendimento.
- Moeda explícita, data da coleta, frete, tributos, quantidade da embalagem e condições detalhadas de parcelamento.
- Histórico temporal de preços ou estoque; quantidade disponível.
- Usuários, responsáveis, pedidos, entregas, reuniões e vencimentos.
- Imagens de produtos em uma coluna própria.

Essas ausências não devem virar dados fictícios. Usar estados vazios úteis, campos de complementação e importadores adicionais. Permitir BRL como moeda escolhida no assistente de importação, registrando que foi definida pelo operador, não lida da planilha. Data da importação e data da observação são campos distintos; data da observação começa desconhecida.

## 4. Escopo do protótipo

### Obrigatório na primeira versão funcional

1. Login individual com perfis gestor e vendedor.
2. Importação XLSX/CSV com prévia, validação, histórico e atualização sem duplicação.
3. Visão geral visual, explorador de produtos, comparador e tela de qualidade dos dados.
4. Cadastro de categorias, atributos, aplicações e regiões, com origem e revisão.
5. Importação ou cadastro manual dos catálogos Portwell e Choice Tech.
6. Cards de produto, comparação e análise, com compartilhamento autenticado.
7. Exportação de card em HTML interativo autossuficiente e versão estática para impressão/PDF.
8. Tarefas de entrega, reunião e acompanhamento; alertas persistidos por usuário.
9. Visão do gestor com todos os alertas da organização, filtros e reatribuição.
10. Documentação, migrações e testes dos fluxos críticos.

### Evoluções, sem bloquear o MVP

- Extração de características com IA e revisão humana.
- Atualização automática das fontes via n8n e APIs.
- Notificações externas por e-mail, Teams ou outros canais.
- Integração com ERP/CRM para alimentar entregas reais.
- Busca semântica, mapas detalhados, SSO e recomendações de equivalência.

Não automatizar contatos comerciais, pesquisa web em massa ou envio de mensagens nesta entrega. O foco é o dashboard baseado nos dados recebidos e nos cadastros internos.

## 5. Arquitetura escolhida

Manter uma aplicação modular única, leve, evitando serviços adicionais desnecessários.

| Camada | Tecnologia proposta | Observação |
|---|---|---|
| Backend | FastAPI + Uvicorn | API e páginas no mesmo domínio |
| Interface | Jinja2 + HTML + CSS + JavaScript modular | Sem necessidade de Node.js no MVP |
| Gráficos | Chart.js, versão fixada | Distribuir arquivos locais, registrar licença |
| Persistência | PostgreSQL + SQLAlchemy + Psycopg 3 | Consultas parametrizadas e paginação |
| Migrações | Alembic | Nunca recriar banco existente para atualizar |
| Importação | openpyxl para leitura XLSX; módulo csv para CSV | Não executar macros nem fórmulas |
| Configuração | pydantic-settings | `.env` local fora do Git |
| Senhas | Argon2 por biblioteca mantida | Confirmar versão compatível antes de instalar |
| Tarefas duráveis | Worker Python separado, fila em PostgreSQL | Sem Redis/Celery no piloto |
| Testes | pytest + HTTPX; navegador automatizado se disponível | Testar com PostgreSQL separado |

Dependências já indicadas anteriormente: fastapi, uvicorn, psycopg, sqlalchemy, alembic, pydantic-settings, jinja2, python-multipart e httpx. Inspecionar as versões existentes. Adicionar somente o necessário; registrar versões testadas. Não fazer downgrade do Python automaticamente.

O aplicativo deve iniciar sem chaves de IA. Regras determinísticas e revisão manual permitem o uso inicial completo. Funcionalidades dependentes de serviços externos devem mostrar “Integração não configurada”.

### Organização de código esperada

```text
C:\PRM\
  PRM_ESPECIFICACAO_CODEX.md
  README.md
  CHANGELOG.md
  .env.example
  .gitignore
  requirements.txt
  app/
    main.py
    config.py
    db.py
    models/
    schemas/
    routers/
    services/
    repositories/
    workers/
    templates/
    static/css/
    static/js/
    static/vendor/
  migrations/
  scripts/
  tests/
  docs/
    STATUS.md
    ARQUITETURA.md
    DADOS.md
    API.md
    OPERACAO_WINDOWS.md
    BACKLOG.md
    decisions/
  data/imports/
  data/exports/
```

Dados e exportações reais ficam fora do Git. Não gravar tabelas, credenciais ou lógica de negócio em arquivos JavaScript do navegador.

## 6. Experiência visual e navegação

Barra lateral com abas: **Visão geral**, **Catálogos**, **Comparador**, **Aplicações e regiões**, **Cards**, **Meus alertas**, **Gestão**, **Importações e qualidade**. Usar rotas próprias para cada aba, detalhes em painel lateral e opção “Abrir em nova aba”. Não abrir múltiplas janelas automaticamente.

Design: fundo claro, azul escuro nos títulos, boa hierarquia, espaços em branco e números legíveis. Cores propostas de identificação: Portwell azul, Choice Tech violeta, Eco Automação verde; não apresentá-las como identidade oficial. Cor vermelha reservada a atraso/erro. Diferenciar estados por texto e ícone além de cor.

Desktop prioritário, utilização possível em notebook/tablet; testar 1366×768, 1920×1080 e 390 px de largura. Navegação por teclado, foco visível, labels e contraste. Tooltips também acessíveis por foco. Sem gráficos 3D. Exibir estados de carregamento, erro recuperável, vazio e falta de permissão.

### 6.1 Visão geral

- Indicadores: ofertas no recorte; empresas com catálogo; marcas; cobertura de preço; comparações revisadas; alertas vencidos visíveis ao usuário.
- Barras agrupadas: quantidade de ofertas por empresa e categoria.
- Barras horizontais: principais marcas, com “Outras” quando necessário.
- Distribuição de disponibilidade e cobertura de informações.
- Histograma de preços apenas com valores válidos, moeda e modalidade explícitas.
- Faixa de qualidade: “169 marcas ausentes”, “612 preços Pix não informados” etc., recalculada conforme filtros e exclusões.
- Gráficos clicáveis: selecionar uma barra aplica o filtro e mostra chip removível.
- Sem séries históricas inventadas, mapa preenchido ficticiamente ou indicadores de faturamento sem transações.

Na primeira importação, empresas sem catálogo exibem “Catálogo ainda não importado”. Não exibir ausência de oferta como prova de lacuna de portfólio antes de receber seus dados.

### 6.2 Catálogos

- Grade de cards com empresa, marca, nome, código, categoria, preço/modalidade, disponibilidade, confiança de classificação e origem.
- Busca por código, nome, marca, modelo e descrição; paginação de 24 ou 48 ofertas.
- Alternância opcional para tabela compacta, usada para auditoria e exportação.
- Selecionar de 2 a 4 ofertas para comparar; seleção persistida na navegação.
- Painel de detalhes: descrição, atributos com unidades, aplicações, região, fonte/linha da planilha, histórico e correções.
- Sem URL de imagem: usar ícone da categoria, sem inventar fotografia.
- Sinalização “Informação da planilha; data da coleta desconhecida”, quando aplicável.

### 6.3 Comparador

- Cards alinhados por produto com indicadores e uma matriz técnica secundária.
- Barras de preço com mesma moeda/modalidade e condições conhecidas.
- Destaques “igual”, “diferente”, “não informado”, “incompatível” por requisito, sem converter desconhecido em zero.
- Opção de comparar livremente produtos não equivalentes, com aviso explícito de comparação exploratória.
- Vínculo de equivalência: `nao_avaliado`, `sugerido`, `confirmado`, `rejeitado`; responsável, justificativa e revisão.
- Nome semelhante sozinho não confirma equivalência. Marca + modelo confiáveis e requisitos técnicos devem ser considerados.
- Aprovação humana obrigatória para tratar itens como substitutos comerciais confirmados.
- Diferença percentual, quando comparável: `(preco_nosso - preco_referencia) / preco_referencia * 100`. Referência identificada e preço maior que zero. Positivo significa nossa oferta mais cara; negativo, mais barata. Não chamar essa diferença de margem.
- Não comparar kit com unidade sem conversão explícita e validada; não inferir custo total de cartão sem conhecer parcelas.
- Botões: salvar comparação, criar card, criar tarefa, copiar link interno.

### 6.4 Aplicações e regiões

- Aplicações como etiquetas controladas: aquisição de dados, comunicação industrial, controle, proteção elétrica etc.; categorias iniciais são propostas editáveis, não classificações automaticamente verdadeiras.
- Mostrar cobertura por empresa/aplicação e percentual de registros ainda não classificados.
- Região significa **cobertura comercial cadastrada**, com país, macrorregião, UF e cidade opcionais; separar de país de fabricação e sede do fornecedor.
- Na ausência de geografia, exibir “Região não informada” e botão para cadastro. Não inferir localização por marca ou endereço do site.
- Visão regional inicial por barras e cards; mapa opcional somente com dados reais e dependência/licença documentadas.

### 6.5 Filtros e semântica

Filtros globais: empresa ofertante, marca, categoria, aplicação, região de atendimento, disponibilidade, modalidade/moeda/faixa de preço, qualidade e data da importação. Filtros técnicos aparecem conforme categoria: protocolo, alimentação, IP, interfaces, tamanho de tela, memória etc.

- Múltiplos valores do mesmo filtro usam **OU**. Filtros diferentes usam **E**.
- Exemplos: telas 10 ou 15 polegadas, simultaneamente com empresa Portwell ou Choice Tech.
- Atributos multivalorados usam OU por padrão, com opção explícita “contém todos” quando útil.
- Faixas numéricas inclusivas; unidades compatíveis e normalizadas. “Não informado” é seleção explícita.
- Estado em query string, sem dados sensíveis, com ações limpar, salvar visão e copiar link.
- Contagens de facetas usam todos os demais filtros, ignorando a própria faceta; explicar isso em DADOS.md.
- Todos os gráficos e totais respeitam o mesmo recorte e permissões.
- Evitar contagem duplicada ao juntar aplicações/atributos: contar ofertas distintas.

## 7. Importação, limpeza e atualização

### Fluxo obrigatório

1. Selecionar arquivo e empresa ofertante. Para a planilha fornecida sugerir Eco Automação, pedindo confirmação na interface.
2. Informar moeda e, se conhecida, data da observação.
3. Detectar aba/cabeçalhos; mostrar mapeamento, amostra de 20 linhas e validações.
4. Calcular SHA-256 e verificar importação concluída anterior para a mesma empresa e arquivo.
5. Processar em staging com job persistido, progresso e contadores.
6. Mostrar inseridos, alterados, inalterados, avisos e rejeitados; aprovar publicação do lote.
7. Publicar alterações transacionalmente ou com mecanismo de visibilidade por lote, sem exibir carga parcial como catálogo completo.

Limite inicial sugerido: 20 MiB e 50 mil linhas, configurável. Leitura sequencial de XLSX; limitar tamanho descompactado e rejeitar formato inválido. CSV com codificação/delimitador detectados e confirmação. Campos numéricos textuais brasileiros devem ter parser explícito; valores inválidos vão para revisão.

### Regras de qualidade

- Preservar `raw_row`, nome do arquivo, aba e número da linha.
- `Codigo` é texto; preservar zeros à esquerda. Se o Excel já tiver perdido esses zeros, registrar a limitação.
- Chave de atualização: empresa + código externo. URLs são evidências auxiliares. Sem código: chave alternativa documentada com URL normalizada ou revisão; não juntar por nome silenciosamente.
- Campos ausentes em um importador parcial não apagam dados existentes; campo explicitamente vazio pode limpar somente após prévia e política documentada.
- Não sobrescrever correções humanas silenciosamente. Guardar valor importado e override revisado; conflitos entram em fila.
- Zero de preço: preservar valor bruto, normalizar para nulo com estado `nao_informado`. Não rotular automaticamente “sob consulta”, pois a origem não diz isso.
- `BackOrder` → `sob_encomenda`, preservando texto bruto; não tratar como entrega imediata.
- Limpar escapes e entidades HTML na exibição, com sanitização; nunca renderizar descrição como HTML confiável.
- Não transformar frases genéricas de marketing em especificações comprovadas.
- Identificar unidade e contexto de atributos: 24 V da alimentação não deve ser confundido com tensão máxima dos contatos. Valores contraditórios ficam em revisão.
- Importação repetida do mesmo arquivo concluído: resultado idempotente; nenhum novo produto, snapshot ou alerta duplicado.
- Arquivo atualizado: criar nova observação e histórico apenas quando relevante. Ausência de uma linha não apaga produto; desativação requer opção explícita e prévia.
- Histórico começa nas observações efetivamente recebidas. Não fabricar valores anteriores.

Para Portwell e Choice Tech, oferecer importador com mapeamento de colunas e modelo CSV vazio. Campos mínimos: código e nome; empresa selecionada no upload; URL, marca, preço, categoria, atributos, aplicações e regiões opcionais. Importar cinco registros reais de cada empresa quando fornecidos; antes disso, comparações entre empresas ficam pendentes.

### Extração de atributos

Primeiro usar regras conservadoras e edição manual. Armazenar valor, unidade, texto de evidência e método (`importado`, `regra`, `ia`, `manual`). Distinguir `sugerido` de `revisado`; a fonte da planilha sustenta apenas “declarado no catálogo”, não certificação técnica independente.

IA opcional: amostra de 50–100 produtos antes de escala, limite de custo, saída estruturada validada, cache por hash do conteúdo + versão do extrator. Nenhuma chamada paga automática para os 7.945 registros. Filtrar credenciais/dados internos antes do envio; tratar descrição como conteúdo não confiável, nunca como instrução.

## 8. Cards compartilháveis e exportação

### Tipos e conteúdo

1. **Produto:** oferta, principais atributos, fonte e pendências.
2. **Comparação:** 2–4 ofertas, diferenças e situação da equivalência.
3. **Análise:** gráfico do recorte, filtros e descrição do indicador.

Cada card tem título, autor, versão, data, observações, filtros e origem dos dados. Pode ser guardado em coleções internas e vinculado a tarefas.

### Compartilhamento dentro da aplicação

- URL interna autenticada, ex.: `/cards/{uuid}`; destinatários selecionados por usuários/grupo interno.
- Permissões visualizar, comentar e editar; revogação pelo dono ou gestor.
- Verificar permissão no backend em toda leitura, atualização e exportação. UUID não substitui autorização.
- Usuário compartilhado pode explorar visualmente o recorte autorizado, abrir fontes, expandir detalhes e adicionar comentário se permitido.
- Card não dá acesso a tarefas pessoais, notas privadas ou dados não incluídos no compartilhamento.
- Modalidade `snapshot` como padrão: números congelados na versão salva; modalidade `live` opcional e claramente identificada, recomputada com permissões atuais e data da atualização.
- Mudança relevante na fonte marca snapshot como potencialmente desatualizado, sem alterar silenciosamente a versão.
- Link interno exige acesso à rede/VPN ou à publicação autenticada da aplicação; ele não funciona em qualquer rede só por ter sido copiado.

### Arquivo HTML interativo exportável

Gerar um único `.html` com CSS, JavaScript necessário e somente os dados autorizados do snapshot embutidos. Funcionar offline ao abrir no navegador: abas, expansão de características, alternância de modalidade e tooltips. Evitar dependências de CDN e chamadas à API. Não incorporar credenciais, sessões, URLs privadas de integração ou o catálogo inteiro para um card pequeno.

O arquivo exportado é uma cópia: **não recebe alertas, não grava alterações no sistema e não pode ser revogado depois de entregue**. Mostrar esse comportamento na exportação. Compartilhamento com controle de acesso deve usar o link interno. Não prometer interatividade em anexos renderizados dentro de Outlook/Teams; abrir o HTML no navegador. Não enviar arquivos automaticamente para ninguém.

### Outras exportações

- Layout de impressão para “Salvar como PDF” do navegador; PDF é estático.
- Exportar dados do recorte em CSV UTF-8 com opção compatível com Excel e proteção contra injeção de fórmulas.
- Em CSV, textos que começam com `=`, `+`, `-` ou `@` precisam de neutralização adequada; manter tipos numéricos válidos.
- Exportações identificam empresa, modalidade, moeda, filtros, data e origem. Aplicar limites e permissões no servidor.

## 9. Tarefas, alertas individuais e visão do gestor

Essas informações não estão na planilha. Criar módulo próprio, alimentado manualmente no MVP e por integrações futuras.

### Tarefas

Tipos: `entrega`, `reuniao`, `follow_up`, `revisao_comparacao`, `generica`.

Campos: título, descrição, responsável principal, criador, participantes opcionais, prioridade, estado, prazo, fuso, entidade vinculada, região opcional e observações. Uma entrega permite referência do pedido e data efetiva; uma reunião permite início, término e status de confirmação. Estados de tarefa: aberta, em andamento, concluída, cancelada. Adiamento de notificação não altera prazo de tarefa.

Regras iniciais, editáveis pelo gestor:

| Evento | Condição | Destinatário | Encerramento |
|---|---|---|---|
| Entrega atrasada | Prazo vencido, sem entrega efetiva, tarefa não concluída/cancelada | Responsável | Entrega registrada ou cancelamento |
| Reunião próxima | Início nas próximas 24 h, não concluída/cancelada | Responsável e participantes internos | Reunião encerrada/cancelada ou fim da janela |
| Confirmação de reunião pendente | Reunião nas próximas 24 h e confirmação pendente | Responsável | Confirmação ou cancelamento |
| Reunião sem desfecho | Término ultrapassado, sem conclusão/cancelamento | Responsável | Registro do desfecho |
| Acompanhamento vencido | Prazo ultrapassado e tarefa aberta/em andamento | Responsável | Conclusão ou cancelamento |
| Revisão pendente | Revisão atribuída com prazo vencido | Revisor | Revisão concluída |

O gestor vê todos os alertas da organização em uma tela; não precisa receber uma cópia de cada notificação. Escalonamento opcional após 48 h de atraso, configurável e deduplicado.

### Semântica dos alertas

- `lido` é estado individual da notificação; `resolvido` deriva da condição ou do registro de solução. Marcar como lido não resolve entrega atrasada.
- Ações: abrir entidade, marcar lido, adiar notificação, concluir tarefa quando autorizado, reatribuir quando gestor.
- Permitir alerta manual direcionado com assunto, motivo e prazo.
- Vendedor vê os próprios alertas; gestor vê todos no âmbito da organização, com filtros por responsável, prioridade, tipo, região, prazo e situação.
- Resumo do gestor: vencidos por responsável, faixas de atraso, agenda de próximos vencimentos e carga de tarefas. Não expor esses totais a vendedores.
- Registrar autor e data de mudanças de prazo, responsável, estado e solução.

### Execução confiável

Worker separado avalia regras a cada 60 segundos, com relógio e intervalo configuráveis. Persistir tarefas e alertas no PostgreSQL; executar independentemente do navegador. Usar trava no banco para impedir avaliação concorrente duplicada e restrição única por tarefa/regra/destinatário/versão do prazo. Reprocessamentos não devem criar alertas repetidos. Ao alterar prazo, encerrar ou atualizar alertas antigos; ao trocar responsável, ajustar destinatários mantendo auditoria.

Persistir timestamps com fuso em UTC; exibir em `America/Sao_Paulo` por padrão. Se o usuário fornecer só a data, mostrar claramente horário-limite adotado, inicialmente 18h no fuso da organização, antes de salvar. Não usar UTC à meia-noite silenciosamente.

Após reinício, o worker procura todos os atrasos ainda ativos. Registrar heartbeat e mostrar aviso ao gestor se ficar desatualizado. O navegador consulta contagem a cada 30–60 segundos. Sem serviço externo configurado, notificações existem somente dentro da aplicação; não alegar envio de e-mail ou push.

## 10. Modelo de dados proposto

Identificadores internos UUID, datas de criação/alteração e chaves estrangeiras. Ofertas são a unidade de catálogo; um mesmo modelo físico pode ter ofertas de empresas distintas.

| Entidade | Campos/relações essenciais |
|---|---|
| `organizations` | Organização interna, nome e fuso |
| `users` | Organização, nome, e-mail único, hash de senha, perfil, ativo |
| `sessions` | Usuário, token em hash, expiração e revogação |
| `companies` | Nome, domínio, tipo `nossa`/`concorrente`; Portwell, Choice Tech e Eco |
| `brands` | Nome canônico e aliases revisados |
| `imports` | Empresa, arquivo, hash, mapeamento, datas, estado e contadores |
| `import_rows` | Lote, linha/aba, JSON original, avisos, erros e publicação |
| `offers` | Empresa, código, URL, nome, marca, categoria, descrição, disponibilidade, ativo, exclusão analítica |
| `offer_observations` | Oferta, lote, valores originais, preços Decimal, moeda, modalidade, data observada opcional, data importada |
| `attribute_definitions` | Categoria, chave, tipo, unidade, comparabilidade |
| `offer_attributes` | Oferta, atributo, valor tipado, unidade, método, evidência, revisão |
| `applications` / `offer_applications` | Vocabulário e relações com status de revisão |
| `regions` / `offer_regions` | Cobertura comercial, origem e validade |
| `comparisons` / `comparison_items` | Criador, ofertas ordenadas, requisitos, modo e conclusão |
| `equivalence_reviews` | Par de ofertas, status, justificativa, revisor e data |
| `saved_views` | Usuário, filtros versionados e nome |
| `cards` / `card_versions` | Autor, tipo, snapshot/filtros, versão, fonte e estado |
| `card_shares` / `card_comments` | Destinatários/permissões, revogação e comentários |
| `tasks` / `task_participants` | Tipo, responsável, prazo, estado e vínculos |
| `alerts` / `notification_receipts` | Condição, destinatário, lido, adiado, resolvido e chave idempotente |
| `jobs` | Tipo, estado, payload, tentativas, lease, progresso e erro sanitizado |
| `audit_events` | Usuário/serviço, ação, entidade, antes/depois sanitizados e timestamp |

Usar tabelas associativas em vez de listas separadas por vírgula. JSONB serve ao bruto e snapshot, não deve impedir filtros indexados sobre atributos normalizados. Índices em empresa+código (único), categoria, marca, status, prazo, responsável e destinatário. Preços em `NUMERIC`, nunca float monetário. Não deduplicar ofertas de empresas diferentes pelo código.

## 11. API e contratos de integração

Rotas sugeridas, versionadas em `/api/v1`. Documentar exemplos e respostas reais em `docs/API.md`.

| Rotas | Operações |
|---|---|
| `/auth/login`, `/auth/logout`, `/auth/me` | Sessão do usuário |
| `/companies`, `/brands`, `/categories`, `/applications`, `/regions` | Cadastros e facetas |
| `/imports/preview`, `/imports/{id}/commit`, `/imports/{id}` | Prévia, publicação e progresso |
| `/products`, `/products/{id}`, `/products/{id}/attributes` | Ofertas e atributos; nomenclatura UI “produtos” |
| `/dashboard/summary`, `/dashboard/charts`, `/filters/options` | Agregados e opções filtradas |
| `/comparisons`, `/comparisons/{id}` | Comparações persistidas |
| `/cards`, `/cards/{id}/shares`, `/cards/{id}/export` | Cards, ACL e exportações |
| `/tasks`, `/tasks/{id}` | Compromissos e alterações |
| `/alerts/mine`, `/alerts/{id}/read`, `/alerts/{id}/snooze` | Caixa pessoal |
| `/management/alerts`, `/management/summary` | Apenas gestor/admin autorizado |
| `/integrations/n8n/results` | Recebimento opcional de resultados |
| `/health/live`, `/health/ready` | Processo e disponibilidade de dependências, sem segredos |

GET não altera dados. Validação no backend, erros legíveis e códigos 400/401/403/404/409/422 conforme o caso. Listagens paginadas; filtros com validação de campos e limite de tamanho. Nunca expor execução de SQL arbitrário.

Integração futura com n8n Cloud: `request_id`, `schema_version`, tipo do job e referências internas no payload; credencial de serviço com escopo mínimo e chave idempotente. Aplicar limites, registrar origem e validar resultados antes de publicação. O n8n Cloud não acessa `127.0.0.1` ou IP privado da empresa. Quando ativado, usar endpoint HTTPS autenticado com conectividade configurada; não abrir PostgreSQL diretamente à internet. Sem túnel, a aplicação local continua funcional.

## 12. Autenticação e permissões

- Perfis MVP: vendedor e gestor. Administração técnica pode ser um perfil separado sem ser confundida com usuário PostgreSQL.
- Gestor gerencia importações, taxonomias, usuários, compartilhamentos e alertas da organização.
- Vendedor consulta catálogos, cria comparações/cards e gerencia tarefas próprias. Não pode atribuir tarefas a terceiros sem permissão.
- Sessão em cookie HttpOnly, SameSite e Secure em HTTPS; CSRF em mutações autenticadas por cookie; logout revoga sessão.
- Backend aplica escopo em consultas, exportações, gráficos e downloads. Botão oculto não é proteção.
- Criar primeiro gestor via comando local com senha digitada em prompt; não distribuir senha padrão.
- Dados de planilha e comentários devem ser escapados. HTML de exportação precisa serializar dados sem permitir fechamento malicioso de tags script.
- Upload e exportação não podem permitir caminhos arbitrários ou acesso a arquivos do servidor.
- `.env` não entra no Git; `.env.example` contém somente nomes e placeholders.
- Registrar eventos úteis sem gravar senha, token, cookie ou payload sensível desnecessário.

## 13. Indicadores e regras de cálculo

| Indicador | Regra |
|---|---|
| Ofertas cadastradas | Contagem distinta por empresa+código, conforme política de ativos e exclusões |
| Cobertura de preço | Ofertas com preço válido na modalidade selecionada / ofertas no recorte |
| Preço mediano | Mediana de preços positivos comparáveis, com moeda/modalidade explícitas |
| Cobertura de atributos | Campos preenchidos / campos aplicáveis à categoria; mostrar revisados separadamente |
| Cobertura de aplicação | Ofertas com ao menos uma aplicação revisada / ofertas no recorte |
| Atrasos | Tarefas vencidas e não concluídas/canceladas, conforme permissão |
| Comparações confirmadas | Comparações ou pares revisados; explicar unidade no rótulo |

Não calcular média de preço de categorias heterogêneas como indicador de competitividade. Não chamar proporção de registros de market share. Não chamar diferenças de catálogo de demanda. Gráficos de atributos multivalorados podem somar mais de 100%; usar denominador e legenda explícitos. Gráficos iniciais retratam a planilha importada, não estoque em tempo real.

## 14. Critérios de aceite e testes

### Importação e integridade

- [ ] Importação bruta conserva 7.945 registros e todos os oito campos originais.
- [ ] Contagens brutas de preços/estoque/marcas reproduzem a seção 3 antes de qualquer exclusão analítica.
- [ ] Todos os registros iniciais são atribuídos à Eco; Portwell/Choice ficam sem ofertas reais.
- [ ] Registro `4574` pode ser excluído reversivelmente dos indicadores; totais indicam a exclusão. O bruto continua 7.945.
- [ ] Reimportar o mesmo arquivo não duplica ofertas nem histórico.
- [ ] Preço zero não vira “grátis”; BackOrder não vira “Em estoque”.
- [ ] Atualizar um arquivo preserva revisão humana e sinaliza conflitos.

### Experiência e comparações

- [ ] Multisseleção usa OU dentro da faceta e E entre facetas, refletida em todos os gráficos.
- [ ] URL de uma visão restaura filtros; permissão continua sendo verificada.
- [ ] Gráficos funcionam com recortes vazios e campos ausentes.
- [ ] Comparador aceita 2–4 ofertas e não calcula percentual com referência zero ou desconhecida.
- [ ] Região vazia não gera mapa com dados inventados.
- [ ] Comparação real entre as três empresas fica explicitamente pendente até receber seus catálogos; testes automatizados usam fixtures sintéticas isoladas, nunca misturadas aos dados reais.

### Compartilhamento e alertas

- [ ] Card compartilhado funciona para destinatário; acesso por URL direta de outro usuário retorna negação.
- [ ] Revogar acesso bloqueia a próxima consulta online.
- [ ] HTML exportado abre sem internet e contém apenas o snapshot autorizado.
- [ ] Impressão/PDF é identificada como estática.
- [ ] Com vendedor A e B, A não consegue ler ou exportar alertas de B; gestor vê ambos.
- [ ] Entrega vencida gera alerta sem navegador aberto; marcar lido não resolve atraso.
- [ ] Resolver tarefa encerra alerta; mudar prazo/responsável produz atualização coerente.
- [ ] Reiniciar worker não perde alertas nem gera duplicados.
- [ ] Testes cobrem meia-noite UTC, horário local, adiamento e cancelamento.

### Operação e desempenho

- [ ] PostgreSQL real usado nos testes de migração, índices e concorrência, em banco de teste separado.
- [ ] Migrações não removem dados do usuário e possuem estratégia documentada de recuperação.
- [ ] Navegador não carrega as 7.945 descrições para montar a primeira tela.
- [ ] Medir latência no servidor real; meta inicial p95 abaixo de 2 s para filtros usuais, com 5 usuários ativos. Meta sujeita a medição, não promessa.
- [ ] Importação mostra progresso e não bloqueia navegação.
- [ ] Reinício do Windows recupera aplicação e worker quando serviços estiverem configurados.
- [ ] Backup e restauração testados em ambiente separado.

## 15. Plano de implementação e entregas

Estimativa de planejamento: 4–6 semanas para uma pessoa com apoio comercial, sujeita ao ambiente e ao escopo de acabamento. Implementar verticalmente, sem deixar toda a persistência para o fim.

| Fase | Entrega | Aceite para seguir |
|---|---|---|
| 0 — Inspeção | Inventário de arquivos, Python, dependências, banco e planilha | Relatório real do ambiente; nada sobrescrito |
| 1 — Fundação | FastAPI, configuração, sessão, migrações e shell visual | Login e página conectada ao banco |
| 2 — Dados | Importador, staging, qualidade, cadastro multiempresa | Contagens reconciliadas; reimportação idempotente |
| 3 — Exploração | Gráficos, filtros, grade, detalhes e comparador | Fluxo exploratório real e origem consultável |
| 4 — Colaboração | Cards, permissões, links, HTML e impressão | Exportação offline e acesso por destinatário testados |
| 5 — Alertas | Tarefas, worker, caixa pessoal e supervisão | Regras, fuso e deduplicação validados |
| 6 — Operação | Documentação, scripts Windows, backup e regressão | Reinício e roteiro de uso demonstrados |

Primeiro marco demonstrável: importar o arquivo, abrir o dashboard com gráficos reais e filtrar ofertas Eco por marca, disponibilidade e preço. Portwell e Choice aparecem com ação “Importar catálogo”.

Segundo marco: carregar registros reais adicionais ou usar fixtures exclusivamente no ambiente de teste para validar comparação entre empresas.

## 16. Execução e manutenção no Windows

Criar scripts PowerShell claros para setup, migração, criação de usuário, execução web e worker. Usar o Python de `.venv` explicitamente. Para desenvolvimento local, servidor na interface loopback; para acesso interno, configurar bind e firewall apenas conforme rede aprovada pelo operador. Documentar que `--reload` é só desenvolvimento.

Documentar configuração de serviço Windows por mecanismo escolhido e validado, incluindo inicialização automática, diretório de trabalho, usuário do serviço, logs, recuperação após falha e variáveis de ambiente. Agendamentos não podem depender do VS Code aberto nem da sessão RDP ativa. Não configurar publicação externa sem instrução do usuário.

Backups incluem banco e arquivos originais necessários à rastreabilidade; manter cópia fora da máquina. O README deve conter restauração, atualização com Alembic e rollback operacional. No MVP, o usuário existente pode ser mantido; documentar futura separação de credencial de migração e credencial de execução com privilégio mínimo.

### Documentos que devem ser mantidos a cada melhoria

- `STATUS.md`: última fase concluída, testes feitos, falhas conhecidas e próxima tarefa concreta.
- `BACKLOG.md`: itens por prioridade, dependências e critérios de aceite.
- `DADOS.md`: mapeamentos, tratamento de nulos, definições de indicadores e origem dos campos.
- `API.md`: contratos, exemplos sem segredos, autenticação e idempotência.
- `ARQUITETURA.md`: módulos, fluxo de dados e decisões de implementação.
- `decisions/`: pequenas decisões datadas quando houver mudança de arquitetura.
- `CHANGELOG.md`: comportamento alterado, migrações e incompatibilidades.

Não depender da memória de uma conversa para continuar o projeto. Em uma nova sessão, ler esta especificação, `STATUS.md`, `BACKLOG.md` e os arquivos afetados. Preservar IDs e históricos ao evoluir. Se requisitos mudarem, atualizar a especificação com justificativa e versão.

## 17. Demonstração final esperada

1. Gestor entra e importa a planilha Eco com prévia e alertas de qualidade.
2. Visualiza gráficos reais e filtra marcas, disponibilidade e preços.
3. Abre um produto, confere a linha de origem e revisa um atributo.
4. Compara duas ofertas e salva a análise, sem alegar equivalência não verificada.
5. Cria um card, compartilha com um vendedor e exporta HTML interativo.
6. Cria uma tarefa de entrega vencida e uma reunião futura para usuários distintos.
7. Vendedores veem somente seus alertas; gestor consulta todos e reatribui uma tarefa.
8. Marca entrega como concluída e verifica resolução do alerta.
9. Reimporta o mesmo arquivo e comprova ausência de duplicação.
10. Reinicia serviços e demonstra persistência de dados e recuperação do worker.

Relatar ao fim o que foi implementado, comandos exatos de execução, verificações realizadas, funcionalidades ainda pendentes e dados adicionais necessários. Não anunciar envio de notificações externas ou integração n8n sem teste real.

## 18. Referências técnicas e limites da especificação

- Dados: inspeção direta de `produtos_ecoautomacao.xlsx`, aba `Produtos`, em 22/09/2026. Não houve validação externa das alegações comerciais dos produtos.
- FastAPI / templates: https://fastapi.tiangolo.com/advanced/templates/
- Chart.js: https://www.chartjs.org/docs/latest/
- openpyxl: https://openpyxl.readthedocs.io/en/stable/

As escolhas e regras de negócio deste documento são propostas para implementação. Confirmar versões e compatibilidade das dependências no ambiente real. Não tratar a existência deste documento como evidência de que o aplicativo já foi construído.
