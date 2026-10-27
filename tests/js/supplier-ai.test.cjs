const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
class Element{constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.dataset={};}append(...x){this.children.push(...x);}setAttribute(k,v){this.attributes[k]=v;}}
const all=e=>[e,...(e.children||[]).flatMap(all)];
const settle=()=>new Promise(r=>setTimeout(r,5));
const preview={run_id:'r1',status:'ok',model:'claude-haiku-5-5',cached:false,source:{type:'website',domain:'sihovision.com'},pages:['https://sihovision.com/'],warnings:[],discarded:1,
 fields:[{key:'legal_name',label:'Razão social',group:'Empresa',kind:'text',current:'',status:'new',preselect:0,actions:['replace'],suggestions:[{value:'Shenzhen Shinho',confidence:'high',verified:true,source_type:'website',source:'https://sihovision.com/',evidence:'Shenzhen Shinho'}]},
  {key:'email',label:'E-mail geral',group:'Contato',kind:'email',current:'contato@empresa.com',status:'differs',preselect:null,actions:['replace','contact'],suggestions:[{value:'info@sihovision.com',confidence:'high',verified:true,source_type:'website',source:'u',evidence:'info'}]},
  {key:'phone',label:'Telefone',group:'Contato',kind:'phone',current:'',status:'conflict',preselect:null,actions:['replace','contact'],suggestions:[{value:'+86 1',confidence:'high',verified:true,source_type:'supplier_document',source:'ficha.xlsx',page:'Cadastro',evidence:'+86 1'},{value:'+86 2',confidence:'high',verified:true,source_type:'website',source:'u',evidence:'+86 2'}]},
  {key:'segment',label:'Segmento',group:'Comercial',kind:'text',current:'',status:'new',preselect:null,actions:['replace'],suggestions:[{value:'Displays',confidence:'medium',verified:true,source_type:'website',source:'u',evidence:'Displays'}]}],
 contacts:[{id:'c1',name:'John Smith',role:'Sales Manager',email:'john@x.com',confidence:'high',source_type:'website',source:'u',duplicate_of:null},{id:'c2',name:'Comercial',email:'sales@x.com',confidence:'high',source_type:'website',source:'u',duplicate_of:'Comercial'}],
 social:[{id:'s1',network:'LinkedIn',url:'https://linkedin.com/company/x',exists:false}]};
function load(){const ctx=vm.createContext({setTimeout,FormData:class{append(){}},document:{}});vm.runInContext(fs.readFileSync(path.join(__dirname,'../../app/static/js/supplier-ai.js'),'utf8'),ctx);return ctx;}

test('Defaults select only high-confidence new fields; conflicts and existing values need a decision',()=>{
 const c=load();const s=c.supplierAIDefaults(preview);
 assert.equal(s.fields.legal_name.action,'replace');assert.equal(s.fields.email.action,'');assert.equal(s.fields.segment.action,'');assert.equal(s.fields.phone.choice,null);
 const body=c.supplierAIApplyBody(preview,s);assert.deepEqual(JSON.parse(JSON.stringify(body)),{run_id:'r1',fields:[{key:'legal_name',choice:0,action:'replace'}],contacts:[],social:['s1']});
 s.fields.phone.action='replace';assert.throws(()=>c.supplierAIApplyBody(preview,s),/Telefone/);
 s.fields.phone.choice=1;assert.equal(c.supplierAIApplyBody(preview,s).fields[1].choice,1);
 const none={fields:{},contacts:new Set(),social:new Set()};assert.throws(()=>c.supplierAIApplyBody(preview,none),/ao menos um/);
});

test('Flow: chooser does not analyze until submitted, review shows evidence/duplicates and applies only selections',async()=>{
 const c=load();const calls=[],modals=[],messages=[];
 const node=(tag,text)=>{const e=new Element(tag);if(text!=null)e.textContent=text;return e;};
 const field=(box,name,label,value='',options)=>{const e=node(options?'select':'input');e.name=name;e.value=value;box.append(node('label',label),e);return e;};
 const current={id:'sup',data:{website:'https://sihovision.com'},documents:[{id:'d1',data:{category:'Ficha cadastral',original_name:'ficha.pdf'}},{id:'d2',data:{category:'Outros',original_name:'x.zip'}}]};
 const request=async(p,method='GET',body)=>{calls.push([p,method,body]);if(p.endsWith('/status'))return {enabled:true};if(p.includes('analisar'))return preview;return {summary:'Fonte: site oficial. 1 campo(s) aplicado(s).'};};
 const ctx={current,request,node,field,modal:(title,build,action,submit)=>modals.push({title,build,action,submit}),msg:t=>messages.push(t),reopen:tab=>messages.push('reopen:'+tab)};
 c.supplierAIStart(ctx);await settle();
 assert.equal(modals[0].title,'Preencher com IA');assert.equal(calls.length,1);
 const box=new Element('div');modals[0].build(box);const docSelect=all(box).find(e=>e.name==='document_id');assert.equal(docSelect.value,'d1');
 await modals[0].action({mode:'site',url:'https://sihovision.com'});await settle();
 assert.deepEqual(JSON.parse(JSON.stringify(calls[1])),['/sup/ai/analisar-site','POST',{url:'https://sihovision.com'}]);
 assert.equal(modals[1].title,'Preenchimento sugerido');assert.equal(modals[1].submit,'Aplicar campos selecionados');
 const review=new Element('div');modals[1].build(review);const texts=all(review).map(e=>e.textContent).filter(Boolean);
 assert.ok(texts.includes('Atual: contato@empresa.com'));assert.ok(texts.includes('Encontrado: info@sihovision.com'));
 assert.ok(texts.some(t=>t.includes('Fonte: ficha cadastral · ficha.xlsx · página Cadastro')));assert.ok(texts.some(t=>t.includes('descartada')));
 const boxes=all(review).filter(e=>e.type==='checkbox');const dup=boxes.find(b=>b.disabled);assert.ok(dup,'duplicate contact disabled');
 const john=all(review).find(e=>e.tag==='label'&&all(e).some(x=>x.textContent==='John Smith · Sales Manager'));const johnBox=all(john).find(e=>e.type==='checkbox');johnBox.checked=true;johnBox.onchange();
 const action=all(review).find(e=>e.tag==='select'&&e.attributes['aria-label']==='Ação para E-mail geral');action.value='contact';action.onchange();
 await modals[1].action({});await settle();
 const [p,method,body]=calls[2];assert.equal(p,'/sup/ai/aplicar');assert.equal(method,'POST');
 assert.deepEqual(JSON.parse(JSON.stringify(body)),{run_id:'r1',fields:[{key:'legal_name',choice:0,action:'replace'},{key:'email',choice:0,action:'contact'}],contacts:['c1'],social:['s1']});
 assert.ok(messages.includes('reopen:Histórico'));
});

test('Disabled server configuration never opens the analysis form',async()=>{
 const c=load();const modals=[],messages=[];
 c.supplierAIStart({current:{id:'x',data:{},documents:[]},request:async()=>({enabled:false}),node:()=>new Element('p'),field(){},modal:()=>modals.push(1),msg:t=>messages.push(t)});await settle();
 assert.equal(modals.length,0);assert.match(messages[0],/não configurada/);
});
