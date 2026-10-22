// Isolated local browser smoke. Mock APIs only; no DB, credentials or paid calls.
const fs = require("node:fs"), http = require("node:http"), path = require("node:path");
const os = require("node:os"), cp = require("node:child_process"), assert = require("node:assert/strict");
const delay = ms => new Promise(r => setTimeout(r, ms));
async function main() {
  const stores = process.argv.includes("--stores");
  const html = cp.execFileSync(".venv/Scripts/python.exe", ["-c",
    `import runpy; print(runpy.run_path('tests/test_operations_workspace.py')['render']('${stores ? "Integrações WooCommerce" : "Geração em Lote"}'))`],
    {encoding:"utf8",env:{...process.env,PYTHONIOENCODING:"utf-8"},windowsHide:true});
  const id = "a".repeat(32);
  const data = {id, created:1792454400, model:"modelo-simulado", state:"finished", total:3, progress:100,
    counts:{done:1,review:1,error:1}, items:[
      {id:1,codigo:"0001",nome:"<script>unsafe</script>",empresa:"choice",pdf:"datasheets/0001.pdf",state:"done",download:true,
        folder:"Produtos/0001",warnings:["Nome usado como referência; revisar"],assets:[
          {name:"Fotos/<script>photo</script>.png",role:"image",bytes:123,analyze:true},
          {name:"desenho.step",role:"drawing_3d",bytes:456,analyze:false}]},
      {id:2,codigo:"0002",nome:"Computador industrial",empresa:"portwell",pdf:"0002.pdf",state:"review",error:"Conferir especificação",download:true},
      {id:3,codigo:"0003",nome:"Sensor",empresa:"sag",pdf:"0003.pdf",state:"error",error:"Falha temporária",technical:"RateLimitError",attempts:3}]};
  const server = http.createServer((req,res) => {
    const url = new URL(req.url,"http://localhost");
    if(url.pathname.startsWith("/api/")) {
      res.setHeader("Content-Type","application/json");
      if (stores) {
        const items = ["choice","sag","portwell"].map(company=>({company, checked_at:"2026-10-20T12:00:00Z",
          woocommerce:{authenticated:false,message:"Teste simulado: credenciais pendentes"},
          wordpress:{authenticated:false,message:"Teste simulado: credenciais pendentes"}}));
        return res.end(JSON.stringify(req.method === "POST" ? items.find(i=>url.pathname.includes("/"+i.company+"/")) : {items}));
      }
      return res.end(JSON.stringify(url.pathname.endsWith("/lotes") ? {items:[data]} : data));
    }
    if(url.pathname.startsWith("/static/")) {
      const target = path.resolve("app", "."+url.pathname);
      if(!target.startsWith(path.resolve("app/static")+path.sep)||!fs.existsSync(target)){res.writeHead(404);return res.end();}
      res.setHeader("Content-Type",target.endsWith(".css")?"text/css":target.endsWith(".js")?"application/javascript":target.endsWith(".svg")?"image/svg+xml":"application/octet-stream");
      return fs.createReadStream(target).pipe(res);
    }
    res.setHeader("Content-Type","text/html; charset=utf-8");res.end(html);
  });
  await new Promise(r=>server.listen(0,"127.0.0.1",r));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(),"prm-batch-browser-"));
  const browser = cp.spawn("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    ["--headless=new","--disable-gpu","--no-first-run","--remote-debugging-port=0",`--user-data-dir=${profile}`,"about:blank"],
    {windowsHide:true,stdio:"ignore"});
  const output = "data/exports/"+(stores?"stores":"batch")+"-visual-"+Date.now(); fs.mkdirSync(output,{recursive:true});
  let ws;
  try {
    let port;
    for(let n=0;n<60;n++){try{port=fs.readFileSync(path.join(profile,"DevToolsActivePort"),"utf8").split("\n")[0];break;}catch{} await delay(250);}
    if(!port)throw Error("Browser did not start");
    const tab=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:"PUT"})).json();
    ws=new WebSocket(tab.webSocketDebuggerUrl);await new Promise(r=>ws.addEventListener("open",r,{once:true}));
    let seq=0;const pending=new Map(),errors=[];
    ws.addEventListener("message",e=>{const msg=JSON.parse(e.data);if(msg.method==="Runtime.exceptionThrown")errors.push(msg.params.exceptionDetails.text);
      const p=pending.get(msg.id);if(p){pending.delete(msg.id);msg.error?p.reject(Error(msg.error.message)):p.resolve(msg.result);}});
    const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
    const evaluate=async expression=>{const r=await send("Runtime.evaluate",{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value;};
    await send("Page.enable");await send("Runtime.enable");
    await send("Page.navigate",{url:origin});await delay(600);
    const reports=[];
    for(const width of [1440,768,390,320])for(const theme of ["light","dark"]) {
      await send("Emulation.setDeviceMetricsOverride",{width,height:1000,deviceScaleFactor:1,mobile:width<600});
      await evaluate(`localStorage.setItem("prm-theme",${JSON.stringify(theme)})`);
      await send("Page.navigate",{url:origin+"/digitalizacao/lotes?lote="+id});await delay(900);
      if(stores) {
        await evaluate(`document.querySelector('[data-test-store="choice"]').click()`);
        await delay(300);
      } else {
        const mode = await evaluate(`(()=>{
          const input=document.querySelector('#batch-identification');
          const company=document.querySelector('#batch-company');
          const initial=input.value==='folder' && company.required && !company.disabled;
          input.value='csv'; input.dispatchEvent(new Event('change'));
          const csv=company.disabled && !company.required;
          input.value='folder'; input.dispatchEvent(new Event('change')); company.value='choice';
          const form=new FormData(document.querySelector('#batch-upload'));
          return {initial,csv,mode:form.get('identificacao'),company:form.get('empresa'),
            inventory:document.querySelector('#batch-products').textContent.includes('desenho.step')};
        })()`);
        assert.deepEqual(mode,{initial:true,csv:true,mode:'folder',company:'choice',inventory:true});
      }
      const result= stores ? await evaluate(`(()=>{return {
        cards:document.querySelectorAll("[data-store]").length,
        results:document.querySelectorAll("[data-wc-status],[data-wp-status]").length,
        tested:document.querySelector("#store-message").textContent.includes("Diagnóstico concluído"),
        overflow:document.documentElement.scrollWidth>innerWidth+1,theme:document.documentElement.dataset.theme
      }})()`) : await evaluate(`(()=>{document.querySelector("#batch-products details").open=true;return {
        rows:document.querySelectorAll("#batch-products tr").length,history:document.querySelectorAll("#batch-history tr").length,
        overflow:document.documentElement.scrollWidth>innerWidth+1,theme:document.documentElement.dataset.theme,
        escaped:document.querySelector("#batch-products").textContent.includes("<script>unsafe</script>"),
        script:!!document.querySelector("#batch-products script"),
        retry:!document.querySelector("#batch-retry").disabled,progress:document.querySelector("#batch-progress").value
      }})()`);
      assert.equal(result.overflow,false);assert.equal(result.theme,theme);assert.deepEqual(errors,[]);
      if(stores) {
        assert.equal(result.cards,3);assert.equal(result.results,6);assert.equal(result.tested,true);
      } else {
        assert.equal(result.rows,3);assert.equal(result.history,1);assert.equal(result.escaped,true);assert.equal(result.script,false);
        assert.equal(result.retry,true);assert.equal(result.progress,100);
      }
      const shot=await send("Page.captureScreenshot",{format:"png",captureBeyondViewport:true});
      fs.writeFileSync(`${output}/${width}-${theme}.png`,Buffer.from(shot.data,"base64"));
      reports.push({width,...result});
    }
    fs.writeFileSync(output+"/report.json",JSON.stringify(reports,null,2));
    console.log(JSON.stringify({output,reports}));
    await send("Browser.close");
  } finally {
    if(ws)ws.close();
    browser.kill();
    server.closeAllConnections();server.close();
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
