(() => {
  "use strict";
  const $=id=>document.getElementById(id),root=$("res-page");if(!root)return;
  // mode "envio": pasta enviada do computador do usuário (padrão); "servidor": pasta em PRM_IMAGE_TOOL_ROOTS.
  const api="/api/v1/imagens";let browsing=null,parent=null,taskId=null,timer=null,previewed=null,mode=null,envio=null;
  const csrf=()=>document.querySelector('input[name="csrf_token"]')?.value||"";
  const message=text=>{$("res-message").textContent=text;};
  const bytes=n=>n>=1073741824?(n/1073741824).toFixed(2)+" GB":n>=1048576?(n/1048576).toFixed(1)+" MB":Math.round(n/1024)+" KB";
  const picker=()=>$("res-picker").picker;
  function el(tag,text,className){const node=document.createElement(tag);if(text!=null)node.textContent=text;if(className)node.className=className;return node;}
  async function request(url,body,method="POST"){
    const r=await fetch(url,body?{method,credentials:"same-origin",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf()},body:JSON.stringify(body)}:{credentials:"same-origin",cache:"no-store"});
    const data=await r.json().catch(()=>({}));if(!r.ok)throw Error(typeof data.detail==="string"?data.detail:"Falha na solicitação");return data;
  }
  const options=(extra={})=>({subpastas:$("res-recursive").checked,tamanho:Number($("res-size").value),...extra});
  const serverOptions=(extra={})=>options({caminho:$("res-path").value.trim(),mover_para_backup:true,...extra});
  const url=action=>mode==="envio"?`${api}/envios/${envio}/${action}`:`${api}/${action}`;
  const body=extra=>mode==="envio"?options(extra):serverOptions(extra);
  function invalidate(){previewed=null;$("res-start").disabled=true;$("res-confirm").checked=false;}
  // Any option change invalidates the preview: conversion always starts from a fresh, confirmed preview.
  ["res-path","res-recursive","res-size"].forEach(id=>$(id).addEventListener("input",invalidate));
  $("res-picker").addEventListener("local-files:change",()=>{invalidate();envio=null;$("res-preview").hidden=true;$("res-result").hidden=true;});
  $("res-confirm").addEventListener("change",()=>{$("res-start").disabled=!(previewed&&$("res-confirm").checked&&previewed.pending&&previewed.space_ok);});

  async function browse(path){
    const data=await request(`${api}/pastas`+(path?`?caminho=${encodeURIComponent(path)}`:""));
    browsing=data.path;parent=data.parent;
    $("res-dialog-path").textContent=data.path||"Raízes permitidas";$("res-up").disabled=!parent;$("res-choose").disabled=!data.path;
    const list=$("res-folders");list.replaceChildren();
    data.folders.forEach(f=>{const li=el("li"),b=el("button",f.name);b.type="button";b.addEventListener("click",()=>browse(f.path).catch(e=>message(e.message)));li.append(b);list.append(li);});
    if(!data.folders.length)list.append(el("li","Nenhuma subpasta.","prm-status"));
  }
  // The server-folder mode only appears when the administrator configured PRM_IMAGE_TOOL_ROOTS.
  request(`${api}/pastas`).then(data=>{$("res-server").hidden=!data.enabled;}).catch(()=>{});
  $("res-browse").addEventListener("click",async()=>{try{await browse($("res-path").value.trim()||null);}catch{await browse(null).catch(e=>message(e.message));}$("res-dialog").showModal();});
  $("res-up").addEventListener("click",()=>browse(parent).catch(e=>message(e.message)));
  $("res-roots").addEventListener("click",()=>browse(null).catch(e=>message(e.message)));
  $("res-cancel").addEventListener("click",()=>$("res-dialog").close());
  $("res-choose").addEventListener("click",()=>{$("res-path").value=browsing;$("res-path").dispatchEvent(new Event("input"));$("res-dialog").close();});

  async function showPreview(){
    message("Analisando as imagens…");
    try{
      const data=await request(url("previa"),body());previewed=data;
      $("res-preview").hidden=false;$("res-preview-root").textContent=`${data.root} · ${data.size} × ${data.size} px · backup em ${data.backup}`;
      for(const key of ["folders","images","pending","already_converted"])root.querySelector(`[data-stat="${key}"]`).textContent=data[key];
      const space=root.querySelector('[data-stat="space"]');space.textContent=`${bytes(data.required_bytes)} / ${bytes(data.free_bytes)}`;space.classList.toggle("is-alert",!data.space_ok);
      $("res-extensions").textContent=Object.entries(data.by_extension).map(([k,v])=>`${v} ${k}`).join(" · ")+(data.restorable?` · ${data.restorable} restauráveis no backup`:"");
      $("res-sample").replaceChildren(...data.sample.map(s=>el("li",s)));
      $("res-confirm").checked=false;$("res-start").disabled=true;
      message(!data.space_ok?"Espaço livre insuficiente para backup e processamento.":data.pending?"Confira a prévia e confirme para converter.":"Nenhuma imagem pendente: tudo já foi convertido pelo PRM.");
    }catch(e){message(e.message);$("res-preview").hidden=true;}
  }
  $("res-form").addEventListener("submit",async event=>{
    event.preventDefault();
    if(!picker()?.hasFiles()){message("Selecione uma pasta ou fotos do seu computador.");return;}
    $("res-send").disabled=true;
    try{if(!envio)envio=await picker().upload();mode="envio";$("res-result").hidden=true;await showPreview();}
    catch(e){message(e.message);}finally{$("res-send").disabled=false;}
  });
  $("res-server-preview").addEventListener("click",()=>{
    if(!$("res-path").value.trim()){message("Informe ou selecione a pasta do servidor.");return;}
    mode="servidor";$("res-result").hidden=true;showPreview();
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
  function finished(){
    previewed=null;$("res-start").disabled=true;
    if(mode==="envio"&&envio){
      $("res-download").href=`${api}/envios/${envio}/resultado.zip`;$("res-download-backup").href=`${api}/envios/${envio}/resultado.zip?backup=true`;
      $("res-result").hidden=false;message("Processamento encerrado. Baixe o ZIP com as imagens convertidas.");
    }else message("Processamento encerrado. Gere uma nova prévia para conferir o resultado.");
  }
  async function poll(){
    clearTimeout(timer);if(!taskId)return;
    try{const task=await request(`${api}/tarefas/${taskId}`);show(task);if(task.status==="running")timer=setTimeout(poll,1000);else finished();}
    catch(e){message(e.message);}
  }
  $("res-start").addEventListener("click",async()=>{
    const where=mode==="envio"?"na cópia enviada ao servidor":"na pasta do servidor";
    if(!previewed||!confirm(`Converter ${previewed.pending} imagem(ns) para ${previewed.size} × ${previewed.size} px ${where}? Os originais ficam em Backup-fotos.`))return;
    try{const task=await request(url("processar"),body({confirmar:true}));taskId=task.id;$("res-start").disabled=true;show(task);poll();}catch(e){message(e.message);}
  });
  $("res-stop").addEventListener("click",async()=>{if(taskId){try{show(await request(`${api}/tarefas/${taskId}/parar`,{}));}catch(e){message(e.message);}}});
  $("res-restore").addEventListener("click",async()=>{
    const path=$("res-path").value.trim();if(!path){message("Informe ou selecione a pasta do servidor.");return;}
    if(!confirm(`Restaurar as imagens originais de ${path}/Backup-fotos? As versões convertidas serão substituídas pelos originais.`))return;
    mode="servidor";
    try{const task=await request(`${api}/restaurar`,{caminho:path,confirmar:true});taskId=task.id;show(task);poll();}catch(e){message(e.message);}
  });
  $("res-discard").addEventListener("click",async()=>{
    if(!envio||!confirm("Remover do servidor as imagens enviadas, convertidas e o Backup-fotos desta operação?"))return;
    try{await request(`/api/v1/envios/${envio}`,{},"DELETE");picker()?.done();envio=null;
      $("res-result").hidden=true;$("res-preview").hidden=true;$("res-progress-panel").hidden=true;message("Arquivos removidos do servidor.");}
    catch(e){message(e.message);}
  });
})();
