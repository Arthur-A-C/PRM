const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.events={};this.value='';this.disabled=false;}
 append(...items){this.children.push(...items);if(this.tag==='select')this.value=this.children.find(c=>c.selected)?.value||this.children[0]?.value||'';}
 replaceChildren(...items){this.children=[];this.append(...items);}
 addEventListener(k,fn){this.events[k]=fn;}
 querySelectorAll(tag){return this.children.flatMap(c=>typeof c==='string'?[]:[...(c.tag===tag?[c]:[]),...c.querySelectorAll(tag)]);}
}
const settle=()=>new Promise(r=>setImmediate(r));
test('catalog import separates origins and requires preview and explicit confirmation',async()=>{
 const ids={};for(const id of ['catalog-import-form','catalog-import-message','catalog-new-competitor','catalog-mapping','catalog-preview','catalog-confirm','catalog-import-preview','catalog-history','catalog-history-content','catalog-file-limit'])ids[id]=new Element('div');
 const form=ids['catalog-import-form'];form.elements={};for(const key of ['company_id','group','file','sheet','header_row','mode'])form.elements[key]=new Element(key==='file'?'input':'select');
 form.elements.group.value='internal';form.elements.file.files=[{size:20}];form.reportValidity=()=>true;
 class Data extends Map {constructor(form){super(Object.entries(form.elements).map(([k,v])=>[k,v.value]));}}
 const calls=[];let confirmed=false;const renderedToken={value:'rendered-token'};
 const cfg={origins:[{id:'own',name:'Portwell',source_group:'internal'},{id:'rival',name:'Rival',source_group:'competitor'}],fields:{external_code:'SKU',name:'Nome'},max_bytes:50000000};
 const preview={source_group:'competitor',origin:'Rival',counts:{new:1,updated:0,unchanged:0,errors:0},sample:[],errors:[],preview_token:'approved-preview'};
 const context={document:{cookie:'custom_csrf_cookie=ignored',querySelector:selector=>{assert.equal(selector,'input[name="csrf_token"]');return renderedToken;},getElementById:id=>ids[id],createElement:tag=>new Element(tag)},Option:function(label,value,def,selected){const e=new Element('option');Object.assign(e,{textContent:label,value,selected});return e;},FormData:Data,confirm:()=>confirmed,fetch:async(url,options={})=>{calls.push([url,options]);let result=cfg;if(url.endsWith('/prepare')){const action=options.body.get('action');result=action==='inspect'?{sheets:['CSV'],sheet:'CSV',headers:['SKU','Nome'],mapping:{external_code:'SKU',name:'Nome'}}:action==='preview'?preview:{result:{inserted:1,updated:0},catalog_url:'/catalogos?view=legacy'};}return {ok:true,json:async()=>result};}};
 vm.runInNewContext(fs.readFileSync('app/static/js/catalog-import.js','utf8'),context);await settle();
 assert.deepEqual(form.elements.company_id.children.map(c=>c.value),['own']);
 form.elements.group.value='competitor';form.elements.group.events.change();
 assert.deepEqual(form.elements.company_id.children.map(c=>c.value),['rival']);
 form.onsubmit({preventDefault(){}});await settle();
 assert.equal(calls.at(-1)[1].body.get('action'),'inspect');
 assert.equal(calls.at(-1)[1].headers['X-CSRF-Token'],'rendered-token');
 assert.equal(calls.at(-1)[1].headers['Content-Type'],undefined); // Browser supplies multipart boundary.
 renderedToken.value='refreshed-token';
 await ids['catalog-preview'].onclick();assert.equal(ids['catalog-confirm'].disabled,false);
 await ids['catalog-confirm'].onclick();assert.equal(calls.filter(([,o])=>o.body?.get('action')==='import').length,0);
 confirmed=true;await ids['catalog-confirm'].onclick();
 assert.equal(calls.at(-1)[1].body.get('expected_preview'),'approved-preview');assert.equal(calls.at(-1)[1].body.get('group'),'competitor');
 assert.equal(calls.at(-1)[1].headers['X-CSRF-Token'],'refreshed-token');assert.equal(ids['catalog-confirm'].disabled,true);
 assert.ok(calls.every(([,options])=>options.credentials==='same-origin'&&options.cache==='no-store'));
 assert.equal(calls.find(([,options])=>options.body?.get('action')==='preview')[1].headers['X-CSRF-Token'],'refreshed-token');
});
