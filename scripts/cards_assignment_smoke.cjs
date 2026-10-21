// Isolated browser, mock REST only. Never reads sessions or writes production data.
const fs=require('node:fs'), http=require('node:http'), path=require('node:path');
const os=require('node:os'), cp=require('node:child_process'), assert=require('node:assert/strict');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function main(){
  const html=cp.execFileSync('.venv/Scripts/python.exe',['-c',"import runpy; print(runpy.run_path('tests/test_operations_workspace.py')['render']('Cards'))"],{encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'},windowsHide:true});
  const users=['desenvolvedor','gestor','vendedor'].map((role,i)=>({id:String(i+1),name:'Usuário '+role,role}));
  const rows=Array.from({length:6},(_,i)=>({id:String(i+1),version:1,title:i===1?'<script>unsafe</script> '+ 'Título extenso '.repeat(20):'Atividade '+i,
    kind:'task',approval:'published',status:'todo',assignee_user_id:'1',due_date:'2026-10-21',timezone:'America/Sao_Paulo',deadline:{band:'prioritize'},details:{}}));
  let assignments=0;
  const server=http.createServer((req,res)=>{
    const url=new URL(req.url,'http://localhost');
    if(url.pathname.startsWith('/api/')){
      res.setHeader('Content-Type','application/json');
      if(url.pathname.endsWith('/users'))return res.end(JSON.stringify({items:users,current_user_id:'1',can_manage:true}));
      if(url.pathname.endsWith('/assign')){let body='';req.on('data',chunk=>body+=chunk);req.on('end',()=>{
        const payload=JSON.parse(body);assert.equal(payload.items.length,1);assert.ok(users.some(u=>u.id===payload.assignee_user_id));
        const row=rows.find(r=>r.id===payload.items[0].id);assert.equal(row.version,payload.items[0].version);
        row.assignee_user_id=payload.assignee_user_id;row.version++;assignments++;res.end(JSON.stringify({items:[row]}));
      });return;}
      return res.end(JSON.stringify({total:rows.length,items:rows}));
    }
    if(url.pathname.startsWith('/static/')){
      const target=path.resolve('app',url.pathname.slice(1));
      if(!target.startsWith(path.resolve('app/static')+path.sep)||!fs.existsSync(target)){res.writeHead(404);return res.end();}
      res.setHeader('Content-Type',target.endsWith('.css')?'text/css':target.endsWith('.js')?'application/javascript':target.endsWith('.svg')?'image/svg+xml':'application/octet-stream');
      return fs.createReadStream(target).pipe(res);
    }
    res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`http://127.0.0.1:${server.address().port}`;
  const profile=fs.mkdtempSync(path.join(os.tmpdir(),'prm-cards-browser-'));
  const browser=cp.spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    ['--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{windowsHide:true,stdio:'ignore'});
  const output='data/exports/cards-assignment-visual-'+Date.now();fs.mkdirSync(output,{recursive:true});let ws;
  try{
    let port;for(let n=0;n<60;n++){try{port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break;}catch{}await delay(250);}
    if(!port)throw Error('Browser did not start');
    const tab=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
    ws=new WebSocket(tab.webSocketDebuggerUrl);await new Promise(r=>ws.addEventListener('open',r,{once:true}));
    let seq=0;const pending=new Map(),errors=[];
    ws.addEventListener('message',event=>{const m=JSON.parse(event.data);if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result);}});
    const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
    const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value;};
    await send('Page.enable');await send('Runtime.enable');await send('Page.navigate',{url:origin});await delay(700);
    const reports=[];
    for(const width of [1440,768,390,320])for(const theme of ['light','dark']){
      await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width<600});
      await evaluate(`localStorage.setItem('prm-theme',${JSON.stringify(theme)})`);
      await send('Page.navigate',{url:origin+'/cards'});await delay(800);
      for(const recipient of ['1','2','3']){
        await evaluate(`(()=>{const card=document.querySelector('.mt-operational-card');card.querySelector('select').value=${JSON.stringify(recipient)};[...card.querySelectorAll('button')].find(b=>b.textContent==='Atribuir').click();})()`);await delay(200);
      }
      const report=await evaluate(`(()=>{const cards=[...document.querySelectorAll('.mt-operational-card')];return {count:cards.length,heights:cards.map(c=>c.getBoundingClientRect().height),widths:cards.map(c=>c.getBoundingClientRect().width),overflow:document.documentElement.scrollWidth>innerWidth+1,script:!!document.querySelector('[data-cards-list] script'),demo:!!document.querySelector('[data-demo-cards]'),assigned:document.querySelector('[data-cards-message]').textContent.includes('Alertas internos'),theme:document.documentElement.dataset.theme};})()`);
      assert.equal(report.count,6);assert.equal(new Set(report.heights).size,1);assert.equal(new Set(report.widths.map(Math.round)).size,1);
      assert.equal(report.overflow,false);assert.equal(report.script,false);assert.equal(report.demo,false);assert.equal(report.assigned,true);assert.equal(report.theme,theme);assert.deepEqual(errors,[]);
      const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});fs.writeFileSync(`${output}/${width}-${theme}.png`,Buffer.from(shot.data,'base64'));reports.push({width,...report});
    }
    assert.equal(assignments,24);fs.writeFileSync(output+'/report.json',JSON.stringify({assignments,reports},null,2));console.log(JSON.stringify({output,assignments,reports}));await send('Browser.close');
  }finally{if(ws)ws.close();browser.kill();server.closeAllConnections();server.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
