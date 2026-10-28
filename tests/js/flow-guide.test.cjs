const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');

// DOM mínimo: seletores "verdadeiros" são controlados pelo teste; o guia só lê a página.
class Node {
  constructor(attrs={}){this.dataset={...attrs};this.attrs={};this.classes=new Set();this.hidden=false;this.textContent='';this.children=[];
    this.classList={toggle:(c,on)=>{on?this.classes.add(c):this.classes.delete(c);},contains:c=>this.classes.has(c)};}
  setAttribute(k,v){this.attrs[k]=String(v);} removeAttribute(k){delete this.attrs[k];}
  querySelectorAll(sel){return this.children.filter(c=>c.matches(sel));}
  querySelector(sel){return this.querySelectorAll(sel)[0]||null;}
  matches(sel){const key=sel.slice(6,-1).replace(/-(\w)/g,(_,c)=>c.toUpperCase());return key in this.dataset;}
}
function setup(){
  const truth=new Set();const targets={'#a':new Node(),'#b':new Node(),'#c':new Node()};
  const flow=new Node({flow:'',flowComplete:'Pronto.'});
  const steps=[['done-a','#a','Faça A'],['done-b','#b','Faça B'],['done-c','#c','Faça C']].map(([done,target,next])=>new Node({flowDone:done,flowTarget:target,flowNext:next}));
  const nextText=new Node({flowNextText:''}),count=new Node({flowCount:''}),go=new Node({flowGo:''}),alert=new Node({flowAlert:'erro'});
  flow.children=[...steps,nextText,count,go,alert];
  let observer;
  const document={readyState:'complete',body:{},addEventListener(){},
    querySelectorAll:sel=>sel==='[data-flow]'?[flow]:[],
    querySelector:sel=>targets[sel]||(truth.has(sel)?{}:null),getElementById:()=>null};
  const context={window:{},document,location:{hash:''},requestAnimationFrame:fn=>fn(),
    MutationObserver:class{constructor(fn){observer=fn;}observe(){}}};
  vm.runInNewContext(fs.readFileSync('app/static/js/flow-guide.js','utf8'),context);
  return {truth,steps,targets,nextText,count,go,alert,flow,refresh:()=>context.window.PRMFlowGuide.refresh()};
}

test('the first unfinished step is current, earlier ones are done and the next action follows it',()=>{
  const g=setup();
  assert.equal(g.steps[0].attrs['aria-current'],'step');assert.equal(g.nextText.textContent,'Faça A');assert.equal(g.count.textContent,'Etapa 1 de 3');
  g.truth.add('done-a');g.refresh();
  assert.deepEqual(g.steps.map(s=>s.dataset.flowState),['done','current','pending']);
  assert.ok(g.steps[0].classes.has('is-done'));assert.equal(g.steps[0].attrs['aria-current'],undefined);
  assert.equal(g.targets['#b'].dataset.flowState,'current');assert.equal(g.go.attrs.href,'#b');
  // Uma etapa posterior "verdadeira" não pula a atual: a ordem é obrigatória.
  g.truth.add('done-c');g.refresh();assert.equal(g.nextText.textContent,'Faça B');
  g.truth.add('done-b');g.refresh();
  assert.ok(g.flow.classes.has('is-complete'));assert.equal(g.nextText.textContent,'Pronto.');assert.equal(g.go.hidden,true);
});

test('alerts appear only while their selector matches',()=>{
  const g=setup();
  assert.equal(g.alert.hidden,true);
  g.truth.add('erro');g.refresh();assert.equal(g.alert.hidden,false);assert.ok(g.flow.classes.has('has-alert'));
  g.truth.delete('erro');g.refresh();assert.equal(g.alert.hidden,true);
});
