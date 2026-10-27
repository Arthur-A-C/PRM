const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
class Element{constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.events={};}append(...x){this.children.push(...x);}setAttribute(k,v){this.attributes[k]=v;}addEventListener(k,f){this.events[k]=f;}close(){this.closed=true;this.events.close?.();}}
const all=e=>[e,...(e.children||[]).flatMap(all)];
const settle=()=>new Promise(r=>setTimeout(r,5));
const json=x=>JSON.parse(JSON.stringify(x));
const sug=(value,extra={})=>({value,confidence:'high',verified:true,source_type:'website',source:'https://www.sihovision.com/contact',evidence:value,...extra});
const preview={run_id:'r1',mode:'new',model:'claude-haiku-5-5',source:{type:'combined',document_name:'ficha.xlsx',domain:'sihovision.com'},pages:['a','b'],warnings:[],discarded:1,
 document:{original_name:'ficha.xlsx',size:10},defaults:{name:'Sihovision',stage:'base_ativa',score:'morno',responsible_user_id:'me',website:'https://www.sihovision.com/'},
 all_fields:[{key:'legal_name',label:'Razão social',group:'Empresa',kind:'text'},{key:'website',label:'Site',group:'Contato',kind:'url'},
  {key:'phone',label:'Telefone',group:'Contato',kind:'phone'},{key:'segment',label:'Segmento',group:'Comercial',kind:'text'},{key:'city',label:'Cidade',group:'Endereço',kind:'text'}],
 fields:[{key:'legal_name',kind:'text',status:'new',preselect:0,suggestions:[sug('Shenzhen Shinho')]},
  {key:'phone',kind:'phone',status:'conflict',preselect:null,suggestions:[sug('+55 47 1111-1111',{source_type:'supplier_document',source:'ficha.xlsx',page:'Cadastro'}),sug('+55 47 2222-2222')]},
  {key:'segment',kind:'text',status:'new',preselect:null,suggestions:[sug('Industrial',{confidence:'medium'})]}],
 contacts:[{id:'c1',name:'John Smith',role:'Sales Manager',email:'john@x.com',confidence:'high',source_type:'website',source:'u',duplicate_of:null}],
 social:[{id:'s1',network:'LinkedIn',url:'https://linkedin.com/company/x'}],
 duplicates:[{id:'old',name:'Sihovision Ltda',responsible:'Kauê',stage:'Em tratativa',reasons:['nome'],strong:false}]};
function load(fetchImpl,confirmImpl=()=>false){const dialog=new Element('dialog');const ctx=vm.createContext({setTimeout,confirm:confirmImpl,fetch:fetchImpl,
 FormData:class{constructor(){this.items=[];}append(k,v){this.items.push([k,v]);}},document:{getElementById:id=>id==='supplier-dialog'?dialog:null,querySelector:()=>({value:'csrf'})}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../../app/static/js/supplier-ai.js'),'utf8'),ctx);return {ctx,dialog};}

test('Initial state prefills only safe suggestions and the body sends edits with their origin choice',()=>{
 const {ctx}=load();const s=ctx.supplierAINewState(preview);
 assert.deepEqual(json(s.fields),{legal_name:{value:'Shenzhen Shinho',choice:0},website:{value:'https://www.sihovision.com/',choice:null},
  phone:{value:'',choice:null},segment:{value:'Industrial',choice:0},city:{value:'',choice:null}});
 assert.deepEqual([...s.contacts],['c1']);assert.deepEqual([...s.social],['s1']);assert.equal(s.attach,true);
 s.fields.legal_name.value='Shenzhen Shinho Brasil';s.fields.phone={value:'+55 47 2222-2222',choice:1};s.also.add('phone:0');s.fields.city.value='Shenzhen';
 const body=json(ctx.supplierAINewBody(preview,s));
 assert.deepEqual(body.fields,{legal_name:{value:'Shenzhen Shinho Brasil',choice:0},website:{value:'https://www.sihovision.com/',choice:null},
  phone:{value:'+55 47 2222-2222',choice:1},segment:{value:'Industrial',choice:0},city:{value:'Shenzhen',choice:null}});
 assert.deepEqual(body.also_contacts,[{key:'phone',choice:0}]);
 assert.equal(body.responsible_user_id,'me');assert.equal(body.stage,'base_ativa');assert.equal(body.score,'morno');
 s.name='  ';assert.throws(()=>ctx.supplierAINewBody(preview,s),/nome/);
});

test('Flow: no supplier until confirmation; cancel discards; confirmation creates and opens the card',async()=>{
 const calls=[];const fetchImpl=async(url,o)=>{calls.push([url,json(JSON.parse(o.body))]);return {ok:true,json:async()=>url.endsWith('/ai/criar')?{id:'new-id',summary:'ok'}:{ok:true}};};
 const {ctx,dialog}=load(fetchImpl);const modals=[],opened=[],requests=[];
 const node=(tag,text)=>{const e=new Element(tag);if(text!=null)e.textContent=text;return e;};
 const field=(box,name,label,value='')=>{const e=node('input');e.name=name;e.value=value;box.append(node('label',label),e);return e;};
 const cfg={manager:false,user_id:'me',users:[{id:'me',name:'Eu'},{id:'other',name:'Outro'}],stages:{base_ativa:'Base ativa',tratativa:'Em tratativa'},scores:{quente:'Quente',morno:'Morno'}};
 const c={cfg,node,field,msg(){},modal:(title,build,action,submit)=>modals.push({title,build,action,submit}),openSupplier:id=>opened.push(id),
  request:async(p,m,b)=>{requests.push([p,m]);return preview;}};
 ctx.supplierAINew(c);
 assert.match(modals[0].title,/1\. Fontes/);assert.equal(modals[0].submit,'Analisar e preencher');
 await assert.rejects(()=>modals[0].action({url:''}),/ficha cadastral e\/ou/);assert.equal(requests.length,0);
 await modals[0].action({url:'https://www.sihovision.com/'});await settle();
 assert.deepEqual(requests,[['/ai/analisar','POST']]);assert.equal(modals[1].submit,'Cadastrar fornecedor');
 const box=new Element('div');modals[1].build(box);const texts=all(box).map(e=>e.textContent).filter(Boolean);
 assert.ok(texts.includes('Fornecedor com nome semelhante'));assert.ok(texts.some(t=>t.includes('Sihovision Ltda · Responsável: Kauê · Etapa: Em tratativa')));
 assert.ok(texts.some(t=>t.includes('Encontrado em: ficha.xlsx — aba Cadastro')));assert.ok(texts.some(t=>t.includes('Encontrado em: sihovision.com/contact')));
 assert.ok(texts.includes('🌤️ Morno'));assert.ok(texts.includes('Anexar ficha.xlsx em Documentos › Ficha cadastral'));
 const owners=all(box).find(e=>e.tag==='select'&&all(e).some(o=>o.textContent==='Eu'));assert.equal(all(owners).filter(o=>o.tag==='option').length,1);  // seller: only self
 const radio=all(box).find(e=>e.type==='radio'&&e.attributes['aria-label']==='Usar +55 47 2222-2222');radio.checked=true;radio.onchange();
 dialog.close();await settle();  // closing before confirming discards the pending analysis
 assert.deepEqual(calls[0],['/api/v1/fornecedores/ai/descartar',{run_id:'r1'}]);
 await modals[1].action({});await settle();
 const [url,body]=calls[1];assert.equal(url,'/api/v1/fornecedores/ai/criar');assert.deepEqual(body.fields.phone,{value:'+55 47 2222-2222',choice:1});
 assert.deepEqual(body.contacts,['c1']);assert.equal(body.attach_document,true);assert.deepEqual(opened,['new-id']);
});

test('Strong duplicate at confirmation shows the message and can open the existing supplier',async()=>{
 const detail={message:'Este fornecedor foi cadastrado enquanto você revisava a análise.',can_continue:false,duplicates:[{id:'dup',name:'Sihovision',reasons:['dominio'],strong:true}]};
 const {ctx}=load(async()=>({ok:false,status:409,json:async()=>({detail})}),()=>true);const modals=[],opened=[];
 const node=(tag,text)=>{const e=new Element(tag);if(text!=null)e.textContent=text;return e;};
 const c={cfg:{manager:true,user_id:'me',users:[{id:'me',name:'Eu'}],stages:{base_ativa:'Base ativa'},scores:{morno:'Morno'}},node,field(){return node('input');},msg(){},
  modal:(t,b,a)=>modals.push({b,a}),openSupplier:id=>opened.push(id),request:async()=>({...preview,duplicates:[]})};
 ctx.supplierAINew(c);await modals[0].a({url:'https://x.com'});await settle();modals[1].b(new Element('div'));
 await assert.rejects(()=>modals[1].a({}),/enquanto você revisava/);assert.deepEqual(opened,['dup']);
});
