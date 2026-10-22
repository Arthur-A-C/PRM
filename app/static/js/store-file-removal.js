(() => {
  "use strict";
  const $=id=>document.getElementById(id),root=$("rm-page");if(!root)return;
  const api="/api/v1/remocao-arquivos";
  let current=new URLSearchParams(location.search).get("lote"),data=null,busy=false;
  const selected=new Set(),opened=new Set();
  const csrf=()=>document.querySelector('input[name="csrf_token"]')?.value||"";
  const message=text=>{$("rm-message").textContent=text;};
  const labels={preview_queued:"Dry Run na fila",preview_running:"Consultando loja",review:"Pronto para aprovação",nothing:"Nada a remover",
    not_found:"SKU inexistente",blocked:"Bloqueado",queued:"Na fila de execução",running:"Removendo",done:"Removido e verificado",
    error:"Erro",uncertain:"Reconciliação manual",cancelled:"Cancelado"};
  const tone={done:"is-ok",review:"is-info",error:"is-alert",blocked:"is-alert",uncertain:"is-alert",not_found:"is-warn",queued:"is-busy",running:"is-busy",preview_queued:"is-busy",preview_running:"is-busy"};
  function el(tag,text,className){const node=document.createElement(tag);if(text!=null)node.textContent=text;if(className)node.className=className;return node;}
  async function request(url,options={}){const r=await fetch(url,{cache:"no-store",credentials:"same-origin",...options});const body=await r.json().catch(()=>({}));if(!r.ok)throw Error(typeof body.detail==="string"?body.detail:"Falha na solicitação");return body;}
  const img=i=>i?`#${i.id}${i.name?" "+i.name:""}`:"—";
  const doc=d=>`${d.label||"sem label"}${d.filename?" ("+d.filename+")":""}`;
  function list(title,items){const box=el("div",null,"rm-list");box.append(el("strong",`${title} (${items.length})`));const ul=el("ul");items.forEach(t=>ul.append(el("li",t)));if(!items.length)ul.append(el("li","—"));box.append(ul);return box;}
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
    if(item.result)box.append(el("p",`Resultado: ${item.result.status}; verificado: ${item.result.verified?"sim":"não"}. Restauração disponível via scripts/store_removal_restore.py.`));
    if(item.audit.length)box.append(list("Auditoria",item.audit.map(a=>`${new Date(a.at*1000).toLocaleString("pt-BR")} · ${a.event}`)));
    return box;
  }
  function visible(){const f=$("rm-filter").value;return data.items.filter(i=>!f||i.state===f);}
  function render(){
    if(!data)return;$("rm-current").hidden=false;window.history.replaceState(null,"","?lote="+data.id);
    $("rm-title").textContent=`${data.mode_label} · ${data.company.toUpperCase()} · ${new Date(data.created*1000).toLocaleString("pt-BR")}`;
    $("rm-summary").textContent=`${data.total} SKU(s) · ${Object.entries(data.counts).map(([k,v])=>`${labels[k]||k}: ${v}`).join(" · ")}`;
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
  }
  async function history(){
    const items=(await request(api)).items,box=$("rm-history");box.replaceChildren();
    items.forEach(h=>{const b=el("button",`${h.company.toUpperCase()} · ${({all:"Remover tudo",gallery:"Galeria",documents:"Documentos",main:"Foto principal"})[h.mode]} · ${new Date(h.created*1000).toLocaleString("pt-BR")}`);b.type="button";
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
  const questions={aprovar:"Aprovar o Dry Run",executar:"Executar a remoção dos aprovados (somente com política/liberação válida)",pausar:"Pausar a fila entre produtos",cancelar:"Cancelar os itens ainda na fila",reprocessar:"Refazer o Dry Run dos itens com erro, bloqueados, inexistentes ou cancelados"};
  root.querySelectorAll("[data-action]").forEach(button=>button.addEventListener("click",async()=>{
    if(!data||busy)return;const action=button.dataset.action,skus=[...selected];
    if(!confirm(`${questions[action]} — ${skus.length&&["aprovar","executar"].includes(action)?skus.length+" SKU(s) selecionado(s)":"todos os aptos"}?`))return;
    busy=true;
    try{const body=["aprovar","executar"].includes(action)?JSON.stringify({skus:skus.length?skus:null}):undefined;
      data=await request(`${api}/${data.id}/${action}`,{method:"POST",headers:{"X-CSRF-Token":csrf(),...(body?{"Content-Type":"application/json"}:{})},body});
      message("Operação registrada.");render();}
    catch(e){message(e.message);}finally{busy=false;}
  }));
  $("rm-select-all").addEventListener("change",e=>{visible().forEach(i=>e.target.checked?selected.add(i.sku):selected.delete(i.sku));render();});
  $("rm-filter").addEventListener("change",render);
  async function poll(){try{if(!busy&&!document.hidden)await refresh();}catch(e){message(e.message);}setTimeout(poll,3000);}poll();
})();
