/* Preencher com IA: fonte → análise (prévia, nada gravado) → revisão humana → aplicar somente o selecionado.
   Everything is rendered with textContent; values applied are referenced by index into the server-stored preview. */
const SUPPLIER_AI_STATUS={new:'Novo',differs:'Diferente do atual',conflict:'Fontes divergentes — escolha',same:'Igual ao atual'};
const SUPPLIER_AI_CONFIDENCE={high:'Alta confiança',medium:'Média confiança',low:'Baixa confiança'};
const SUPPLIER_AI_ACTIONS={replace:'Substituir',contact:'Adicionar como novo contato',append:'Adicionar ao final'};
const SUPPLIER_AI_READABLE=['.pdf','.docx','.xlsx','.xls','.csv','.txt','.png','.jpg','.jpeg'];
function supplierAIDefaults(p){const fields={};p.fields.forEach(f=>{fields[f.key]={action:f.preselect!=null?'replace':'',choice:f.preselect!=null?f.preselect:f.suggestions.length===1?0:null};});return {fields,contacts:new Set(),social:new Set(p.social.filter(s=>!s.exists).map(s=>s.id))};}
function supplierAIApplyBody(p,state){const fields=[];for(const f of p.fields){const s=state.fields[f.key];if(!s||!s.action)continue;if(s.choice==null)throw Error('Escolha qual valor usar em: '+f.label);fields.push({key:f.key,choice:s.choice,action:s.action});}
 const body={run_id:p.run_id,fields,contacts:[...state.contacts],social:[...state.social]};if(!fields.length&&!body.contacts.length&&!body.social.length)throw Error('Selecione ao menos um item para aplicar.');return body;}
function supplierAISource(s){return s.source_type==='website'?'Fonte: site oficial · '+s.source:'Fonte: ficha cadastral · '+s.source+(s.page!=null?' · página '+s.page:'');}
function supplierAIStart(ctx,preset={}){
 const {current,request,node,field,modal,msg}=ctx;let uploaded=null;
 const docs=current.documents.filter(d=>SUPPLIER_AI_READABLE.some(x=>(d.data.original_name||'').toLowerCase().endsWith(x))).sort((a,b)=>(b.data.category==='Ficha cadastral')-(a.data.category==='Ficha cadastral'));
 request('/'+current.id+'/ai/status').then(status=>{if(!status.enabled){msg('IA de fornecedores não configurada no servidor.');return;}
 modal('Preencher com IA',box=>{
  const intro=node('p','A IA apenas sugere dados encontrados na fonte. Nada é gravado até você revisar e aplicar.');intro.className='supplier-ai-note';box.append(intro);
  field(box,'mode','Fonte',preset.document_id?'document':'site',{document:'Ler ficha cadastral',site:'Buscar no site oficial',combined:'Combinar ficha + site'});
  field(box,'url','Site oficial',current.data.website||'',null,'url').placeholder='https://www.exemplo.com/';
  field(box,'document_id','Documento',preset.document_id||docs[0]?.id||'',{'':'Enviar novo arquivo…',...Object.fromEntries(docs.map(d=>[d.id,d.data.category+' · '+d.data.original_name]))});
  const f=field(box,'file','Novo arquivo (salvo em Ficha cadastral)','',null,'file');f.accept=SUPPLIER_AI_READABLE.join(',');
 },async v=>{
  let doc=v.document_id;
  if(v.mode!=='site'&&!doc){if(uploaded)doc=uploaded;else{if(!v.file||!v.file.size)throw Error('Selecione um documento ou envie um arquivo.');const fd=new FormData();fd.append('file',v.file);fd.append('category','Ficha cadastral');doc=uploaded=(await request('/'+current.id+'/documents','POST',fd)).id;}}
  msg('Analisando… pode levar até 1 minuto. Nenhum dado é gravado nesta etapa.');
  const path={site:'/ai/analisar-site',document:'/ai/analisar-documento',combined:'/ai/analisar-combinado'}[v.mode];
  const p=await request('/'+current.id+path,'POST',v.mode==='site'?{url:v.url}:v.mode==='combined'?{document_id:doc,url:v.url}:{document_id:doc});
  msg('Análise concluída. Revise antes de aplicar.');setTimeout(()=>supplierAIReview(ctx,p),0);
 },'Analisar');}).catch(e=>msg(e.message));
}
function supplierAIReview(ctx,p){
 const {current,request,node,modal,msg}=ctx;const state=supplierAIDefaults(p);
 const check=(label,on,fn,disabled=false)=>{const l=node('label');l.className='supplier-ai-check';const c=node('input');c.type='checkbox';c.checked=on;c.disabled=disabled;c.onchange=()=>fn(c.checked);l.append(c,node('span',label));return l;};
 modal('Preenchimento sugerido',box=>{
  const head=node('section');head.className='supplier-ai-head';
  head.append(node('p',(p.source.type==='website'?'Site oficial: '+(p.source.domain||''):p.source.type==='combined'?'Ficha + site: '+(p.source.document_name||'')+' · '+(p.source.domain||''):'Ficha cadastral: '+(p.source.document_name||''))+(p.pages.length?' · '+p.pages.length+' página(s) lida(s)':'')+' · modelo '+p.model+(p.cached?' · resultado recente reaproveitado':'')));
  if(p.discarded)head.append(node('p',p.discarded+' sugestão(ões) descartada(s) por não terem evidência na fonte.'));
  p.warnings.forEach(w=>head.append(node('p','⚠ '+w)));if(!p.fields.length&&!p.contacts.length&&!p.social.length)head.append(node('p','Nenhum dado cadastral encontrado nesta fonte.'));box.append(head);
  const groups={};p.fields.forEach(f=>(groups[f.group]=groups[f.group]||[]).push(f));
  Object.entries(groups).forEach(([label,items])=>{const g=node('fieldset');g.className='supplier-form-group supplier-ai-group';g.append(node('legend',label));items.forEach(f=>{
   const s=state.fields[f.key],row=node('div');row.className='supplier-ai-field status-'+f.status;
   const title=node('div');title.className='supplier-ai-title';const badge=node('span',SUPPLIER_AI_STATUS[f.status]);badge.className='supplier-ai-badge';
   if(f.status==='same'||!f.current)title.append(check(f.label,Boolean(s.action),on=>{s.action=on?'replace':'';},f.status==='same'),badge);
   else{const sel=node('select');sel.setAttribute('aria-label','Ação para '+f.label);const keep=node('option','Manter atual');keep.value='';sel.append(keep);f.actions.forEach(a=>{const o=node('option',SUPPLIER_AI_ACTIONS[a]);o.value=a;sel.append(o);});sel.value=s.action;sel.onchange=()=>{s.action=sel.value;};title.append(node('strong',f.label),badge,sel);}
   row.append(title);if(f.current)row.append(node('p','Atual: '+f.current));
   f.suggestions.forEach((x,i)=>{const opt=node('div');opt.className='supplier-ai-option';
    if(f.suggestions.length>1&&f.status!=='same'){const r=node('input');r.type='radio';r.name='ai-'+f.key;r.checked=s.choice===i;r.onchange=()=>{s.choice=i;};r.setAttribute('aria-label',x.value);opt.append(r);}
    opt.append(node('span',(f.current?'Encontrado: ':'')+x.value));const meta=node('small',[SUPPLIER_AI_CONFIDENCE[x.confidence],supplierAISource(x),x.verified?'':'evidência não verificável automaticamente',x.warning||''].filter(Boolean).join(' · '));meta.className='conf-'+x.confidence;opt.append(meta);
    const ev=node('details');ev.append(node('summary','Evidência'),node('p',x.evidence));opt.append(ev);row.append(opt);});
   g.append(row);});box.append(g);});
  if(p.contacts.length){const g=node('fieldset');g.className='supplier-form-group supplier-ai-group';g.append(node('legend','Contatos sugeridos'));p.contacts.forEach(c=>{const row=node('div');row.className='supplier-ai-field';
   row.append(check([c.name,c.role].filter(Boolean).join(' · ')+(c.duplicate_of?' (já existe: '+c.duplicate_of+')':''),false,on=>{on?state.contacts.add(c.id):state.contacts.delete(c.id);},Boolean(c.duplicate_of)));
   const m=node('small',[c.email,c.phone,c.mobile,c.whatsapp&&'WhatsApp '+c.whatsapp,SUPPLIER_AI_CONFIDENCE[c.confidence],supplierAISource(c)].filter(Boolean).join(' · '));row.append(m);g.append(row);});box.append(g);}
  if(p.social.length){const g=node('fieldset');g.className='supplier-form-group supplier-ai-group';g.append(node('legend','Redes sociais (links do site oficial)'));p.social.forEach(x=>{const row=node('div');row.className='supplier-ai-field';row.append(check(x.network+': '+x.url+(x.exists?' (já na ficha)':''),state.social.has(x.id),on=>{on?state.social.add(x.id):state.social.delete(x.id);},x.exists));g.append(row);});box.append(g);}
 },async()=>{const r=await request('/'+current.id+'/ai/aplicar','POST',supplierAIApplyBody(p,state));msg(r.summary);setTimeout(()=>ctx.reopen('Histórico'),0);},'Aplicar campos selecionados');
}

/* Novo fornecedor com IA: fontes → análise (nada é criado) → revisão editável → Cadastrar fornecedor (uma transação no servidor). */
const SUPPLIER_AI_SCORE_ICONS={quente:'🔥 ',morno:'🌤️ ',frio:'❄️ ',congelando:'🧊 '};
const SUPPLIER_AI_REASONS={cnpj:'mesmo CNPJ',registro:'mesmo registro empresarial',dominio:'mesmo domínio do site',nome:'nome semelhante'};
function supplierAINewState(p){
 const byKey=Object.fromEntries(p.fields.map(f=>[f.key,f]));const fields={};
 p.all_fields.forEach(({key})=>{const f=byKey[key];let choice=null;
  if(f&&f.preselect!=null)choice=f.preselect;else if(f&&f.status!=='conflict'&&f.suggestions.length===1&&f.suggestions[0].confidence!=='low'&&!f.suggestions[0].warning)choice=0;
  fields[key]={value:choice!=null?f.suggestions[choice].value:key==='website'?(p.defaults.website||''):'',choice};});
 return {fields,also:new Set(),contacts:new Set(p.contacts.filter(c=>!c.duplicate_of).map(c=>c.id)),social:new Set(p.social.map(s=>s.id)),
  name:p.defaults.name||'',stage:p.defaults.stage,score:p.defaults.score,responsible:p.defaults.responsible_user_id,attach:Boolean(p.document),allowName:false};}
function supplierAINewBody(p,state){
 const fields={};
 for(const [key,f] of Object.entries(state.fields)){const value=String(f.value||'').trim();if(value)fields[key]={value,choice:f.choice};}
 if(!String(state.name||'').trim())throw Error('Informe o nome do fornecedor.');
 return {run_id:p.run_id,name:state.name.trim(),responsible_user_id:state.responsible,stage:state.stage,score:state.score,fields,
  also_contacts:[...state.also].map(x=>{const [key,choice]=x.split(':');return {key,choice:Number(choice)};}),
  contacts:[...state.contacts],social:[...state.social],attach_document:state.attach,allow_name_duplicate:state.allowName};}
function supplierAIFoundIn(s){return s.source_type==='website'?'Encontrado em: '+String(s.source).replace(/^https?:\/\/(www\.)?/,''):'Encontrado em: '+s.source+(s.page!=null?' — '+(typeof s.page==='number'?'página ':'aba ')+s.page:'');}
async function supplierAIPost(path,body){
 const r=await fetch('/api/v1/fornecedores'+path,{method:'POST',credentials:'same-origin',headers:{'X-CSRF-Token':document.querySelector('[name=csrf_token]')?.value||'','Content-Type':'application/json'},body:JSON.stringify(body)});
 const data=await r.json().catch(()=>({}));if(!r.ok){const e=Error(typeof data.detail==='string'?data.detail:data.detail?.message||'Não foi possível cadastrar.');e.detail=data.detail;e.status=r.status;throw e;}return data;}
function supplierAINew(ctx){
 const {request,node,field,modal,msg}=ctx;
 modal('✨ Novo fornecedor com IA · 1. Fontes',box=>{
  const intro=node('p','Envie a ficha cadastral e/ou informe o site oficial. A IA só sugere: nenhum fornecedor é criado até você revisar e confirmar.');intro.className='supplier-ai-note';box.append(intro);
  const f=field(box,'file','Ficha cadastral (arraste aqui ou escolha) — PDF, DOCX, XLSX, XLS, CSV, PNG ou JPG','',null,'file');f.accept=SUPPLIER_AI_READABLE.join(',');f.className='supplier-ai-drop';
  field(box,'url','Site oficial','',null,'url').placeholder='https://empresa.com';
 },async v=>{
  const hasFile=Boolean(v.file&&v.file.size),url=String(v.url||'').trim();
  if(!hasFile&&!url)throw Error('Envie a ficha cadastral e/ou informe o site oficial.');
  const fd=new FormData();if(hasFile)fd.append('file',v.file);fd.append('url',url);
  msg('Analisando… pode levar até 1 minuto. Nenhum fornecedor é criado nesta etapa.');
  const p=await request('/ai/analisar','POST',fd);msg('Análise concluída. Revise antes de cadastrar.');setTimeout(()=>supplierAINewReview(ctx,p),0);
 },'Analisar e preencher');
}
function supplierAINewReview(ctx,p){
 const {cfg,node,modal,msg}=ctx;const state=supplierAINewState(p);const byKey=Object.fromEntries(p.fields.map(f=>[f.key,f]));let created=false;
 const dialog=document.getElementById('supplier-dialog');
 const check=(label,on,fn,disabled=false)=>{const l=node('label');l.className='supplier-ai-check';const c=node('input');c.type='checkbox';c.checked=on;c.disabled=disabled;c.onchange=()=>fn(c.checked);l.append(c,node('span',label));return l;};
 const select=(label,options,value,fn)=>{const l=node('label',label);const e=node('select');Object.entries(options).forEach(([k,t])=>{const o=node('option',t);o.value=k;e.append(o);});e.value=value;e.onchange=()=>fn(e.value);l.append(e);return l;};
 modal('✨ Novo fornecedor com IA · 2. Revisar e 3. Confirmar',box=>{
  const head=node('section');head.className='supplier-ai-head';
  head.append(node('p',['Fontes: '+({combined:'ficha cadastral + site oficial',supplier_document:'ficha cadastral',website:'site oficial'}[p.source.type]),p.source.document_name,p.source.domain,p.pages.length?p.pages.length+' página(s) lida(s)':'','modelo '+p.model].filter(Boolean).join(' · ')));
  if(p.discarded)head.append(node('p',p.discarded+' sugestão(ões) descartada(s) por não terem evidência na fonte.'));p.warnings.forEach(w=>head.append(node('p','⚠ '+w)));
  if(p.duplicates.length){const d=node('section');d.className='supplier-ai-duplicates';const strong=p.duplicates.some(x=>x.strong);
   d.append(node('strong',strong?'Possível fornecedor já cadastrado':'Fornecedor com nome semelhante'));
   p.duplicates.forEach(x=>{const row=node('p',`${x.name} · Responsável: ${x.responsible||'—'} · Etapa: ${x.stage} · ${x.reasons.map(r=>SUPPLIER_AI_REASONS[r]).join(', ')}`);
    const open=node('button','Abrir fornecedor existente');open.type='button';open.onclick=()=>{dialog?.close();ctx.openSupplier(x.id);};row.append(open);d.append(row);});
   if(!strong)d.append(check('Entendo que pode ser outra empresa; cadastrar mesmo assim',false,on=>{state.allowName=on;}));head.append(d);}
  box.append(head);
  const crm=node('fieldset');crm.className='supplier-form-group supplier-ai-group';crm.append(node('legend','Fornecedor no PRM'));
  const name=node('label','Nome do fornecedor');const ni=node('input');ni.value=state.name;ni.maxLength=200;ni.required=true;ni.oninput=()=>{state.name=ni.value;};name.append(ni);crm.append(name);
  const owners=cfg.manager?cfg.users:cfg.users.filter(u=>u.id===cfg.user_id);
  crm.append(select('Responsável no PRM',Object.fromEntries(owners.map(u=>[u.id,u.name])),state.responsible,v=>{state.responsible=v;}),
   select('Etapa inicial',cfg.stages,state.stage,v=>{state.stage=v;}),
   select('Score inicial',Object.fromEntries(Object.entries(cfg.scores).map(([k,t])=>[k,(SUPPLIER_AI_SCORE_ICONS[k]||'')+t])),state.score,v=>{state.score=v;}));
  if(p.document)crm.append(check(`Anexar ${p.document.original_name} em Documentos › Ficha cadastral`,state.attach,on=>{state.attach=on;}));
  box.append(crm);
  const groups={};p.all_fields.forEach(f=>(groups[f.group]=groups[f.group]||[]).push(f));
  Object.entries(groups).forEach(([label,items])=>{const g=node('fieldset');g.className='supplier-form-group supplier-ai-group';g.append(node('legend',label));
   items.forEach(meta=>{const f=byKey[meta.key],s=state.fields[meta.key],row=node('div');row.className='supplier-ai-field'+(f?' status-'+f.status:'');
    const l=node('label',meta.label);const input=node(meta.key==='notes'?'textarea':'input');if(meta.key!=='notes')input.type={email:'email',url:'url',phone:'tel'}[meta.kind]||'text';
    input.value=s.value;input.maxLength=meta.key==='uf'?2:4000;input.oninput=()=>{s.value=input.value;};l.append(input);row.append(l);
    if(f){if(f.status==='conflict')row.append(node('small','Fontes divergentes — escolha qual usar.'));
     f.suggestions.forEach((x,i)=>{const opt=node('div');opt.className='supplier-ai-option';
      if(f.suggestions.length>1){const r=node('input');r.type='radio';r.name='new-'+meta.key;r.checked=s.choice===i;r.setAttribute('aria-label','Usar '+x.value);r.onchange=()=>{s.choice=i;s.value=x.value;input.value=x.value;};opt.append(r);}
      opt.append(node('span',x.value));const m=node('small',[SUPPLIER_AI_CONFIDENCE[x.confidence],supplierAIFoundIn(x),x.verified?'':'evidência não verificável automaticamente',x.warning||''].filter(Boolean).join(' · '));m.className='conf-'+x.confidence;opt.append(m);
      const ev=node('details');ev.append(node('summary','Evidência'),node('p',x.evidence));opt.append(ev);
      if(f.suggestions.length>1&&['email','phone'].includes(f.kind))opt.append(check('cadastrar também como contato',false,on=>{on?state.also.add(meta.key+':'+i):state.also.delete(meta.key+':'+i);}));
      row.append(opt);});}
    g.append(row);});box.append(g);});
  if(p.contacts.length){const g=node('fieldset');g.className='supplier-form-group supplier-ai-group';g.append(node('legend','Contatos'));p.contacts.forEach(c=>{const row=node('div');row.className='supplier-ai-field';
   row.append(check([c.name,c.role].filter(Boolean).join(' · ')+(c.duplicate_of?' (repetido)':''),state.contacts.has(c.id),on=>{on?state.contacts.add(c.id):state.contacts.delete(c.id);},Boolean(c.duplicate_of)));
   row.append(node('small',[c.email,c.phone,c.mobile,c.whatsapp&&'WhatsApp '+c.whatsapp,SUPPLIER_AI_CONFIDENCE[c.confidence],supplierAIFoundIn(c)].filter(Boolean).join(' · ')));g.append(row);});box.append(g);}
  if(p.social.length){const g=node('fieldset');g.className='supplier-form-group supplier-ai-group';g.append(node('legend','Redes sociais'));p.social.forEach(x=>{const row=node('div');row.className='supplier-ai-field';row.append(check(x.network+': '+x.url,state.social.has(x.id),on=>{on?state.social.add(x.id):state.social.delete(x.id);}));g.append(row);});box.append(g);}
  dialog?.addEventListener('close',()=>{if(!created)supplierAIPost('/ai/descartar',{run_id:p.run_id}).catch(()=>{});},{once:true});
 },async()=>{
  let result;try{result=await supplierAIPost('/ai/criar',supplierAINewBody(p,state));}
  catch(e){if(e.status===409&&e.detail&&typeof e.detail==='object'){const names=(e.detail.duplicates||[]).map(x=>`${x.name} (${x.reasons.map(r=>SUPPLIER_AI_REASONS[r]).join(', ')})`).join('; ');
    if(e.detail.can_continue&&confirm(e.detail.message+'\n\n'+names+'\n\nCadastrar mesmo assim?')){state.allowName=true;result=await supplierAIPost('/ai/criar',supplierAINewBody(p,state));}
    else{const strong=(e.detail.duplicates||[]).find(x=>x.strong);if(strong&&confirm(e.detail.message+'\n\n'+names+'\n\nAbrir o fornecedor existente?')){created=true;dialog?.close();ctx.openSupplier(strong.id);}throw Error(e.detail.message+(names?' — '+names:''));}}
   else throw e;}
  created=true;msg(result.summary);setTimeout(()=>ctx.openSupplier(result.id),0);
 },'Cadastrar fornecedor');
}
