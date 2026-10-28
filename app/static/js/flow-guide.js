// Guia de etapas declarativo: "onde estou, o que já foi feito, o que falta e qual é a próxima ação".
// Cada etapa ([data-flow-done]) declara um seletor CSS que fica verdadeiro quando ela termina; a etapa atual é a
// primeira ainda não concluída. O guia só lê a página (DOM) que os scripts de cada ferramenta já atualizam:
// não faz requisições, não altera formulários e não muda o comportamento das ferramentas.
(() => {
  'use strict';
  if (window.PRMFlowGuide) return;
  // Só grava quando muda: atributos repetidos gerariam novas mutações e um ciclo de reavaliação.
  const setHidden = (node, value) => { if (node.hidden !== value) node.hidden = value; };
  const setText = (node, value) => { if (node && node.textContent !== value) node.textContent = value; };
  const matches = selector => { try { return !!(selector && document.querySelector(selector)); } catch { return false; } };

  function evaluate(flow) {
    const steps = [...flow.querySelectorAll('[data-flow-done]')];
    let current = steps.findIndex(step => !matches(step.dataset.flowDone));
    const complete = current === -1;
    if (complete) current = steps.length;
    steps.forEach((step, index) => {
      const state = index < current ? 'done' : index === current ? 'current' : 'pending';
      step.classList.toggle('is-done', state === 'done');
      if (state === 'current') step.setAttribute('aria-current', 'step'); else step.removeAttribute('aria-current');
      step.dataset.flowState = state;
      const target = step.dataset.flowTarget && document.querySelector(step.dataset.flowTarget);
      if (target) target.dataset.flowState = state;
    });
    const step = steps[current];
    const next = flow.querySelector('[data-flow-next-text]');
    setText(next, complete ? (flow.dataset.flowComplete || 'Todas as etapas concluídas.') : step.dataset.flowNext || step.textContent.trim());
    const count = flow.querySelector('[data-flow-count]');
    setText(count, complete ? `${steps.length} de ${steps.length} etapas concluídas` : `Etapa ${current + 1} de ${steps.length}`);
    const go = flow.querySelector('[data-flow-go]');
    if (go) {
      const target = !complete && step.dataset.flowTarget;
      setHidden(go, !target);
      if (target) go.setAttribute('href', target);
    }
    flow.classList.toggle('is-complete', complete);
    let alerting = false;
    flow.querySelectorAll('[data-flow-alert]').forEach(alert => { setHidden(alert, !matches(alert.dataset.flowAlert)); alerting ||= !alert.hidden; });
    flow.classList.toggle('has-alert', alerting);
  }

  function start() {
    const flows = [...document.querySelectorAll('[data-flow]')];
    if (!flows.length) return;
    let queued = false;
    const refresh = () => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; flows.forEach(evaluate); });
    };
    new MutationObserver(refresh).observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['hidden', 'disabled', 'class', 'data-tone', 'open'] });
    ['input', 'change'].forEach(type => document.addEventListener(type, refresh, true));
    flows.forEach(evaluate);
    // Um link para #catalog-import (ou outro <details>) abre o bloco recolhido.
    const target = location.hash && document.getElementById(location.hash.slice(1));
    if (target && target.tagName === 'DETAILS') target.open = true;
  }

  window.PRMFlowGuide = { refresh: () => document.querySelectorAll('[data-flow]').forEach(evaluate) };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
