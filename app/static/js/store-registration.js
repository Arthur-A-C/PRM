(() => {
  "use strict";
  const $=id=>document.getElementById(id),root=$("api-registration");if(!root)return;
  const api="/api/v1/cadastro-api";let selected=new URLSearchParams(location.search).get("lote"),busy=false;
  // Per-item approval choices survive the 4s polling re-render.
  const choices=new Map();
  const message=text=>$("api-registration-message").textContent=text;
  function mode() {
    const folders=$("api-registration-mode").value==="folder";
    $("api-registration-sheet").required=!folders;
    $("api-registration-root-field").hidden=!folders;
    $("api-registration-root").disabled=!folders;
  }
  $("api-registration-mode").addEventListener("change",mode);mode();
  const headers=(json=false)=>({"X-CSRF-Token":document.querySelector('input[name="csrf_token"]')?.value||"",...(json?{"Content-Type":"application/json"}:{})});
  const labels={preview_queued:"Prévia na fila",preview_running:"Consultando",review:"Pronto para aprovação",
    blocked:"Bloqueado",queued:"Envio na fila",running:"Enviando arquivos",done:"Verificado",error:"Erro",uncertain:"Reconciliação manual"};
  const actions={upload:"Enviar",add:"Incluir no WCDA",already_linked:"Ignorar: já vinculado (mesmo hash)",conflict:"Conflito: reconciliar",duplicate_in_package:"Ignorar: duplicado no pacote"};
  async function request(url,options={}) {
    const r=await fetch(url,{cache:"no-store",credentials:"same-origin",...options});
    const data=await r.json();if(!r.ok)throw Error(typeof data.detail==="string"?data.detail:"Falha na solicitação");return data;
  }
  function el(tag,text,className){const node=document.createElement(tag);if(text!=null)node.textContent=text;if(className)node.className=className;return node;}
  function table(head,rows){
    const t=el("table"),h=el("thead"),b=el("tbody"),hr=el("tr");
    head.forEach(c=>hr.append(el("th",c)));h.append(hr);
    rows.forEach(r=>{const tr=el("tr");r.forEach(c=>tr.append(el("td",c)));b.append(tr);});t.append(h,b);
    const wrap=el("div",null,"table-scroll");wrap.append(t);return wrap;
  }
  function list(items){const ul=el("ul");items.forEach(i=>ul.append(el("li",i)));return ul;}
  const size=b=>b>=1048576?(b/1048576).toFixed(2)+" MB":(b/1024).toFixed(1)+" KB";
  function check(item,key,text){
    const label=el("label",null,"api-choice"),box=el("input");box.type="checkbox";
    box.checked=Boolean(choices.get(item.sku)?.[key]);
    box.addEventListener("change",()=>choices.set(item.sku,{...choices.get(item.sku),[key]:box.checked}));
    label.append(box,el("span",text));return label;
  }
  function dryRun(item){
    const d=item.dry_run,details=el("details",null,"api-dry-run"),img=d.images,docs=d.documents;
    const sending=img.actions.filter(a=>a.action==="upload").length,adding=docs.actions.filter(a=>a.action==="add").length;
    details.append(el("summary",`Dry Run · Produto ${item.product_id} · SKU ${item.sku} · ${sending} imagem(ns) a enviar · ${adding} documento(s) a incluir`+
      (item.approval?" · Aprovado"+(item.approval.replace_main?" (substituir principal)":""):"")));
    details.append(el("p","Somente imagens e _wcda_arquivos. Nome, descrições, categorias, atributos, SKU, preço, estoque e status não são enviados.","prm-note"));
    if(item.blockers.length)details.append(el("h4","Bloqueios"),list(item.blockers));
    details.append(el("p",d.write_gate));
    if(item.homologation_grant)details.append(el("p",`Liberação de homologação de uso único ativa (${item.homologation_grant.purpose}) até ${new Date(item.homologation_grant.expires*1000).toLocaleString("pt-BR")}.`,"prm-note"));
    if(item.state==="review"&&!item.approval){
      const box=el("div",null,"api-choices");box.append(check(item,"approve","Selecionar para aprovação"));
      if(img.main_image.replacement_available)box.append(check(item,"replace","Substituir a imagem principal atual (a atual vai para a galeria)"));
      details.append(box);
    }
    details.append(el("h4",`Imagens · ${img.current.length} vinculada(s), preservada(s)`),table(["Arquivo","Papel","Tamanho","Ação","Nome de upload"],
      img.actions.map(a=>[a.name,a.role==="main_image"?"Principal":"Galeria",size(a.bytes),actions[a.action]||a.action,a.upload_name])));
    details.append(table(["Ordem final","Origem","Arquivo / ID"],img.final_order.map((m,n)=>[n===0?"Principal":"Galeria "+n,
      m.source==="existing"?"Loja (preservada)":"Pacote PRM",m.source==="existing"?`${m.name||"—"} (ID ${m.id})`:m.name+" (ID após upload)"])));
    if(img.main_image.replacement_available)details.append(el("p","O produto já tem imagem principal: ela é mantida por padrão. A nova principal só a substitui com aprovação explícita."));
    details.append(el("h4",`Documentos WCDA · ${docs.existing.length} existente(s), ordem preservada · modo ${docs.mode==="first_inclusion"?"primeira inclusão (campo vazio)":docs.mode==="append"?"acréscimo":"bloqueado"}`),
      table(["Label","Arquivo","Tamanho","Ação","URL"],[
        ...docs.existing.map(x=>[x.label||"—",x.filename||"—",x.filesize||"—","Preservar","existente"]),
        ...docs.actions.map(a=>[a.label,a.upload_name,a.wcda_entry?a.wcda_entry.filesize:size(a.bytes),actions[a.action]||a.action,a.action==="add"?"obtida após upload":"—"])]));
    if(d.ignored?.length)details.append(el("h4","Ignorados"),list(d.ignored.map(i=>`${i.name}: ${i.reason}`)));
    if(d.dependencies.length)details.append(el("h4","Dependências"),list(d.dependencies));
    details.append(el("p",`Recuperação: ${d.rollback.strategy} Nenhuma mídia é excluída da biblioteca.`));
    if(item.result)details.append(el("p",`Resultado: ${item.result.status}, verificado: ${item.result.verified?"sim":"não"}.`));
    if(item.audit?.length)details.append(el("h4","Auditoria"),list(item.audit.map(a=>`${new Date(a.at*1000).toLocaleString("pt-BR")} · ${a.actor} · ${a.event}`)));
    const raw=el("details");raw.append(el("summary","JSON completo"),el("pre",JSON.stringify(d,null,2)));details.append(raw);
    return details;
  }
  function render(data) {
    selected=data.id;history.replaceState(null,"","?lote="+selected);
    $("api-registration-actions").hidden=false;$("api-registration-report").href=`${api}/${selected}/relatorio`;
    $("api-registration-dry-run").href=`${api}/${selected}/dry-run`;
    const open=new Set([...root.querySelectorAll(".api-dry-run[open]")].map(d=>d.dataset.sku));
    $("api-registration-items").replaceChildren();
    const count=state=>data.items.filter(i=>i.state===state).length;
    const terminal=data.items.filter(i=>!["preview_queued","preview_running","queued","running"].includes(i.state)).length;
    $("api-registration-progress").value=data.items.length?100*terminal/data.items.length:0;
    $("api-registration-summary").textContent=`Total: ${data.items.length} · Prontos: ${count("review")} · Verificados: ${count("done")} · Bloqueados: ${count("blocked")} · Erros: ${count("error")} · Incertos: ${count("uncertain")}`;
    $("api-registration-confirm").disabled=!data.can_confirm;
    $("api-registration-approve").disabled=!data.items.some(i=>i.state==="review"&&!i.approval);
    data.items.forEach(item=>{
      const tr=document.createElement("tr");
      [item.sku,labels[item.state]||item.state,
       `${item.existing_images??"—"} imagens / ${item.existing_documents??"—"} documentos`,
       item.files.map(f=>`${f.name} (${size(f.bytes)}) ${f.label}`).join(" · "),
       [item.error,...item.warnings].filter(Boolean).join(" · ")].forEach(text=>{
        const td=document.createElement("td");td.textContent=text;tr.append(td);
      });
      $("api-registration-items").append(tr);
      if(item.dry_run){
        const row=document.createElement("tr"),cell=document.createElement("td");
        const details=dryRun(item);details.dataset.sku=item.sku;details.open=open.has(item.sku);
        cell.colSpan=5;cell.append(details);row.append(cell);$("api-registration-items").append(row);
      }
    });
  }
  async function refresh() {
    if(selected)render(await request(`${api}/${selected}`));
    const data=await request(api);$("api-registration-history").replaceChildren();
    data.items.forEach(item=>{const b=document.createElement("button");b.type="button";
      b.textContent=`${item.company} · ${new Date(item.created*1000).toLocaleString("pt-BR")} · ${item.id}`;
      b.addEventListener("click",()=>{choices.clear();request(`${api}/${item.id}`).then(render).catch(e=>message(e.message));});
      $("api-registration-history").append(b);});
  }
  $("api-registration-upload").addEventListener("submit",async event=>{
    event.preventDefault();if(busy)return;busy=true;
    try{
      const form=new FormData(event.target);
      if(!$("api-registration-sheet").files.length)form.delete("planilha");
      choices.clear();
      const picker=await window.PRMLocalFiles?.applyTo(event.target,form);
      message("Importando arquivos para prévia…");render(await request(api,{method:"POST",headers:headers(),body:form}));picker?.done();message("SKUs identificados; consulta na fila. Nenhuma gravação na loja autorizada.");}
    catch(e){message(e.message);}finally{busy=false;}
  });
  async function post(action,body,question){
    if(!selected||busy||!confirm(question))return;
    busy=true;try{render(await request(`${api}/${selected}/${action}`,{method:"POST",headers:headers(Boolean(body)),body:body?JSON.stringify(body):undefined}));}
    catch(e){message(e.message);}finally{busy=false;}
  }
  $("api-registration-approve").addEventListener("click",()=>{
    const picked=[...choices].filter(([,c])=>c.approve).map(([sku])=>sku);
    const replace=[...choices].filter(([,c])=>c.replace).map(([sku])=>sku);
    // No selection approves the whole batch; replacing a main image is always an explicit per-SKU opt-in.
    post("aprovar",{skus:picked.length?picked:null,replace_main:replace},
      picked.length?`Aprovar o Dry Run de ${picked.length} item(ns)? Nenhum arquivo é enviado nesta etapa.`:"Aprovar o Dry Run de todos os itens prontos? Nenhum arquivo é enviado nesta etapa.");
  });
  $("api-registration-confirm").addEventListener("click",()=>post("confirmar",null,"Enfileirar o envio dos itens aprovados? Somente staging autorizado aceita gravação."));
  $("api-registration-retry").addEventListener("click",()=>post("reprocessar",null,"Refazer a prévia dos itens com erro?"));
  async function poll(){try{if(!busy&&!document.hidden)await refresh();}catch(e){message(e.message);}setTimeout(poll,4000);}poll();
})();
