const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const ctx=vm.createContext({document:{getElementById:()=>null}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../app/static/js/suppliers.js'),'utf8'),ctx);
test('Common user cannot pick another owner in UI payload',()=>{
 const cfg={manager:false,user_id:'self',users:[{id:'self'},{id:'other'}]};
 assert.equal(ctx.supplierOwnerOptions(cfg).length,1);
 assert.equal(ctx.supplierPayload({responsible_user_id:'other'},cfg).responsible_user_id,'self');
});
test('Manager can select organization user; backend remains authority',()=>{
 const cfg={manager:true,user_id:'self',users:[{id:'self'},{id:'other'}]};
 assert.equal(ctx.supplierOwnerOptions(cfg).length,2);
 assert.equal(ctx.supplierPayload({responsible_user_id:'other'},cfg).responsible_user_id,'other');
});
test('Drag persists stage and rolls back after API failure',async()=>{
 const item={id:'1',stage:'base_ativa'};let paints=0;
 await ctx.supplierMove(item,'tratativa',async(id,body)=>{assert.equal(body.expected_stage,'base_ativa');assert.equal(body.stage,'tratativa');},()=>paints++);
 assert.equal(item.stage,'tratativa');
 await assert.rejects(ctx.supplierMove(item,'ativo',async()=>{throw Error('403');},()=>paints++));
 assert.equal(item.stage,'tratativa');assert.equal(paints,3);
});
test('Quick filters and friendly timeline',()=>{
 const items=[{responsible_user_id:'me',data:{next_action:'Ligar',next_action_date:'2026-01-01'}},{responsible_user_id:'other',data:{}}];
 assert.equal(ctx.supplierQuickFilter(items,'mine','me').length,1);
 assert.equal(ctx.supplierQuickFilter(items,'overdue','me','2026-10-26').length,1);
 assert.equal(ctx.supplierQuickFilter(items,'empty','me').length,1);
 assert.match(ctx.supplierHistoryText({event:'score_changed',data:{before:'morno',after:'quente'}},{scores:{morno:'Morno',quente:'Quente'},users:[]}),/Morno → Quente/);
});
