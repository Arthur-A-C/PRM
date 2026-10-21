(() => {
  const root=document.querySelector('[data-meeting-demo]');if(!root)return;
  const el=(tag,text,cls)=>{const node=document.createElement(tag);node.textContent=text;if(cls)node.className=cls;return node;};
  const types={explicit:'Compromisso declarado',offer:'Oferta a confirmar',suggestion:'Possibilidade a avaliar',request:'Solicitação'};
  fetch('/api/v1/meeting-demo',{credentials:'same-origin'}).then(async response=>{
    if(!response.ok)return;const data=await response.json();if(!data.available)return;
    root.hidden=false;root.querySelector('[data-demo-notice]').textContent=data.notice;
    if(root.classList.contains('cards-showcase')){
      const counts={all:data.cards.length,task:data.cards.filter(c=>c.kind==='task').length,event:data.cards.filter(c=>c.kind==='event').length,pending:data.cards.filter(c=>!c.assignee_user_id).length};
      root.querySelectorAll('[data-demo-count]').forEach(node=>{node.textContent=counts[node.dataset.demoCount];});
    }
    // During the mock-only phase, do not display unmigrated operational controls/errors.
    fetch('/api/v1/planner/users',{credentials:'same-origin'}).then(response=>{
      if(response.status===503){document.querySelectorAll('[data-meeting-page], [data-planner]').forEach(node=>{node.hidden=true;});}
    }).catch(()=>{});
    const list=root.querySelector('[data-demo-cards]');
    data.cards.forEach(card=>{
      const item=el('article','','mt-card is-draft');item.append(el('span','MOCK · não operacional','mt-chip'),el('h3',card.title),el('p',types[card.commitment_type]||card.commitment_type));
      item.append(el('p','Participante citado: '+(card.speaker||'Não identificado')),el('p','Responsável PRM: pendente'));
      item.append(el('p',card.confirmed_date?'Data confirmada: 24/09/2026 · 15h candidato · 40 min estimados':'Prazo: a confirmar'+(card.due.raw_expression?' · expressão original: '+card.due.raw_expression:'')));
      if(card.checklist.length){const ul=el('ul','');card.checklist.forEach(text=>ul.append(el('li',text)));item.append(ul);}
      const details=el('details','');details.append(el('summary','Evidências da transcrição e pendências'));
      card.evidence.forEach(e=>details.append(el('blockquote',e.quote)));
      card.ambiguities.filter(t=>t!=='Mês/ano ausentes da transcrição').forEach(t=>details.append(el('p',t)));
      if(card.confirmed_date)details.append(el('p','Mês e ano confirmados pelo usuário; não inferidos pelo mock.'));
      item.append(details);list.append(item);
      if(root.classList.contains('cards-showcase')){
        item.dataset.kind=card.kind;
        const eyebrow=el('div','','cards-card-eyebrow');eyebrow.append(el('span',card.kind==='event'?'EVENTO':'AÇÃO'),el('span',String(list.children.length).padStart(2,'0'),'cards-sequence'));item.prepend(eyebrow);
      }
    });
  }).catch(()=>{ /* Optional demonstration never blocks the operational dashboard. */ });
})();
