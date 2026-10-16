// Regression checks against scripts.workspace_preview only. No credentials/API writes.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  const output = process.argv[2];
  if (!output) throw new Error('Usage: node scripts/workspace_visual_smoke.cjs OUTPUT_DIRECTORY');
  fs.mkdirSync(output, { recursive: true });
  const reports = [];
  for (const width of [1440, 1280, 768, 390, 320]) {
    for (const theme of ['light', 'dark']) {
      for (const route of ['/', '/digitalizacao']) {
        const tab = await (await fetch('http://127.0.0.1:9225/json/new?about:blank', { method: 'PUT' })).json();
        const socket = new WebSocket(tab.webSocketDebuggerUrl);
        await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }); });
        let seq = 0;
        const pending = new Map(), errors = [];
        socket.addEventListener('message', event => {
          const message = JSON.parse(event.data);
          if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
          if (!pending.has(message.id)) return;
          const task = pending.get(message.id); pending.delete(message.id); clearTimeout(task.timer);
          message.error ? task.reject(new Error(message.error.message)) : task.resolve(message.result);
        });
        const send = (method, params = {}) => new Promise((resolve, reject) => {
          const id = ++seq;
          const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Timeout: ${method}`)); }, 15000);
          pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }));
        });
        const evaluate = async expression => {
          const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
          if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
          return result.result.value;
        };
        try {
          await send('Page.enable'); await send('Runtime.enable');
          await send('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.clear(); localStorage.setItem('prm-theme', '${theme}');` });
          await send('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 600 });
          await send('Page.navigate', { url: 'http://127.0.0.1:8871' + route });
          await delay(600);
          const checks = await evaluate(`(() => {
            const results = [];
            const check = (ok, label) => { if (!ok) throw new Error(label); results.push(label); };
            const q = s => document.querySelector(s);
            const shown = s => !!q(s) && getComputedStyle(q(s)).display !== 'none';
            check(document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1, 'no page overflow');
            check(document.documentElement.dataset.theme === '${theme}', 'theme applied');
            const ids = [...document.querySelectorAll('[id]')].map(el => el.id);
            check(new Set(ids).size === ids.length, 'unique DOM IDs');
            if (q('[data-operations]')) {
              const data = JSON.parse(q('#ops-data').textContent);
              check(Number(q('[data-ops-total]').textContent.replaceAll('.', '')) === data.accepted, 'real snapshot totals');
              q('[data-ops-company-card=choice]').click();
              check(q('[data-ops-company]').value === 'choice', 'company card context');
              check(q('[data-ops-search-source]').value === 'choice', 'search scope');
              check(Number(q('[data-ops-total]').textContent.replaceAll('.', '')) === data.sources.find(s => s.code === 'choice').accepted, 'filtered metric');
              q('[data-ops-company-card=sag]').click();
              check(q('[data-ops-total]').textContent === '—', 'SAG empty state not invented');
              q('[data-ops-company]').value = 'dimensional'; q('[data-ops-company]').dispatchEvent(new Event('change'));
              check(shown('[data-ops-competitor-panel=dimensional]') && !shown('[data-ops-competitor-panel=eco]'), 'competitor switch');
              check(q('[data-ops-pending-link]').getAttribute('href').includes('source=dimensional'), 'pending link scope');
              q('[data-ops-view=attributes]').click();
              check(shown('#ops-attributes') && !shown('#ops-overview'), 'attributes tab');
              q('[data-ops-view=attributes]').dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}));
              check(shown('#ops-quality') && document.activeElement.id === 'ops-tab-quality', 'keyboard tabs');
              q('#ops-quality details').open = true;
              check(document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1, 'quality table contained');
              q('[data-ops-view=overview]').click();
              q('[data-ops-company]').value = 'all'; q('[data-ops-company]').dispatchEvent(new Event('change'));
              q('[data-ops-competitor=eco]').click();
              q('[data-ops-density]').click();
              check(localStorage.getItem('prm-density') === 'compact', 'density preference');
              q('[data-ops-density]').click();
            } else {
              for (const company of ['portwell', 'choice', 'sag']) {
                q('[data-company-select=' + company + ']').click();
                check(q('#digitalizacao-empresa').value === company && q('.digitalizacao-page').dataset.company === company, company + ' company selection');
              }
              q('[data-company-select=choice]').click();
              for (const [id, value] of [['digitalizacao-codigo', 'VISUAL-LOCAL'], ['digitalizacao-produto', 'Produto de teste visual local']]) {
                q('#' + id).value = value; q('#' + id).dispatchEvent(new Event('input', {bubbles: true}));
              }
              check(q('#context-product-name').textContent.includes('Produto de teste'), 'live product context');
              q('[data-workspace-inspector]').click();
              check(!shown('#workspace-product-context'), 'collapse context');
              q('[data-workspace-inspector]').click();
              check(shown('#workspace-product-context'), 'restore context');
              check(typeof window.prmDigitalizacao.snapshot === 'function' && typeof window.prmRegistration.finalizePackage === 'function', 'existing workflow hooks retained');
            }
            if (${width} < 600) {
              q('[data-prm-nav-toggle]').click();
              check(document.body.classList.contains('nav-open'), 'mobile menu opens');
              document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
              check(!document.body.classList.contains('nav-open'), 'mobile menu escape');
            }
            check(document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1, 'no overflow after interactions');
            return results;
          })()`);
          const label = `${route === '/' ? 'dashboard' : 'digitalizacao'}-${width}-${theme}`;
          const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
          fs.writeFileSync(path.join(output, label + '.png'), Buffer.from(shot.data, 'base64'));
          if (width === 1440 || width === 390) {
            if (route === '/digitalizacao') {
              const imageChecks = await evaluate(`(async () => {
                const blob = await (await fetch('/static/brand-lockup.png')).blob();
                const transfer = new DataTransfer();
                transfer.items.add(new File([blob], 'fixture-local-1.png', {type: 'image/png'}));
                transfer.items.add(new File([blob], 'fixture-local-2.png', {type: 'image/png'}));
                const input = document.querySelector('#digitalizacao-imagens');
                input.files = transfer.files; input.dispatchEvent(new Event('change', {bubbles: true}));
                if (window.prmDigitalizacao.snapshot().images.length !== 2) throw new Error('image selection');
                const main = [...document.querySelectorAll('.digitalizacao-image-actions button')].find(b => b.textContent === 'Tornar principal');
                main.click();
                if (window.prmDigitalizacao.snapshot().images[0].file.name !== 'fixture-local-2.png') throw new Error('main image');
                const rotate = document.querySelector('.digitalizacao-image-actions [aria-label="Girar 90 graus para a direita"]');
                rotate.click();
                if (window.prmDigitalizacao.snapshot().images[0].rotation !== 90) throw new Error('image rotation');
                return ['local image selection', 'main image ordering', 'image rotation'];
              })()`);
              checks.push(...imageChecks);
            }
            await evaluate(`document.querySelector('${route === '/' ? '.ops-coverage' : '#digitalizacao-fotos-etapa'}').scrollIntoView()`);
            await delay(250);
            const detail = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
            fs.writeFileSync(path.join(output, label + '-detail.png'), Buffer.from(detail.data, 'base64'));
            if (route === '/digitalizacao') {
              await evaluate(`document.querySelector('.digitalizacao-image-preview').click(); if (!document.querySelector('#digitalizacao-image-dialog').open) throw new Error('image dialog');`);
              const modal = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
              fs.writeFileSync(path.join(output, label + '-modal.png'), Buffer.from(modal.data, 'base64'));
              await evaluate(`document.querySelector('#digitalizacao-image-dialog-close').click(); [...document.querySelectorAll('.digitalizacao-image-actions .danger-action')].forEach(b => b.click()); if (window.prmDigitalizacao.snapshot().images.length) throw new Error('remove images');`);
              checks.push('image enlargement dialog', 'remove local images');
            }
          }
          assert.deepEqual(errors, [], 'No uncaught browser errors');
          reports.push({ route, width, theme, checks, browserErrors: errors });
          process.stdout.write(`PASS ${label}: ${checks.length} checks\n`);
        } finally {
          socket.close(); await fetch(`http://127.0.0.1:9225/json/close/${tab.id}`);
        }
      }
    }
  }
  fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(reports, null, 2));
}
main().catch(error => { process.stderr.write(error.stack + '\n'); process.exitCode = 1; });
