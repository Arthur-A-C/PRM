const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const context = vm.createContext({ document: { getElementById: () => null } });
vm.runInContext(fs.readFileSync(path.join(__dirname, '../../app/static/js/store-registration.js'), 'utf8'), context);

test('Bulk selection includes only eligible ready and approved items; second click clears all', () => {
  const items = [{sku:'001',state:'review'}, {sku:'002',state:'review',approval:{}},
    ...['blocked','error','uncertain','running'].map(state=>({sku:state,state})),
    {sku:'old',state:'review',needs_refresh:true}, {sku:'manual',state:'review',requires_manual_review:true},
    {sku:'disabled',state:'review',disabled:true}, {sku:'blocker',state:'review',blockers:['Review']}];
  const choices = new Map();
  context.registrationSelectAll(items,choices,true);
  assert.deepEqual([...choices].filter(([,c])=>c.select).map(([sku])=>sku),['001','002']);
  assert.equal(context.registrationSelectionCount(items,choices).selected,2);
  assert.equal(context.registrationSelectionCount(items,choices).eligible,2);
  assert.deepEqual(Array.from(context.registrationSelected(items,choices,'aprovar')),['001']);
  assert.deepEqual(Array.from(context.registrationSelected(items,choices,'confirmar')),['002']);
  choices.set('001',{select:false});
  assert.equal(context.registrationSelectionCount(items,choices).selected,1);
  assert.equal(context.registrationSelected(items,choices,'aprovar').length,0);
  items[1].needs_refresh=true;
  assert.equal(context.registrationSelectionCount(items,choices).selected,0);
  assert.equal(context.registrationSelected(items,choices,'confirmar').length,0);
  context.registrationSelectAll(items,choices,false);
  assert.equal([...choices.values()].filter(c=>c.select).length,0);
});

test('FastAPI error strings and arrays are readable', () => {
  assert.equal(context.registrationErrorMessage('SKU inválido', 422), 'SKU inválido');
  assert.equal(context.registrationErrorMessage([{loc: ['body', 'skus', 0], msg: 'Código inválido'}], 422), 'skus.0: Código inválido');
  assert.match(context.registrationErrorMessage(null, 500), /HTTP 500/);
});
test('Sending one selected SKU never implicitly selects the remaining 22', () => {
  const items = Array.from({length: 23}, (_, n) => ({sku: String(n), state: 'review', approval: {}}));
  assert.equal(context.registrationSelected(items, new Map(), 'confirmar').length, 0);
  const selected = context.registrationSelected(items, new Map([['3', {select: true}]]), 'confirmar');
  assert.equal(selected.length, 1); assert.equal(selected[0], '3');
  items[3].needs_refresh = true;
  assert.equal(context.registrationSelected(items, new Map([['3', {select: true}]]), 'confirmar').length, 0);
});
test('Restore only selects recoverable items; preview selection remains read-only', () => {
  const items = [{sku: '01', can_rollback: true}, {sku: '02', can_rollback: false}];
  const picked = new Map(items.map(i => [i.sku, {select: true}]));
  assert.equal(context.registrationSelected(items, picked, 'restaurar').length, 1);
  assert.equal(context.registrationSelected(items, picked, 'reprocessar').length, 2);
});
test('Registration scope is explicit, combinable and rendered for the Dry Run', () => {
  assert.equal(context.registrationScopeValue({gallery: true, documents: false, main: false}), 'gallery');
  assert.equal(context.registrationScopeValue({gallery: true, documents: true, main: true}), 'gallery,documents,main');
  assert.equal(context.registrationScopeValue({gallery: false, documents: true, main: true}), 'documents,main');
  assert.equal(context.registrationScopeValue({gallery: false, documents: false, main: false}), '');
  assert.equal(context.registrationScopeText({gallery: true, documents: true, main: false}), '✓ Galeria · ✓ Documentos · ✗ Principal');
  assert.match(context.registrationScopeText(null), /Escopo anterior/);
});
test('Scope change targets only selected items that may get a new Dry Run; bulk approval ignores scope states', () => {
  const items = ['review', 'awaiting_main', 'nothing', 'blocked', 'done', 'queued', 'running'].map(state => ({sku: state, state}));
  const picked = new Map(items.map(i => [i.sku, {select: true}]));
  assert.deepEqual(Array.from(context.registrationSelected(items, picked, 'escopo')), ['review', 'awaiting_main', 'nothing', 'blocked']);
  const choices = new Map();
  context.registrationSelectAll(items, choices, true);
  assert.deepEqual([...choices].filter(([, c]) => c.select).map(([sku]) => sku), ['review']);
  assert.deepEqual(Array.from(context.registrationSelected(items, choices, 'aprovar')), ['review']);
});
test('Dry Run shows the <SKU>_n classification: detected main, numeric gallery, duplicates and outside files', () => {
  const rule = {pattern: '0012_<n>.ext', main: {name: '0012_1.png'}, gallery: [{name: '0012_2.png'}, {name: '0012_3.png'}, {name: '0012_10.png'}],
    duplicates: [], outside: ['frente.png']};
  assert.deepEqual(Array.from(context.registrationImageRule(rule, '0012')), ['Principal detectada automaticamente: 0012_1.png',
    'Galeria: 1. 0012_2.png · 2. 0012_3.png · 3. 0012_10.png', 'Imagem fora do padrão de nomenclatura: frente.png']);
  const missing = context.registrationImageRule({...rule, main: null, gallery: [], duplicates: [2], outside: []}, '0012');
  assert.deepEqual(Array.from(missing), ['Foto principal não encontrada no padrão 0012_1.ext.', 'Galeria: nenhuma imagem no padrão.',
    'Mais de uma imagem encontrada para a posição _2.']);
  assert.equal(context.registrationImageRule(null, '0012').length, 0);
});
test('Status badges always carry text, distinguish approval and use the shared tones', () => {
  assert.deepEqual(Array.from(context.registrationStatus({state: 'review'})), ['Pronto para aprovação', 'is-info']);
  assert.deepEqual(Array.from(context.registrationStatus({state: 'review', approval: {by: 'x'}})), ['Aprovado', 'is-ok']);
  assert.deepEqual(Array.from(context.registrationStatus({state: 'blocked'})), ['Bloqueado', 'is-alert']);
  assert.deepEqual(Array.from(context.registrationStatus({state: 'done'})), ['Verificado', 'is-ok']);
  assert.match(context.registrationStatus({state: 'running'})[1], /is-busy/);
  assert.deepEqual(Array.from(context.registrationStatus({state: 'estado_novo'})), ['estado_novo', '']);
  for (const state of ['preview_queued','preview_running','review','awaiting_main','nothing','blocked','queued','running','done','error','uncertain','rollback_queued','rollback_running','rolled_back','rollback_error'])
    assert.ok(context.registrationStatus({state})[0].length > 2, state);
});
