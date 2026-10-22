(() => {
  "use strict";
  const $=id=>document.getElementById(id),root=$("rm-page");if(!root)return;
  const api="/api/v1/remocao-arquivos";
  let current=new URLSearchParams(location.search).get("lote"),data=null,busy=false,envs=null,perms=null;
  const selected=new Set(),opened=new Set();
  const csrf=()=>document.querySelector('input[name="csrf_token"]')?.value||"";
  const message=text=>{$("rm-message").textContent=text;};
  const COMPANY={choice:"Choice",sag:"SAG",portwell:"Portwell"};
  const labels={preview_queued:"Dry Run na fila",preview_running:"Consultando loja",review:"Pronto para aprovação",nothing:"Nada a remover",
    not_found:"SKU inexistente",blocked:"Bloqueado",queued:"Na fila de execução",running:"Fazendo backup e removendo",done:"Removido e verificado",
    error:"Erro",uncertain:"Incerto: reconferir",cancelled:"Cancelado",restore_queued:"Restauração na fila",restoring:"Restaurando",
    restored:"Restaurado e verificado",restore_error:"Erro na restauração",reconcile_queued:"Reconferência na fila",reconciling:"Reconferindo"};
  const tone={done:"is-ok",restored:"is-ok",review:"is-info",error:"is-alert",blocked:"is-alert",uncertain:"is-alert",restore_error:"is-alert",not_found:"is-warn",
    queued:"is-busy",running:"is-busy",preview_queued:"is-busy",preview_running:"is-busy",restore_queued:"is-busy",restoring:"is-busy",reconcile_queued:"is-busy",reconciling:"is-busy"};
  const events={batch_created:"Lote criado",approved:"Aprovado",queued:"Enviado para execução",grant_issued:"Liberação emitida",grant_consumed:"Liberação utilizada",
    permissions_verified:"Permissões da loja conferidas",backup_verified:"Backup verificado",removal_sent:"Remoção enviada",removal_verified:"Remoção confirmada na loja",
    done:"Concluído",error:"Erro",uncertain:"Incerto",blocked_worker:"Bloqueado no worker",blocked_attempt:"Tentativa bloqueada",restore_queued:"Restauração solicitada",
    restore_sent:"Restauração enviada",restored:"Restaurado",restore_done:"Restauração concluída",media_reuploaded:"Imagem reenviada do backup",
    document_reuploaded:"Documento reenviado do backup",reconcile_queued:"Reconferência solicitada",reconciled:"Reconferido",paused:"Pausado",cancelled:"Cancelado",
    not_found:"SKU inexistente",preview_review:"Dry Run pronto",preview_nothing:"Nada a remover",preview_blocked:"Dry Run bloqueado"};
  function el(tag,text,className){const node=document.createElement(tag);if(text!=null)node.textContent=text;if(className)node.className=className;return node;}
  async function request(url,options={}){const r=await fetch(url,{cache:"no-store",credentials:"same-origin",...options});const body=await r.json().catch(()=>({}));if(!r.ok)throw Error(typeof body.detail==="string"?body.detail:"Falha na solicitação");return body;}
  const post=(url,body,method="POST")=>request(url,{method,headers:{"X-CSRF-Token":csrf(),"Content-Type":"application/json"},body:JSON.stringify(body||{})});
  const when=t=>t?new Date(t*1000).toLocaleString("pt-BR"):"—";
  const person=id=>(data?.people||{})[id]||(id==="worker"?"PRM (worker)":id||"—");
  const img=i=>i?`#${i.id}${i.name?" "+i.name:""}`:"—";
  const doc=d=>`${d.label||"sem label"}${d.filename?" ("+d.filename+")":""}`;
  const size=n=>n>=1048576?(n/1048576).toFixed(1)+" MB":Math.max(1,Math.round(n/1024))+" KB";
  function list(title,items){const box=el("div",null,"rm-list");box.append(el("strong",`${title} (${items.length})`));const ul=el("ul");items.forEach(t=>ul.append(el("li",t)));if(!items.length)ul.append(el("li","—"));box.append(ul);return box;}

  // --- Confirmação digitada ---------------------------------------------------------------
  function typed(title,text,phrase){
    return new Promise(resolve=>{
      const dialog=$("rm-confirm"),input=$("rm-confirm-input"),ok=$("rm-confirm-ok");
      $("rm-confirm-title").textContent=title;$("rm-confirm-text").textContent=text;$("rm-confirm-phrase").textContent=phrase;
      input.value="";ok.disabled=true;
      const check=()=>{ok.disabled=input.value.trim().toUpperCase().replace(/\s+/g," ")!==phrase;};
      const done=value=>{input.removeEventListener("input",check);dialog.close();resolve(value);};
      input.addEventListener("input",check);
      $("rm-confirm-cancel").onclick=()=>done(null);
      dialog.querySelector("form").onsubmit=e=>{e.preventDefault();if(!ok.disabled)done(input.value.trim());};
      dialog.addEventListener("cancel",()=>resolve(null),{once:true});
      dialog.showModal();input.focus();
    });
  }

  // --- Ambientes ----------------------------------------------------------------------------
  function pill(text,cls){return el("span",text,"prm-pill "+(cls||""));}
  function renderEnvs(){
    const grid=$("rm-env-grid");grid.replaceChildren();
    $("rm-env-summary").textContent=(envs.master_switch?"Trava mestra do servidor: liberada.":"Trava mestra do servidor: bloqueada — nenhuma operação de produção pode ser liberada.")+
      (envs.https?" Conexão HTTPS.":" Você está acessando por HTTP: operações de produção exigem HTTPS.");
    envs.companies.forEach(c=>{
      const card=el("article",null,"rm-env-card"),p=c.permissions,mine=Object.entries({approve:"aprovar",execute:"executar",restore:"restaurar",admin:"administrar"}).filter(([k])=>p[k]).map(([,v])=>v);
      card.append(el("h3",COMPANY[c.company]));
      const badges=el("div",null,"rm-env-badges");
      badges.append(pill(c.active?"Produção ativa":c.production?"Produção ligada, trava do servidor bloqueando":"Homologação",c.active?"is-alert":"is-info"),
        pill(c.four_eyes?"Quatro olhos: ativo":"Quatro olhos: desativado",c.four_eyes?"is-ok":"is-warn"));
      card.append(badges);
      card.append(el("p",`Suas permissões: ${mine.length?mine.join(", "):"nenhuma"}.`,"prm-status"));
      if(c.changed_at)card.append(el("p",`Última alteração: ${when(c.changed_at)}.`,"prm-status"));
      const pf=c.preflight||{};
      if(pf.at)card.append(el("p",`Teste da loja em ${when(pf.at)}: ${pf.ok?"aprovado":"com falhas — "+(pf.checks||[]).filter(x=>!x.ok).map(x=>x.detail).join("; ")}`,"prm-status"));
      const actions=el("div",null,"rm-env-actions");
      const button=(text,fn,cls)=>{const b=el("button",text,cls||"button-secondary");b.type="button";b.addEventListener("click",()=>fn().catch(e=>message(e.message)));actions.append(b);return b;};
      if(Object.values(p).some(Boolean))button("Testar conexão",async()=>{message(`Testando ${COMPANY[c.company]} (somente leitura)…`);const r=await post(`${api}/ambientes/${c.company}/teste`);message(r.ok?"Conexão, credenciais e permissões da loja confirmadas.":"Teste com falhas: "+r.checks.filter(x=>!x.ok).map(x=>x.detail).join("; "));await loadEnvs();});
      if(p.admin){
        if(c.production)button("Desativar produção",async()=>{if(!confirm(`Desativar a produção da ${COMPANY[c.company]}? Liberações ainda não usadas deixam de valer.`))return;await post(`${api}/ambientes/${c.company}/producao`,{ativar:false});message("Produção desativada.");await loadEnvs();},"button-secondary prm-btn-danger");
        else button("Ativar produção",async()=>{const phrase=`ATIVAR PRODUCAO ${c.company.toUpperCase()}`;const v=await typed(`Ativar produção · ${COMPANY[c.company]}`,"Ativar a produção NÃO remove nada: cada lote continua exigindo Dry Run, aprovação, confirmação e, com quatro olhos, outra pessoa para executar. O PRM testa a loja antes de ativar.",phrase);if(!v)return;await post(`${api}/ambientes/${c.company}/producao`,{ativar:true,confirmacao:v});message("Produção ativada para "+COMPANY[c.company]+".");await loadEnvs();});
        if(c.four_eyes)button("Desativar quatro olhos",async()=>{const phrase=`DESATIVAR QUATRO OLHOS ${c.company.toUpperCase()}`;const v=await typed("Desativar quatro olhos","Sem quatro olhos, quem aprova também poderá executar o mesmo lote.",phrase);if(!v)return;await post(`${api}/ambientes/${c.company}/quatro-olhos`,{ativar:false,confirmacao:v});await loadEnvs();});
        else button("Ativar quatro olhos",async()=>{await post(`${api}/ambientes/${c.company}/quatro-olhos`,{ativar:true});await loadEnvs();});
      }
      card.append(actions);grid.append(card);
    });
  }
  async function loadEnvs(){envs=await request(`${api}/ambientes`);renderEnvs();if(envs.companies.some(c=>c.permissions.admin))await loadPermissions();else $("rm-permissions").hidden=true;}

  // --- Permissões -----------------------------------------------------------------------------
  async function loadPermissions(){
    perms=await request(`${api}/permissoes`);$("rm-permissions").hidden=false;
    const select=$("rm-perm-company"),value=select.value;select.replaceChildren(...perms.admin_of.map(c=>{const o=el("option",COMPANY[c]);o.value=c;return o;}));
    if(perms.admin_of.includes(value))select.value=value;renderPermissions();
  }
  function renderPermissions(){
    const company=$("rm-perm-company").value,body=$("rm-perm-rows");body.replaceChildren();
    perms.users.forEach(u=>{
      const tr=el("tr"),flags=u.companies[company];tr.append(el("td",`${u.name} (${u.email})`),el("td",u.role));
      const boxes={};
      [["approve","aprovar"],["execute","executar"],["restore","restaurar"],["admin","administrar"]].forEach(([k,label])=>{
        const td=el("td"),box=el("input");box.type="checkbox";box.checked=flags[k];box.setAttribute("aria-label",`${label} · ${u.name}`);
        if(k==="admin"&&u.role!=="desenvolvedor")box.disabled=true;boxes[k]=box;td.append(box);tr.append(td);});
      const td=el("td"),save=el("button","Salvar","button-secondary");save.type="button";
      save.addEventListener("click",async()=>{try{await post(`${api}/permissoes`,{usuario:u.id,empresa:company,aprovar:boxes.approve.checked,executar:boxes.execute.checked,restaurar:boxes.restore.checked,administrar:boxes.admin.checked},"PUT");message(`Permissões de ${u.name} na ${COMPANY[company]} salvas.`);await loadEnvs();}catch(e){message(e.message);}});
      td.append(save);tr.append(td);body.append(tr);
    });
  }
  $("rm-perm-company").addEventListener("change",renderPermissions);

  // --- Lote --------------------------------------------------------------------------------
  function detail(item){
    const d=item.dry_run,box=el("div",null,"rm-detail");
    if(!d){box.append(el("p",item.error||"Sem Dry Run."));return box;}
    const grid=el("div",null,"rm-detail-grid");
    grid.append(list("Atual · principal",[img(d.current.main)].filter(t=>t!=="—")),list("Atual · galeria",d.current.gallery.map(img)),list("Atual · documentos WCDA",d.current.documents.map(doc)),
      list("Desvincular · imagens",d.unlink.images.map(img)),list("Desvincular · documentos",d.unlink.documents.map(doc)),
      list("Preservar · imagens",d.preserve.images.map(img)),list("Preservar · documentos",d.preserve.documents.map(doc)),
      list("Proposto · principal",[img(d.proposed.main)].filter(t=>t!=="—")),list("Proposto · galeria",d.proposed.gallery.map(img)));
    box.append(grid);
    box.append(list("Gravações previstas",d.writes.map(w=>`${w.api} ${w.method} ${w.endpoint} · ${JSON.stringify(w.payload)}`)));
    if(d.blockers.length)box.append(list("Bloqueios",d.blockers));
    if(d.warnings.length)box.append(list("Avisos",d.warnings));
    box.append(el("p",`Campos protegidos (não enviados): ${d.protected_fields.join(", ")}. Mídia nunca é excluída da biblioteca.`,"prm-status"));
    if(item.write_gate)box.append(el("p",item.write_gate,"prm-note"));
    const who=[];
    if(item.approval)who.push(`Aprovado por ${person(item.approval.by)} em ${when(item.approval.at)}`);
    if(item.execution)who.push(`Execução solicitada por ${person(item.execution.by)} em ${when(item.execution.at)} (${item.execution.env==="production"?"produção":"homologação"})`);
    if(who.length)box.append(el("p",who.join(" · ")));
    if(item.backup){const p=el("p",`Backup verificado: ${item.backup.images} imagem(ns), ${item.backup.documents} documento(s), ${size(item.backup.bytes)}. `);
      const a=el("a","Baixar backup");a.href=`${api}/${data.id}/backup/${encodeURIComponent(item.sku)}`;p.append(a);box.append(p);}
    if(item.result)box.append(el("p",`Resultado: ${item.result.status}; verificado na loja: ${item.result.verified?"sim":"não"}.`));
    if(item.restore)box.append(el("p",`Restauração: ${item.restore.status}${item.restore.reuploaded?.length?` · ${item.restore.reuploaded.length} arquivo(s) reenviado(s) do backup`:""}.`));
    if(item.audit.length)box.append(list("Auditoria",item.audit.map(a=>`${when(a.at)} · ${person(a.actor)} · ${events[a.event]||a.event}`)));
    return box;
  }
  function visible(){const f=$("rm-filter").value;return data.items.filter(i=>!f||i.state===f);}
  function render(){
    if(!data)return;$("rm-current").hidden=false;window.history.replaceState(null,"","?lote="+data.id);
    $("rm-title").textContent=`${data.mode_label} · ${COMPANY[data.company]||data.company} · ${when(data.created)}`;
    $("rm-summary").textContent=`${data.total} SKU(s) · ${Object.entries(data.counts).map(([k,v])=>`${labels[k]||k}: ${v}`).join(" · ")}`;
    const env=data.environment;
    $("rm-batch-env").textContent=env.active?`Produção ativa nesta loja${env.four_eyes?" · quatro olhos: quem aprova não executa":""}. Criado por ${person(data.owner)}.`:`Homologação: só executa com política de staging ou liberação de homologação. Criado por ${person(data.owner)}.`;
    $("rm-progress").value=data.progress;$("rm-done").textContent=`${data.done} concluídos`;$("rm-skipped").textContent=`${data.skipped} ignorados`;$("rm-failed").textContent=`${data.failed} com erro`;
    $("rm-report").href=`${api}/${data.id}/relatorio`;$("rm-json").href=`${api}/${data.id}/dry-run`;
    const body=$("rm-items");body.replaceChildren();
    visible().forEach(item=>{
      const d=item.dry_run,tr=el("tr"),pick=el("td"),box=el("input");box.type="checkbox";box.checked=selected.has(item.sku);box.setAttribute("aria-label","Selecionar "+item.sku);
      box.addEventListener("change",()=>box.checked?selected.add(item.sku):selected.delete(item.sku));pick.append(box);tr.append(pick);
      const sku=el("td"),toggle=el("button",item.sku,"rm-sku");toggle.type="button";toggle.setAttribute("aria-expanded",String(opened.has(item.sku)));
      toggle.addEventListener("click",()=>{opened.has(item.sku)?opened.delete(item.sku):opened.add(item.sku);render();});sku.append(toggle);tr.append(sku);
      const c=d?.current;
      [item.product_id?`#${item.product_id}`:"—",c?img(c.main):"—",c?String(c.gallery.length):"—",c?String(c.documents.length):"—",
       d?`${d.unlink.images.length} imagem(ns) · ${d.unlink.documents.length} doc(s)`:"—",d?`${d.preserve.images.length} imagem(ns) · ${d.preserve.documents.length} doc(s)`:"—"].forEach(t=>tr.append(el("td",t)));
      const status=el("td");status.append(el("span",(labels[item.state]||item.state)+(item.approval&&item.state==="review"?" · aprovado":""),"prm-pill "+(tone[item.state]||"")));tr.append(status);
      tr.append(el("td",[item.error,...(d?.warnings||[])].filter(Boolean).join(" · ")||"—"));
      body.append(tr);
      if(opened.has(item.sku)){const row=el("tr",null,"rm-detail-row"),td=el("td");td.colSpan=10;td.append(detail(item));row.append(td);body.append(row);}
    });
    if(!body.children.length){const tr=el("tr"),td=el("td","Nenhum SKU neste filtro.");td.colSpan=10;tr.append(td);body.append(tr);}
    if(!$("rm-audit").hidden)loadAudit();
  }
  async function loadAudit(){
    const rows=(await request(`${api}/${data.id}/auditoria`)).items,body=$("rm-audit-rows");body.replaceChildren();
    rows.slice().reverse().forEach(a=>{const tr=el("tr");tr.append(el("td",when(a.at)),el("td",a.sku||"lote"),el("td",a.actor==="worker"?"PRM (worker)":a.actor),el("td",events[a.event]||a.event),
      el("td",a.detail.reason||a.detail.error||a.detail.status||a.detail.env||""));body.append(tr);});
  }
  $("rm-audit-toggle").addEventListener("click",async()=>{const box=$("rm-audit");box.hidden=!box.hidden;$("rm-audit-toggle").setAttribute("aria-expanded",String(!box.hidden));if(!box.hidden&&data)await loadAudit().catch(e=>message(e.message));});
  async function history(){
    const items=(await request(api)).items,box=$("rm-history");box.replaceChildren();
    items.forEach(h=>{const b=el("button",`${(COMPANY[h.company]||h.company).toUpperCase()} · ${({all:"Remover tudo",gallery:"Galeria",documents:"Documentos",main:"Foto principal"})[h.mode]} · ${when(h.created)}`);b.type="button";
      b.addEventListener("click",()=>{current=h.id;selected.clear();opened.clear();refresh();});box.append(b);});
    if(!items.length)box.append(el("p","Nenhum lote.","prm-status"));
  }
  async function refresh(){if(current){data=await request(`${api}/${current}`);render();}await history();}
  $("rm-form").addEventListener("submit",async event=>{
    event.preventDefault();if(busy)return;busy=true;message("Criando lote e enfileirando o Dry Run…");
    try{const form=new FormData(event.target);if(!$("rm-sheet").files.length)form.delete("planilha");
      data=await request(api,{method:"POST",headers:{"X-CSRF-Token":csrf()},body:form});current=data.id;selected.clear();opened.clear();render();
      message(`${data.total} SKU(s) na fila de Dry Run`+(data.duplicates_removed?` · ${data.duplicates_removed} repetido(s) unificado(s)`:"")+". Nenhuma alteração na loja.");history();}
    catch(e){message(e.message);}finally{busy=false;}
  });
  const questions={aprovar:"Aprovar o Dry Run",pausar:"Pausar a fila entre produtos",cancelar:"Cancelar os itens ainda na fila",
    reprocessar:"Refazer o Dry Run dos itens com erro, bloqueados, inexistentes ou cancelados",reconferir:"Reconferir na loja (somente leitura) os itens incertos ou com erro",
    executar:"Executar a remoção dos aprovados",restaurar:"Restaurar os vínculos anteriores dos itens removidos"};
  const withSkus=new Set(["aprovar","executar","restaurar","reconferir"]);
  function targets(action,skus){
    const pick=i=>!skus.length||skus.includes(i.sku);
    if(action==="executar")return data.items.filter(i=>i.state==="review"&&i.approval&&i.approval.dry_run_sha256===i.dry_run?.dry_run_sha256&&pick(i)).length;
    if(action==="restaurar")return data.items.filter(i=>i.restorable&&pick(i)).length;
    return null;
  }
  root.querySelectorAll("[data-action]").forEach(button=>button.addEventListener("click",async()=>{
    if(!data||busy)return;const action=button.dataset.action,skus=[...selected];
    const scope=skus.length&&withSkus.has(action)?skus.length+" SKU(s) selecionado(s)":"todos os aptos";
    let confirmacao="";
    if(["executar","restaurar"].includes(action)&&data.environment.active){
      const count=targets(action,skus);if(!count){message("Nenhum item apto para esta ação.");return;}
      const phrase=`${action==="executar"?"EXECUTAR":"RESTAURAR"} ${count} ${data.company.toUpperCase()}`;
      const text=action==="executar"?`Remover (${data.mode_label.toLowerCase()}) de ${count} produto(s) da ${COMPANY[data.company]} em produção. Antes de cada produto o PRM faz e confere o backup; sem backup válido nada é removido.`
        :`Restaurar os vínculos anteriores de ${count} produto(s) da ${COMPANY[data.company]} em produção. Arquivos apagados da biblioteca são reenviados a partir do backup.`;
      confirmacao=await typed(action==="executar"?"Executar remoção em produção":"Restaurar em produção",text,phrase);if(!confirmacao)return;
    }else if(!confirm(`${questions[action]} — ${scope}?`))return;
    busy=true;
    try{const body=withSkus.has(action)?{skus:skus.length?skus:null,confirmacao}:{};
      data=await post(`${api}/${data.id}/${action}`,body);message("Operação registrada.");render();}
    catch(e){message(e.message);}finally{busy=false;}
  }));
  $("rm-select-all").addEventListener("change",e=>{visible().forEach(i=>e.target.checked?selected.add(i.sku):selected.delete(i.sku));render();});
  $("rm-filter").addEventListener("change",render);
  loadEnvs().catch(e=>{$("rm-env-summary").textContent=e.message;});
  async function poll(){try{if(!busy&&!document.hidden)await refresh();}catch(e){message(e.message);}setTimeout(poll,3000);}poll();
})();
