/* Additive meeting/cards/planner controller. No catalog or digitalization hooks changed. */
(() => {
  'use strict';
  const base = '/api/v1/planner', q = (s, root = document) => root.querySelector(s);
  const csrf = q('input[name=csrf_token]')?.value || '';
  const labels = {draft:'Rascunho',approved:'Aprovado',rejected:'Rejeitado',published:'Publicado',todo:'A fazer',in_progress:'Em andamento',waiting_external:'Aguardando parceiro',blocked:'Bloqueada',done:'Concluída',cancelled:'Cancelada',on_time:'Em dia',attention:'Atenção',prioritize:'Priorizar',overdue:'Vencida',no_deadline:'Sem prazo',unconfirmed:'Prazo a confirmar',assigned:'Atribuição',today:'Vence hoje',soon:'Vencimento próximo'};
  let users = [], me = '', canManage = false, active = null, meetingId = null, meetingData = null, cardRows = [], offset = 0, selected = new Map(), pollTimer;
  let month = new Intl.DateTimeFormat('en-CA', {timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit'}).format(new Date());
  // Intl en-CA month-only may use MM/YYYY; build year/month by parts instead.
  const nowParts = Object.fromEntries(new Intl.DateTimeFormat('en', {timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()).map(p => [p.type,p.value]));
  month = `${nowParts.year}-${nowParts.month}`;
  let band = '', bucket = '';
  const el = (tag, text, cls) => { const node = document.createElement(tag); if(text !== undefined) node.textContent = text; if(cls) node.className = cls; return node; };
  const button = (text, action, cls='cc-btn') => { const node=el('button',text,cls); node.type='button'; node.addEventListener('click',()=>Promise.resolve().then(action).catch(report)); return node; };
  const displayDate = value => value ? value.slice(0,10).split('-').reverse().join('/') : 'Sem data confirmada';
  const username = id => users.find(u=>u.id===id)?.name || (id ? 'Usuário atribuído' : 'Responsável pendente');
  function report(error) { const boxes=[...document.querySelectorAll('[data-meeting-message],[data-cards-message],[data-planner-message],[data-alerts-message]')]; const target = active && q('#activity-dialog')?.open ? q('[data-activity-message]') : boxes.find(n=>n.offsetParent!==null) || boxes[0]; if(target) target.textContent = error.message || String(error); }
  const hub = () => q('[data-planner-hub]');
  const sheetAsk = o => window.PRM?.sheet?.ask ? window.PRM.sheet.ask(o) : Promise.resolve(prompt(o.label || o.title));
  const sheetConfirm = o => window.PRM?.sheet?.confirm ? window.PRM.sheet.confirm(o) : Promise.resolve(confirm(o.text || o.title));
  const origins = {planner:'Criado no Planner',fornecedor:'Criado a partir do fornecedor'};
  async function api(path, options={}) {
    const response = await fetch(base+path,{credentials:'same-origin',...options,headers:{'X-CSRF-Token':csrf,...(options.body && !(options.body instanceof FormData)?{'Content-Type':'application/json'}:{}),...options.headers}});
    if(!response.ok) { let error; try{error=await response.json();}catch{error={detail:`HTTP ${response.status}`};} throw new Error(typeof error.detail==='string'?error.detail:'Dados inválidos; confira os campos, datas e permissões.'); }
    return response;
  }
  const get = async path => (await api(path)).json();
  const post = async (path,payload={}) => (await api(path,{method:'POST',body:JSON.stringify(payload)})).json();
  const patch = async (path,payload) => (await api(path,{method:'PATCH',body:JSON.stringify(payload)})).json();
  function params(form) { const out=new URLSearchParams(); if(form) for(const [key,value] of new FormData(form)) if(value) out.set(key,value==='on'?'true':value); return out; }
  const userLabel = u => `${u.name} · ${u.role || 'usuário'}`;
  function fillUsers(root=document) { root.querySelectorAll('[data-mt-users]').forEach(select=>{ const value=select.value, first=select.options[0]?.textContent || 'Pendente'; select.replaceChildren(new Option(first,'')); users.forEach(u=>select.add(new Option(userLabel(u),u.id))); select.value=value; }); }
  function card(row, selection=false) {
    const article=el('article',undefined,'mt-card'+(row.approval==='draft'?' is-draft':'')); article.dataset.id=row.id; article.dataset.band=row.deadline.band;
    if(selection) { article.classList.add('mt-operational-card'); const label=el('label',undefined,'mt-check'), check=el('input'); check.type='checkbox'; check.checked=selected.has(row.id); check.addEventListener('change',()=>{check.checked?selected.set(row.id,row):selected.delete(row.id);article.classList.toggle('is-print-selected',check.checked);}); label.append(check,el('span','Selecionar'));article.append(label);article.classList.toggle('is-print-selected',check.checked); }
    const heading=el('h3',(row.kind==='event'?'◷ ':'☑ ')+row.title);heading.title=row.title;
    const tone={approved:'is-info',rejected:'is-alert',on_time:'is-ok',done:'is-ok',attention:'is-warn',prioritize:'is-warn',today:'is-warn',soon:'is-info',overdue:'is-alert'};const bandKey=labels[row.deadline.band]?row.deadline.band:row.status;
    const chips=el('div',undefined,'mt-chips');chips.append(el('span',labels[row.approval]||row.approval,('mt-chip '+(tone[row.approval]||'')).trim()),el('span',labels[row.deadline.band]||labels[row.status]||row.status,('mt-chip '+(tone[bandKey]||'')).trim()));
    article.append(heading,chips);
    if(row.details.simulation) chips.append(el('span','Exemplo simulado · revisão humana obrigatória','mt-chip is-warn'));
    const due=row.due_date?displayDate(row.due_date):row.due_at?new Date(row.due_at).toLocaleString('pt-BR',{timeZone:row.timezone}):'Sem data confirmada';
    article.append(el('p',`${username(row.assignee_user_id)} · ${due} · ${row.timezone}`));
    if(row.details.owner) article.append(el('p','Entrega: '+(row.details.owner.display_name||row.details.owner.name)+' · '+row.details.owner.kind));
    if(row.details.original?.due?.raw_expression) article.append(el('p','Expressão original: '+row.details.original.due.raw_expression));
    const actions=el('div',undefined,'mt-card-actions');
    if(selection && canManage) {
      const wrap=el('label','Atribuir responsável'), select=el('select');
      select.setAttribute('aria-label','Responsável de '+row.title);
      select.add(new Option('Selecione um usuário',''));
      users.forEach(u=>select.add(new Option(userLabel(u),u.id)));
      select.value=row.assignee_user_id||'';wrap.append(select);
      const save=button('Atribuir',async()=>{
        if(!select.value)throw Error('Selecione um usuário ativo.');
        save.disabled=true;select.disabled=true;
        try {
          await post('/assign',{items:[{id:row.id,version:row.version}],assignee_user_id:select.value,reason:'Atribuição explícita pelo menu Cards'});
          selected.delete(row.id);await loadCards();
          q('[data-cards-message]').textContent=['done','cancelled'].includes(row.status)?'Responsável atualizado. Cards concluídos/cancelados não geram alertas.':row.approval==='published'?'Responsável atualizado. Alertas internos ativados para o usuário.':'Responsável atualizado. Revise, aprove e publique o card para ativar os alertas.';
        } finally {save.disabled=false;select.disabled=false;}
      });
      actions.append(wrap,save);
    }
    actions.append(button('Abrir / revisar',()=>openActivity(row.id)));article.append(actions);
    return article;
  }
  async function openActivity(id) {
    active=await get('/activities/'+id); const dialog=q('#activity-dialog'), form=q('[data-activity-edit]');
    q('#activity-dialog-title').textContent=active.title;
    const kind=q('[data-activity-kind]');if(kind)kind.textContent=active.details.planner_kind==='followup'?'Follow-up'+(active.details.category?' · '+active.details.category:''):active.kind==='event'?'Reunião':active.details.planner_kind==='task'?'Tarefa':'Card';
    const summary=[el('p',`${labels[active.approval]} · ${labels[active.status]} · Versão ${active.version}`)], links=el('p',undefined,'mt-activity-links');
    links.append(el('span','Origem: '+(origins[active.details.origin]||(active.details.field_origin==='ai'?'Sugestão da IA a partir de reunião':'Reunião'))));
    if(active.details.supplier_id){const a=el('a','Fornecedor: '+(active.details.supplier_name||'abrir'));a.href='/fornecedores?fornecedor='+encodeURIComponent(active.details.supplier_id);links.append(a);}
    if(active.meeting_id&&!active.details.created_in_planner||active.details.planner_kind==='meeting'){const id=active.meeting_id;links.append(button('Abrir reunião',()=>{q('#activity-dialog').close();if(hub())document.dispatchEvent(new CustomEvent('prm:open-meeting-drawer',{detail:{id}}));else location.href='/planner?meeting='+encodeURIComponent(id);},'cc-btn mt-link-btn'));}
    summary.push(links);q('[data-activity-summary]').replaceChildren(...summary);
    for(const name of ['title','description','assignee_user_id','due_date','due_at','end_at','timezone','status']) form.elements[name].value=active[name]||'';
    if(form.elements.priority) form.elements.priority.value=active.details.priority||'normal';
    form.elements.no_deadline_accepted.checked=active.no_deadline_accepted;
    form.elements.checklist.value=(active.details.checklist||[]).join('\n'); form.elements.reason.value='';
    Array.from(form.elements).forEach(field=>{if(field.name) field.disabled=!active.can_review && !['reason','status'].includes(field.name);});
    document.querySelectorAll('[data-review],[data-publish-one],[data-assign-me]').forEach(b=>b.disabled=!active.can_review);
    const evidence=q('[data-activity-evidence]'); evidence.replaceChildren(el('h3','Origem e evidências'));
    (active.details.original?.ambiguities||[]).forEach(t=>evidence.append(el('p',t)));
    if(active.details.original?.time_candidate) evidence.append(el('p',`Hora candidata: ${active.details.original.time_candidate}; duração estimada: ${active.details.original.duration_estimate_minutes||'não informada'} min. Não confirmada automaticamente.`));
    if(active.evidence_access) (active.details.original?.evidence||[]).forEach(e=>{const block=el('blockquote',e.quote); block.append(button('Ver segmento',async()=>{dialog.close();location.href='/planner?meeting='+active.meeting_id+'&segment='+encodeURIComponent(e.segment_id);}));evidence.append(block);});
    else evidence.append(el('p','Você pode executar a atividade; acesso à transcrição é restrito ao curador/gestor.'));
    q('[data-activity-history]').replaceChildren(...active.history.map(h=>el('p',`${new Date(h.at).toLocaleString('pt-BR')} · ${h.action} · ${h.reason}`)));
    q('[data-activity-message]').textContent=''; if(!dialog.open) dialog.showModal();
  }
  q('[data-activity-close]')?.addEventListener('click',()=>window.PRM?.sheet?window.PRM.sheet.requestClose(q('#activity-dialog')):q('#activity-dialog').close());
  q('[data-activity-comment]')?.addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget,submit=q('[type=submit]',form),id=active.id,text=form.elements.text.value.trim();
    if(!text)return;submit.disabled=true;
    const key=id+'\n'+text;if(form.dataset.commentKey!==key){form.dataset.commentKey=key;form.dataset.requestId=crypto.randomUUID();}
    try{await post('/activities/'+id+'/comments',{request_id:form.dataset.requestId,text});form.reset();delete form.dataset.commentKey;
      if(active.id===id){const updated=await get('/activities/'+id);q('[data-activity-history]').replaceChildren(...updated.history.map(h=>el('p',`${new Date(h.at).toLocaleString('pt-BR')} · ${h.action} · ${h.reason}`)));q('[data-activity-message]').textContent='Comentário registrado. Campos ainda não salvos foram preservados.';}}
    catch(e){report(e);}finally{submit.disabled=false;}
  });
  q('[data-assign-me]')?.addEventListener('click',()=>{q('[data-activity-edit]').elements.assignee_user_id.value=me;});
  q('[data-copy-link]')?.addEventListener('click',()=>navigator.clipboard.writeText(location.origin+'/planner?activity='+active.id).then(()=>{q('[data-activity-message]').textContent='Link copiado; exige login e autorização.';}).catch(report));
  q('[data-activity-edit]')?.addEventListener('submit',async event=>{event.preventDefault(); const form=event.currentTarget,save=q('[data-activity-save]');if(!form.reportValidity())return;if(save){save.disabled=true;save.setAttribute('aria-busy','true');}try{
    const payload={version:active.version,reason:form.elements.reason.value,status:form.elements.status.value};
    if(active.can_review) Object.assign(payload,{title:form.elements.title.value,description:form.elements.description.value,
      assignee_user_id:form.elements.assignee_user_id.value||null,due_date:form.elements.due_date.value||null,due_at:form.elements.due_at.value||null,end_at:form.elements.end_at.value||null,
      timezone:form.elements.timezone.value,no_deadline_accepted:form.elements.no_deadline_accepted.checked,checklist:form.elements.checklist.value.split('\n').map(t=>t.trim()).filter(Boolean),...(form.elements.priority?{priority:form.elements.priority.value}:{})});
    await patch('/activities/'+active.id,payload); await openActivity(active.id); q('[data-activity-message]').textContent='Alteração humana salva; se aprovado, o card voltou para revisão.'; await refresh();
  }catch(error){report(error);}finally{if(save){save.disabled=false;save.removeAttribute('aria-busy');}}});
  document.querySelectorAll('[data-review]').forEach(b=>b.addEventListener('click',async()=>{try{await post('/activities/'+active.id+'/review',{version:active.version,decision:b.dataset.review,reason:q('[data-activity-edit]').elements.reason.value||'Revisão explícita do card'});await openActivity(active.id);await refresh();}catch(e){report(e);}}));
  q('[data-publish-one]')?.addEventListener('click',async()=>{try{if(!await sheetConfirm({title:'Publicar atividade',kicker:'Publicação',text:'A atividade aprovada entra na agenda e ativa os alertas internos do responsável.',confirm:'Publicar'}))return;await post('/publish',{items:[{id:active.id,version:active.version}]});await openActivity(active.id);await refresh();}catch(e){report(e);}});
  async function loadCards() {
    if(!q('[data-cards-list]')) return;
    const search=params(q('[data-cards-filters]')); search.set('offset',offset); const meeting=new URLSearchParams(location.search).get('meeting'); if(meeting)search.set('meeting',meeting);
    const result=await get('/activities?'+search);cardRows=result.items;
    q('[data-cards-list]').replaceChildren(...(cardRows.length?cardRows.map(a=>card(a,true)):[el('p','Nenhum card neste filtro. Importe uma reunião para criar rascunhos.') ]));
    q('[data-cards-count]').textContent=`${result.total?offset+1:0}–${Math.min(offset+100,result.total)} de ${result.total}`;
    q('[data-cards-prev]').disabled=offset===0;q('[data-cards-next]').disabled=offset+100>=result.total;
  }
  q('[data-cards-filters]')?.addEventListener('submit',e=>{e.preventDefault();offset=0;selected.clear();loadCards().catch(report);});
  q('[data-cards-prev]')?.addEventListener('click',()=>{offset=Math.max(0,offset-100);loadCards().catch(report);});
  q('[data-cards-next]')?.addEventListener('click',()=>{offset+=100;loadCards().catch(report);});
  document.querySelectorAll('[data-review-selected]').forEach(b=>b.addEventListener('click',async()=>{try{
    if(!selected.size)throw Error('Selecione os cards para revisar.');
    const decision={approved:'Aprovar',rejected:'Rejeitar',draft:'Devolver à revisão'}[b.dataset.reviewSelected];const reason=await sheetAsk({title:decision+' cards selecionados',kicker:'Revisão em lote',subtitle:`${selected.size} card(s) · o lote inteiro é validado`,label:'Motivo da revisão',confirm:decision,danger:b.dataset.reviewSelected==='rejected'});if(!reason)return;
    await post('/review',{items:[...selected.values()].map(a=>({id:a.id,version:a.version})),decision:b.dataset.reviewSelected,reason});
    selected.clear();await refresh();
  }catch(e){report(e);}}));
  q('[data-assign-selected]')?.addEventListener('click',async()=>{try{
    if(!selected.size)throw Error('Selecione os cards para atribuir.');
    const reason=await sheetAsk({title:'Atribuir cards selecionados',kicker:'Atribuição em lote',subtitle:`${selected.size} card(s)`,label:'Motivo da atribuição',confirm:'Atribuir'});if(!reason)return;
    await post('/assign',{items:[...selected.values()].map(a=>({id:a.id,version:a.version})),assignee_user_id:q('[data-batch-assignee]').value||null,reason});
    selected.clear();await refresh();
  }catch(e){report(e);}});
  document.querySelectorAll('[data-export]').forEach(b=>b.addEventListener('click',async()=>{try{if(!selected.size)throw Error('Selecione pelo menos um card.');const response=await api('/export',{method:'POST',body:JSON.stringify({ids:[...selected.keys()],format:b.dataset.export})});const url=URL.createObjectURL(await response.blob()),a=el('a');a.href=url;a.download='cards.'+b.dataset.export;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){report(e);}}));
  q('[data-print]')?.addEventListener('click',()=>{if(!selected.size){report(Error('Selecione cards para imprimir.'));return;}q('[data-cards-message]').textContent='Retrato de '+new Date().toLocaleString('pt-BR')+' · Somente seleção visível nesta página';window.print();});
  q('[data-publish-selected]')?.addEventListener('click',async()=>{try{if(!selected.size)throw Error('Selecione cards aprovados.');if(!await sheetConfirm({title:'Publicar cards selecionados',kicker:'Publicação em lote',text:`${selected.size} card(s) aprovados entram na agenda e ativam alertas. O lote inteiro é validado antes.`,confirm:'Publicar'}))return;await post('/publish',{items:[...selected.values()].map(a=>({id:a.id,version:a.version}))});selected.clear();await refresh();}catch(e){report(e);}});
  async function loadMeetings(append=false) {
    const target=q('[data-meetings-list]');if(!target)return;
    const start=append?Number(q('[data-meetings-more]').dataset.offset):0;
    const result=await get('/meetings?offset='+start);if(!append)target.replaceChildren();
    result.items.forEach(m=>{const item=el('article',undefined,'mt-card');item.append(el('h3',m.title),el('p',`${displayDate(m.date)} · ${m.partner||'Parceiro pendente'}`),button('Abrir reunião',()=>openMeeting(m.id)));target.append(item);});
    if(!result.items.length&&!append)target.append(el('p','Nenhuma reunião importada.'));
    q('[data-meetings-more]').hidden=result.next_offset===null;q('[data-meetings-more]').dataset.offset=result.next_offset;
  }
  q('[data-meetings-more]')?.addEventListener('click',()=>loadMeetings(true).catch(report));
  q('[data-meeting-create]')?.addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget, submit=q('[type=submit]',form);submit.disabled=true;try{
    const data=new FormData(form), text=data.get('text'), txt=form.elements.txt.files[0], audio=form.elements.audio.files[0];
    if([!!text.trim(),!!txt,!!audio].filter(Boolean).length!==1)throw Error('Escolha uma entrada: texto colado, TXT ou áudio.');
    const result=await post('/meetings',{title:data.get('title'),partner:data.get('partner'),opportunity:data.get('opportunity'),meeting_date:data.get('meeting_date')||null,timezone:data.get('timezone'),text});
    if(txt||audio){const upload=new FormData();upload.set('file',txt||audio);q('[data-meeting-message]').textContent='Enviando arquivo; aguarde a confirmação.';await api('/meetings/'+result.id+(txt?'/txt':'/audio'),{method:'POST',body:upload});}
    q('[data-meeting-message]').textContent='Reunião criada. Revise antes de analisar/publicar.';form.reset();await loadMeetings();await openMeeting(result.id);
  }catch(e){report(e);}finally{submit.disabled=false;}});
  async function openMeeting(id) {
    clearTimeout(pollTimer);meetingId=id;meetingData=await get('/meetings/'+id);
    const m=meetingData,target=q('[data-meeting-detail]');target.hidden=false;target.replaceChildren(el('h2',m.title),el('p',`${displayDate(m.meeting_date)} · ${m.timezone} · versão ${m.version}`));
    const meta=el('form',undefined,'mt-form');
    function input(label,name,value,type='text'){const wrap=el('label',label),field=el('input');field.name=name;field.type=type;field.value=value||'';wrap.append(field);return wrap;}
    meta.append(input('Data da reunião','meeting_date',m.meeting_date,'date'),input('Data do próximo evento (confirmação humana)','confirmed_event_date',m.metadata?.event_date,'date'),input('Fuso','timezone',m.timezone),input('Motivo da confirmação','reason',''));
    const save=el('button','Salvar metadados','cc-btn');save.type='submit';meta.append(save);meta.addEventListener('submit',async e=>{e.preventDefault();try{await patch('/meetings/'+id+'/metadata',{version:m.version,meeting_date:meta.elements.meeting_date.value||null,confirmed_event_date:meta.elements.confirmed_event_date.value||null,timezone:meta.elements.timezone.value,reason:meta.elements.reason.value});await openMeeting(id);}catch(error){report(error);}});target.append(meta);
    target.append(el('h3','Participantes · não unir pessoas por semelhança de nome'));
    m.participants.forEach(p=>{const row=el('div',undefined,'mt-toolbar'),name=el('input');name.value=p.display_name||p.name;name.setAttribute('aria-label','Alias de '+p.name);const kind=el('select');kind.setAttribute('aria-label','Tipo de participante');[['unconfirmed','Não confirmado'],['internal','Interno'],['external','Externo']].forEach(([v,t])=>kind.add(new Option(t,v)));kind.value=p.kind;const user=el('select');user.setAttribute('aria-label','Vínculo interno');user.add(new Option('Sem vínculo',''));users.forEach(u=>user.add(new Option(u.name,u.id)));user.value=p.user_id||'';row.append(el('span',p.name),name,kind,user,button('Confirmar vínculo',async()=>{await patch('/meetings/'+id+'/participants',{version:m.version,participant_id:p.id,display_name:name.value,kind:kind.value,user_id:user.value||null,reason:'Vínculo confirmado explicitamente pelo revisor'});await openMeeting(id);}));target.append(row);});
    m.audio.forEach(a=>{const player=el('audio');player.controls=true;player.preload='metadata';player.src=a.url;target.append(el('p',a.name),player,button('Somente transcrever',async()=>{await post('/meetings/'+id+'/transcriptions',{audio_id:a.id});await openMeeting(id);}),button('Transcrever e analisar',async()=>{if(await sheetConfirm({title:'Transcrever e analisar',kicker:'Reunião',text:'O áudio é transcrito localmente e o texto é enviado ao Claude para sugerir cards. Pode gerar custo de API.',confirm:'Autorizar'})){await post('/meetings/'+id+'/transcriptions',{audio_id:a.id,analyze_after:true,consent_to_send_text:true});await openMeeting(id);}}));});
    const revisions=el('select');revisions.setAttribute('aria-label','Revisão da transcrição');m.revisions.forEach((r,i)=>revisions.add(new Option(`Revisão ${m.revisions.length-i} · ${r.source} · ${r.sha256.slice(0,10)}`,r.id)));target.append(revisions);
    const grid=el('div',undefined,'mt-review-grid'),left=el('section'),right=el('section');grid.append(left,right);target.append(grid);
    const drawRevision=()=>{left.replaceChildren();right.replaceChildren();const r=m.revisions.find(r=>r.id===revisions.value);if(!r)return;
      left.append(el('h3','Texto e análise'),el('p',r.quality.complete?'Transcrição completa segundo a origem; revise nomes e datas.':'TRANSCRIÇÃO PARCIAL: aceite explícito necessário.'));
      const editor=el('textarea');editor.rows=8;editor.value=r.text;editor.setAttribute('aria-label','Corrigir transcrição');left.append(editor,button('Salvar nova revisão',async()=>{const reason=await sheetAsk({title:'Salvar nova revisão da transcrição',kicker:'Reunião',label:'Motivo da correção',confirm:'Salvar revisão'});if(!reason)return;await post('/meetings/'+id+'/transcripts',{text:editor.value,reason});await openMeeting(id);}));
      left.append(button('Analisar com Claude',async()=>{if(!await sheetConfirm({title:'Analisar com Claude',kicker:'Reunião',text:'Esta revisão da transcrição será enviada ao Claude configurado para sugerir cards. Pode gerar custo de API.',confirm:'Enviar para análise'}))return;const partial=!r.quality.complete&&await sheetConfirm({title:'Transcrição parcial',kicker:'Reunião',text:'A transcrição está incompleta. Os cards sugeridos manterão esse aviso. Analisar mesmo assim?',confirm:'Analisar parcial'});await post('/meetings/'+id+'/analyses',{revision_id:r.id,provider:'anthropic',consent_to_send_text:true,accept_partial:partial});await openMeeting(id);}));
      const transcript=el('div',undefined,'mt-transcript');r.segments.forEach(s=>{const block=el('div',undefined,'mt-segment');block.id=s.id;block.append(el('strong',`${s.timestamp||'Sem timestamp'} · ${s.speaker||'Falante desconhecido'}`),el('p',s.text));if(s.start_ms!==null&&m.audio.length)block.append(button('Ouvir trecho',()=>{const player=q('audio',target);player.currentTime=s.start_ms/1000;return player.play();}));transcript.append(block);});right.append(el('h3','Transcrição e evidências'),transcript);
      const sid=new URLSearchParams(location.search).get('segment');if(sid){const match=document.getElementById(sid);if(match){match.classList.add('is-highlighted');match.scrollIntoView({block:'center'});}}
    }; revisions.addEventListener('change',drawRevision);drawRevision();
    left.append(el('h3','Execuções persistidas')); const states=el('div');left.append(states);
    m.runs.filter(run=>!['schedule','planner'].includes(run.stage)).forEach(run=>{const entry=el('article',undefined,'mt-card');entry.append(el('strong',`${run.stage} · ${run.state}`));if(run.provider==='fixture')entry.append(el('p','SIMULAÇÃO — não é análise de IA'));if(run.summary)entry.append(el('p',run.summary));if(run.error)entry.append(el('p',run.error));(run.warnings||[]).forEach(w=>entry.append(el('p',w)));(run.decisions||[]).forEach(w=>entry.append(el('p','Decisão/contexto: '+w)));if(['queued','running'].includes(run.state))entry.append(button('Cancelar etapa',async()=>{await post('/runs/'+run.id+'/cancel');await openMeeting(id);}));if(run.state==='failed')entry.append(button('Tentar novamente (pode cobrar API)',async()=>{if(await sheetConfirm({title:'Tentar novamente',kicker:'Reunião',text:'Repetir esta etapa? A análise pode ter sido faturada mesmo após o tempo limite.',confirm:'Repetir etapa'})){await post('/runs/'+run.id+'/retry');await openMeeting(id);}}));states.append(entry);});
    const link=el('a','Revisar cards desta reunião','cc-btn');link.href='/planner?view=revisao&meeting='+id;left.append(link);
    document.dispatchEvent(new CustomEvent('prm:meeting-opened',{detail:{id,title:m.title}}));
    if(m.runs.some(r=>['queued','running'].includes(r.state))) {
      const notice=el('p','Processamento em andamento. Suas edições não serão recarregadas automaticamente.');
      target.append(notice);
      const poll=async()=>{try{if(meetingId!==id)return;const next=await get('/meetings/'+id);
        if(m.runs.map(r=>r.id+r.state).join()!==next.runs.map(r=>r.id+r.state).join()) {
          notice.replaceChildren(el('span','A execução foi atualizada. Salve suas edições antes de recarregar. '),button('Recarregar reunião',()=>openMeeting(id)));
        } else pollTimer=setTimeout(poll,5000);
      }catch(e){report(e);}};pollTimer=setTimeout(poll,5000);
    }
  }
  let alertCategory='';
  async function loadAlerts(){const target=q('[data-alerts-list]');if(!target)return;const result=await get('/alerts');
    const go=(text,href)=>{const a=el('a',text,'cc-btn');a.href=href;return a;};
    const alertCard=a=>{const node=el('article',undefined,'mt-card mt-alert'+(a.read_at?' is-read':''));const tone={overdue:'is-alert',today:'is-warn',soon:'is-info'}[a.kind]||'';
      const chips=el('div',undefined,'mt-chips');if(a.category)chips.append(el('span',a.category,'mt-chip mt-category'));chips.append(el('span',labels[a.kind]||a.kind,('mt-chip '+tone).trim()));
      node.append(chips,el('h3',a.title));if(a.supplier_name)node.append(el('p',a.supplier_name,'mt-alert-supplier'));
      const actions=el('div',undefined,'mt-alert-actions'),sid=a.supplier_id?encodeURIComponent(a.supplier_id):'';
      if(sid){actions.append(go('Abrir fornecedor','/fornecedores?fornecedor='+sid),go('Registrar interação','/fornecedores?fornecedor='+sid+'&acao=interacao'),go('Criar follow-up','/planner?new=followup&supplier='+sid));
        if(a.suggest_meeting)actions.append(go('Agendar reunião','/fornecedores?fornecedor='+sid+'&acao=reuniao'));actions.append(go('Ver no Planner','/planner?activity='+encodeURIComponent(a.activity_id)));}
      else actions.append(button('Abrir atividade',()=>openActivity(a.activity_id)));
      actions.append(button(a.read_at?'Lido':'Marcar lido',async()=>{await post('/alerts/'+a.id+'/read');await loadAlerts();}));node.append(actions);return node;};
    if(!result.items.length){const empty=el('div',undefined,'prm-empty');empty.append(el('strong','Nenhum alerta ativo.'),el('p','Prazos de atividades publicadas atribuídas a você e follow-ups automáticos de fornecedores aparecem aqui. Rascunhos não geram notificações.'));target.replaceChildren(empty);return;}
    const categories=[...new Set(result.items.map(a=>a.category||'Prazos'))];if(alertCategory&&!categories.includes(alertCategory))alertCategory='';
    const filter=el('div',undefined,'mt-chips mt-alert-filter');filter.setAttribute('role','group');filter.setAttribute('aria-label','Categoria do alerta');
    ['',...categories].forEach(c=>{const b=button((c||'Todas')+' · '+result.items.filter(a=>!c||(a.category||'Prazos')===c).length,()=>{alertCategory=c;return loadAlerts();},'cc-btn');b.setAttribute('aria-pressed',String(alertCategory===c));filter.append(b);});
    const shown=result.items.filter(a=>!alertCategory||(a.category||'Prazos')===alertCategory);
    const order=[['overdue','Atrasados'],['today','Hoje'],['soon','Próximos'],['assigned','Atribuições e avisos']];const known=new Set(order.map(([k])=>k));
    const groups=[...order,['other','Outros']].map(([key,title])=>[title,shown.filter(a=>key==='other'?!known.has(a.kind):a.kind===key)]).filter(([,items])=>items.length);
    target.replaceChildren(filter,...groups.map(([title,items])=>{const section=el('section',undefined,'mt-alert-group');const head=el('h3',undefined,'mt-alert-group-title');head.append(el('span',title),el('span',String(items.length),'mt-count'));const list=el('div',undefined,'mt-card-list');list.append(...items.map(alertCard));section.append(head,list);return section;}));}
  async function loadPlanner(){const root=q('[data-planner]');if(!root)return;const search=params(q('[data-planner-filters]')), summary=await get('/activities/overview?'+search);
    q('[data-deadline-bands]').replaceChildren(...Object.entries(summary.bands).map(([key,value])=>{const b=button('',()=>{band=band===key?'':key;bucket='';return loadPlanner();},'mt-deadline');b.dataset.band=key;b.setAttribute('aria-pressed',String(band===key));b.append(el('span',labels[key]),el('strong',value.count),el('small',value.percent.toLocaleString('pt-BR')+'%'));return b;}));
    q('[data-deadline-scope]').textContent=`${summary.denominator} tarefas abertas com prazo confirmado · ${summary.no_deadline} sem prazo aceito · ${summary.unconfirmed} a confirmar · atualizado ${new Date(summary.updated_at).toLocaleString('pt-BR')}`;
    const max=Math.max(1,...summary.histogram.map(h=>h.count));q('[data-deadline-histogram]').replaceChildren(...summary.histogram.map(h=>{const b=button('',()=>{bucket=bucket===h.label?'':h.label;band='';return loadPlanner();});b.title=`${h.label}: ${h.count} tarefas abertas autorizadas`;b.dataset.band=h.label.startsWith('atraso')||h.label==='venceu hoje'?'overdue':['hoje','1d','2d'].includes(h.label)?'prioritize':h.label==='3–7d'?'attention':'on_time';const bar=el('span',undefined,'mt-bar'),fill=el('i');fill.style.setProperty('--height',(70*h.count/max)+'px');bar.append(fill);b.append(el('strong',h.count),bar,el('span',h.label));return b;}));
    const [year,m]=month.split('-').map(Number),start=month+'-01',next=new Date(Date.UTC(year,m,1)),end=next.toISOString().slice(0,10);search.set('start',start);search.set('end',end);if(band)search.set('band',band);if(bucket)search.set('bucket',bucket);
    if(q('[data-show-proposals]')?.checked)search.set('include_proposals','true');
    const result=await get('/activities/calendar?'+search),calendar=q('[data-calendar]');calendar.replaceChildren();q('[data-month]').value=month;q('[data-calendar-scope]').textContent=(labels[band]||bucket||'Todas as faixas')+' · '+result.items.length+' atividades no mês';
    ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'].forEach(d=>calendar.append(el('div',d,'mt-weekday')));
    const first=(new Date(Date.UTC(year,m-1,1)).getUTCDay()+6)%7,last=new Date(Date.UTC(year,m,0)).getUTCDate();for(let i=0;i<first;i++)calendar.append(el('div','', 'mt-day is-padding'));
    for(let day=1;day<=last;day++){const date=`${month}-${String(day).padStart(2,'0')}`,cell=el('section',undefined,'mt-day'+(date===`${nowParts.year}-${nowParts.month}-${nowParts.day}`?' is-today':''));cell.setAttribute('aria-label',displayDate(date));cell.append(el('strong',displayDate(date)));const rows=result.items.filter(r=>r.calendar_date<=date&&r.calendar_end>=date);const draw=(all=false)=>{cell.querySelectorAll('button').forEach(b=>b.remove());rows.slice(0,all?rows.length:3).forEach(row=>{const b=button(`${row.kind==='event'?'◷':'☑'} ${row.due_at?new Date(row.due_at).toLocaleTimeString('pt-BR',{timeZone:row.timezone,hour:'2-digit',minute:'2-digit'}):'Dia inteiro'} · ${row.title}`,()=>openActivity(row.id),'');b.dataset.band=row.deadline.band;b.title=username(row.assignee_user_id)+' · '+(labels[row.deadline.band]||labels[row.status]);cell.append(b);});if(!all&&rows.length>3)cell.append(button('+'+(rows.length-3)+' · ver todos',()=>draw(true)));};draw();calendar.append(cell);}
    const undatedParams=params(q('[data-planner-filters]'));undatedParams.set('limit','200');undatedParams.set('undated','true');const list=await get('/activities?'+undatedParams);const undated=list.items;q('[data-undated]').replaceChildren(...undated.map(a=>card(a)),el('p',list.total>200?'Mostrando até 200 atividades sem data; consulte Cards para todas as páginas.':!undated.length?'Nenhuma atividade sem data neste filtro.':''));
  }
  q('[data-planner-filters]')?.addEventListener('submit',e=>{e.preventDefault();loadPlanner().catch(report);});
  q('[data-show-proposals]')?.addEventListener('change',()=>loadPlanner().catch(report));
  q('[data-month]')?.addEventListener('change',e=>{if(/^\d{4}-\d{2}$/.test(e.target.value)){month=e.target.value;loadPlanner().catch(report);}});
  document.querySelectorAll('[data-month-step]').forEach(b=>b.addEventListener('click',()=>{const [y,m]=month.split('-').map(Number);month=new Date(Date.UTC(y,m-1+Number(b.dataset.monthStep),1)).toISOString().slice(0,7);loadPlanner().catch(report);}));
  q('[data-month-today]')?.addEventListener('click',()=>{month=`${nowParts.year}-${nowParts.month}`;loadPlanner().catch(report);});
  q('[data-clear-band]')?.addEventListener('click',()=>{band='';bucket='';loadPlanner().catch(report);});
  async function refresh(){await Promise.all([loadCards(),loadPlanner(),loadAlerts()]);document.dispatchEvent(new CustomEvent('prm:planner-changed'));}
  // Integração com o Planner (planner.js): abrir itens e recarregar listas sem duplicar a lógica de revisão.
  document.addEventListener('prm:open-activity',e=>openActivity(e.detail.id).catch(report));
  document.addEventListener('prm:open-meeting',e=>openMeeting(e.detail.id).catch(report));
  document.addEventListener('prm:planner-refresh',()=>Promise.all([loadCards(),loadAlerts(),loadMeetings()]).catch(report));
  async function init(){const result=await get('/users');users=result.items;me=result.current_user_id;canManage=result.can_manage;fillUsers();await Promise.all([refresh(),loadMeetings()]);const search=new URLSearchParams(location.search);if(search.get('activity'))await openActivity(search.get('activity'));if(search.get('meeting')&&q('[data-meeting-detail]')&&!hub())await openMeeting(search.get('meeting'));}
  if(q('[data-alerts-list]')) setInterval(()=>{if(!document.hidden)loadAlerts().catch(report);},60000);
  init().catch(report);
})();
