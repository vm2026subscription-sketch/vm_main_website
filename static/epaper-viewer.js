/* ══════════════════════════════════════════════════
   Vidyarthi Mitra E-Paper Viewer JS
   ══════════════════════════════════════════════════ */

const EP = {
  // State
  currentDate: null,
  currentPage: 1,
  totalPages: 1,
  zoom: 1,
  minZoom: 1,
  maxZoom: 3,
  isDragging: false,
  dragStart: { x: 0, y: 0 },
  panOffset: { x: 0, y: 0 },
  editions: [],
  pages: [],
  articles: [],
  currentEdition: null,
  currentLanguage: '',
  mastheadUrl: '',
  ttsUtterance: null,
  ttsPlaying: false,

  footerLinksDefault: [
    { key: 'search',    icon: 'fa fa-magnifying-glass', url: '/epaper' },
    { key: 'whatsapp',  icon: 'fab fa-whatsapp',        url: 'https://wa.me/?text=Vidyarthi%20Mitra%20E-Paper' },
    { key: 'facebook',  icon: 'fab fa-facebook-f',      url: 'https://www.facebook.com/' },
    { key: 'x',         icon: 'fab fa-x-twitter',       url: 'https://x.com/' },
  ],

  // DOM refs
  el: {},

  init() {
    this.cacheDOM();
    this.bindEvents();
    this.renderFooterLinks(this.footerLinksDefault);
    // Load the latest published edition automatically instead of defaulting to today
    this.loadLatestEdition();
    // Load editions list for calendar in background
    this.loadEditions();
    // Poll for new editions every 5 minutes
    this.startAutoRefreshPoll();
    // Load news sidebar
    this.loadNewsSidebar();
  },

  async loadLatestEdition() {
    try {
      const _initEl = document.getElementById('__epInitialEdition__');
      const data = _initEl
        ? JSON.parse(_initEl.textContent)
        : await this._cachedFetch('/api/epaper/latest');
      const d = data.date ? new Date(data.date + 'T00:00:00') : new Date();
      this.currentDate = d;
      if (this.el.dateBtnText) {
        const opts = { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' };
        this.el.dateBtnText.textContent = d.toLocaleDateString('hi-IN', opts);
      }
      this.currentPage = 1;
      this.currentEdition = data;
      this.currentLanguage = data.language || 'Hindi';
      this.pages = data.pages || [];
      this.totalPages = this.pages.length || 1;
      this.mastheadUrl = data.masthead_image_url || '';
      this.updateEditionBrand(data);
      this.applyMastheadImage(this.mastheadUrl);
      this.renderFooterLinks(data.footer_links || this.footerLinksDefault);
      document.getElementById('epEmptyState')?.style.setProperty('display', 'none');
      this.fetchAndRenderLanguageTabs(data.date);
      this.renderThumbnails();
      this.showPage(1);
    } catch (e) {
      // No published editions — show empty state
      this.setDate(new Date());
    }
  },

  // ── Auto-refresh poll ──────────────────────────────
  startAutoRefreshPoll() {
    const POLL_MS = 5 * 60 * 1000; // every 5 minutes
    setInterval(async () => {
      try {
        // Bypass cache with timestamp so we always get fresh data
        const res = await fetch('/api/epaper/latest?_t=' + Date.now());
        if (!res.ok) return;
        const data = await res.json();
        if (!data.date) return;
        const currentISO = this.currentDate ? this.formatDateISO(this.currentDate) : '';
        if (data.date > currentISO) {
          this._showNewEditionBanner(data);
        }
      } catch (e) { /* silently ignore network errors */ }
    }, POLL_MS);
  },

  _showNewEditionBanner(data) {
    if (document.getElementById('epNewEditionBanner')) return;
    const banner = document.createElement('div');
    banner.id = 'epNewEditionBanner';
    banner.className = 'ep-new-edition-banner';
    const icon = document.createElement('span');
    icon.className = 'ep-neb-icon'; icon.textContent = '📰';
    const text = document.createElement('span');
    text.className = 'ep-neb-text'; text.textContent = 'New edition available: ';
    const strong = document.createElement('strong');
    strong.textContent = data.name || data.date;
    text.appendChild(strong);
    const loadBtn = document.createElement('button');
    loadBtn.className = 'ep-neb-load'; loadBtn.textContent = 'Load Now';
    loadBtn.onclick = () => EP._loadNewEdition(data.date);
    const closeBtn = document.createElement('button');
    closeBtn.className = 'ep-neb-close'; closeBtn.textContent = '✕';
    closeBtn.onclick = () => banner.remove();
    banner.append(icon, text, loadBtn, closeBtn);
    document.body.appendChild(banner);
  },

  _loadNewEdition(date) {
    document.getElementById('epNewEditionBanner')?.remove();
    this.setDate(new Date(date + 'T00:00:00'));
  },

  // API response cache (5-minute TTL)
  _apiCache: {},
  _cacheTTL: 5 * 60 * 1000,
  async _cachedFetch(url) {
    const now = Date.now();
    const cached = this._apiCache[url];
    if (cached && (now - cached.ts) < this._cacheTTL) {
      return cached.data;
    }
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    this._apiCache[url] = { data, ts: now };
    return data;
  },

  // Optimize Cloudinary image URLs: auto format, auto quality, resize width
  optimizeCloudinaryUrl(url, width = 400) {
    if (!url || typeof url !== 'string') return url;
    // Only transform Cloudinary URLs (res.cloudinary.com)
    if (!url.includes('res.cloudinary.com')) return url;
    // Avoid double-transforming (if /upload/f_auto already present)
    if (url.includes('/f_auto')) return url;
    // Insert transforms after /upload/ — f_auto picks WebP/AVIF, q_auto adjusts quality
    return url.replace('/upload/', `/upload/f_auto,q_auto,w_${width},c_limit/`);
  },

  cacheDOM() {
    this.el = {
      header: document.getElementById('epHeader'),
      collapseBtn: document.getElementById('epCollapseBtn'),
      nav: document.getElementById('epNav'),
      navList: document.getElementById('epNavList'),
      main: document.getElementById('epMain'),
      viewer: document.getElementById('epViewer'),
      pageContainer: document.getElementById('epPageContainer'),
      pageImg: document.getElementById('epPageImg'),
      hotspotsLayer: document.getElementById('epHotspots'),
      editionName: document.getElementById('epEditionName'),
      editionMeta: document.getElementById('epEditionMeta'),
      dateBtn: document.getElementById('epDateBtn'),
      dateBtnText: document.getElementById('epDateText'),
      calendarOverlay: document.getElementById('epCalendarOverlay'),
      calGrid: document.getElementById('epCalGrid'),
      calTitle: document.getElementById('epCalTitle'),
      prevPage: document.getElementById('epPrevPage'),
      nextPage: document.getElementById('epNextPage'),
      pageInfo: document.getElementById('epPageInfo'),
      zoomIn: document.getElementById('epZoomIn'),
      zoomOut: document.getElementById('epZoomOut'),
      fitPage: document.getElementById('epFitPage'),
      fullscreen: document.getElementById('epFullscreen'),
      articlePanel: document.getElementById('epArticlePanel'),
      articleCategory: document.getElementById('epArtCategory'),
      articleTitle: document.getElementById('epArtTitle'),
      articleDate: document.getElementById('epArtDate'),
      articleImg: document.getElementById('epArtImg'),
      articleText: document.getElementById('epArtText'),
      articleBack: document.getElementById('epArtBack'),
      aiTabs: document.querySelectorAll('.ep-ai-tab'),
      aiContents: document.querySelectorAll('.ep-ai-content'),
      // Voice bar elements
      voiceBar: document.getElementById('epVoiceBar'),
      voicePlayBtn: document.getElementById('epVoicePlayBtn'),
      voicePlayIcon: document.getElementById('epVoicePlayIcon'),
      voiceProgressBg: document.getElementById('epVoiceProgressBg'),
      voiceProgressFill: document.getElementById('epVoiceProgressFill'),
      voiceElapsed: document.getElementById('epVoiceElapsed'),
      voiceRemaining: document.getElementById('epVoiceRemaining'),
      voiceTitle: document.getElementById('epVoiceTitle'),
      voiceSpeedBtn: document.getElementById('epVoiceSpeedBtn'),
      voiceCloseBtn: document.getElementById('epVoiceCloseBtn'),
      voiceBack: document.getElementById('epVoiceBack'),
      voiceForward: document.getElementById('epVoiceForward'),
      voiceDuration: document.getElementById('epVoiceDuration'),
      voiceVolBtn: document.getElementById('epVoiceVolBtn'),
      artBackFromPlayer: document.getElementById('epArtBackFromPlayer'),
      voiceSelect: document.getElementById('epVoiceSelect'),
      ttsStartBtn: document.getElementById('epTtsStartBtn'),
      ttsEstimate: document.getElementById('epTtsEstimate'),
      ttsPrompt: document.getElementById('epTtsPrompt'),
      readingTime: document.getElementById('epReadingTime'),
      readTimeText: document.getElementById('epReadTimeText'),
      translateSelect: document.getElementById('epTranslateSelect'),
      translateOutput: document.getElementById('epTranslateOutput'),
      summaryOutput: document.getElementById('epSummaryOutput'),
      toast: document.getElementById('epToast'),
      // Thumbnail strip
      thumbStrip: document.getElementById('epThumbStrip'),
      thumbScroll: document.getElementById('epThumbScroll'),
      thumbToggle: document.getElementById('epThumbToggle'),
      thumbLeft: document.getElementById('epThumbLeft'),
      thumbRight: document.getElementById('epThumbRight'),
      // Edge arrows
      edgePrev: document.getElementById('epEdgePrev'),
      edgeNext: document.getElementById('epEdgeNext'),
      // Scroll buttons
      scrollUp: document.getElementById('epScrollUp'),
      scrollDown: document.getElementById('epScrollDown'),
      // Masthead
      mastheadImg: document.getElementById('epMastheadImg'),
      // Footer links
      footerLinks: document.getElementById('epFooterLinks'),
    };
  },

  bindEvents() {
    // Header collapse
    this.el.collapseBtn?.addEventListener('click', () => this.toggleHeader());

    // Date picker
    this.el.dateBtn?.addEventListener('click', () => this.toggleCalendar());
    this.el.calendarOverlay?.addEventListener('click', (e) => {
      if (e.target === this.el.calendarOverlay) this.toggleCalendar(false);
    });

    // Page nav
    this.el.prevPage?.addEventListener('click', () => this.changePage(-1));
    this.el.nextPage?.addEventListener('click', () => this.changePage(1));

    // Edge page arrows
    this.el.edgePrev?.addEventListener('click', () => this.changePage(-1));
    this.el.edgeNext?.addEventListener('click', () => this.changePage(1));

    // Side nav click zones
    document.getElementById('epSideNavLeft')?.addEventListener('click', () => this.changePage(-1));
    document.getElementById('epSideNavRight')?.addEventListener('click', () => this.changePage(1));

    // Zoom
    this.el.zoomIn?.addEventListener('click', () => this.setZoom(this.zoom + 0.25));
    this.el.zoomOut?.addEventListener('click', () => this.setZoom(this.zoom - 0.25));
    this.el.fitPage?.addEventListener('click', () => this.setZoom(1));
    this.el.fullscreen?.addEventListener('click', () => this.toggleFullscreen());

    // Scroll buttons — scroll amount scales with zoom level
    this.el.scrollUp?.addEventListener('click', () => {
      const viewer = this.el.viewer;
      if (viewer) viewer.scrollBy({ top: -(250 * this.zoom), behavior: 'smooth' });
    });
    this.el.scrollDown?.addEventListener('click', () => {
      const viewer = this.el.viewer;
      if (viewer) viewer.scrollBy({ top: 250 * this.zoom, behavior: 'smooth' });
    });

    // Thumbnail strip
    this.el.thumbToggle?.addEventListener('click', () => this.toggleThumbStrip());
    this.el.thumbLeft?.addEventListener('click', () => {
      this.el.thumbScroll?.scrollBy({ left: -200, behavior: 'smooth' });
    });
    this.el.thumbRight?.addEventListener('click', () => {
      this.el.thumbScroll?.scrollBy({ left: 200, behavior: 'smooth' });
    });

    // Fullscreen change listener
    document.addEventListener('fullscreenchange', () => {
      if (!document.fullscreenElement) {
        document.body.classList.remove('ep-fullscreen');
      }
    });

    // Viewer wheel zoom (Ctrl+scroll) + normal scroll passthrough
    const v = this.el.viewer;
    if (v) {
      v.addEventListener('wheel', (e) => {
        if (e.ctrlKey || e.metaKey) {
          e.preventDefault();
          const delta = e.deltaY < 0 ? 0.1 : -0.1;
          this.setZoom(this.zoom + delta);
        }
      }, { passive: false });

      // Pinch-to-zoom on touch
      let _lastDist = null;
      v.addEventListener('touchstart', (e) => {
        if (e.touches.length === 2) {
          const dx = e.touches[0].clientX - e.touches[1].clientX;
          const dy = e.touches[0].clientY - e.touches[1].clientY;
          _lastDist = Math.hypot(dx, dy);
        }
      }, { passive: true });
      v.addEventListener('touchmove', (e) => {
        if (e.touches.length === 2 && _lastDist !== null) {
          const dx = e.touches[0].clientX - e.touches[1].clientX;
          const dy = e.touches[0].clientY - e.touches[1].clientY;
          const dist = Math.hypot(dx, dy);
          this.setZoom(this.zoom * (dist / _lastDist));
          _lastDist = dist;
        }
      }, { passive: true });
      v.addEventListener('touchend', () => { _lastDist = null; }, { passive: true });
    }

    // Article panel back
    this.el.articleBack?.addEventListener('click', () => this.closeArticle());

    // AI tabs
    this.el.aiTabs?.forEach(tab => {
      tab.addEventListener('click', () => this.switchAiTab(tab.dataset.tab));
    });

 // TTS / Voice Player
    this.el.ttsStartBtn?.addEventListener('click', () => this.voicePlay());
    this.el.voiceVolBtn?.addEventListener('click', () => this.voiceToggleMute());
    this.el.artBackFromPlayer?.addEventListener('click', () => this.closeArticle());
    this.el.voicePlayBtn?.addEventListener('click', () => this.voiceToggle());
    this.el.voiceSpeedBtn?.addEventListener('click', () => this.voiceCycleSpeed());
    this.el.voiceCloseBtn?.addEventListener('click', () => this.voiceStop());
    this.el.voiceBack?.addEventListener('click', () => this.voiceSkip(-10));
    this.el.voiceForward?.addEventListener('click', () => this.voiceSkip(10));

    // Seekable progress bar — click to jump
    this.el.voiceProgressBg?.addEventListener('click', (e) => {
      const audio = this._voice.audio;
      if (!audio || !audio.duration) return;
      const rect = this.el.voiceProgressBg.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      audio.currentTime = pct * audio.duration;
      this._voiceUpdateUI();
    });

    // Voice selector — set voice, translate visible article text,
    // and if audio is playing regenerate audio in new language
    this.el.voiceSelect?.addEventListener('change', async () => {
      const val = this.el.voiceSelect.value;
      this._voice.selectedVoice = val;
      await this._translatePanelForVoice(val);
      // If already playing or paused, restart playback with new language
      if (this._voice.playing || this._voice.paused) {
        try { await this.voicePlay(); } catch (e) { /* swallow */ }
      }
    });

    // Translate
    this.el.translateSelect?.addEventListener('change', () => this.translateArticle());

    // Keyboard
    document.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft') this.changePage(-1);
      if (e.key === 'ArrowRight') this.changePage(1);
      if (e.key === 'Escape') this.closeArticle();
      if (e.key === ' ' || e.key === 'Spacebar') {
        const tag = document.activeElement?.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || document.activeElement?.isContentEditable) return;
        if (this.currentArticle && (this._voice.playing || this._voice.paused || this._voice.loading)) {
          e.preventDefault();
          this.voiceToggle();
        }
      }
      if (e.key === '+' || e.key === '=') this.setZoom(this.zoom + 0.25);
      if (e.key === '-') this.setZoom(this.zoom - 0.25);
    });

    // Category nav scroll
    document.getElementById('epNavLeft')?.addEventListener('click', () => {
      this.el.navList.scrollBy({ left: -200, behavior: 'smooth' });
    });
    document.getElementById('epNavRight')?.addEventListener('click', () => {
      this.el.navList.scrollBy({ left: 200, behavior: 'smooth' });
    });

    // Calendar nav
    document.getElementById('epCalPrev')?.addEventListener('click', () => this.calendarNav(-1));
    document.getElementById('epCalNext')?.addEventListener('click', () => this.calendarNav(1));
  },

  // ── Header ──
  toggleHeader() {
    const hidden = this.el.header.classList.toggle('collapsed');
    this.el.collapseBtn.classList.toggle('header-hidden', hidden);
    this.el.nav.classList.toggle('header-hidden', hidden);
    this.el.main.classList.toggle('header-hidden', hidden);
    this.el.collapseBtn.innerHTML = hidden
      ? '<i class="fa fa-chevron-down"></i>'
      : '<i class="fa fa-chevron-up"></i>';
  },

  // ── Date ──
  setDate(d) {
    this.currentDate = d;
    const opts = { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' };
    if (this.el.dateBtnText) {
      this.el.dateBtnText.textContent = d.toLocaleDateString('hi-IN', opts);
    }
    this.currentPage = 1;
    // Clear API cache when switching dates so fresh data loads
    const iso = this.formatDateISO(d);
    delete this._apiCache[`/api/epaper/edition/${iso}`];
    delete this._apiCache['/api/epaper/editions'];
    this.loadEditionForDate(d);
  },

  updateEditionBrand(edition = null) {
    const name = edition?.name?.trim() || 'e-Paper';
    const language = edition?.language?.trim() || 'Vidyarthi Mitra';
    const dateText = edition?.date ? edition.date : '';

    if (this.el.editionName) this.el.editionName.textContent = name;
    if (this.el.editionMeta) {
      this.el.editionMeta.textContent = dateText ? `${language} • ${dateText}` : language;
    }
    document.title = edition?.name?.trim()
      ? `${edition.name} | Vidyarthi Mitra E-Paper`
      : 'Vidyarthi Mitra — E-Paper Reader';
  },

  applyMastheadImage(url) {
    if (!this.el.mastheadImg) return;
    const existing = this.el.mastheadImg.querySelector('img');
    if (url) {
      let img = existing;
      if (!img) {
        img = document.createElement('img');
        img.alt = 'E-Paper Header';
        this.el.mastheadImg.innerHTML = '';
        this.el.mastheadImg.appendChild(img);
      }
      img.src = url;
      document.body.classList.add('has-masthead');
    } else {
      this.el.mastheadImg.innerHTML = '<span class="ep-masthead-placeholder">Header image</span>';
      document.body.classList.remove('has-masthead');
    }
  },

  updatePageHeader(page, pageNum) {
    const el = this.el.mastheadImg;
    if (!el) return;
    const masthead = el.closest('.ep-masthead') || el.parentElement;
    const viewer = this.el.viewer || document.getElementById('epViewer');
    const grid = document.getElementById('epBlockGrid');
    if (pageNum === 1) {
      el.style.cssText = '';
      if (masthead) masthead.style.cssText = '';
      if (viewer) viewer.style.paddingTop = '';
      if (grid) grid.style.marginTop = '';
      this.applyMastheadImage(this.mastheadUrl || '');
      return;
    }
    // Page 2+: collapse all spacing so section header sits flush above content
    if (masthead) masthead.style.cssText = 'padding:0;border-bottom:none;';
    if (viewer) viewer.style.paddingTop = '0';
    if (grid) grid.style.marginTop = '0';
    const num = String(pageNum).padStart(2, '0');
    const cat = (page.category || '').toUpperCase();
    const dateRange = page.date_range || '';
    el.style.cssText = 'border:none;border-radius:0;background:#fff;padding:0;height:72px;';
    el.innerHTML = `
      <div style="border-top:2px dotted #d9252a;border-bottom:2px dotted #d9252a;padding:6px 14px;display:flex;align-items:center;justify-content:space-between;background:#fff;width:100%;height:100%;box-sizing:border-box;">
        <div style="display:flex;align-items:center;gap:14px;">
          <span style="font-size:26px;font-weight:800;color:#d9252a;line-height:1;font-family:Georgia,serif;">${num}</span>
          <span style="font-size:14px;font-weight:800;color:#d9252a;border-left:3px solid #d9252a;padding-left:12px;font-family:Georgia,serif;letter-spacing:.5px;">${cat}</span>
        </div>
        <div style="text-align:right;flex-shrink:0;">
          ${dateRange ? `<div style="font-size:10px;font-weight:600;color:#374151;margin-bottom:2px;">${dateRange}</div>` : ''}
          <div style="font-size:11px;font-weight:800;color:#d9252a;">Vidyarthi Mitra</div>
        </div>
      </div>`;
    document.body.classList.add('has-masthead');
  },

  resolveFooterLinks(rawLinks) {
    const base = this.footerLinksDefault.map(item => ({ ...item }));
    if (!Array.isArray(rawLinks)) return base;
    rawLinks.forEach(item => {
      const key = item?.key || '';
      const target = base.find(link => link.key === key);
      if (target) {
        if (item.url)  target.url  = item.url;
        if (item.icon) target.icon = item.icon;
      } else if (item?.url) {
        base.push({ key: key || 'link', url: item.url, icon: item.icon || 'fa fa-link' });
      }
    });
    return base;
  },

  renderFooterLinks(rawLinks) {
    if (!this.el.footerLinks) return;
    const links = this.resolveFooterLinks(rawLinks);
    this.el.footerLinks.innerHTML = links.map(item => {
      const href  = item.url  || '#';
      const label = item.key  || 'link';
      return `<a class="ep-footer-link" href="${href}" target="_blank" rel="noopener" aria-label="${label}"><i class="${item.icon}"></i></a>`;
    }).join('');
  },

  formatDateISO(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  },

  // ── Calendar ──
  calendarMonth: null,
  calendarYear: null,

  toggleCalendar(show) {
    const overlay = this.el.calendarOverlay;
    if (!overlay) return;
    const isOpen = overlay.classList.contains('open');
    if (show === false || (show === undefined && isOpen)) {
      overlay.classList.remove('open');
    } else {
      this.calendarMonth = this.currentDate.getMonth();
      this.calendarYear = this.currentDate.getFullYear();
      this.renderCalendar();
      overlay.classList.add('open');
    }
  },

  calendarNav(dir) {
    this.calendarMonth += dir;
    if (this.calendarMonth < 0) { this.calendarMonth = 11; this.calendarYear--; }
    if (this.calendarMonth > 11) { this.calendarMonth = 0; this.calendarYear++; }
    this.renderCalendar();
  },

  renderCalendar() {
    const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    if (this.el.calTitle) this.el.calTitle.textContent = `${months[this.calendarMonth]} ${this.calendarYear}`;

    const grid = this.el.calGrid;
    if (!grid) return;
    grid.innerHTML = '';

    const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    dayNames.forEach(d => {
      const el = document.createElement('div');
      el.className = 'ep-cal-day-name';
      el.textContent = d;
      grid.appendChild(el);
    });

    const firstDay = new Date(this.calendarYear, this.calendarMonth, 1).getDay();
    const daysInMonth = new Date(this.calendarYear, this.calendarMonth + 1, 0).getDate();
    const today = new Date();

    for (let i = 0; i < firstDay; i++) {
      const el = document.createElement('div');
      grid.appendChild(el);
    }

    for (let day = 1; day <= daysInMonth; day++) {
      const el = document.createElement('div');
      el.className = 'ep-cal-day';
      el.textContent = day;

      const d = new Date(this.calendarYear, this.calendarMonth, day);
      if (d > today) el.classList.add('disabled');
      if (d.toDateString() === today.toDateString()) el.classList.add('today');
      if (d.toDateString() === this.currentDate.toDateString()) el.classList.add('selected');

      // Check if edition exists
      const iso = this.formatDateISO(d);
      if (this.editions.some(e => e.date === iso)) el.classList.add('has-edition');

      if (!el.classList.contains('disabled')) {
        el.addEventListener('click', () => {
          this.setDate(new Date(this.calendarYear, this.calendarMonth, day));
          this.toggleCalendar(false);
        });
      }
      grid.appendChild(el);
    }
  },

  // ── Data Loading ──
  async loadEditions() {
    try {
      const data = await this._cachedFetch('/api/epaper/editions');
      this.editions = Array.isArray(data) ? data : (data.editions || data.results || []);
    } catch (e) { console.warn('Could not load editions:', e); }
  },

  async loadEditionForDate(d) {
    const iso = this.formatDateISO(d);

    // Show loading skeleton immediately
    this.showLoadingSkeleton();

    try {
      const data = await this._cachedFetch(`/api/epaper/edition/${iso}`);
      this.currentEdition = data;
      this.currentLanguage = data.language || 'Hindi';
      this.pages = data.pages || [];
      this.totalPages = this.pages.length || 1;
      this.mastheadUrl = data.masthead_image_url || '';
      this.updateEditionBrand(data);
      this.applyMastheadImage(this.mastheadUrl);
      this.renderFooterLinks(data.footer_links || this.footerLinksDefault);
      document.getElementById('epEmptyState')?.style.setProperty('display', 'none');
      this.fetchAndRenderLanguageTabs(data.date);
      this.renderThumbnails();
      this.showPage(1);
    } catch (e) {
      console.warn('Edition load error:', e);
      this.showDemoPage();
    }
  },

  showLoadingSkeleton() {
    const viewer = this.el.viewer || document.getElementById('epViewer');
    if (!viewer) return;

    // Remove existing block grid to show skeleton
    let grid = document.getElementById('epBlockGrid');
    if (!grid) {
      grid = document.createElement('div');
      grid.id = 'epBlockGrid';
      grid.className = 'ep-block-grid';
      viewer.appendChild(grid);
    }
    grid.style.display = 'block';
    if (this.el.pageContainer) this.el.pageContainer.style.display = 'none';

    grid.innerHTML = `
      <div class="ep-canvas-viewer" style="position:relative;width:100%;padding-bottom:141.25%;">
        <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;">
          <div style="text-align:center;">
            <div style="width:48px;height:48px;border:3px solid #e0e0e0;border-top:3px solid #e41e26;border-radius:50%;animation:epSpin .8s linear infinite;margin:0 auto 16px;"></div>
            <p style="color:#6b7280;font-size:14px;font-weight:500;">Loading edition...</p>
          </div>
        </div>
      </div>
    `;
  },

  showDemoPage() {
    this.currentEdition = null;
    this.totalPages = 1;
    this.pages = [];
    this.updateEditionBrand(null);
    this.applyMastheadImage('');
    this.renderFooterLinks(this.footerLinksDefault);
    if (this.el.pageImg) {
      this.el.pageImg.src = '';
      this.el.pageImg.alt = 'No edition available';
    }
    if (this.el.hotspotsLayer) this.el.hotspotsLayer.innerHTML = '';
    const grid = document.getElementById('epBlockGrid');
    if (grid) grid.style.display = 'none';
    if (this.el.pageContainer) this.el.pageContainer.style.display = 'none';
    document.getElementById('epEmptyState')?.style.setProperty('display', 'block');
    this.updatePager();
    this.showToast('इस तारीख का संस्करण उपलब्ध नहीं है');
  },

  // ── Language Tabs ──
  async fetchAndRenderLanguageTabs(date) {
    if (!this.el.navList) return;
    try {
      const data = await this._cachedFetch(`/api/epaper/editions-by-date/${date}`);
      this.renderLanguageTabs(data.editions || []);
    } catch (e) {
      this.renderLanguageTabs([]);
    }
  },

  renderLanguageTabs(editions) {
    if (!this.el.navList) return;
    if (!editions.length) {
      this.el.navList.innerHTML = '';
      return;
    }
    this.el.navList.innerHTML = editions.map(ed =>
      `<a class="ep-nav-item ${ed.language === this.currentLanguage ? 'active' : ''}" data-lang="${ed.language}">${ed.language}</a>`
    ).join('');
    this.el.navList.querySelectorAll('.ep-nav-item').forEach(item => {
      item.addEventListener('click', async (e) => {
        e.preventDefault();
        const lang = item.dataset.lang;
        if (lang === this.currentLanguage) return;
        this.el.navList.querySelectorAll('.ep-nav-item').forEach(n => n.classList.remove('active'));
        item.classList.add('active');
        await this.loadEditionForLanguage(lang);
      });
    });
  },

  async loadEditionForLanguage(lang) {
    if (!this.currentEdition) return;
    const date = this.currentEdition.date;
    // Bypass cache so unpublished state is always fresh
    const url = `/api/epaper/edition/${date}?lang=${encodeURIComponent(lang)}`;
    delete this._apiCache[url];
    this.showLoadingSkeleton();
    try {
      const data = await fetch(url).then(r => r.json());
      this.currentEdition = data;
      this.currentLanguage = data.language || lang;
      this.pages = data.pages || [];
      this.totalPages = this.pages.length || 1;
      this.mastheadUrl = data.masthead_image_url || '';
      this.updateEditionBrand(data);
      this.applyMastheadImage(this.mastheadUrl);
      this.renderFooterLinks(data.footer_links || this.footerLinksDefault);
      document.getElementById('epEmptyState')?.style.setProperty('display', 'none');
      // Update active tab
      this.el.navList?.querySelectorAll('.ep-nav-item').forEach(n => {
        n.classList.toggle('active', n.dataset.lang === this.currentLanguage);
      });
      this.renderThumbnails();
      this.showPage(1);
    } catch (e) {
      this.showToast('Edition not available');
    }
  },

  // ── Page Display ──
  showPage(num) {
    this.currentPage = Math.max(1, Math.min(num, this.totalPages));
    this.setZoom(1);
    this.panOffset = { x: 0, y: 0 };
    this.applyTransform();
    this.updatePager();

     const page = this.pages[this.currentPage - 1];
    if (!page) return;

    this.updatePageHeader(page, this.currentPage);

    const viewer = this.el.viewer || document.getElementById('epViewer');
    document.getElementById('epEmptyState')?.style.setProperty('display', 'none');

    // Check if page uses new block format
    if (page.blocks && page.blocks.length > 0) {
      // Hide legacy elements
      if (this.el.pageContainer) this.el.pageContainer.style.display = 'none';
      this.renderBlockGrid(page.blocks, viewer, page.page_image_url || '');
    } else if (page.page_image_url) {
      const isPdf = page.page_image_url.toLowerCase().endsWith('.pdf');
      if (this.el.pageContainer) this.el.pageContainer.style.display = '';

      if (isPdf) {
        // Render PDF in an iframe
        if (this.el.pageImg) this.el.pageImg.style.display = 'none';
        let pdfFrame = document.getElementById('epPdfFrame');
        if (!pdfFrame) {
          pdfFrame = document.createElement('iframe');
          pdfFrame.id = 'epPdfFrame';
          pdfFrame.style.cssText = 'width:100%;height:100%;border:none;display:block;';
          this.el.pageContainer.appendChild(pdfFrame);
        }
        pdfFrame.style.display = 'block';
        pdfFrame.src = page.page_image_url;
        if (this.el.hotspotsLayer) this.el.hotspotsLayer.style.display = 'none';
      } else {
        // Image page
        const pdfFrame = document.getElementById('epPdfFrame');
        if (pdfFrame) pdfFrame.style.display = 'none';
        if (this.el.pageImg) {
          this.el.pageImg.style.display = 'block';
          this.el.pageImg.src = page.page_image_url;
        }
        if (this.el.hotspotsLayer) this.el.hotspotsLayer.style.display = 'block';
        this.renderHotspots(page.articles || []);
      }

      const grid = document.getElementById('epBlockGrid');
      if (grid) grid.style.display = 'none';
    }

    // Scroll viewer to top when switching pages
    if (this.el.viewer) this.el.viewer.scrollTop = 0;

    // Update thumbnail active state
    this.updateThumbActive();
  },

  changePage(dir) {
    this.showPage(this.currentPage + dir);
  },

  updatePager() {
    if (this.el.pageInfo) this.el.pageInfo.textContent = `${this.currentPage} / ${this.totalPages}`;
    if (this.el.prevPage) this.el.prevPage.disabled = this.currentPage <= 1;
    if (this.el.nextPage) this.el.nextPage.disabled = this.currentPage >= this.totalPages;
    // Update edge arrows
    if (this.el.edgePrev) this.el.edgePrev.disabled = this.currentPage <= 1;
    if (this.el.edgeNext) this.el.edgeNext.disabled = this.currentPage >= this.totalPages;
  },

  getBlockType(block) {
    if (block?.type === 'divider') return 'divider';
    if (block?.type === 'shape')   return 'shape';
    return 'article';
  },

  buildShapeMarkup(block) {
    const fill   = block.no_fill ? 'none' : (block.fill_color   || '#cccccc');
    const stroke = block.stroke_color || '#111827';
    const sw     = block.stroke_width || 0;
    const op     = (block.opacity ?? 100) / 100;
    const cr     = block.corner_radius || 0;
    switch (block.shape_type) {
      case 'rect':
        return `<div style="width:100%;height:100%;background:${fill};border:${sw}px solid ${sw > 0 ? stroke : 'transparent'};border-radius:${cr}%;opacity:${op};box-sizing:border-box;"></div>`;
      case 'circle':
        return `<div style="width:100%;height:100%;background:${fill};border:${sw}px solid ${sw > 0 ? stroke : 'transparent'};border-radius:50%;opacity:${op};box-sizing:border-box;"></div>`;
      case 'line-h':
      case 'line-v':
        return `<div style="width:100%;height:100%;background:${fill === 'none' ? stroke : fill};border-radius:${cr}%;opacity:${op};"></div>`;
      case 'triangle': {
        const svgSw = sw > 0 ? `stroke="${stroke}" stroke-width="${sw * 2}" stroke-linejoin="round"` : '';
        return `<svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none" style="opacity:${op};display:block;"><polygon points="50,2 98,98 2,98" fill="${fill}" ${svgSw}/></svg>`;
      }
      case 'arrow': {
        const af = fill === 'none' ? 'transparent' : fill;
        return `<svg width="100%" height="100%" viewBox="0 0 120 40" preserveAspectRatio="none" style="opacity:${op};display:block;overflow:visible;"><path d="M2 20 H90 M78 5 L110 20 L78 35" fill="none" stroke="${af === 'transparent' ? stroke : af}" stroke-width="${Math.max(2, sw + 3)}" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
      }
      default:
        return `<div style="width:100%;height:100%;background:${fill};opacity:${op};"></div>`;
    }
  },

  buildDividerMarkup(block) {
    const orientation = block?.divider_orientation === 'vertical' ? 'vertical' : 'horizontal';
    const thickness = Math.max(1, parseInt(block?.divider_thickness, 10) || 6);
    const color = block?.divider_color || '#e41e26';
    const style = block?.divider_style || 'solid';

    const lineStyle = orientation === 'vertical'
      ? `height:100%;border-left:${thickness}px ${style} ${color};`
      : `width:100%;border-top:${thickness}px ${style} ${color};`;

    return `
      <div class="ep-block-divider ${orientation}">
        <div class="ep-divider-line-preview ${orientation}" style="${lineStyle}"></div>
      </div>
    `;
  },

  // ── Block Grid (NEW) ──
  renderBlockGrid(blocks, viewer, pageImageUrl = '') {
    let grid = document.getElementById('epBlockGrid');
    if (!grid) {
      grid = document.createElement('div');
      grid.id = 'epBlockGrid';
      grid.className = 'ep-block-grid';
      (viewer || document.getElementById('epViewer'))?.appendChild(grid);
    }
    grid.style.display = 'block';
    // Page 2+ collapses external spacing (updatePageHeader may have already set this,
    // but on initial render the grid is created here so set it again)
    grid.style.marginTop = this.currentPage > 1 ? '0' : '';
    if (this.el.hotspotsLayer) this.el.hotspotsLayer.style.display = 'none';

    this.articles = [];

    // Match admin canvas dimensions exactly for block position math
    const CANVAS_W = 800;
    const canvasH = 1131; // must match CANVAS_H in epaper-admin.js (A4 at 800px)
    const aspectRatio = '141.42'; // A4 fixed display (800 × √2 ≈ 1131px)

    // Background: page scan image if present
    const bgStyle = pageImageUrl
      ? `background-image:url('${pageImageUrl}');background-size:100% 100%;background-repeat:no-repeat;background-position:center;`
      : '';

    grid.innerHTML = `
      <div class="ep-canvas-viewer" style="position:relative;width:100%;padding-bottom:${aspectRatio}%;${bgStyle}">
        ${blocks.map((block) => {
          const type = this.getBlockType(block);
          const hasImg = block.image_url && block.image_url.length > 10;
          const x = ((block.x || 0) / CANVAS_W * 100).toFixed(2);
          const y = ((block.y || 0) / canvasH * 100).toFixed(2);
          const w = ((block.w || 200) / CANVAS_W * 100).toFixed(2);
          const h = ((block.h || 150) / canvasH * 100).toFixed(2);
          const bw = block.border_width ?? 0;
          const br = block.border_radius ?? 0;
          const bc = block.border_color || '#e41e26';
          const bs = block.border_style || 'solid';
          const borderCSS = type === 'article' && bw > 0 ? `border:${bw}px ${bs} ${bc};` : '';
          const baseStyle = `position:absolute;left:${x}%;top:${y}%;width:${w}%;height:${h}%;border-radius:${br}px;${borderCSS}overflow:hidden;`;

          if (type === 'divider') {
            return `
              <div class="ep-block-divider-card" style="${baseStyle}">
                ${this.buildDividerMarkup(block)}
              </div>
            `;
          }

          if (type === 'shape') {
            return `
              <div style="${baseStyle}pointer-events:none;">
                ${this.buildShapeMarkup(block)}
              </div>
            `;
          }

          const articleIndex = this.articles.push({
            ...block,
            headline: block.headline,
            sub_headline: block.sub_headline,
            body_text: block.body_text,
            body_html: block.body_html || '',
            category_label: block.category_label,
            article_image_url: block.image_url,
            gallery: block.gallery || [],
          }) - 1;

          // Optimize Cloudinary images: smaller width for card thumbnails
          const imgSrc = hasImg ? this.optimizeCloudinaryUrl(block.image_url, 400) : '';

          return `
            <div class="ep-block-card" onclick="EP.openArticle(${articleIndex})" title="${block.headline || ''}" style="${baseStyle}cursor:pointer;">
              ${hasImg ? `<img class="ep-block-img" src="${imgSrc}" alt="${block.headline || ''}" draggable="false" loading="lazy" style="width:100%;height:100%;object-fit:contain;display:block;">` : `
                <div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#f3f4f6,#e5e7eb);color:#d1d5db;font-size:28px;">
                  <i class="fa fa-newspaper"></i>
                </div>
              `}
            </div>
          `;
        }).join('')}
      </div>
    `;
  },

  // ── Hotspots (Legacy) ──
  renderHotspots(articles) {
    if (!this.el.hotspotsLayer) return;
    this.el.hotspotsLayer.innerHTML = '';
    this.articles = articles;

    articles.forEach((art, i) => {
      const hs = document.createElement('div');
      hs.className = 'ep-hotspot';
      hs.style.left = (art.click_region_x || 0) + '%';
      hs.style.top = (art.click_region_y || 0) + '%';
      hs.style.width = (art.click_region_w || 20) + '%';
      hs.style.height = (art.click_region_h || 15) + '%';
      hs.title = art.headline || 'Read article';
      hs.addEventListener('click', () => this.openArticle(i));
      this.el.hotspotsLayer.appendChild(hs);
    });
  },

  // ── Zoom ──
  setZoom(level) {
    this.zoom = Math.max(this.minZoom, Math.min(this.maxZoom, level));
    this.applyTransform();
    // Reflect button disabled state
    if (this.el.zoomOut) this.el.zoomOut.disabled = this.zoom <= this.minZoom;
    if (this.el.zoomIn)  this.el.zoomIn.disabled  = this.zoom >= this.maxZoom;
  },

  applyTransform() {
    const z = this.zoom;
    const grid = document.getElementById('epBlockGrid');
    const useGrid = grid && grid.style.display !== 'none';
    const target = useGrid ? grid : this.el.pageContainer;
    const viewer = this.el.viewer;
    if (!target) return;

    target.style.zoom = z;
    target.style.transform = '';
    target.style.marginBottom = '';

    if (!viewer) return;

    if (z > 1) {
      // Zoomed in: switch to flex-start so the content doesn't clip on the left,
      // then scroll to show the center of the zoomed content
      viewer.style.justifyContent = 'flex-start';
      requestAnimationFrame(() => {
        const excess = viewer.scrollWidth - viewer.clientWidth;
        if (excess > 0) viewer.scrollLeft = Math.round(excess / 2);
      });
    } else {
      // Zoomed out or normal: let flexbox center the content
      viewer.style.justifyContent = '';
      viewer.scrollLeft = 0;
    }
  },

  toggleFullscreen() {
    if (!document.fullscreenElement) {
      document.body.classList.add('ep-fullscreen');
      // Request fullscreen on documentElement so masthead, toolbar and nav are all visible
      document.documentElement.requestFullscreen?.();
    } else {
      document.body.classList.remove('ep-fullscreen');
      document.exitFullscreen?.();
    }
  },

  // ── Thumbnail Strip ──
  toggleThumbStrip() {
    const strip = this.el.thumbStrip;
    const toggle = this.el.thumbToggle;
    if (!strip) return;
    strip.classList.toggle('collapsed');
    if (toggle) {
      toggle.innerHTML = strip.classList.contains('collapsed')
        ? '<i class="fa fa-chevron-down"></i>'
        : '<i class="fa fa-chevron-up"></i>';
    }
  },

  renderThumbnails() {
    const container = this.el.thumbScroll;
    if (!container || !this.pages.length) {
      if (container) container.innerHTML = '';
      return;
    }

    container.innerHTML = this.pages.map((page, i) => {
      const isActive = (i + 1) === this.currentPage;

      // Prefer the actual page scan; fall back to first block image
      let thumbUrl = '';
      if (page.page_image_url) {
        thumbUrl = this.optimizeCloudinaryUrl(page.page_image_url, 160);
      } else {
        const firstImg = (page.blocks || []).find(b => b.type !== 'shape' && b.image_url && b.image_url.length > 10);
        if (firstImg) thumbUrl = this.optimizeCloudinaryUrl(firstImg.image_url, 160);
      }

      return `
        <div class="ep-thumb-card ${isActive ? 'active' : ''}" onclick="EP.showPage(${i + 1})">
          <div class="ep-thumb-label">Page ${i + 1}</div>
          ${thumbUrl
            ? `<img class="ep-thumb-img" src="${thumbUrl}" alt="Page ${i + 1}" loading="lazy">`
            : `<div class="ep-thumb-placeholder"><i class="fa fa-newspaper"></i></div>`
          }
        </div>
      `;
    }).join('');
  },

  updateThumbActive() {
    const container = this.el.thumbScroll;
    if (!container) return;
    container.querySelectorAll('.ep-thumb-card').forEach((card, i) => {
      card.classList.toggle('active', (i + 1) === this.currentPage);
    });
    // Scroll active thumbnail into view
    const activeCard = container.querySelector('.ep-thumb-card.active');
    if (activeCard) {
      activeCard.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }
  },

  // ── Article Panel ──
  currentArticle: null,
  _origArticleTitle: null,
  _origArticleHTML: null,

  openArticle(index) {
    const art = this.articles[index];
    if (!art) return;
    this.currentArticle = art;

    // Reset voice select and player state each time a new article opens
    if (this.el.voiceSelect) this.el.voiceSelect.value = '';
    this._voice.selectedVoice = '';
    if (this.el.ttsPrompt) this.el.ttsPrompt.style.display = '';
    if (this.el.voiceBar) this.el.voiceBar.classList.remove('loading', 'playing', 'topbar');
    if (this.el.ttsStartBtn) { this.el.ttsStartBtn.innerHTML = '<i class="fa fa-play"></i> <span>Play</span>'; this.el.ttsStartBtn.classList.remove('loading'); }

    if (this.el.articleCategory) this.el.articleCategory.textContent = art.category_label || 'News';
    if (this.el.articleTitle) this.el.articleTitle.textContent = art.headline || '';
    if (this.el.articleDate) this.el.articleDate.textContent = art.created_at || this.formatDateISO(this.currentDate);
    // Only show admin-uploaded gallery images — never show the newspaper clipping
    const gallery = art.gallery || [];
    if (this.el.articleImg) {
      this.el.articleImg.style.display = 'none';
      this.el.articleImg.onclick = null;
    }

    // Rich HTML content or plain text
    if (this.el.articleText) {
      let galHTML = '';
      if (gallery.length > 0) {
        galHTML = '<div class="ep-article-gallery-full">';
        gallery.forEach((img, i) => {
          galHTML += `<img src="${img}" alt="Image ${i+1}" class="ep-gallery-full-img" loading="lazy" onload="this.classList.add('loaded')" onclick="EP.openGalleryViewer(${index}, ${i})">`;
        });
        galHTML += '</div>';
      }

      if (art.body_html && art.body_html.length > 10) {
        this.el.articleText.innerHTML = galHTML + art.body_html;
      } else {
        this.el.articleText.innerHTML = galHTML + (art.body_text || '').split('\n').map(p => `<p>${p}</p>`).join('');
      }
    }

    // Save originals for translation restore
    this._origArticleTitle = art.headline || '';
    this._origArticleHTML  = this.el.articleText ? this.el.articleText.innerHTML : '';

    // Reset AI tabs
    this.switchAiTab(null);
    this.stopTTS();
    this.updateReadingTime();

    this.el.articlePanel?.classList.add('open');
    if (this.el.articlePanel) this.el.articlePanel.scrollTop = 0;
    document.body.style.overflow = 'hidden';

    // Show video button if article has video
    const vidBtn = document.getElementById('epVideoBtn');
    if (vidBtn) vidBtn.style.display = art.has_video && art.video_url ? 'inline-flex' : 'none';

    this.trackEvent('article_read', { headline: art.headline, category: art.category_label });
  },

  // Gallery lightbox viewer
  openGalleryViewer(artIndex, imgIndex) {
    const art = this.articles[artIndex];
    if (!art || !art.gallery) return;
    const imgs = art.gallery;
    this._galImgs = imgs;
    this._galIdx = imgIndex;
    this._openLightbox();
  },

  _openLightbox() {
    let overlay = document.getElementById('epGalleryOverlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'epGalleryOverlay';
      overlay.className = 'ep-gallery-overlay';
      overlay.innerHTML = `
        <button class="ep-gal-close" onclick="EP.closeGalleryViewer()"><i class="fa fa-times"></i></button>
        <button class="ep-gal-prev" onclick="EP.galleryNav(-1)"><i class="fa fa-chevron-left"></i></button>
        <img class="ep-gal-img" id="epGalImg" src="" alt="">
        <button class="ep-gal-next" onclick="EP.galleryNav(1)"><i class="fa fa-chevron-right"></i></button>
        <div class="ep-gal-counter" id="epGalCounter"></div>
      `;
      // Click overlay background to close
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) EP.closeGalleryViewer();
      });
      document.body.appendChild(overlay);
    }

    this._showGalImg();
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
  },

  _showGalImg() {
    const img = document.getElementById('epGalImg');
    const counter = document.getElementById('epGalCounter');
    if (img) img.src = this._galImgs[this._galIdx];
    if (counter) counter.textContent = `${this._galIdx + 1} / ${this._galImgs.length}`;
  },

  galleryNav(dir) {
    this._galIdx = (this._galIdx + dir + this._galImgs.length) % this._galImgs.length;
    this._showGalImg();
  },

  closeGalleryViewer() {
    document.getElementById('epGalleryOverlay')?.classList.remove('open');
    document.body.style.overflow = '';
  },

  closeArticle() {
    this.el.articlePanel?.classList.remove('open');
    document.body.style.overflow = '';
    this.stopTTS();
    this.currentArticle = null;
  },

  // ── AI Tabs ──
  switchAiTab(tab) {
    this.el.aiTabs?.forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    this.el.aiContents?.forEach(c => c.classList.toggle('active', c.dataset.tab === tab));

    if (tab === 'summarize') this.summarizeArticle();
    if (tab === 'translate') {
      this._autoSetTranslateLang();
    }
  },

  _autoSetTranslateLang() {
    if (!this.el.translateSelect || !this.currentArticle) return;
    const text = this._getArticleText();
    if (!text) return;
    const isDevanagari = this.detectLang(text) === 'hi-IN';
    this.el.translateSelect.value = isDevanagari ? 'en' : 'hi';
  },

  async _translatePanelForVoice(voiceVal) {
    if (!this.currentArticle) return;

    const VOICE_LANG = {
      'hi-IN-MadhurNeural': 'hi', 'hi-IN-SwaraNeural': 'hi',
      'mr-IN-ManoharNeural': 'mr', 'mr-IN-AarohiNeural': 'mr',
      'en-IN-PrabhatNeural': 'en', 'en-IN-NeerjaNeural': 'en',
    };
    const lang = VOICE_LANG[voiceVal] || '';

    // Restore originals on Auto
    if (!lang) {
      if (this.el.articleTitle) this.el.articleTitle.textContent = this._origArticleTitle || '';
      if (this.el.articleText)  this.el.articleText.innerHTML  = this._origArticleHTML  || '';
      this.showToast('Restored original language');
      return;
    }

    this.showToast('🔄 Translating...');

    const art = this.currentArticle;
    const headline = art.headline || '';

    // Get body as plain text from the original stored HTML
    const bodyEl = document.createElement('div');
    bodyEl.innerHTML = this._origArticleHTML || '';
    const bodyText = (bodyEl.innerText || bodyEl.textContent || '').trim();

    try {
      // Translate headline and body in parallel as separate calls
      // so we can reliably place them back in the right elements
      const [hRes, bRes] = await Promise.all([
        fetch('/api/epaper/translate', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: headline, target_lang: lang }),
        }),
        fetch('/api/epaper/translate', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: bodyText.slice(0, 4000), target_lang: lang }),
        }),
      ]);

      const hData = hRes.ok ? await hRes.json() : {};
      const bData = bRes.ok ? await bRes.json() : {};

      const newTitle = hData.translated_text || headline;
      const newBody  = bData.translated_text || bodyText;

      if (this.el.articleTitle) this.el.articleTitle.textContent = newTitle;
      if (this.el.articleText) {
        this.el.articleText.innerHTML = newBody
          .split(/\n+/)
          .filter(p => p.trim())
          .map(p => `<p>${p}</p>`)
          .join('');
      }

      const langNames = { hi: 'हिंदी', mr: 'मराठी', en: 'English' };
      this.showToast(`✅ Translated to ${langNames[lang] || lang}`);
    } catch (e) {
      this.showToast('Translation failed');
    }
  },

  // ══════════════════════════════════════════════
  //  PREMIUM VOICE BAR SYSTEM — Edge Neural TTS
  //  Real Indian news anchor voice (server-side)
  // ══════════════════════════════════════════════
  _voice: {
    rate: 1,
    playing: false,
    paused: false,
    text: '',
    audio: null,        // HTML5 Audio element
    selectedVoice: '',  // Edge TTS voice ID (auto-detect if empty)
    loading: false,
    abortController: null,
  },

  detectLang(text) {
    const devanagari = (text.match(/[\u0900-\u097F]/g) || []).length;
    const total = text.length;
    if (devanagari / total > 0.3) {
      const marathiWords = ['\u0906\u0939\u0947','\u0928\u093E\u0939\u0940','\u0906\u0923\u093F','\u092E\u0932\u093E','\u0906\u092A\u0923','\u0939\u094B\u0924\u0947','\u0915\u0947\u0932\u0947','\u091D\u093E\u0932\u0947','\u092E\u094D\u0939\u0923\u093E\u0932\u0947','\u092E\u0939\u093E\u0930\u093E\u0937\u094D\u091F\u094D\u0930'];
      const hindiWords   = ['\u0939\u0948','\u0928\u0939\u0940\u0902','\u0914\u0930','\u0925\u093E','\u0939\u0948\u0902','\u092F\u0939','\u0915\u0939\u093E','\u092C\u0924\u093E\u092F\u093E','\u0907\u0938\u0938\u0947'];
      const mr = marathiWords.filter(w => text.includes(w)).length;
      const hi = hindiWords.filter(w => text.includes(w)).length;
      return mr > hi ? 'mr-IN' : 'hi-IN';
    }
    return 'en-IN';
  },

  // Get article plain text
  _getArticleText() {
    const art = this.currentArticle;
    if (!art) return '';
    let text = '';
    if (art.headline) text += art.headline + '। ';
    if (art.sub_headline) text += art.sub_headline + '। ';
    if (art.body_text && art.body_text.trim()) {
      text += art.body_text;
    } else if (art.body_html) {
      const tmp = document.createElement('div');
      tmp.innerHTML = art.body_html;
      text += tmp.textContent || tmp.innerText || '';
    }
    return text.trim();
  },

  // ── Sentence highlight state ────────────────────────
  _ttsSpans: [],
  _ttsTotalChars: 0,
  _ttsCurrentSpan: -1,
  _estimatedTtsDuration: 0,

  _splitSentences(text) {
    text = text.replace(/\s+/g, ' ').trim();
    const sentences = [];
    let buf = '';
    for (let i = 0; i < text.length; i++) {
      buf += text[i];
      const ch = text[i];
      if (/[।!?]/.test(ch)) {
        if (buf.trim()) sentences.push(buf.trim());
        buf = '';
      } else if (ch === '.') {
        const next = text[i + 1] || '';
        const afterNext = text[i + 2] || '';
        const isRealEnd = (next === ' ' && /[A-Zऀ-ॿ]/.test(afterNext)) || !next || next === '\n';
        if (isRealEnd) {
          if (buf.trim()) sentences.push(buf.trim());
          buf = '';
          if (next === ' ') i++;
        }
      }
    }
    if (buf.trim()) sentences.push(buf.trim());
    return sentences.filter(Boolean);
  },

  _prepareHighlight() {
    this._ttsSpans = [];
    this._ttsCurrentSpan = -1;
    let charOffset = 0;

    const titleEl = this.el.articleTitle;
    if (titleEl) {
      titleEl.querySelectorAll('.ep-tts-sentence').forEach(s => s.outerHTML = s.textContent);
      titleEl.normalize();
      const t = titleEl.textContent.trim();
      const sp = document.createElement('span');
      sp.className = 'ep-tts-sentence';
      sp.textContent = t;
      titleEl.textContent = '';
      titleEl.appendChild(sp);
      this._ttsSpans.push({ el: sp, start: charOffset, end: charOffset + t.length });
      charOffset += t.length + 2;
    }

    const paras = this.el.articleText ? this.el.articleText.querySelectorAll('p') : [];
    (paras.length ? paras : (this.el.articleText ? [this.el.articleText] : [])).forEach(p => {
      p.querySelectorAll('.ep-tts-sentence').forEach(s => s.outerHTML = s.textContent);
      p.normalize();
      const txt = p.textContent.trim();
      const sentences = this._splitSentences(txt);
      p.textContent = '';
      sentences.forEach((s, si) => {
        const sp = document.createElement('span');
        sp.className = 'ep-tts-sentence';
        sp.textContent = s;
        p.appendChild(sp);
        if (si < sentences.length - 1) p.appendChild(document.createTextNode(' '));
        this._ttsSpans.push({ el: sp, start: charOffset, end: charOffset + s.length });
        charOffset += s.length + 1;
      });
    });

    this._ttsTotalChars = charOffset || 1;
    // Estimate audio duration for the whole text so highlighting can use
    // a stable timebase even if the actual audio blob durations differ
    const fullText = (this.el.articleTitle?.textContent || '') + ' ' + (this.el.articleText?.innerText || '');
    this._estimatedTtsDuration = this._estimateAudioDuration(fullText.trim());
  },

  _highlightAt(currentTime, duration) {
    if (!this._ttsTotalChars) return;
    // Use the larger of measured audio duration and estimated total duration
    const denom = Math.max(duration || 0, this._estimatedTtsDuration || 0.001);
    if (!denom) return;
    const pos = (currentTime / denom) * this._ttsTotalChars;
    let idx = -1;
    for (let i = 0; i < this._ttsSpans.length; i++) {
      if (pos >= this._ttsSpans[i].start && pos < this._ttsSpans[i].end) { idx = i; break; }
    }
    if (idx === this._ttsCurrentSpan) return;
    if (this._ttsCurrentSpan >= 0 && this._ttsSpans[this._ttsCurrentSpan])
      this._ttsSpans[this._ttsCurrentSpan].el.classList.remove('ep-tts-active');
    this._ttsCurrentSpan = idx;
    if (idx >= 0 && this._ttsSpans[idx]) {
      this._ttsSpans[idx].el.classList.add('ep-tts-active');
      this._ttsSpans[idx].el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  },

  // Estimate TTS duration (seconds) from text length and approximate WPM
  _estimateAudioDuration(text) {
    if (!text) return 0;
    // Count words approximately
    const words = (text.trim().split(/\s+/).filter(Boolean) || []).length;
    // Pick WPM based on detected language
    const lang = this.detectLang(text);
    let wpm = 180; // default English
    if (lang === 'hi-IN' || lang === 'mr-IN') wpm = 150;
    // Adjust for rate (1x = normal)
    const rate = this._voice?.rate || 1;
    const effectiveWpm = Math.max(80, Math.round(wpm * rate));
    const minutes = words / effectiveWpm;
    return Math.max(1, Math.round(minutes * 60));
  },

  _clearHighlight() {
    this.el.articleText?.querySelectorAll('.ep-tts-sentence.ep-tts-active').forEach(el => el.classList.remove('ep-tts-active'));
    this.el.articleTitle?.querySelectorAll('.ep-tts-sentence.ep-tts-active').forEach(el => el.classList.remove('ep-tts-active'));
    this._ttsCurrentSpan = -1;
  },

  // Calculate reading time in minutes
  _calcReadingTime(text) {
    if (!text) return 0;
    const lang = this.detectLang(text);
    const words = text.split(/\s+/).filter(Boolean).length;
    const wpm = lang === 'hi-IN' ? 150 : 180;
    return Math.max(1, Math.ceil(words / wpm));
  },

  // Format seconds to M:SS
  _formatTime(seconds) {
    const s = Math.max(0, Math.round(seconds));
    const m = Math.floor(s / 60);
    const ss = String(s % 60).padStart(2, '0');
    return `${m}:${ss}`;
  },

  // Update reading time display when article opens
  updateReadingTime() {
    const text = this._getArticleText();
    const mins = this._calcReadingTime(text);
    const label = mins <= 1 ? '1 min listen' : `${mins} min listen`;

    if (this.el.readingTime) {
      this.el.readingTime.style.display = 'inline-flex';
      if (this.el.readTimeText) this.el.readTimeText.textContent = label;
    }
    if (this.el.ttsEstimate) {
      const langLabel = this.detectLang(text) === 'hi-IN' ? 'Hindi' : 'English';
      this.el.ttsEstimate.textContent = `Estimated: ${label} • ${langLabel} • AI Voice`;
    }
  },

  // Fast inline text preprocessing for TTS (no LLM needed)
  _preprocessTTSText(text) {
    if (!text) return text;
    let t = text;

    // Expand common Hindi abbreviations
    const hindiAbbr = {
      'JEE': 'जे ई ई', 'NEET': 'नीट', 'IIT': 'आई आई टी',
      'IIM': 'आई आई एम', 'NIT': 'एन आई टी',
      'UP': 'उत्तर प्रदेश', 'MP': 'मध्य प्रदेश', 'MH': 'महाराष्ट्र',
      'CM': 'मुख्यमंत्री', 'PM': 'प्रधानमंत्री',
      'BJP': 'बी जे पी', 'RSS': 'आर एस एस', 'AAP': 'आम आदमी पार्टी',
      'CBSE': 'सी बी एस ई', 'ICSE': 'आई सी एस ई',
      'SSC': 'एस एस सी', 'HSC': 'एच एस सी',
      'CET': 'सी ई टी', 'MHT-CET': 'एम एच टी सी ई टी',
      'DTE': 'डी टी ई', 'NGO': 'एन जी ओ',
    };

    // Only replace standalone abbreviations (word boundaries)
    for (const [abbr, expansion] of Object.entries(hindiAbbr)) {
      const regex = new RegExp(`\\b${abbr}\\b`, 'g');
      t = t.replace(regex, expansion);
    }

    // Convert ₹ amounts to Hindi words
    t = t.replace(/₹\s?(\d[\d,]*)/g, (_, num) => {
      const n = parseInt(num.replace(/,/g, ''));
      if (n >= 10000000) return `${(n/10000000).toFixed(1)} करोड़ रुपये`;
      if (n >= 100000) return `${(n/100000).toFixed(1)} लाख रुपये`;
      if (n >= 1000) return `${(n/1000).toFixed(0)} हज़ार रुपये`;
      return `${n} रुपये`;
    });

    // Convert percentage symbols
    t = t.replace(/(\d+)%/g, '$1 प्रतिशत');

    // Add natural pauses after sentences
    t = t.replace(/।\s*/g, '। ... ');
    t = t.replace(/\.\s+/g, '. ... ');

    // Clean up excessive whitespace
    t = t.replace(/\s{3,}/g, '  ');

    return t.trim();
  },

  // ── Start playing (fetch audio from Edge TTS API) ──
  async voicePlay() {
    if (!this.currentArticle) return;

    // If already paused, just resume from current position
    if (this._voice.paused && this._voice.audio) {
      this._voice.audio.play();
      this._voice.paused = false;
      this._voice.playing = true;
      this._voiceUpdatePlayIcon();
      return;
    }

    // Read from the currently DISPLAYED text (may already be translated)
    const displayedTitle = this.el.articleTitle?.textContent || '';
    const displayedBody  = (this.el.articleText?.innerText || this.el.articleText?.textContent || '')
                            .replace(/[\r\n]+/g, ' ').replace(/ +/g, ' ').trim();
    const rawText = (displayedTitle + '। ' + displayedBody).trim() || this._getArticleText();
    if (!rawText) { this.showToast('No text to read'); return; }

    // Stop any existing playback
    this.voiceStop();
    this._voice.loading = true;

    // Show voice bar immediately
    if (this.el.voiceBar) this.el.voiceBar.classList.add('loading', 'topbar');
    if (this.el.voiceTitle) this.el.voiceTitle.textContent = displayedTitle || this.currentArticle.headline || 'Article';
    if (this.el.ttsStartBtn) { this.el.ttsStartBtn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> <span>Loading...</span>'; this.el.ttsStartBtn.classList.add('loading'); }
    this._voiceUpdatePlayIcon();

    // Prepare sentence spans for highlight
    this._prepareHighlight();

    // Text is already in the right language (translated by _translatePanelForVoice)
    let textToRead = rawText;
    let rateStr = '+0%';
    let pitchStr = '+0Hz';

    // Inline text preprocessing (fast, no LLM needed)
    textToRead = this._preprocessTTSText(textToRead);

    // Step: Generate TTS Audio directly (skip LLM for speed)
    this.showToast('🎙️ Generating voice...');
    
    // If rate wasn't set by LLM, set it by user default
    if (rateStr === '+0%' && this._voice.rate !== 1) {
      const pct = Math.round((this._voice.rate - 1) * 100);
      rateStr = pct >= 0 ? `+${pct}%` : `${pct}%`;
    }

    this._voice.text = textToRead; // Store what we are actually reading

    try {
      const res = await fetch('/api/epaper/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: textToRead, voice: this._voice.selectedVoice || '', rate: rateStr, pitch: pitchStr }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || 'TTS request failed');
      }

      const audioBlob = await res.blob();
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      this._voice.audio = audio;

      audio.addEventListener('loadedmetadata', () => {
        this._voice.loading = false;
        if (this.el.voiceDuration) this.el.voiceDuration.textContent = this._formatTime(audio.duration || 0);
        this._voiceUpdatePlayIcon();
      });

      audio.addEventListener('timeupdate', () => {
        this._voiceUpdateUI();
        this._highlightAt(audio.currentTime, audio.duration);
      });

      audio.addEventListener('ended', () => {
        this._clearHighlight();
        this._voiceFinished();
      });

      audio.addEventListener('error', (e) => {
        console.warn('Audio error:', e);
        this.showToast('Audio playback error');
        this._voiceFinished();
      });

      await audio.play();
      if (this.el.voiceBar) this.el.voiceBar.classList.remove('loading');
      this._voice.playing = true;
      this._voice.paused = false;
      this._voice.loading = false;
      if (this.el.ttsStartBtn) { this.el.ttsStartBtn.innerHTML = '<i class="fa fa-play"></i> <span>Play</span>'; this.el.ttsStartBtn.classList.remove('loading'); }
      this._voiceUpdatePlayIcon();
      this.showToast('🔊 Now playing');
      this.trackEvent('voice_play', { article: this.currentArticle?.headline, voice: this._voice.selectedVoice || 'auto' });

    } catch (err) {
      console.error('TTS Error:', err);
      this._voice.loading = false;
      if (this.el.ttsStartBtn) { this.el.ttsStartBtn.innerHTML = '<i class="fa fa-play"></i> <span>Play</span>'; this.el.ttsStartBtn.classList.remove('loading'); }
      if (this.el.voiceBar) this.el.voiceBar.classList.remove('loading', 'topbar');
      if (this.el.ttsPrompt) this.el.ttsPrompt.style.display = '';
      this._clearHighlight();
      this.showToast('Voice generation failed. Try again.');
      this._voiceUpdatePlayIcon();
    }
  },

  _voiceFinished() {
    this._voice.playing = false;
    this._voice.paused = false;
    this._voice.loading = false;
    if (this.el.voiceProgressFill) this.el.voiceProgressFill.style.width = '100%';
    if (this._voice.audio) {
      const dur = this._voice.audio.duration || 0;
      if (this.el.voiceElapsed) this.el.voiceElapsed.textContent = this._formatTime(dur);
    }
    if (this.el.voiceRemaining) this.el.voiceRemaining.textContent = '0:00';
    this._voiceUpdatePlayIcon();
    if (this.el.voiceBar) this.el.voiceBar.classList.remove('playing', 'loading', 'topbar');
    setTimeout(() => {
      if (this.el.voiceBar) this.el.voiceBar.classList.remove('topbar');
      if (this.el.ttsPrompt) this.el.ttsPrompt.style.display = '';
    }, 1800);
    this.showToast('✅ Finished reading');
  },

  // Toggle play/pause
  voiceToggle() {
    const audio = this._voice.audio;

    if (this._voice.loading) return; // Still generating

    if (!audio || (!this._voice.playing && !this._voice.paused)) {
      // Not started yet, start fresh
      this.voicePlay();
      return;
    }

    if (this._voice.paused) {
      // Resume
      audio.play();
      this._voice.paused = false;
      this._voice.playing = true;
    } else if (this._voice.playing) {
      // Pause
      audio.pause();
      this._voice.paused = true;
      this._voice.playing = false;
    }
    this._voiceUpdatePlayIcon();
  },

  // Stop and hide voice bar
  voiceStop() {
    const audio = this._voice.audio;
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
      if (audio.src && audio.src.startsWith('blob:')) URL.revokeObjectURL(audio.src);
      this._voice.audio = null;
    }
    this._voice.playing = false;
    this._voice.paused = false;
    this._voice.loading = false;
    if (this.el.ttsStartBtn) { this.el.ttsStartBtn.innerHTML = '<i class="fa fa-play"></i> <span>Play</span>'; this.el.ttsStartBtn.classList.remove('loading'); }
    if (this.el.voiceBar) this.el.voiceBar.classList.remove('playing', 'loading', 'topbar');
    if (this.el.ttsPrompt) this.el.ttsPrompt.style.display = '';
    if (this.el.voiceProgressFill) this.el.voiceProgressFill.style.width = '0%';
    this._clearHighlight();
    this._voiceUpdatePlayIcon();
  },

  // Skip forward/backward by seconds
  voiceSkip(seconds) {
    const audio = this._voice.audio;
    if (!audio || (!this._voice.playing && !this._voice.paused)) return;
    audio.currentTime = Math.max(0, Math.min(audio.duration || 0, audio.currentTime + seconds));
    this._voiceUpdateUI();
  },

  // Cycle speed — regenerate audio at new speed
  voiceCycleSpeed() {
    const speeds = [0.75, 1, 1.25, 1.5, 2];
    const idx = speeds.indexOf(this._voice.rate);
    this._voice.rate = speeds[(idx + 1) % speeds.length];
    if (this.el.voiceSpeedBtn) this.el.voiceSpeedBtn.textContent = this._voice.rate + 'x';

    // If playing, we need to regenerate audio with new rate
    if (this._voice.playing || this._voice.paused) {
      const audio = this._voice.audio;
      if (audio) {
        // Use HTML5 Audio playbackRate for instant speed change (no re-fetch needed!)
        audio.playbackRate = this._voice.rate;
      }
    }
    this.showToast(`Speed: ${this._voice.rate}x`);
  },

  // Mute / unmute
  voiceToggleMute() {
    const audio = this._voice.audio;
    if (!audio) return;
    audio.muted = !audio.muted;
    if (this.el.voiceVolBtn) {
      this.el.voiceVolBtn.innerHTML = audio.muted
        ? '<i class="fa fa-volume-xmark"></i>'
        : '<i class="fa fa-volume-high"></i>';
    }
  },

  // Update play/pause icon + waveform state
  _voiceUpdatePlayIcon() {
    if (this.el.voicePlayIcon) {
      if (this._voice.loading) {
        this.el.voicePlayIcon.className = 'fa fa-spinner fa-spin';
      } else {
        this.el.voicePlayIcon.className = this._voice.playing
          ? 'fa fa-pause' : 'fa fa-play';
      }
    }
    if (this.el.voiceBar) {
      this.el.voiceBar.classList.toggle('playing', this._voice.playing);
    }
  },

  // Real-time UI update using actual audio position
  _voiceUpdateUI() {
    const audio = this._voice.audio;
    if (!audio) return;

    const duration = audio.duration || 0;
    const current = audio.currentTime || 0;
    const pct = duration > 0 ? (current / duration) * 100 : 0;
    const remaining = Math.max(0, duration - current);

    if (this.el.voiceProgressFill) this.el.voiceProgressFill.style.width = pct + '%';
    if (this.el.voiceElapsed) this.el.voiceElapsed.textContent = this._formatTime(current);
    if (this.el.voiceRemaining) this.el.voiceRemaining.textContent = '-' + this._formatTime(remaining);
    if (this.el.voiceDuration) this.el.voiceDuration.textContent = this._formatTime(duration);
  },

  // Legacy compat — called by closeArticle
  stopTTS() {
    this.voiceStop();
  },


  // ── Translate ──
  async translateArticle() {
    if (!this.currentArticle || !this.el.translateOutput) return;
    const lang = this.el.translateSelect?.value || 'hi';
    const text = this._getArticleText();
    if (!text) return;

    this.el.translateOutput.innerHTML = '<div class="ep-summary-loading"><div class="spinner"></div>Translating...</div>';

    try {
      const res = await fetch('/api/epaper/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text.slice(0, 3500), target_lang: lang })
      });
      if (res.ok) {
        const data = await res.json();
        if (data.error) {
          this.el.translateOutput.textContent = text;
          this.showToast('Translation failed');
        } else {
          this.el.translateOutput.textContent = data.translated_text || text;
        }
      } else {
        this.el.translateOutput.textContent = text;
        this.showToast('Translation failed');
      }
    } catch (e) {
      this.el.translateOutput.textContent = text;
      this.showToast('Translation service unavailable');
    }
  },

  // ── Summarize ──
  async summarizeArticle() {
    if (!this.currentArticle || !this.el.summaryOutput) return;
    const text = this.currentArticle.body_text || '';
    if (!text) { this.el.summaryOutput.innerHTML = '<p>No content to summarize.</p>'; return; }

    this.el.summaryOutput.innerHTML = '<div class="ep-summary-loading"><div class="spinner"></div>AI is summarizing...</div>';
    this.trackEvent('ai_summarize', { article: this.currentArticle?.headline });

    try {
      const res = await fetch('/api/epaper/summarize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      if (res.ok) {
        const data = await res.json();
        const points = data.summary || [];
        this.el.summaryOutput.innerHTML = `<h4>✨ AI Summary</h4><ul>${points.map(p => `<li>${p}</li>`).join('')}</ul>`;
      } else {
        this.el.summaryOutput.innerHTML = '<p>Summary unavailable.</p>';
      }
    } catch (e) {
      this.el.summaryOutput.innerHTML = '<p>Summarization service unavailable.</p>';
    }
  },

  // ── Download Audio ──
  downloadAudio() {
    const audio = this._voice.audio;
    if (!audio || !audio.src || !audio.src.startsWith('blob:')) {
      this.showToast('Play the article first to download audio');
      return;
    }
    const headline = (this.currentArticle?.headline || 'article')
      .replace(/[^a-z0-9ऀ-ॿ\s]/gi, '').trim().replace(/\s+/g, '-').slice(0, 60);
    const a = document.createElement('a');
    a.href = audio.src;
    a.download = `${headline || 'audio'}.mp3`;
    a.click();
    this.showToast('⬇️ Downloading audio...');
  },

  // ── Save Edition as PDF ──
  async savePDF() {
    if (!this.pages.length) {
      this.showToast('No edition pages available');
      return;
    }
    const originalPage = this.currentPage;
    const originalZoom = this.zoom;
    const captures = [];
    const viewer = document.getElementById('epPaper') || this.el.viewer || document.body;
    if (!viewer) {
      this.showToast('PDF export is unavailable right now');
      return;
    }

    try {
      for (let pageNum = 1; pageNum <= this.pages.length; pageNum++) {
        this.showPage(pageNum);
        this.setZoom(1);
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));

        if (typeof window.html2canvas !== 'function') {
          throw new Error('html2canvas unavailable');
        }

        const canvas = await window.html2canvas(viewer, {
          backgroundColor: '#ffffff',
          useCORS: true,
          scale: Math.max(2, Math.min(3, (window.devicePixelRatio || 1.5) * 1.5)),
        });
        captures.push(canvas.toDataURL('image/png'));
      }
    } catch (err) {
      console.error('Edition PDF capture failed:', err);
      this.showToast('PDF export failed');
      return;
    } finally {
      if (originalPage) this.showPage(originalPage);
      this.setZoom(originalZoom);
    }

    const win = window.open('', '_blank');
    if (!win) {
      this.showToast('Allow popups to save PDF');
      return;
    }

    const title = this.currentEdition?.name || 'Vidyarthi Mitra E-Paper';
    const pagesHtml = captures.map((src, index) => `
      <section class="pdf-page">
        <img src="${src}" alt="Page ${index + 1}">
      </section>
    `).join('');

    win.document.write(`<!DOCTYPE html><html><head>
      <meta charset="utf-8">
      <title>${title.replace(/</g, '&lt;')}</title>
      <style>
        @page { size: A4 portrait; margin: 0; }
        * { box-sizing: border-box; }
        html, body { margin: 0; padding: 0; width: 210mm; min-height: 297mm; background: #fff; }
        body { font-family: Arial, sans-serif; }
        .pdf-page {
          width: 210mm;
          height: 297mm;
          page-break-after: always;
          display: flex;
          align-items: center;
          justify-content: center;
          background: #fff;
          overflow: hidden;
        }
        .pdf-page:last-child { page-break-after: auto; }
        .pdf-page img {
          width: 100%;
          height: 100%;
          object-fit: contain;
          display: block;
        }
      </style>
    </head><body>${pagesHtml}
      <script>
        window.onload = function () { setTimeout(function () { window.print(); }, 300); };
      </script>
    </body></html>`);
    win.document.close();
    this.showToast('📄 Opening print dialog for full edition PDF');
  },

  // ── Share ──
  shareArticle(platform) {
    if (!this.currentArticle) return;
    const title = this.currentArticle.headline || 'Vidyarthi Mitra E-Paper';
    const url = window.location.href;
    const text = encodeURIComponent(title + ' - ' + url);

    const urls = {
      whatsapp: `https://wa.me/?text=${text}`,
      twitter: `https://twitter.com/intent/tweet?text=${text}`,
      facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`,
    };

    if (urls[platform]) window.open(urls[platform], '_blank', 'width=600,height=400');
    else { navigator.clipboard?.writeText(url); this.showToast('Link copied!'); }
    this.trackEvent('share', { platform, article: title });
  },

  // ── GA4 Analytics ──
  trackEvent(action, params = {}) {
    if (typeof gtag === 'function') {
      gtag('event', action, { event_category: 'epaper', ...params });
    }
    // Also log for debug
    console.debug('[EP Analytics]', action, params);
  },

  // ── Video Player ──
  playArticleVideo(videoUrl) {
    if (!videoUrl) return;
    const panel = document.getElementById('epVideoOverlay');
    const player = document.getElementById('epVideoPlayer');
    if (!panel || !player) return;

    player.src = videoUrl;
    panel.classList.add('open');
    player.play();
    this.trackEvent('video_play', { url: videoUrl });
  },

  closeVideo() {
    const panel = document.getElementById('epVideoOverlay');
    const player = document.getElementById('epVideoPlayer');
    if (panel) panel.classList.remove('open');
    if (player) { player.pause(); player.src = ''; }
  },

  // ── Toast ──
  showToast(msg) {
    if (!this.el.toast) return;
    this.el.toast.textContent = msg;
    this.el.toast.classList.add('show');
    setTimeout(() => this.el.toast.classList.remove('show'), 2500);
  },

  // ── News Sidebar ──
  async loadNewsSidebar() {
    const container = document.getElementById('epNewsCards');
    if (!container) return;
    try {
      // Fetch a large pool so we can pick 2 per category
      const res = await fetch('/api/news?limit=60&category=all');
      const data = await res.json();
      const pool = data.articles || [];
      if (!pool.length) { container.innerHTML = '<p style="color:#6b7280;font-size:12px;padding:8px 0">No news available</p>'; return; }

      // Group by category, keep first 2 per category
      const PER_CAT = 2;
      const seen = {};
      const picked = [];
      for (const a of pool) {
        const cat = a.category || 'news';
        if (!seen[cat]) seen[cat] = 0;
        if (seen[cat] < PER_CAT) { picked.push(a); seen[cat]++; }
      }

      container.innerHTML = picked.map(a => {
        const thumb = a.image || a.image_url || '';
        const catLabel = (a.category || 'news').replace(/_/g, ' ');
        const ago = this._newsTimeAgo(a.pub_date);
        return `
          <a class="ep-news-card" href="${a.link || '#'}" target="_blank" rel="noopener">
            <div class="ep-news-card-thumb">
              ${thumb
                ? `<img src="${thumb}" alt="" loading="lazy" onerror="this.parentElement.innerHTML='<div class=ep-news-card-thumb-placeholder><i class=\\'fa fa-newspaper\\'></i></div>'">`
                : '<div class="ep-news-card-thumb-placeholder"><i class="fa fa-newspaper"></i></div>'}
            </div>
            <div class="ep-news-card-body">
              <div class="ep-news-card-cat">${catLabel}</div>
              <div class="ep-news-card-title">${a.title || ''}</div>
              <div class="ep-news-card-meta">${a.source_name || ''} · ${ago}</div>
            </div>
          </a>`;
      }).join('');
    } catch (e) {
      container.innerHTML = '';
    }
  },

  _newsTimeAgo(dateStr) {
    if (!dateStr) return '';
    try {
      const diff = Date.now() - new Date(dateStr).getTime();
      const m = Math.floor(diff / 60000);
      if (m < 1) return 'Just now';
      if (m < 60) return `${m}m ago`;
      const h = Math.floor(m / 60);
      if (h < 24) return `${h}h ago`;
      return `${Math.floor(h / 24)}d ago`;
    } catch { return ''; }
  },
};

// Initialize on DOM ready
window.EP = EP;
document.addEventListener('DOMContentLoaded', () => EP.init());