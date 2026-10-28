const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');

class El {
  constructor(data={}){this.dataset=data;this.hidden=false;this.attrs={};this.events={};this.children=[];this.textContent='';}
  setAttribute(k,v){this.attrs[k]=v;} addEventListener(k,fn){this.events[k]=fn;}
  querySelectorAll(sel){return sel==='tr[data-cmp-row]'?this.children:[];}
}
test('filters hide rows and empty groups without touching data',()=>{
  const rows=[new El({cmpRow:'diff missing'}),new El({cmpRow:'equal'}),new El({cmpRow:'missing'}),new El({cmpRow:'meta'})];
  const groupA=new El(),groupB=new El(),meta=new El();groupA.children=rows.slice(0,2);groupB.children=[rows[2]];meta.children=[rows[3]];
  const buttons=['all','diff','equal','missing'].map(f=>new El({cmpFilter:f}));
  const status=new El(),empty=new El();empty.hidden=true;
  const root={querySelectorAll:sel=>sel==='[data-cmp-filter]'?buttons:sel==='tr[data-cmp-row]'?rows:sel==='tbody'?[groupA,groupB,meta]:[],
    querySelector:sel=>sel==='[data-cmp-status]'?status:sel==='[data-cmp-empty]'?empty:null};
  vm.runInNewContext(fs.readFileSync('app/static/js/comparison-view.js','utf8'),{document:{querySelector:()=>root}});
  buttons[1].events.click();
  assert.deepEqual(rows.map(r=>r.hidden),[false,true,true,true]);
  assert.equal(groupB.hidden,true);assert.equal(groupA.hidden,false);
  assert.equal(buttons[1].attrs['aria-pressed'],'true');assert.equal(buttons[0].attrs['aria-pressed'],'false');
  assert.equal(status.textContent,'1 de 3 características com diferença');assert.equal(empty.hidden,true);
  buttons[0].events.click();
  assert.ok(rows.every(r=>!r.hidden));assert.equal(status.textContent,'');
});
