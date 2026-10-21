# Cards e alertas operacionais

Atualizado em 21/10/2026.

## Atribuição

Abra `/cards`. Desenvolvedores e gestores veem, em cada card, **Atribuir responsável**, com usuários ativos da própria organização. Selecione desenvolvedor, gestor ou vendedor e clique em **Atribuir**. A opção de atribuição em lote permanece disponível. O nome e o nível ajudam a identificar o destinatário; o vínculo persistido usa o UUID, nunca comparação aproximada do nome.

Em rascunhos, a atribuição não publica automaticamente. Revise, informe prazo (ou aceite explicitamente tarefa sem prazo), aprove e publique. Em cards publicados, a troca de responsável atualiza os alertas imediatamente. Vendedores acessam suas atividades e conservam os limites de autoria/responsabilidade: não podem atribuir a outro usuário.

Dados de staging/demonstração não são cards de trabalho. Os painéis mock foram retirados da navegação operacional, mas seus arquivos/endpoint administrativo foram preservados. Propostas marcadas com `details.simulation` não aparecem nas listas/calendário operacionais e não geram alertas. Não há conversão automática de exemplos em compromissos reais.

## Prazos e destinatários

Somente atividades **publicadas**, não concluídas/canceladas e atribuídas a um usuário ativo da mesma organização notificam:

- Atribuição: aviso ao usuário responsável.
- Até sete dias do prazo: vencimento próximo.
- Dia do prazo: vence hoje.
- Depois do prazo: atraso. Datas sem horário vencem ao terminar o dia no fuso do card; instantes vencem após o horário exato informado.
- Tarefa explicitamente publicada sem prazo: alerta sem prazo; não se inventa vencimento. Eventos exigem data.

Os avisos aparecem em **Meus alertas** (`/alertas`), somente para o destinatário, em qualquer um dos três níveis. A página atualiza a lista a cada 60 segundos enquanto visível. Não há envio automático de e-mail, WhatsApp ou convite externo.

Alterar responsável/prazo resolve avisos da versão anterior. Concluir/cancelar encerra os ativos; reabrir restaura avisos elegíveis. A chave única atividade/versão do prazo/tipo/destinatário evita duplicação a cada ciclo. Um aviso reativado volta a não lido. Ler a API não agenda notificações; edição/publicação e worker são responsáveis pela persistência.

## Operação

O banco oficial agora está em `20261021_0011`. Foram criadas as sete tabelas pendentes do módulo; organizações, usuários, senhas e ofertas foram preservados. Nenhuma reunião/card/alerta de staging foi copiado: a lista oficial inicia vazia, até a criação de cards de reuniões reais. A extração de uma reunião usa o fluxo e workers já documentados em `REUNIOES_PLANNER.md`; esta entrega não executou chamadas pagas de IA.

O agendador exclusivo de alertas foi iniciado localmente em 21/10/2026. Para iniciar após reiniciar o computador, mantenha este comando ativo na pasta oficial do projeto:

```powershell
.\.venv\Scripts\python.exe -m scripts.meeting_worker --stage alerts
```

Para verificar apenas um ciclo (sem deixar um processo ativo):

```powershell
.\.venv\Scripts\python.exe -m scripts.meeting_worker --stage alerts --once
```

Uma trava PostgreSQL impede dois workers da mesma fila. O processo verifica prazos a cada minuto e não invoca Claude, ASR ou lojas. Se o processo parar, novas atribuições/publicações ainda sincronizam imediatamente seus próprios avisos, mas a passagem do tempo exige reiniciar o worker. Não foi criado serviço de inicialização automática do Windows.

## Interface e validação

Cards têm altura uniforme de 32rem (512px com a fonte base atual), colunas responsivas e ações no rodapé. Texto extenso permanece acessível em **Abrir / revisar**; o título também possui tooltip. Conteúdo excepcionalmente extenso pode rolar dentro do card; impressão usa altura livre para não cortar dados.

Testes automatizados cobrem destinatários nos três níveis, limites de organização/usuário ativo, CSRF e versão, alertas privados, proximidade/hoje/atraso, reatribuição, conclusão/reabertura e exclusão de simulações. Teste visual `node scripts/cards_assignment_smoke.cjs` usa Edge isolado, APIs mock e dados sintéticos, sem tocar contas ou atividades reais.
