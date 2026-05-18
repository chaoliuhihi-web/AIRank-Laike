
(function(){
  const cfg = window.AIRANK_CONFIG || {};
  const header = document.querySelector('[data-header]');
  const menuButton = document.querySelector('.menu-button');
  const nav = document.getElementById('siteNav');
  const storageKey = 'airank_attribution';

  function emit(event, payload){
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push(Object.assign({ event }, payload || {}));
  }

  function setScrolled(){ header?.classList.toggle('is-scrolled', window.scrollY > 8); }
  setScrolled(); window.addEventListener('scroll', setScrolled, {passive:true});
  menuButton?.addEventListener('click', () => {
    const open = nav?.classList.toggle('is-open');
    menuButton.setAttribute('aria-expanded', open ? 'true':'false');
    document.body.classList.toggle('nav-open', !!open);
  });
  nav?.querySelectorAll('a').forEach(a => a.addEventListener('click', () => { nav.classList.remove('is-open'); menuButton?.setAttribute('aria-expanded','false'); document.body.classList.remove('nav-open'); }));

  function getAttribution(){
    const params = new URLSearchParams(location.search);
    const keys = ['utm_source','utm_medium','utm_campaign','utm_content','utm_term','gclid','bd_vid'];
    let saved = {};
    try { saved = JSON.parse(sessionStorage.getItem(storageKey) || '{}'); } catch(e) {}
    const current = { landingPage: location.pathname + location.search, referrer: document.referrer || saved.referrer || '' };
    keys.forEach(k => { if(params.get(k)) current[k] = params.get(k); });
    const merged = Object.assign({}, saved, current);
    try { sessionStorage.setItem(storageKey, JSON.stringify(merged)); } catch(e) {}
    return merged;
  }
  const attribution = getAttribution();

  const modal = document.getElementById('leadModal');
  const close = modal?.querySelector('.modal__close');
  function normalizeUrl(value){
    const v = (value || '').trim();
    if(!v) return v;
    return /^https?:\/\//i.test(v) ? v : 'https://' + v;
  }
  function getDiagnosisUrl(website, intent){
    const target = new URL(cfg.diagnosisPath || '/diagnosis/', window.location.origin);
    if(website) target.searchParams.set('website', website);
    if(intent) target.searchParams.set('intent', intent);
    return target.pathname + target.search + '#hero';
  }
  function prefillModal(data){
    if(!modal || !data) return;
    Object.entries(data).forEach(([name, value]) => {
      const input = modal.querySelector(`[name="${name}"]`);
      if(input && value) input.value = value;
    });
  }
  const openLead = (event, prefill) => {
    event?.preventDefault();
    prefillModal(prefill);
    modal?.classList.add('is-open'); modal?.setAttribute('aria-hidden','false');
    emit('lead_modal_open', { page: location.pathname });
    setTimeout(()=>modal?.querySelector('input')?.focus(), 30);
  };
  const closeLead = () => { modal?.classList.remove('is-open'); modal?.setAttribute('aria-hidden','true'); };
  document.addEventListener('click', e => {
    const trigger = e.target.closest?.('a[href="#lead"], .js-open-lead');
    if(trigger) openLead(e);
  });
  close?.addEventListener('click', closeLead);
  modal?.addEventListener('click', e => { if(e.target === modal) closeLead(); });
  document.addEventListener('keydown', e => { if(e.key === 'Escape') closeLead(); });

  const revealItems = document.querySelectorAll('.reveal, .reveal-group');
  if('IntersectionObserver' in window){
    const observer = new IntersectionObserver(entries => { entries.forEach(entry => { if(entry.isIntersecting){ entry.target.classList.add('is-visible'); observer.unobserve(entry.target); } }); }, {threshold:.12, rootMargin:'0px 0px -40px 0px'});
    revealItems.forEach(el => observer.observe(el));
  } else { revealItems.forEach(el => el.classList.add('is-visible')); }

  function serialize(form){ return Object.fromEntries(new FormData(form).entries()); }
  function addHoneyPot(form){
    if(form.querySelector('[name="airank_company_url"]')) return;
    const hp = document.createElement('input');
    hp.type = 'text'; hp.name = 'airank_company_url'; hp.tabIndex = -1; hp.autocomplete = 'off'; hp.setAttribute('aria-hidden','true'); hp.className = 'hp-field';
    form.appendChild(hp);
  }
  function prefillWebsiteFromQuery(){
    const params = new URLSearchParams(location.search);
    const website = normalizeUrl(params.get('website') || params.get('url') || '');
    if(!website) return;
    document.querySelectorAll('input[name="website"]').forEach(input => {
      if(!input.value) input.value = website;
    });
  }
  document.querySelectorAll('[data-lead-form]').forEach(form => {
    form.noValidate = true;
    addHoneyPot(form);
  });
  prefillWebsiteFromQuery();

  async function postJSON(endpoint, payload, signal){
    const res = await fetch(endpoint, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload), signal });
    if(!res.ok) throw Object.assign(new Error('request failed'), {status:res.status});
    return res.json().catch(() => ({}));
  }

  async function submitLead(form){
    const status = form.querySelector('.form-status');
    const submitBtn = form.querySelector('button[type="submit"]');
    const websiteInput = form.querySelector('input[name="website"]');
    if(websiteInput) websiteInput.value = normalizeUrl(websiteInput.value);

    if(!form.checkValidity()){ form.reportValidity(); return; }

    // Progressive CTA: collect website first, then continue on the diagnosis page.
    if(form.hasAttribute('data-progressive-form')){
      const data = serialize(form);
      emit('lead_progressive_start', { page: location.pathname, intent: form.dataset.leadIntent || 'quick-check' });
      status && (status.textContent = '正在进入免费体检页...');
      window.location.href = getDiagnosisUrl(data.website, form.dataset.leadIntent || 'quick-check');
      return;
    }

    const data = serialize(form);
    if(data.airank_company_url){
      status && (status.textContent = '提交成功，我们会尽快联系你。');
      return;
    }
    const payload = Object.assign({}, data, {
      intent: form.dataset.leadIntent || 'lead',
      page: location.pathname,
      pageTitle: document.title,
      submittedAt: new Date().toISOString(),
      attribution,
      viewport: `${window.innerWidth}x${window.innerHeight}`,
      consent: true
    });
    delete payload.airank_company_url;

    status && (status.textContent = '正在提交...');
    status?.classList.remove('error','success');
    submitBtn && (submitBtn.disabled = true);
    emit('lead_submit_start', { page: payload.page, intent: payload.intent });

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), cfg.requestTimeout || 10000);
    try{
      if(!cfg.leadEndpoint) throw new Error('lead endpoint is not configured');
      try {
        await postJSON(cfg.leadEndpoint, payload, controller.signal);
      } catch(primaryError) {
        if(cfg.leadFallbackEndpoint && primaryError.status === 404){
          await postJSON(cfg.leadFallbackEndpoint, payload, controller.signal);
        } else { throw primaryError; }
      }
      clearTimeout(timer);
      status?.classList.add('success');
      status && (status.textContent = '提交成功，我们会尽快联系你。');
      emit('lead_submit_success', { page: payload.page, intent: payload.intent });
      form.reset();
      if(cfg.enableRedirectAfterSubmit && cfg.successRedirect){
        setTimeout(() => { window.location.href = cfg.successRedirect; }, 450);
      }
    } catch(err){
      clearTimeout(timer);
      if(['localhost','127.0.0.1'].includes(location.hostname)){
        try {
          const cached = JSON.parse(localStorage.getItem('airank_local_leads') || '[]');
          cached.push(payload);
          localStorage.setItem('airank_local_leads', JSON.stringify(cached.slice(-20)));
        } catch(e) {}
        status?.classList.add('success');
        status && (status.textContent = '本地预览已模拟提交成功，正式上线会发送到线索接口。');
        emit('lead_submit_local_success', { page: payload.page, intent: payload.intent });
        form.reset();
        if(cfg.enableRedirectAfterSubmit && cfg.successRedirect){
          setTimeout(() => { window.location.href = cfg.successRedirect; }, 450);
        }
        return;
      }
      status?.classList.add('error');
      const phone = cfg.contactPhoneDisplay || '400-110-8776';
      status && (status.textContent = `提交失败，请稍后重试，或直接拨打 ${phone}。`);
      emit('lead_submit_error', { page: payload.page, intent: payload.intent, message: String(err && err.message || err) });
    } finally {
      submitBtn && (submitBtn.disabled = false);
    }
  }
  document.querySelectorAll('[data-lead-form]').forEach(form => form.addEventListener('submit', e => { e.preventDefault(); submitLead(form); }));

  function addHotspots(host, links){
    if(!host || host.querySelector('.slice-hotspots')) return;
    const layer = document.createElement('div');
    layer.className = 'slice-hotspots';
    layer.setAttribute('aria-label', '图片区域快捷入口');
    links.forEach(item => {
      const a = document.createElement('a');
      a.href = item.href || '#lead';
      a.title = item.label;
      a.setAttribute('aria-label', item.label);
      if(item.modal) a.className = 'js-open-lead';
      a.style.left = `${item.x}%`;
      a.style.top = `${item.y}%`;
      a.style.width = `${item.w}%`;
      a.style.height = `${item.h}%`;
      layer.appendChild(a);
    });
    host.appendChild(layer);
  }

  function enhanceClickableImageSections(){
    const page = document.body.dataset.page;
    if(page === 'resources'){
      addHotspots(document.querySelector('#featured .featured-resource'), [
        { label:'领取 AI 获客趋势报告', modal:true, x:0, y:0, w:100, h:100 }
      ]);
    }
    if(page === 'pricing'){
      addHotspots(document.querySelector('#plans .slice-frame--showcase'), [
        { label:'选择体验版', modal:true, x:4, y:7, w:28, h:45 },
        { label:'选择启动版', modal:true, x:36, y:5, w:28, h:48 },
        { label:'选择增长版', modal:true, x:68, y:7, w:28, h:45 },
        { label:'预约定价方案咨询', modal:true, x:34, y:83, w:32, h:8 }
      ]);
    }
    if(page === 'solutions'){
      addHotspots(document.querySelector('#knowledge-intensive .slice-frame--showcase'), [
        { label:'咨询知识密集型企业方案', modal:true, x:61, y:72, w:19, h:11 }
      ]);
      addHotspots(document.querySelector('#complex-sales .slice-frame--showcase'), [
        { label:'咨询复杂销售型企业方案', modal:true, x:14, y:72, w:19, h:12 }
      ]);
      addHotspots(document.querySelector('#content-assets .slice-frame--showcase'), [
        { label:'咨询内容资产型机构方案', modal:true, x:61, y:72, w:19, h:11 }
      ]);
    }
  }

  function enhanceResourceTabs(){
    const tabs = Array.from(document.querySelectorAll('body[data-page="resources"] .search-section .tabs a'));
    if(!tabs.length) return;
    const targets = ['articles','articles','articles','downloads','downloads','articles','learning','downloads'];
    tabs.forEach((tab, index) => {
      tab.href = `#${targets[index] || 'articles'}`;
      tab.addEventListener('click', e => {
        e.preventDefault();
        tabs.forEach(item => item.classList.remove('is-active'));
        tab.classList.add('is-active');
        document.getElementById(targets[index] || 'articles')?.scrollIntoView({ behavior:'smooth', block:'start' });
      });
    });
    const form = document.querySelector('body[data-page="resources"] .search-box');
    const input = form?.querySelector('input');
    form?.addEventListener('submit', e => {
      e.preventDefault();
      document.getElementById('articles')?.scrollIntoView({ behavior:'smooth', block:'start' });
      input?.focus();
    });
    form?.querySelector('button')?.addEventListener('click', () => form.requestSubmit());
  }

  enhanceClickableImageSections();
  enhanceResourceTabs();
})();
