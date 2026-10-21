// Read-only visual smoke in an existing local CDP browser. No session or DB writes.
const fs=require('node:fs'),assert=require('node:assert/strict');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function main(){
  const folder=process.argv[2],html=fs.readFileSync(folder+'/cards.html','utf8');
  const demo=JSON.parse(fs.readFileSync('data/meetings/read-ai-dashboard-demo.json','utf8'));
  const reports=[];
  for(const width of [1440,768,390,320])for(const theme of ['light','dark']){
    const tab=await(await fetch('http://127.0.0.1:9225/json/new?about:blank',{method:'PUT'})).json();
    const ws=new WebSocket(tab.webSocketDebuggerUrl);await new Promise(r=>ws.addEventListener('open',r,{once:true}));
    let id=0;const pending=new Map(),errors=[];
    ws.addEventListener('message',event=>{const msg=JSON.parse(event.data);if(msg.method==='Runtime.exceptionThrown')errors.push(msg.params.exceptionDetails.text);const p=pending.get(msg.id);if(p){pending.delete(msg.id);msg.error?p.reject(Error(msg.error.message)):p.resolve(msg.result);}});
    const send=(method,params={})=>new Promise((resolve,reject)=>{const key=++id;pending.set(key,{resolve,reject});ws.send(JSON.stringify({id:key,method,params}));});
    const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value;};
    try{
      await send('Page.enable');await send('Runtime.enable');
      await send('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:width<600});
      await send('Page.navigate',{url:'http://127.0.0.1:8000/login'});await delay(400);
      await evaluate(`localStorage.setItem('prm-theme',${JSON.stringify(theme)});window.fetch=async url=>new Response(JSON.stringify(String(url).includes('meeting-demo')?${JSON.stringify({available:true,...demo})}:{detail:'Módulo não migrado'}),{status:String(url).includes('meeting-demo')?200:503,headers:{'Content-Type':'application/json'}});`);
      const tree=await send('Page.getFrameTree');await send('Page.setDocumentContent',{frameId:tree.frameTree.frame.id,html});await delay(1000);
      const result=await evaluate(`(()=>{const root=document.querySelector('.cards-showcase');const details=root.querySelector('.mt-card details');details.open=true;return {visible:!root.hidden,cards:root.querySelectorAll('.mt-card').length,counts:[...root.querySelectorAll('[data-demo-count]')].map(n=>n.textContent),overflow:document.documentElement.scrollWidth>innerWidth+1,details:details.open,theme:document.documentElement.dataset.theme,columns:getComputedStyle(root.querySelector('.mt-card-list')).gridTemplateColumns};})()`);
      assert.equal(result.visible,true);assert.equal(result.cards,7);assert.deepEqual(result.counts,['7','6','1','7']);assert.equal(result.overflow,false);assert.equal(result.theme,theme);assert.deepEqual(errors,[]);
      const capture=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});fs.writeFileSync(`${folder}/cards-${width}-${theme}.png`,Buffer.from(capture.data,'base64'));
      reports.push({width,theme,...result});
    }finally{ws.close();await fetch('http://127.0.0.1:9225/json/close/'+tab.id);}
  }
  fs.writeFileSync(folder+'/visual-report.json',JSON.stringify(reports,null,2));console.log(JSON.stringify(reports));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
