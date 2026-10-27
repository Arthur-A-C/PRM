(() => {
  "use strict";
  const $=id=>document.getElementById(id),root=$("pub-page");if(!root)return;
  const api="/api/v1/publicacao-lote";
  let current=new URLSearchParams(location.search).get("lote"),data=null,busy=false,lots=[];
  const selected=new Set(),opened=new Set(),replace=new Set();
  const csrf=()=>document.querySelector('input[name="csrf_token"]')?.value||"";
  const message=text=>{$("pub-message").textContent=text;};
  const tone={done:"is-ok",review:"is-info",blocked:"is-alert",error:"is-alert",invalid:"is-alert",uncertain:"is-alert",
    awaiting_product:"is-warn",queued:"is-busy",running:"is-busy",preview_queued:"is-busy",preview_running:"is-busy"};
  function el(tag,text,className){const node=document.createElement(tag);if(text!=null)node.textContent=text;if(className)node.className=className;return node;}
  function pill(text,state){return el("span",text,"prm-pill "+(tone[state]||""));}
  async function request(url,options={}){
    const r=await fetch(url,{cache:"no-store",credentials:"same-origin",...options});
    const body=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(errorText(body.detail,r.status));return body;
  }
  // FastAPI sends a string or a list of {loc,msg}: show the real reason (422/403/401), never a generic text.
  function errorText(detail,status){
    if(typeof detail==="string")return detail;
    if(Array.isArray(detail)&&detail.length)return detail.map(d=>typeof d==="string"?d:[(d?.loc||[]).filter(x=>x!=="body").join("."),d?.msg].filter(Boolean).join(": ")).join("; ");
    return `HTTP ${status}: o servidor não retornou uma mensagem de erro legível.`;
  }
  function visible(){
    const stage=$("pub-filter-stage").value,issue=$("pub-filter-issue").value,text=$("pub-filter-text").value.trim().toLowerCase();
    return data.items.filter(i=>(!stage||String(i.stage)===stage)&&(!text||i.sku.toLowerCase().includes(text))&&
      (!issue||(issue==="issues"&&i.issues.length)||(issue==="awaiting"&&i.store==="awaiting_product")||(issue==="published"&&i.store==="done")));
  }
  function detail(item){
    const box=el("div",null,"pub-detail");
    box.append(el("p",`Dry Run: ${item.uploads} imagem(ns) a enviar · ${item.documents_add} documento(s) a incluir no WCDA`+(item.product_id?` · produto ${item.product_id}`:"")));
    if(item.ignored.length)box.append(el("p","Ignorados (não publicados): "+item.ignored.join(", ")));
    if(item.write_gate)box.append(el("p",item.write_gate,"prm-note"));

    if(item.result)box.append(el("p",`Resultado: ${item.result.status}; verificado: ${item.result.verified?"sim":"não"}.`));
    if(item.store==="review"&&!item.approved&&item.uploads){
      const label=el("label",null,"pub-choice"),check=el("input");check.type="checkbox";check.checked=replace.has(item.sku);
      check.addEventListener("change",()=>check.checked?replace.add(item.sku):replace.delete(item.sku));
      label.append(check,el("span","Substituir a imagem principal atual, se existir (a atual vai para a galeria)"));box.append(label);
    }
    if(item.audit.length){const ul=el("ul");item.audit.forEach(a=>ul.append(el("li",`${new Date(a.at*1000).toLocaleString("pt-BR")} · ${a.event}`)));box.append(el("strong","Log de publicação"),ul);}
    return box;
  }
  function render(){
    if(!data)return;
    $("pub-current").hidden=false;window.history.replaceState(null,"","?lote="+data.id);
    $("pub-title").textContent=`Lote ${data.company.toUpperCase()} · ${new Date(data.created*1000).toLocaleString("pt-BR")}`;
    $("pub-summary").textContent=`${data.total} produto(s) · processamento ${data.progress}% · publicados ${data.published}`;
    $("pub-progress").value=data.progress;$("pub-export").href=`${api}/${data.id}/exportar`;
    document.querySelectorAll("#pub-steps li").forEach(li=>{
      const count=data.stages[li.dataset.stage]||0;li.querySelector("[data-stage-count]").textContent=count;li.classList.toggle("has-items",count>0);
    });
    const body=$("pub-items");body.replaceChildren();
    const rows=visible();
    if(!rows.length){const tr=el("tr"),td=el("td","Nenhum produto neste filtro.");td.colSpan=10;tr.append(td);body.append(tr);}
    rows.forEach(item=>{
      const tr=el("tr"),box=el("input");box.type="checkbox";box.checked=selected.has(item.sku);box.setAttribute("aria-label","Selecionar "+item.sku);
      box.addEventListener("change",()=>box.checked?selected.add(item.sku):selected.delete(item.sku));
      const pick=el("td");pick.append(box);tr.append(pick);
      const sku=el("td"),toggle=el("button",item.sku,"pub-sku");toggle.type="button";toggle.setAttribute("aria-expanded",String(opened.has(item.sku)));
      toggle.addEventListener("click",()=>{opened.has(item.sku)?opened.delete(item.sku):opened.add(item.sku);render();});sku.append(toggle);tr.append(sku);
      [item.company.toUpperCase(),item.folder||"—",String(item.images),String(item.documents)].forEach(t=>tr.append(el("td",t)));
      const processing=el("td");processing.append(pill(item.processing_label,item.processing));tr.append(processing);
      const sheet=el("td");
      if(item.pdf){const a=el("a",item.datasheet);a.href=`/api/v1/digitalizacao/lotes/${data.datasheet_batch}/produtos/${item.item}/pdf`;a.target="_blank";a.rel="noopener";sheet.append(a);}
      else sheet.textContent=item.datasheet;tr.append(sheet);
      const store=el("td");store.append(pill(item.store_label+(item.approved&&item.store==="review"?" · aprovado":""),item.store||""));tr.append(store);
      tr.append(el("td",item.issues.join(" · ")||"—"));
      body.append(tr);
      if(opened.has(item.sku)){const row=el("tr",null,"pub-detail-row"),td=el("td");td.colSpan=10;td.append(detail(item));row.append(td);body.append(row);}
    });
  }
  function renderHistory(){
    const company=$("pub-history-company").value,box=$("pub-history");box.replaceChildren();
    lots.filter(h=>!company||h.company===company).forEach(h=>{
      const b=el("button",`${h.company.toUpperCase()} · ${new Date(h.created*1000).toLocaleString("pt-BR")}`);b.type="button";
      b.addEventListener("click",()=>{current=h.id;selected.clear();opened.clear();replace.clear();refresh();});box.append(b);
    });
    if(!box.children.length)box.append(el("p","Nenhum lote.","prm-status"));
  }
  async function refresh(){
    if(current){data=await request(`${api}/${current}`);render();}
    lots=(await request(api)).items;renderHistory();
  }
  const labels={processar:"Iniciar o processamento (usa a IA para gerar os datasheets)",pausar:"Pausar itens ainda na fila",reprocessar:"Reprocessar itens com erro (usa a IA)",
    preparar:"Gerar o Dry Run de publicação (somente leitura na loja)",aprovar:"Aprovar o Dry Run (não publica)",
    publicar:"Confirmar o envio dos arquivos aprovados para a loja",retomar:"Refazer o Dry Run dos itens com erro ou aguardando cadastro por CSV"};
  root.querySelectorAll("[data-action]").forEach(button=>button.addEventListener("click",async()=>{
    if(!data||busy)return;
    const action=button.dataset.action,skus=[...selected];
    const items=data.items.filter(i=>selected.has(i.sku)).map(i=>i.item);
    const scope=skus.length?`${skus.length} produto(s) selecionado(s)`:"todos os produtos aptos";
    if(!confirm(`${labels[action]} — ${scope}?`))return;
    const body={pausar:null,retomar:null,processar:{items:items.length?items:null},reprocessar:{items:items.length?items:null},
      preparar:{skus:skus.length?skus:null},aprovar:{skus:skus.length?skus:null,replace_main:[...replace]},publicar:{skus:skus.length?skus:null,confirmado:true}}[action];
    busy=true;
    try{
      data=await request(`${api}/${data.id}/${action}`,{method:"POST",headers:{"X-CSRF-Token":csrf(),...(body?{"Content-Type":"application/json"}:{})},body:body?JSON.stringify(body):undefined});
      const failed=Array.isArray(data.result)?data.result.filter(r=>!r.ok):[];
      message(failed.length?failed.map(r=>`${r.skus.join(", ")}: ${r.error}`).join(" · "):"Operação registrada.");render();
    }catch(e){message(e.message);}finally{busy=false;}
  }));
  $("pub-select-all").addEventListener("change",event=>{visible().forEach(i=>event.target.checked?selected.add(i.sku):selected.delete(i.sku));render();});
  ["pub-filter-stage","pub-filter-issue","pub-filter-text"].forEach(id=>$(id).addEventListener("input",render));
  $("pub-history-company").addEventListener("change",renderHistory);
  $("pub-upload").addEventListener("submit",async event=>{
    event.preventDefault();if(busy)return;busy=true;
    try{const form=new FormData(event.target),picker=await window.PRMLocalFiles?.applyTo(event.target,form);message("Importando e validando…");
      data=await request(api,{method:"POST",headers:{"X-CSRF-Token":csrf()},body:form});picker?.done();current=data.id;selected.clear();render();
      message("Produtos identificados. Confira a prévia e clique em Processar.");refresh();}
    catch(e){message(e.message);}finally{busy=false;}
  });
  async function poll(){try{if(!busy&&!document.hidden)await refresh();}catch(e){message(e.message);}setTimeout(poll,4000);}poll();
})();
