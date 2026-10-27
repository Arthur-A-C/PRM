const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attributes={};this.hidden=false;this.value='';this.events={};this.classList={add(){},remove(){}};}
 append(...x){this.children.push(...x);}replaceChildren(...x){this.children=x;}setAttribute(k,v){this.attributes[k]=v;}addEventListener(k,f){this.events[k]=f;}after(){}focus(){}reset(){}showModal(){this.open=true;}close(){this.open=false;}
 querySelectorAll(selector){return this.children.flatMap(c=>[...(selector==='[data-tab]'?c.dataset?.tab?[c]:[]:c.tag==='button'?[c]:[]),...c.querySelectorAll(selector)]);}
}
const settle=()=>new Promise(r=>setImmediate(r));
test('Drawer, quick create, score, interaction, task, folder and drag handlers use API without reload',async()=>{
 const ids={};for(const id of ['suppliers','supplier-filters','supplier-board','supplier-detail','supplier-backdrop','supplier-dialog','supplier-form','supplier-fields','supplier-form-title','supplier-form-error','supplier-message','supplier-new','supplier-cancel'])ids[id]=new Element('div');ids['supplier-detail'].hidden=true;
 const cfg={manager:false,user_id:'me',users:[{id:'me',name:'Eu'}],stages:{base_ativa:'Base ativa',tratativa:'Em tratativa'},scores:{morno:'Morno',quente:'Quente'},categories:['Contratos','Outros']};
 const item={id:'one',name:'Empresa',stage:'base_ativa',score:'morno',responsible_user_id:'me',data:{},contacts:[],tasks:[{id:'t1',assignee_user_id:'me',data:{title:'Ligar',status:'pendente',priority:'normal'}}],documents:[{id:'d1',data:{category:'Contratos',original_name:'contrato.pdf',size:1,status:'Vigente'}}],history:[]};const calls=[];
 class FormData{constructor(){this.entries=[];}[Symbol.iterator](){return this.entries[Symbol.iterator]();}}
 const ctx=vm.createContext({FormData,URLSearchParams,location:{search:''},history:{replaceState(){}},document:{getElementById:id=>ids[id],createElement:t=>new Element(t),querySelector:()=>({value:'csrf'}),addEventListener(){},body:new Element('body')},fetch:async(url,options)=>{calls.push([url,options]);let data;if(url.endsWith('/config'))data=cfg;else if(options.method==='PATCH'){Object.assign(item,JSON.parse(options.body));data=item;}else if(url.includes('/tasks/')&&options.method==='PUT'){item.tasks[0].data.status='concluida';data=item.tasks[0];}else if(url.includes('?'))data={items:[item]};else data=item;return {ok:true,json:async()=>JSON.parse(JSON.stringify(data))};}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../../app/static/js/suppliers.js'),'utf8'),ctx);await settle();await settle();
 function all(e){return [e,...e.children.flatMap(all)];}const find=(e,text)=>all(e).find(x=>x.tag==='button'&&x.textContent===text);
 const board=ids['supplier-board'];let card=all(board).find(e=>e.className==='supplier-card');assert.equal(card.draggable,true);await card.onclick();assert.equal(ids['supplier-detail'].hidden,false);
 let score=all(ids['supplier-detail']).find(e=>e.name==='score');score.value='quente';await score.onchange();assert.equal(item.score,'quente');
 await find(ids['supplier-detail'],'Documentos').onclick();assert.ok(all(ids['supplier-detail']).some(e=>e.textContent==='📁 Contratos · 1 arquivo(s)'));
 await find(ids['supplier-detail'],'Tarefas').onclick();await find(ids['supplier-detail'],'✓ Concluir').onclick();assert.equal(item.tasks[0].data.status,'concluida');
 await find(ids['supplier-detail'],'Nova interação').onclick();assert.equal(ids['supplier-dialog'].open,true);assert.equal(ids['supplier-form-title'].textContent,'Registrar interação');ids['supplier-dialog'].close();
 ids['supplier-new'].onclick();const names=all(ids['supplier-fields']).map(e=>e.name).filter(Boolean);assert.deepEqual(names,['name','stage','score','responsible_user_id','cnpj','website','primary_contact']);
 const col=all(board).find(e=>e.dataset.stage==='tratativa');await col.events.drop({preventDefault(){},dataTransfer:{getData:()=>item.id}});assert.equal(item.stage,'tratativa');
 assert.ok(calls.filter(([,o])=>o.method==='PATCH').every(([,o])=>o.headers['X-CSRF-Token']==='csrf'));
});
