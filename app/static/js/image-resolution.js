(() => {
  "use strict";
  const $=id=>document.getElementById(id),root=$("res-page");if(!root)return;
  const api="/api/v1/imagens";let browsing=null,parent=null,taskId=null,timer=null,previewed=null;
  const csrf=()=>document.querySelector('input[name="csrf_token"]')?.value||"";
  const message=text=>{$("res-message").textContent=text;};
  const bytes=n=>n>=1073741824?(n/1073741824).toFixed(2)+" GB":n>=1048576?(n/1048576).toFixed(1)+" MB":Math.round(n/1024)+" KB";
  function el(tag,text,className){const node=document.createElement(tag);if(text!=null)node.textContent=text;if(className)node.className=className;return node;}
  async function request(url,body){
    const r=await fetch(url,body?{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf()},body:JSON.stringify(body)}:{credentials:"same-origin",cache:"no-store"});
    const data=await r.json().catch(()=>({}));if(!r.ok)throw Error(typeof data.detail==="string"?data.detail:"Falha na solicitação");return data;
  }
  const options=(extra={})=>({caminho:$("res-path").value.trim(),subpastas:$("res-recursive").checked,tamanho:Number($("res-size").value),mover_para_backup:true,...extra});
  // Any option change invalidates the preview: conversion always starts from a fresh, confirmed preview.
  ["res-path","res-recursive","res-size"].forEach(id=>$(id).addEventListener("input",()=>{previewed=null;$("res-start").disabled=true;$("res-confirm").checked=false;}));
  $("res-confirm").addEventListener("change",()=>{$("res-start").disabled=!(previewed&&$("res-confirm").checked&&previewed.pending&&previewed.space_ok);});

  async function browse(path){
    const data=await request(`${api}/pastas`+(path?`?caminho=${encodeURIComponent(path)}`:""));
    browsing=data.path;parent=data.parent;
    $("res-dialog-path").textContent=data.path||"Raízes permitidas";$("res-up").disabled=!parent;$("res-choose").disabled=!data.path;
    const list=$("res-folders");list.replaceChildren();
    data.folders.forEach(f=>{const li=el("li"),b=el("button",f.name);b.type="button";b.addEventListener("click",()=>browse(f.path).catch(e=>message(e.message)));li.append(b);list.append(li);});
    if(!data.folders.length)list.append(el("li","Nenhuma subpasta.","prm-status"));
  }
  $("res-browse").addEventListener("click",async()=>{try{await browse($("res-path").value.trim()||null);}catch{await browse(null).catch(e=>message(e.message));}$("res-dialog").showModal();});
  $("res-up").addEventListener("click",()=>browse(parent).catch(e=>message(e.message)));
  $("res-roots").addEventListener("click",()=>browse(null).catch(e=>message(e.message)));
  $("res-cancel").addEventListener("click",()=>$("res-dialog").close());
  $("res-choose").addEventListener("click",()=>{$("res-path").value=browsing;$("res-path").dispatchEvent(new Event("input"));$("res-dialog").close();});

  $("res-form").addEventListener("submit",async event=>{
    event.preventDefault();message("Analisando a pasta…");
    try{
      const data=await request(`${api}/previa`,options());previewed=data;
      $("res-preview").hidden=false;$("res-preview-root").textContent=`${data.root} · ${data.size} × ${data.size} px · backup em ${data.backup}`;
      for(const key of ["folders","images","pending","already_converted"])root.querySelector(`[data-stat="${key}"]`).textContent=data[key];
      const space=root.querySelector('[data-stat="space"]');space.textContent=`${bytes(data.required_bytes)} / ${bytes(data.free_bytes)}`;space.classList.toggle("is-alert",!data.space_ok);
      $("res-extensions").textContent=Object.entries(data.by_extension).map(([k,v])=>`${v} ${k}`).join(" · ")+(data.restorable?` · ${data.restorable} restauráveis no backup`:"");
      $("res-sample").replaceChildren(...data.sample.map(s=>el("li",s)));
      $("res-confirm").checked=false;$("res-start").disabled=true;
      message(!data.space_ok?"Espaço livre insuficiente para backup e processamento.":data.pending?"Confira a prévia e confirme para converter.":"Nenhuma imagem pendente: tudo já foi convertido pelo PRM.");
    }catch(e){message(e.message);$("res-preview").hidden=true;}
  });

  function show(task){
    $("res-progress-panel").hidden=false;$("res-progress").value=task.progress;
    $("res-done").textContent=`${task.done} concluídas`;$("res-skipped").textContent=`${task.skipped} ignoradas`;$("res-failed").textContent=`${task.failed} com erro`;
    $("res-status").textContent={running:task.kind==="restore"?"Restaurando":"Convertendo",finished:"Concluído",stopped:"Interrompido",failed:"Falhou"}[task.status]||task.status;
    $("res-current").textContent=task.current?`Arquivo atual: ${task.current}`:`${task.done+task.skipped+task.failed} de ${task.total} arquivos processados`;
    $("res-stop").disabled=task.status!=="running";
    $("res-errors-wrap").hidden=!task.errors.length;
    $("res-errors").replaceChildren(...task.errors.map(e=>{const tr=el("tr");tr.append(el("td",e.file||"—"),el("td",e.error));return tr;}));
  }
  async function poll(){
    clearTimeout(timer);if(!taskId)return;
    try{const task=await request(`${api}/tarefas/${taskId}`);show(task);if(task.status==="running")timer=setTimeout(poll,1000);else{message("Processamento encerrado. Gere uma nova prévia para conferir o resultado.");previewed=null;$("res-start").disabled=true;}}
    catch(e){message(e.message);}
  }
  $("res-start").addEventListener("click",async()=>{
    if(!previewed||!confirm(`Substituir ${previewed.pending} imagem(ns) por versões ${previewed.size} × ${previewed.size} px? Os originais irão para Backup-fotos.`))return;
    try{const task=await request(`${api}/processar`,options({confirmar:true}));taskId=task.id;$("res-start").disabled=true;show(task);poll();}catch(e){message(e.message);}
  });
  $("res-stop").addEventListener("click",async()=>{if(taskId){try{show(await request(`${api}/tarefas/${taskId}/parar`,{}));}catch(e){message(e.message);}}});
  $("res-restore").addEventListener("click",async()=>{
    const path=$("res-path").value.trim();if(!path){message("Informe ou selecione a pasta principal.");return;}
    if(!confirm(`Restaurar as imagens originais de ${path}\\Backup-fotos? As versões convertidas serão substituídas pelos originais.`))return;
    try{const task=await request(`${api}/restaurar`,{caminho:path,confirmar:true});taskId=task.id;show(task);poll();}catch(e){message(e.message);}
  });
})();
