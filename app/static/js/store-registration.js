function registrationErrorMessage(detail, status) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(item => typeof item === "string" ? item :
    [Array.isArray(item?.loc) ? item.loc.filter(x => x !== "body").join(".") : "", item?.msg || registrationErrorMessage(item?.detail, status)].filter(Boolean).join(": ")).join("; ");
  return `HTTP ${status}: o servidor não retornou uma mensagem de erro legível.`;
}
const REGISTRATION_SCOPE = [["gallery", "Galeria"], ["documents", "Documentos"], ["main", "Principal"]];
// States the backend accepts for a new Dry Run (also for a scope change or a main choice).
const REGISTRATION_REPREVIEW = ["error", "awaiting_product", "review", "blocked", "awaiting_main", "nothing"];
function registrationScopeValue(scope) {
  return REGISTRATION_SCOPE.map(([key]) => key).filter(key => scope?.[key]).join(",");
}
function registrationScopeText(scope) {
  if (!scope) return "Escopo anterior (lote sem escolha explícita)";
  return REGISTRATION_SCOPE.map(([key, label]) => `${scope[key] ? "✓" : "✗"} ${label}`).join(" · ");
}
// Official naming <SKU>_1 = main, <SKU>_2.. = gallery (numeric order), as classified by the backend.
function registrationImageRule(rule, sku) {
  if (!rule) return [];
  const lines = [rule.main ? `Principal detectada automaticamente: ${rule.main.name}` : `Foto principal não encontrada no padrão ${sku}_1.ext.`];
  lines.push(rule.gallery.length ? `Galeria: ${rule.gallery.map((g, n) => `${n + 1}. ${g.name}`).join(" · ")}` : "Galeria: nenhuma imagem no padrão.");
  rule.duplicates.forEach(n => lines.push(`Mais de uma imagem encontrada para a posição _${n}.`));
  if (rule.outside.length) lines.push(`Imagem fora do padrão de nomenclatura: ${rule.outside.join(", ")}`);
  return lines;
}
// Status do item em selo padronizado: [rótulo, tom]. Tom é só reforço; o texto sempre diz o estado.
const REGISTRATION_STATUS = {preview_queued: ["Prévia na fila", "is-info is-busy"], preview_running: ["Consultando", "is-info is-busy"],
  review: ["Pronto para aprovação", "is-info"], awaiting_main: ["Escolher principal", "is-warn"], nothing: ["Sem alteração", ""],
  blocked: ["Bloqueado", "is-alert"], queued: ["Envio na fila", "is-info is-busy"], running: ["Enviando arquivos", "is-info is-busy"],
  done: ["Verificado", "is-ok"], error: ["Erro", "is-alert"], uncertain: ["Incerto: reconciliar", "is-warn"],
  rollback_queued: ["Restauração na fila", "is-info is-busy"], rollback_running: ["Restaurando", "is-info is-busy"],
  rolled_back: ["Restaurado", ""], rollback_error: ["Erro na restauração", "is-alert"], awaiting_product: ["Aguardando produto", "is-warn"]};
function registrationStatus(item) {
  if (item.state === "review" && item.approval) return ["Aprovado", "is-ok"];
  return REGISTRATION_STATUS[item.state] || [item.state, ""];
}
function registrationSelected(items, choices, action) {
  return items.filter(i => choices.get(i.sku)?.select && (action === "aprovar" ? registrationEligible(i) && !i.approval : action === "confirmar" ? registrationEligible(i) && i.approval :
    action === "restaurar" ? i.can_rollback : action === "escopo" ? REGISTRATION_REPREVIEW.includes(i.state) : true)).map(i => i.sku);
}
function registrationEligible(item) {
  return item.state === "review" && !item.needs_refresh && !item.disabled && !item.requires_manual_review &&
    !item.blockers?.length && !item.dry_run?.blockers?.length;
}
function registrationSelectAll(items, choices, checked) {
  items.forEach(i => choices.set(i.sku, {...choices.get(i.sku), select: checked && registrationEligible(i), approve: false}));
}
function registrationSelectionCount(items, choices) {
  const eligible = items.filter(registrationEligible);
  return {eligible: eligible.length, selected: eligible.filter(i => choices.get(i.sku)?.select).length};
}
(() => {
  "use strict";
  const $=id=>document.getElementById(id),root=$("api-registration");if(!root)return;
  const api="/api/v1/cadastro-api";let selected=new URLSearchParams(location.search).get("lote"),busy=false,current=null;
  // Per-item approval choices survive the 4s polling re-render.
  const choices=new Map(),autoOpened=new Set();
  function updateSelection() {
    const count=registrationSelectionCount(current?.items||[],choices),all=$("api-registration-select-all");
    all.checked=count.eligible>0&&count.selected===count.eligible;
    all.indeterminate=count.selected>0&&count.selected<count.eligible;
    all.disabled=!count.eligible;
    $("api-registration-selection-count").textContent=`${count.selected} selecionados de ${count.eligible} elegíveis`;
    root.querySelectorAll('input[data-selection-sku]').forEach(box=>{box.checked=Boolean(choices.get(box.dataset.selectionSku)?.select);});
  }
  $("api-registration-select-all").addEventListener("change",event=>{
    registrationSelectAll(current?.items||[],choices,event.target.checked);updateSelection();
  });
  const message=text=>$("api-registration-message").textContent=text;
  function mode() {
    const folders=$("api-registration-mode").value==="folder";
    $("api-registration-sheet").required=!folders;
    $("api-registration-root-field").hidden=!folders;
    $("api-registration-root").disabled=!folders;
  }
  $("api-registration-mode").addEventListener("change",mode);mode();
  // What to register: sent with the import and re-validated by the API and the worker.
  const scopeBoxes=[...root.querySelectorAll("input[data-scope]")];
  const formScope=()=>Object.fromEntries(scopeBoxes.map(box=>[box.dataset.scope,box.checked]));
  function syncScope(){
    const scope=formScope();
    $("api-registration-scope-all").checked=scopeBoxes.every(box=>box.checked);
    $("api-registration-scope-main-note").hidden=!scope.main;
    $("api-registration-scope-value").value=registrationScopeValue(scope);
  }
  $("api-registration-scope-all").addEventListener("change",event=>{scopeBoxes.forEach(box=>{box.checked=event.target.checked;});syncScope();});
  scopeBoxes.forEach(box=>box.addEventListener("change",syncScope));syncScope();
  const headers=(json=false)=>({"X-CSRF-Token":document.querySelector('input[name="csrf_token"]')?.value||"",...(json?{"Content-Type":"application/json"}:{})});
  const actions={upload:"Enviar",add:"Incluir no WCDA",already_linked:"Ignorar: já vinculado (mesmo hash)",conflict:"Conflito: reconciliar",duplicate_in_package:"Ignorar: duplicado no pacote",
    promote:"Promover a principal (já vinculada, sem novo upload)",already_main:"Já é a principal"};
  async function request(url,options={}) {
    const r=await fetch(url,{cache:"no-store",credentials:"same-origin",...options});
    const data=await r.json().catch(()=>({}));if(!r.ok)throw Error(registrationErrorMessage(data.detail,r.status));return data;
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
    if(key==="approve")key="select";
    const label=el("label",null,"api-choice"),box=el("input");box.type="checkbox";
    box.checked=Boolean(choices.get(item.sku)?.[key]);
    if(key==="select")box.dataset.selectionSku=item.sku;
    box.addEventListener("change",()=>{choices.set(item.sku,{...choices.get(item.sku),[key]:box.checked});updateSelection();});
    label.append(box,el("span",text));return label;
  }
  function mainPicker(item){
    // Explicit, per SKU: the folder suggestion is only labelled, never preselected.
    const d=item.dry_run,box=el("div",null,"api-choices"),select=el("select"),button=el("button","Usar como principal (refaz o Dry Run)","button-secondary");
    select.setAttribute("aria-label","Imagem principal de "+item.sku);
    select.append(Object.assign(el("option","Escolha a imagem principal…"),{value:""}));
    d.main_options.forEach(o=>select.append(Object.assign(el("option",`${o.name} (${size(o.bytes)})${o.suggested?" · sugerida pela pasta":""}`),{value:o.sha256})));
    select.value=choices.get(item.sku)?.main??item.main_choice?.sha256??"";
    select.addEventListener("change",()=>choices.set(item.sku,{...choices.get(item.sku),main:select.value}));
    button.type="button";
    button.addEventListener("click",()=>{
      if(!select.value){message("Escolha a imagem principal de "+item.sku+".");return;}
      const name=d.main_options.find(o=>o.sha256===select.value)?.name;
      post("principal",{sku:item.sku,sha256:select.value},`Usar ${name} como principal de ${item.sku}? O Dry Run será refeito e precisará de nova aprovação.`);
    });
    const label=el("label","Foto principal: ");label.append(select);box.append(label,button);return box;
  }
  function scopeSummary(item){
    const d=item.dry_run,img=d.images,docs=d.documents,main=img.main_image,scope=d.registration_scope,wrap=el("div",null,"api-scope-summary");
    const current=main.current?`#${main.current.id} ${main.current.name||""}`.trim():"sem principal";
    const lines=[`Escopo: ${registrationScopeText(scope)}`,`Principal atual: ${current}`];
    if(scope.main)lines.push(`Nova principal: ${main.proposed?main.proposed.name:"não escolhida"}`);
    lines.push(`Galeria: ${scope.gallery?`${Math.max(img.current.length-1,0)} atuais +${img.gallery_added} nova(s)`:"fora do escopo"}`);
    lines.push(`Documentos: ${docs.in_scope?`${docs.existing.length} atuais +${docs.actions.filter(a=>a.action==="add").length} novo(s)`:"fora do escopo"}`);
    wrap.append(list(lines),el("p",main.message,main.action==="replace"?"prm-status":"prm-note"));
    if(d.image_rule)wrap.append(el("h4",`Classificação pelo padrão ${d.image_rule.pattern}`),list(registrationImageRule(d.image_rule,item.sku)));
    if(d.nothing_message)wrap.append(el("p",d.nothing_message,"prm-note"));
    if(scope.main&&d.main_options?.length&&REGISTRATION_REPREVIEW.includes(item.state))wrap.append(mainPicker(item));
    return wrap;
  }
  function dryRun(item){
    const d=item.dry_run,details=el("details",null,"api-dry-run"),img=d.images,docs=d.documents;
    const sending=img.actions.filter(a=>a.action==="upload").length,adding=docs.actions.filter(a=>a.action==="add").length;
    details.append(el("summary",`Dry Run · Produto ${item.product_id} · SKU ${item.sku} · ${registrationScopeText(d.registration_scope)} · ${sending} imagem(ns) a enviar · ${adding} documento(s) a incluir`+
      (item.approval?" · Aprovado"+(item.approval.replace_main?" (substituir principal)":""):"")));
    if(d.registration_scope)details.append(scopeSummary(item));
    details.append(el("p","Somente imagens e _wcda_arquivos. Nome, descrições, categorias, atributos, SKU, preço, estoque e status não são enviados.","prm-note"));
    if(item.blockers.length)details.append(el("h4","Bloqueios"),list(item.blockers));
    details.append(el("p",item.write_gate||d.write_gate));
    if(item.needs_refresh)details.append(el("p","Prévia anterior à atualização: selecione este SKU e clique em Refazer prévia antes de aprovar.","prm-note"));
    if(item.state==="review"&&!item.approval&&!item.needs_refresh){
      const box=el("div",null,"api-choices");box.append(check(item,"approve","Selecionar para aprovação"));
      if(!d.registration_scope&&img.main_image.replacement_available)box.append(check(item,"replace","Substituir a imagem principal atual (a atual vai para a galeria)"));
      details.append(box);
    }
    details.append(el("h4",`Imagens · ${img.current.length} vinculada(s), preservada(s)`),table(["Arquivo","Papel","Tamanho","Ação","Nome de upload"],
      img.actions.map(a=>[a.name,a.role==="main_image"?"Principal":"Galeria",size(a.bytes),actions[a.action]||a.action,a.upload_name])));
    details.append(table(["Ordem final","Origem","Arquivo / ID"],img.final_order.map((m,n)=>[n===0?"Principal":"Galeria "+n,
      m.source==="existing"?"Loja (preservada)":"Pacote PRM",m.source==="existing"?`${m.name||"—"} (ID ${m.id})`:m.name+" (ID após upload)"])));
    if(!d.registration_scope&&img.main_image.replacement_available)details.append(el("p","O produto já tem imagem principal: ela é mantida por padrão. A nova principal só a substitui com aprovação explícita."));
    details.append(el("h4",`Documentos WCDA · ${docs.existing.length} existente(s), ordem preservada · modo ${docs.mode==="absent"?"ausente — será criado automaticamente":docs.mode==="first_inclusion"?"primeira inclusão (campo vazio)":docs.mode==="append"?"acréscimo":"bloqueado"}`),
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
    // A state transition invalidates an old ready selection; never select newly ready items automatically.
    if(current?.id===data.id)current.items.filter(registrationEligible).forEach(old=>{
      const next=data.items.find(i=>i.sku===old.sku);
      if(!next||!registrationEligible(next))choices.delete(old.sku);
    });
    current=data;selected=data.id;history.replaceState(null,"","?lote="+selected);
    $("api-registration-actions").hidden=false;$("api-registration-report").href=`${api}/${selected}/relatorio`;
    $("api-registration-dry-run").href=`${api}/${selected}/dry-run`;
    const open=new Set([...root.querySelectorAll(".api-dry-run[open]")].map(d=>d.dataset.sku));
    $("api-registration-items").replaceChildren();
    const count=state=>data.items.filter(i=>i.state===state).length;
    const terminal=data.items.filter(i=>!["preview_queued","preview_running","queued","running","rollback_queued","rollback_running"].includes(i.state)).length;
    $("api-registration-progress").value=data.items.length?100*terminal/data.items.length:0;
    $("api-registration-summary").textContent=`Total: ${data.items.length} · Prontos: ${count("review")} · Verificados: ${count("done")} · Escolher principal: ${count("awaiting_main")} · Sem alteração: ${count("nothing")} · Bloqueados: ${count("blocked")} · Erros: ${count("error")} · Incertos: ${count("uncertain")}`;
    $("api-registration-confirm").disabled=!data.can_confirm;
    $("api-registration-approve").disabled=!data.items.some(i=>i.state==="review"&&!i.approval&&!i.needs_refresh);
    $("api-registration-restore").disabled=!data.items.some(i=>i.can_rollback);
    data.items.forEach(item=>{
      const tr=document.createElement("tr");
      const pick=el("td");pick.append(check(item,"select","Selecionar "+item.sku));tr.append(pick);
      const [statusLabel,statusTone]=registrationStatus(item);
      [item.sku,null,
       `${item.existing_images??"—"} imagens / ${item.existing_documents??"—"} documentos`,
       item.files.map(f=>`${f.name} (${size(f.bytes)}) ${f.label}`).join(" · "),
       [item.error,...item.warnings].filter(Boolean).join(" · ")].forEach((text,n)=>{
        const td=document.createElement("td");
        if(n===1)td.append(el("span",statusLabel,"prm-badge "+statusTone));else td.textContent=text;
        tr.append(td);
      });
      $("api-registration-items").append(tr);
      if(item.dry_run){
        const row=document.createElement("tr"),cell=document.createElement("td");
        const details=dryRun(item);details.dataset.sku=item.sku;
        // Opened once when the SKU waits for its main choice; afterwards the user's collapse is kept.
        if(item.state==="awaiting_main"&&!autoOpened.has(item.sku)){autoOpened.add(item.sku);open.add(item.sku);}
        details.open=open.has(item.sku);
        cell.colSpan=6;cell.append(details);row.append(cell);$("api-registration-items").append(row);
      }
    });
    updateSelection();
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
      syncScope();
      if(!$("api-registration-scope-value").value){message("Escolha o que deseja cadastrar: Fotos da galeria, Documentos e/ou Foto principal.");return;}
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
    const picked=registrationSelected(current?.items||[],choices,"aprovar");
    const replace=picked.filter(sku=>choices.get(sku)?.replace);
    if(!picked.length){message("Selecione um SKU com prévia atualizada para aprovar.");return;}
    post("aprovar",{skus:picked,replace_main:replace},
      `Aprovar o Dry Run de ${picked.length} item(ns)? Nenhum arquivo é enviado nesta etapa.`);
  });
  function sendSelected(action) {
    if(!current)return;
    const skus=registrationSelected(current.items,choices,action);
    if(!skus.length){message("Selecione o SKU desejado na primeira coluna. Nenhum lote será enviado automaticamente.");return;}
    const question=action==="confirmar" ? `Enviar arquivos dos ${skus.length} produto(s) selecionado(s) para ${current.company.toUpperCase()}? SKUs: ${skus.join(", ")}` :
      action==="restaurar" ? `Restaurar os vínculos anteriores de ${skus.length} produto(s)? SKUs: ${skus.join(", ")}` :
      `Refazer o Dry Run de ${skus.length} produto(s) selecionado(s), sem enviar arquivos?`;
    post(action,{skus,confirmado:true},question);
  }
  $("api-registration-scope-apply").addEventListener("click",()=>{
    if(!current)return;
    const skus=registrationSelected(current.items,choices,"escopo"),scope=formScope();
    if(!registrationScopeValue(scope)){message("Marque o que deseja cadastrar em “O que deseja cadastrar?”.");return;}
    if(!skus.length){message("Selecione os SKUs que devem mudar de escopo (itens enviados ou em envio não mudam).");return;}
    post("escopo",{escopo:scope,skus},`Aplicar o escopo ${registrationScopeText(scope)} a ${skus.length} SKU(s)? O Dry Run será refeito e aprovações anteriores serão descartadas.`);
  });
  $("api-registration-restore").addEventListener("click",()=>sendSelected("restaurar"));
  $("api-registration-confirm").addEventListener("click",()=>sendSelected("confirmar"));
  $("api-registration-retry").addEventListener("click",()=>sendSelected("reprocessar"));
  async function poll(){try{if(!busy&&!document.hidden)await refresh();}catch(e){message(e.message);}setTimeout(poll,4000);}poll();
})();
