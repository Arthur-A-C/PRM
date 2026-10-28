(() => {
  "use strict";
  const $=id=>document.getElementById(id),root=$("wa-page");if(!root)return;
  const api="/api/v1/pauta-semanal";
  let agenda=null,page=1,dialogSave=null,busy=false;
  const csrf=()=>document.querySelector('input[name="csrf_token"]')?.value||"";
  const message=text=>{$("wa-message").textContent=text;};
  const tone={deployed:"is-ok",merged:"is-info",pr_open:"is-info",pr_draft:"",pr_closed:"",branch:"",issue_open:"is-warn",issue_closed:"is-ok",
    ci_ok:"is-ok",ci_fail:"is-alert",ci_pending:"is-warn",ci_none:"",task_done:"is-ok",task_open:"is-info",task_blocked:"is-alert",
    task_overdue:"is-alert",task_next:"is-info",decision:"is-warn"};
  const actions={generated:"Gerada",regenerated:"Gerada novamente",item_edited:"Item editado",item_restored:"Texto gerado restaurado",
    overview_edited:"Resumo editado",manual_added:"Anotação adicionada",manual_edited:"Anotação editada",manual_removed:"Anotação removida",
    approve:"Aprovada",reopen:"Reaberta",archive:"Arquivada",unarchive:"Desarquivada",exported_pdf:"PDF exportado"};
  function el(tag,text,className){const n=document.createElement(tag);if(text!=null)n.textContent=text;if(className)n.className=className;return n;}
  async function request(url,options={}){
    const r=await fetch(url,{cache:"no-store",credentials:"same-origin",...options});
    const body=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(typeof body.detail==="string"?body.detail:Array.isArray(body.detail)?body.detail.map(d=>d.msg).join("; "):"Falha na solicitação");
    return body;
  }
  const send=(url,body,method="POST")=>request(url,{method,headers:{"Content-Type":"application/json","X-CSRF-Token":csrf()},body:body===undefined?undefined:JSON.stringify(body)});
  const when=v=>v?new Date(v).toLocaleString("pt-BR",{timeZone:"America/Sao_Paulo"}):"—";
  const day=v=>v?new Date(v+"T12:00:00").toLocaleDateString("pt-BR"):"";
  const safeLink=url=>/^https:\/\//.test(url)||url.startsWith("/")?url:null;
  // One operation at a time; a click during another one is answered, never silently dropped.
  async function guard(task){if(busy){message("Aguarde: outra operação ainda está em andamento.");return;}busy=true;try{await task();}catch(e){message(e.message);}finally{busy=false;}}

  function edit(title,hint,text,save){
    $("wa-dialog-title").textContent=title;$("wa-dialog-hint").textContent=hint||"";$("wa-dialog-text").value=text||"";dialogSave=save;$("wa-dialog").showModal();$("wa-dialog-text").focus();
  }
  $("wa-dialog-cancel").addEventListener("click",()=>window.PRM?.sheet?window.PRM.sheet.requestClose($("wa-dialog")):$("wa-dialog").close());
  const confirmBox=o=>window.PRM?.sheet?window.PRM.sheet.confirm(o):Promise.resolve(confirm([o.title,o.text].filter(Boolean).join("\n\n")));
  $("wa-dialog").querySelector("form").addEventListener("submit",e=>{e.preventDefault();const text=$("wa-dialog-text").value;$("wa-dialog").close();if(dialogSave)guard(()=>dialogSave(text));});

  // --- Pauta -------------------------------------------------------------------------------------
  function render(){
    const a=agenda,box=$("wa-agenda");if(!a){box.hidden=true;return;}
    box.hidden=false;root.dataset.status=a.status;
    $("wa-title").textContent=a.title;
    const ai=a.generation.ai||{};
    $("wa-meta").textContent=`Versão ${a.version} · gerada em ${when(a.generated_at)} por ${a.generated_by}`+(a.approved_at?` · aprovada em ${when(a.approved_at)} por ${a.approved_by}`:"")+
      ` · redação: ${ai.used?`IA (${ai.accepted} texto(s) aceitos, ${ai.rejected} recusado(s) pela verificação)`:"por regras"}`;
    const badges=$("wa-badges");badges.replaceChildren(el("span",a.status_label,"prm-pill "+({draft:"is-info",approved:"is-ok",archived:""}[a.status])));
    if(a.sources.repository)badges.append(el("span",`${a.sources.repository}: ${a.sources.pulls} PR(s), ${a.sources.commits} commit(s), ${a.sources.issues} issue(s)`,"prm-pill"));
    badges.append(el("span",`Planner: ${a.sources.planner} tarefa(s)`,"prm-pill"));
    badges.append(el("span",a.sources.deployed_commit?`Commit em produção: ${a.sources.deployed_commit.slice(0,12)}`:"Commit em produção não informado","prm-pill "+(a.sources.deployed_commit?"is-ok":"is-warn")));
    const warnings=[...(a.generation.github_error?[`GitHub: ${a.generation.github_error}`]:[]),...a.generation.warnings,...(!ai.used&&ai.reason?[ai.reason]:[])];
    $("wa-warnings").replaceChildren(...warnings.map(w=>el("li",w)));
    $("wa-overview-text").textContent=a.overview||"—";
    $("wa-pdf").href=`${api}/pautas/${a.id}/pdf`;
    root.querySelectorAll("[data-transition]").forEach(b=>{b.hidden=!({aprovar:["draft"],reabrir:["approved"],arquivar:["draft","approved"],desarquivar:["archived"]})[b.dataset.transition].includes(a.status);});
    const editable=a.status==="draft";root.querySelectorAll(".wa-edit-only").forEach(n=>n.hidden=!editable);
    renderSections(editable);renderManual(editable);renderPeople();
    if($("wa-audit-box").open)loadAudit();
  }
  function renderSections(editable){
    const host=$("wa-sections");host.replaceChildren();
    agenda.sections.forEach(section=>{
      const visible=section.items.filter(i=>!i.hidden);
      const card=el("section",null,"wa-section");card.dataset.section=section.key;
      card.append(el("h3",`${section.label} (${visible.length})`));
      if(!section.items.length){card.append(el("p","Nada registrado nas fontes desta semana.","prm-status"));host.append(card);return;}
      const list=el("ul",null,"wa-items");
      section.items.forEach(item=>{
        const li=el("li",null,"wa-item"+(item.hidden?" is-hidden":""));li.dataset.key=item.key;
        li.append(el("p",item.text,"wa-item-text"));
        const meta=el("div",null,"wa-item-meta");
        meta.append(el("span",item.status_label,"prm-pill "+(tone[item.status]||"")));
        if(item.tags.includes("bug"))meta.append(el("span","bug","prm-pill is-warn"));
        if(item.wording==="ai")meta.append(el("span","redação IA","prm-pill"));
        if(item.edited)meta.append(el("span",`editado${item.edited_by?" por "+item.edited_by:""}`,"prm-pill is-info"));
        if(item.hidden)meta.append(el("span","oculto na pauta","prm-pill"));
        if(item.people.length)meta.append(el("span",item.people.join(", "),"wa-people-names"));
        item.links.forEach(l=>{const url=safeLink(l.url);if(!url)return;const a=el("a",l.label,"wa-source");a.href=url;if(url.startsWith("http")){a.target="_blank";a.rel="noopener noreferrer";}meta.append(a);});
        li.append(meta);
        if(item.source_changed)li.append(el("p",item.source_changed,"wa-flag"));
        if(item.source_missing)li.append(el("p","A fonte deste item não aparece mais na coleta; texto humano preservado.","wa-flag"));
        if(editable){
          const tools=el("div",null,"wa-item-tools");
          const button=(text,fn)=>{const b=el("button",text,"button-secondary");b.type="button";b.addEventListener("click",fn);tools.append(b);};
          button("Editar",()=>edit("Editar item",`Situação comprovada: ${item.status_label}. Não descreva como implantado o que não estiver implantado.`,item.text,
            async text=>{agenda=await send(`${api}/pautas/${agenda.id}/itens/${encodeURIComponent(item.key)}`,{version:agenda.version,text},"PATCH");render();message("Item salvo.");}));
          button(item.hidden?"Mostrar":"Ocultar",()=>guard(async()=>{agenda=await send(`${api}/pautas/${agenda.id}/itens/${encodeURIComponent(item.key)}`,{version:agenda.version,hidden:!item.hidden},"PATCH");render();}));
          if(item.edited)button("Restaurar texto gerado",()=>guard(async()=>{agenda=await send(`${api}/pautas/${agenda.id}/restaurar-item/${encodeURIComponent(item.key)}`,{version:agenda.version});render();}));
          li.append(tools);
        }
        list.append(li);
      });
      card.append(list);host.append(card);
    });
  }
  function renderManual(editable){
    const host=$("wa-manual");host.replaceChildren();
    if(!agenda.manual.length){host.append(el("p","Nenhuma anotação ainda.","prm-status"));return;}
    agenda.manual.forEach(m=>{
      const box=el("div",null,"wa-manual-item");box.dataset.kind=m.kind;
      box.append(el("span",m.kind_label,"prm-pill "+(m.kind==="decision"?"is-warn":"is-info")),el("p",m.text),el("small",`${m.author} · ${when(m.created_at)}`,"prm-status"));
      if(editable){
        const b=el("button","Editar","button-secondary");b.type="button";
        b.addEventListener("click",()=>edit("Editar anotação","",m.text,async text=>{agenda=await send(`${api}/pautas/${agenda.id}/anotacoes/${m.id}`,{version:agenda.version,text},"PATCH");render();}));
        const r=el("button","Remover","button-secondary");r.type="button";
        r.addEventListener("click",async()=>{if(await confirmBox({title:"Remover anotação",kicker:"Pauta semanal",text:"A anotação sai da pauta; a remoção fica registrada no histórico.",confirm:"Remover",danger:true}))guard(async()=>{agenda=await request(`${api}/pautas/${agenda.id}/anotacoes/${m.id}?version=${agenda.version}`,{method:"DELETE",headers:{"X-CSRF-Token":csrf()}});render();});});
        box.append(b,r);
      }
      host.append(box);
    });
  }
  function renderPeople(){
    const host=$("wa-people"),rows=agenda.generation.contributions||[];host.replaceChildren();
    if(!rows.length){host.append(el("p","Sem contribuições identificadas nas fontes.","prm-status"));return;}
    const labels=Object.fromEntries(agenda.sections.flatMap(s=>s.items).map(i=>[i.status,i.status_label]));
    rows.forEach(r=>{const card=el("div",null,"wa-person");card.append(el("strong",r.person),
      el("p",Object.entries(r.counts).map(([k,v])=>`${labels[k]||k}: ${v}`).join(" · ")));host.append(card);});
  }
  async function loadAudit(){
    const rows=(await request(`${api}/pautas/${agenda.id}/historico`)).items,body=$("wa-audit");body.replaceChildren();
    rows.forEach(r=>{const tr=el("tr");tr.append(el("td",when(r.at)),el("td",r.actor),el("td",actions[r.action]||r.action),
      el("td",r.changes.key||r.changes.kind||(r.changes.to?`${r.changes.from} → ${r.changes.to}`:"")||(r.changes.items!=null?`${r.changes.items} itens${r.changes.ai?" · IA":""}`:"")));body.append(tr);});
  }
  $("wa-audit-box").addEventListener("toggle",()=>{if($("wa-audit-box").open&&agenda)loadAudit().catch(e=>message(e.message));});

  $("wa-overview-edit").addEventListener("click",()=>edit("Editar resumo","O resumo editado é preservado nas próximas gerações.",agenda.overview,
    async text=>{agenda=await send(`${api}/pautas/${agenda.id}/resumo`,{version:agenda.version,text},"PUT");render();}));
  $("wa-manual-form").addEventListener("submit",e=>{e.preventDefault();guard(async()=>{
    agenda=await send(`${api}/pautas/${agenda.id}/anotacoes`,{version:agenda.version,kind:$("wa-manual-kind").value,text:$("wa-manual-text").value});
    $("wa-manual-text").value="";render();message("Anotação adicionada.");});});
  const questions={aprovar:"Aprovar a pauta? Edições exigirão reabrir.",reabrir:"Reabrir a pauta para edição?",arquivar:"Arquivar a pauta? Ela fica no histórico, somente leitura.",desarquivar:"Desarquivar a pauta (volta para rascunho)?"};
  const transitionLabels={aprovar:"Aprovar",reabrir:"Reabrir",arquivar:"Arquivar",desarquivar:"Desarquivar"};
  root.querySelectorAll("[data-transition]").forEach(b=>b.addEventListener("click",async()=>{const action=b.dataset.transition;
    if(agenda&&await confirmBox({title:`${transitionLabels[action]} pauta`,kicker:"Pauta semanal",text:questions[action],confirm:transitionLabels[action]}))guard(async()=>{agenda=await send(`${api}/pautas/${agenda.id}/${action}`,{version:agenda.version});render();history();message(`Pauta: ${agenda.status_label.toLowerCase()}.`);});}));

  async function open(date){
    const rows=(await request(`${api}/pautas?page=1`)).items;
    const monday=mondayOf(date);
    const found=rows.find(r=>r.week_start===monday);
    if(found){agenda=await request(`${api}/pautas/${found.id}`);render();message("");}
    else{agenda=null;render();message("Ainda não há pauta para esta semana. Clique em “Gerar ou atualizar pauta”.");}
  }
  function mondayOf(value){const d=new Date(value+"T12:00:00");d.setDate(d.getDate()-((d.getDay()+6)%7));return d.toISOString().slice(0,10);}
  $("wa-open").addEventListener("click",()=>guard(()=>open($("wa-week").value)));
  $("wa-week-form").addEventListener("submit",async e=>{e.preventDefault();
    const monday=mondayOf($("wa-week").value),same=agenda&&agenda.week_start===monday;
    if(same&&agenda.status==="archived"){message("Pauta arquivada: desarquive antes de gerar novamente.");return;}
    if(same&&agenda.status==="approved"&&!await confirmBox({title:"Gerar pauta novamente",kicker:"Pauta semanal",text:"A pauta está aprovada. Gerar novamente a devolve para rascunho.",warnings:["Edições humanas são preservadas."],confirm:"Gerar novamente"}))return;
    guard(async()=>{$("wa-generate").classList.add("is-busy");message("Coletando GitHub e Planner…");
      try{agenda=await send(`${api}/pautas`,{semana:$("wa-week").value,version:same?agenda.version:null});render();history();
        message(agenda.generation.github_error?"Pauta gerada com o Planner; o GitHub não respondeu (veja o aviso).":"Pauta atualizada. Edições humanas foram preservadas.");}
      finally{$("wa-generate").classList.remove("is-busy");}});});

  // --- Histórico -----------------------------------------------------------------------------------
  async function history(append=false){
    const q=encodeURIComponent($("wa-q").value),status=$("wa-status").value;
    const data=await request(`${api}/pautas?q=${q}&status=${status}&page=${page}`),host=$("wa-history");
    if(!append)host.replaceChildren();
    data.items.forEach(a=>{const b=el("button",null,"wa-history-item");b.type="button";
      b.append(el("strong",`${day(a.week_start)} a ${day(a.week_end)}`),el("span",a.status_label,"prm-pill "+({draft:"is-info",approved:"is-ok",archived:""}[a.status])),
        el("small",`${a.counts.merged+a.counts.deployed} integrado(s) · ${a.counts.review} em revisão · ${a.counts.decisions} decisão(ões)`,"prm-status"));
      b.addEventListener("click",()=>guard(async()=>{agenda=await request(`${api}/pautas/${a.id}`);$("wa-week").value=a.week_start;render();window.scrollTo({top:0,behavior:"smooth"});}));host.append(b);});
    if(!host.children.length)host.append(el("p","Nenhuma pauta encontrada.","prm-status"));
    $("wa-more").hidden=!data.more;
  }
  $("wa-search").addEventListener("submit",e=>{e.preventDefault();page=1;history().catch(err=>message(err.message));});
  $("wa-more").addEventListener("click",()=>{page+=1;history(true).catch(err=>message(err.message));});

  // --- Configuração ----------------------------------------------------------------------------------
  async function loadSettings(){
    const s=await request(`${api}/configuracao`),i=s.integration;
    $("wa-enabled").checked=s.enabled;$("wa-weekday").value=String(s.weekday);$("wa-time").value=s.draft_time;$("wa-ai").checked=s.ai_enabled;$("wa-filter").value=s.planner_filter;
    $("wa-people-map").value=Object.entries(s.people).map(([k,v])=>`${k} = ${v}`).join("\n");
    const days=["segunda","terça","quarta","quinta","sexta","sábado","domingo"];
    $("wa-integration").textContent=(i.github_configured?`GitHub: ${i.repository}.`:"GitHub não configurado no servidor (somente Planner).")+
      (i.deployed_commit?` Commit em produção: ${i.deployed_commit.slice(0,12)}.`:" Commit em produção não informado: nada aparece como implantado.")+
      (i.ai_model_configured&&s.ai_enabled?" Redação com IA ativa.":" Redação por regras.")+
      (s.enabled?` Rascunho automático: ${days[s.weekday]} às ${s.draft_time}.`:" Rascunho automático desligado.");
  }
  $("wa-settings").addEventListener("submit",e=>{e.preventDefault();guard(async()=>{
    const people={};for(const line of $("wa-people-map").value.split("\n")){const [k,...v]=line.split("=");if(k.trim()&&v.join("=").trim())people[k.trim()]=v.join("=").trim();}
    await send(`${api}/configuracao`,{enabled:$("wa-enabled").checked,weekday:Number($("wa-weekday").value),draft_time:$("wa-time").value,ai_enabled:$("wa-ai").checked,planner_filter:$("wa-filter").value,people},"PUT");
    await loadSettings();message("Configuração salva.");});});
  $("wa-test").addEventListener("click",()=>guard(async()=>{const r=await send(`${api}/configuracao/teste`);message(r.message);}));

  const today=new Date().toLocaleDateString("en-CA",{timeZone:"America/Sao_Paulo"});
  $("wa-week").value=today;
  Promise.all([loadSettings(),history(),open(today)]).catch(e=>message(e.message));
})();
