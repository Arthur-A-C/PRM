const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
// Digitalização sem o bloco "Cadastro automatizado": finalizar, baixar e recuperar continuam na etapa 08.
const settle=()=>new Promise(r=>setTimeout(r,5));
function load(fetchImpl){
 const el=id=>({id,value:'',textContent:'',hidden:true,disabled:true,files:[],events:{},classList:{toggle(){}},setAttribute(){},addEventListener(k,f){this.events[k]=f;}});
 const nodes=Object.fromEntries(['digitalizacao-pacote-status','digitalizacao-baixar-pacote','digitalizacao-recuperar','digitalizacao-run-id','digitalizacao-manuais','digitalizacao-certificados','digitalizacao-outros'].map(id=>[id,el(id)]));
 const store={},finalized=[];
 const window={location:{search:''},setTimeout,confirm:()=>false,prmDigitalizacao:{markFinalized:v=>finalized.push(v),restoreRun(){},invalidateForFiles(){},
  snapshot:()=>({company:'portwell',sku:'ABC123',technicalName:'Sensor X',runId:'r1',analysis:{model:'X1'}})},addEventListener(){}};
 const ctx=vm.createContext({window,fetch:fetchImpl,FormData:class{constructor(){this.items=[];}append(k,v){this.items.push([k,v]);}},URLSearchParams,
  localStorage:{getItem:k=>store[k]??null,setItem:(k,v)=>{store[k]=v;},removeItem:k=>{delete store[k];}},
  document:{getElementById:id=>nodes[id]||null,querySelector:()=>({value:'csrf'}),createElement:()=>el('pre')}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../../app/static/js/registration.js'),'utf8'),ctx);
 return {window,nodes,finalized};
}

test('Package flow works without the removed registration block',async()=>{
 const calls=[];const record={run_id:'r1',status:'validated',folder_path:'/pacotes/ABC123',package_version:1,sku:'ABC123',manifest:{}};
 const {window,nodes,finalized}=load(async(url,o)=>{calls.push([url,o]);return {ok:true,json:async()=>record};});
 assert.equal(typeof window.prmRegistration.finalizePackage,'function');
 await window.prmRegistration.finalizePackage();await settle();
 const [url,o]=calls[0];assert.equal(url,'/api/v1/digitalizacao/finalizar');
 const product=JSON.parse(o.body.items.find(([k])=>k==='product_json')[1]);
 assert.equal(product.commercial_title,'Sensor X');assert.equal(product.supplier,null);assert.deepEqual(product.attributes,[]);
 assert.deepEqual(product.category_paths,[]);assert.equal(product.validation_status,'needs_review');
 assert.match(nodes['digitalizacao-pacote-status'].textContent,/validados em \/pacotes\/ABC123\. Versão 1/);
 assert.equal(nodes['digitalizacao-baixar-pacote'].disabled,false);assert.deepEqual(finalized,[true]);
});
