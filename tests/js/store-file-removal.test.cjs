const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const context = vm.createContext({ document: { getElementById: () => null } });
vm.runInContext(fs.readFileSync(path.join(__dirname, '../../app/static/js/store-file-removal.js'), 'utf8'), context);

test('FastAPI details: string, validation array, nested detail and absent response', () => {
  const message = context.removalErrorMessage;
  assert.equal(message('Dry Run não aprovado', 422), 'Dry Run não aprovado');
  assert.equal(message([{loc: ['body', 'skus', 0], msg: 'Código inválido'}, {loc: ['body', 'confirmacao'], msg: 'Confirme'}], 422), 'skus.0: Código inválido; confirmacao: Confirme');
  assert.equal(message({detail: 'Backup inválido'}, 422), 'Backup inválido');
  assert.match(message(null, 500), /HTTP 500/);
});

const permissions = {approve: true, execute: true, restore: true};
const review = {sku: '0001', state: 'review', dry_run: {dry_run_sha256: 'hash'}};
const approved = {...review, approval: {dry_run_sha256: 'hash'}};
const available = (items, selected, busy, perms = permissions) => context.removalActionAvailability({items, permissions: perms}, selected, busy);

test('Execute requires current approval; restore requires a restorable item', () => {
  assert.equal(available([review]).executar, false);
  assert.equal(available([review]).aprovar, true);
  assert.equal(available([approved]).executar, true);
  assert.equal(available([{...approved, approval: {dry_run_sha256: 'old'}}]).executar, false);
  assert.equal(available([{sku: '0001', state: 'done', restorable: true}]).restaurar, true);
  assert.equal(available([{sku: '0001', state: 'restored', restorable: false}]).restaurar, false);
});

test('Selection, role permissions, running state and busy state constrain buttons', () => {
  assert.equal(available([approved], new Set(['0002'])).executar, false);
  assert.equal(available([approved], new Set(['0001'])).executar, true);
  assert.equal(available([approved], undefined, false, {}).executar, false);
  assert.equal(available([{...approved, state: 'running'}]).executar, false);
  assert.equal(Object.keys(available([approved], undefined, true)).length, 0);
});

test('Queue actions are offered only for corresponding states', () => {
  assert.equal(available([{state: 'restore_queued'}]).pausar, true);
  assert.equal(available([{state: 'restore_queued'}]).cancelar, true);
  assert.equal(available([{state: 'preview_queued'}]).pausar, false);
  assert.equal(available([{state: 'uncertain'}]).reconferir, true);
  assert.equal(available([{state: 'blocked'}]).reprocessar, true);
  assert.equal(available([{state: 'done'}]).reprocessar, false);
});
