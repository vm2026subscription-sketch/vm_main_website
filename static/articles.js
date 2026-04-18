/* ================================================
   Career Articles — articlepage.js
   ================================================ */
(function () {
  'use strict';

  // ── refs ────────────────────────────────────────
  const grid       = document.getElementById('card-grid');
  const cards      = Array.from(grid.querySelectorAll('.card'));
  const searchEl   = document.getElementById('search-input');
  const searchBtn  = document.getElementById('search-btn');
  const clearBtn   = document.getElementById('search-clear');
  const pills      = Array.from(document.querySelectorAll('.cat-pill'));
  const metaLine   = document.getElementById('meta-line');
  const emptyState = document.getElementById('empty');
  const modalWrap  = document.getElementById('modal-wrap');
  const modalArt   = document.getElementById('modal-article');
  const totalCount = Number(metaLine?.dataset?.total || cards.length);

  let activeCat   = 'all';
  let searchQuery = '';

  function setAllCategoryActive() {
    activeCat = 'all';
    pills.forEach(p => p.classList.toggle('active', p.dataset.cat === 'all'));
  }

  function runSearch(forceAllCategories) {
    searchQuery = (searchEl.value || '').trim().toLowerCase();
    clearBtn.classList.toggle('visible', searchQuery.length > 0);
    if (forceAllCategories) setAllCategoryActive();
    applyFilters();
  }

  // ── filter engine ────────────────────────────────
  function applyFilters() {
    let visible = 0;
    cards.forEach((card, idx) => {
      const cat   = card.dataset.cat   || '';
      const title = card.dataset.title || '';
      const desc  = card.dataset.desc  || '';
      const matchCat    = activeCat === 'all' || cat === activeCat;
      const matchSearch = !searchQuery ||
        title.includes(searchQuery) || desc.includes(searchQuery) ||
        cat.includes(searchQuery);

      const show = matchCat && matchSearch;
      card.hidden = !show;
      if (show) {
        // re-trigger entry animation
        card.style.setProperty('--i', visible);
        card.style.animation = 'none';
        void card.offsetWidth;
        card.style.animation = '';
        visible++;
      }
    });

    emptyState.hidden = visible > 0;
    metaLine.textContent = visible === 0
      ? 'No matching articles found.'
      : `Showing ${visible} of ${totalCount} article${visible !== 1 ? 's' : ''}`;

    // sync URL
    const url = new URL(window.location);
    activeCat !== 'all'
      ? url.searchParams.set('category', activeCat)
      : url.searchParams.delete('category');
    searchQuery
      ? url.searchParams.set('q', searchQuery)
      : url.searchParams.delete('q');
    history.replaceState(null, '', url);
  }

  // ── category pills ───────────────────────────────
  pills.forEach(pill => {
    pill.addEventListener('click', () => {
      pills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      activeCat = pill.dataset.cat;
      applyFilters();
    });
  });

  // ── search ───────────────────────────────────────
  let timer;
  searchEl.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      runSearch(true);
    }, 160);
  });

  searchEl.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      e.preventDefault();
      clearTimeout(timer);
      runSearch(true);
    }
  });

  if (searchBtn) {
    searchBtn.addEventListener('click', () => {
      clearTimeout(timer);
      runSearch(true);
    });
  }

  clearBtn.addEventListener('click', () => {
    searchEl.value  = '';
    searchQuery     = '';
    clearBtn.classList.remove('visible');
    applyFilters();
    searchEl.focus();
  });

  // ── reset all ────────────────────────────────────
  window.resetAll = function () {
    searchEl.value = '';
    searchQuery    = '';
    activeCat      = 'all';
    clearBtn.classList.remove('visible');
    pills.forEach(p => p.classList.toggle('active', p.dataset.cat === 'all'));
    applyFilters();
  };

  // ── init from URL params (Flask passes via template,
  //    but also re-init in JS so page is consistent) ──
  (function init() {
    const params = new URLSearchParams(window.location.search);
    const cat = params.get('category') || 'all';
    const q   = params.get('q')        || '';
    if (cat !== 'all') {
      activeCat = cat;
      pills.forEach(p => p.classList.toggle('active', p.dataset.cat === cat));
    }
    if (q) {
      searchQuery     = q.toLowerCase();
      searchEl.value  = q;
      clearBtn.classList.add('visible');
    }
    applyFilters();
  })();

  // ── modal ────────────────────────────────────────
  window.openModal = function (btn) {
    const title = btn.dataset.title || '';
    modalArt.textContent = title ? `Enquiry about: ${title}` : '';
    // clear previous inputs
    ['f-name','f-email','f-phone','f-msg'].forEach(id => {
      const el = document.getElementById(id);
      if (el) { el.value = ''; el.classList.remove('error'); }
    });
    const submitBtn = document.getElementById('modal-submit');
    submitBtn.textContent = 'Send Message';
    submitBtn.disabled    = false;
    submitBtn.classList.remove('success');
    modalWrap.classList.add('open');
    modalWrap.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  };

  window.closeModal = function () {
    modalWrap.classList.remove('open');
    modalWrap.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  };

  modalWrap.addEventListener('click', e => {
    if (e.target === modalWrap) closeModal();
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && modalWrap.classList.contains('open')) closeModal();
  });

  window.submitModal = function () {
    const fields = [
      { id: 'f-name',  check: v => v.trim().length > 1 },
      { id: 'f-email', check: v => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) },
      { id: 'f-phone', check: v => v.trim().length > 5 },
      { id: 'f-msg',   check: v => v.trim().length > 2 },
    ];

    let valid = true;
    fields.forEach(f => {
      const el = document.getElementById(f.id);
      const ok = f.check(el.value);
      el.classList.toggle('error', !ok);
      if (!ok) valid = false;
    });
    if (!valid) return;

    const btn = document.getElementById('modal-submit');
    btn.disabled    = true;
    btn.textContent = 'Sending…';

    // simulate async submit
    setTimeout(() => {
      btn.textContent = '✓ Message Sent!';
      btn.classList.add('success');
      setTimeout(closeModal, 1600);
    }, 900);
  };

})();
