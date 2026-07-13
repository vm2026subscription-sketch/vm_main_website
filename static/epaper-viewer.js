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
  baseFitZoom: 1,
  _fitRaf: null,
  _resizeTimer: null,
  _viewerResizeObserver: null,
  isDragging: false,
  dragStart: { x: 0, y: 0, scrollLeft: 0, scrollTop: 0 },
  panOffset: { x: 0, y: 0 },
  editions: [],
  pages: [],
  articles: [],
  currentEdition: null,
  currentLanguage: '',
  mastheadUrl: '',
  ttsUtterance: null,
  ttsPlaying: false,
  _toastTimer: null,
  isEditionOpen: false,
  newsSidebarOpen: false,
  _newsSidebarLoaded: false,
  _landingShowAll: false,
  landingLanguageFilter: '',

  footerLinksDefault: [
    { key: 'search', icon: 'fa fa-magnifying-glass', url: '/epaper' },
    { key: 'whatsapp', icon: 'fab fa-whatsapp', url: 'https://wa.me/?text=Vidyarthi%20Mitra%20E-Paper' },
    { key: 'facebook', icon: 'fab fa-facebook-f', url: 'https://www.facebook.com/' },
    { key: 'x', icon: 'fab fa-x-twitter', url: 'https://x.com/' },
  ],

  // DOM refs
  el: {},

  init() {
    // Run FIRST — the history rewrite must not be blocked by any later init error.
    this._setupEditionBackTarget();
    this.cacheDOM();
    this.ensureArticleFeatureUI();
    this.cacheDOM();
    this.bindEvents();
    this.renderFooterLinks(this.footerLinksDefault);
    const shouldAutoOpen = document.body.dataset.epaperMode === 'edition';
    this.setReaderMode(shouldAutoOpen);
    this.setNewsSidebarState(false);

    if (shouldAutoOpen) {
      this.loadLatestEdition();
    }

    const initLang = (document.body.dataset.initialLanguage || '').trim().toLowerCase();
    if (initLang) this.landingLanguageFilter = initLang;

    this.loadEditions();
    this.startAutoRefreshPoll();
    this._initSwipeHint();
    this._initViewportFit();
  },

  // Make the Back button on a specific edition page (/epaper/YYYY-MM-DD) return
  // to the ePaper landing (/epaper) instead of the site home page. Inserts
  // /epaper directly behind the current edition entry in history.
  _setupEditionBackTarget() {
    if (!/^\/epaper\/\d{4}-\d{2}-\d{2}/.test(location.pathname)) return;
    const editionPath = location.pathname + location.search;
    try {
      const landingPath = location.hostname.startsWith('epaper.') ? '/' : '/epaper';
      history.replaceState(null, '', landingPath);
      history.pushState(null, '', editionPath);
      this._editionBackNav = true;
    } catch (e) { /* history unavailable — leave default behaviour */ }
  },

  setReaderMode(isOpen) {
    this.isEditionOpen = !!isOpen;
    document.body.classList.toggle('ep-edition-open', this.isEditionOpen);
    if (this.isEditionOpen) this.scheduleFitToWidth();
  },

  setNewsSidebarState(isOpen) {
    this.newsSidebarOpen = !!isOpen;
    this.el.main?.classList.toggle('news-sidebar-collapsed', !this.newsSidebarOpen);
    if (this.el.newsToggleBtn) {
      this.el.newsToggleBtn.setAttribute('aria-label', this.newsSidebarOpen ? 'Hide latest news' : 'Show latest news');
      this.el.newsToggleBtn.setAttribute('aria-pressed', this.newsSidebarOpen ? 'true' : 'false');
    }
    if (this.el.newsReopenBtn) {
      this.el.newsReopenBtn.setAttribute('aria-hidden', this.newsSidebarOpen ? 'true' : 'false');
    }
  },

  toggleNewsSidebar() {
    const opening = !this.newsSidebarOpen;
    this.setNewsSidebarState(opening);
    if (opening && !this._newsSidebarLoaded) {
      this._newsSidebarLoaded = true;
      this.loadNewsSidebar();
    }
  },

  _initSwipeHint() {
    if (window.innerWidth > 768) return;
    if (localStorage.getItem('ep_swipe_known')) return;
    const hint = document.getElementById('epSwipeHint');
    if (!hint) return;
    hint.classList.add('ep-swipe-hint-visible');
    hint.addEventListener('animationend', () => {
      hint.style.display = 'none';
      localStorage.setItem('ep_swipe_known', '1');
    }, { once: true });
  },

  async loadLatestEdition() {
    try {
      const _initEl = document.getElementById('__epInitialEdition__');
      const data = _initEl
        ? JSON.parse(_initEl.textContent)
        : await this._cachedFetch('/api/epaper/latest');
      this.applyEditionData(data, false);
    } catch (e) {
      // No published editions — show empty state
      this.setDate(new Date());
    }
  },

  // ── Auto-refresh poll ──────────────────────────────
  applyEditionData(data, updateUrl = true) {
    const d = data?.date ? new Date(`${data.date}T00:00:00`) : new Date();
    this.currentDate = d;
    this.updateDateButton(d);
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
    this.setReaderMode(true);
    this.showPage(1);
    this.registerEditionView();
    if (updateUrl && data?.date) {
      const editionUrl = `/epaper/${data.date}`;
      if (window.location.pathname !== editionUrl) {
        // Opening an edition FROM the /epaper list -> PUSH so Back returns to
        // the list. Switching between editions -> REPLACE so Back doesn't have
        // to step through every edition you viewed.
        const onLanding = window.location.pathname === '/' || window.location.pathname === '/epaper' || window.location.pathname === '/epaper/';
        if (onLanding) {
          history.pushState(null, '', editionUrl);
        } else {
          history.replaceState(null, '', editionUrl);
        }
      }
      this._editionBackNav = true;
    }
  },

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
        const isFreshPublishForCurrentDate = data.date === currentISO && (!this.currentEdition || !this.pages.length);
        if (data.date > currentISO || isFreshPublishForCurrentDate) {
          this.invalidateEditionCache(data.date);
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
    icon.className = 'ep-neb-icon'; icon.innerHTML = '<i class="fa fa-newspaper"></i>';
    const text = document.createElement('span');
    text.className = 'ep-neb-text'; text.textContent = 'New edition available: ';
    const strong = document.createElement('strong');
    strong.textContent = data.name || data.date;
    text.appendChild(strong);
    const loadBtn = document.createElement('button');
    loadBtn.className = 'ep-neb-load'; loadBtn.textContent = 'Load Now';
    loadBtn.onclick = () => EP._loadNewEdition(data.date);
    const closeBtn = document.createElement('button');
    closeBtn.className = 'ep-neb-close'; closeBtn.innerHTML = '<i class="fa fa-times"></i>';
    closeBtn.onclick = () => banner.remove();
    banner.append(icon, text, loadBtn, closeBtn);
    document.body.appendChild(banner);
  },

  _loadNewEdition(date) {
    document.getElementById('epNewEditionBanner')?.remove();
    this.invalidateEditionCache(date);
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

  // Return Cloudinary URL as-is — PNG is already lossless, no transformation needed
  optimizeCloudinaryUrl(url, width = 400) {
    return url || '';
  },

  invalidateEditionCache(date = '') {
    delete this._apiCache['/api/epaper/latest'];
    delete this._apiCache['/api/epaper/editions'];
    Object.keys(this._apiCache).forEach(key => {
      if (key.startsWith('/api/epaper/edition/')) delete this._apiCache[key];
      if (key.startsWith('/api/epaper/editions-by-date/')) delete this._apiCache[key];
    });
    if (date) {
      delete this._apiCache[`/api/epaper/edition/${date}`];
      delete this._apiCache[`/api/epaper/editions-by-date/${date}`];
    }
  },

  ensureArticleFeatureUI() {
    const aiBar = document.getElementById('epTtsPrompt');
    const summarizeTab = document.querySelector('.ep-ai-tab[data-tab="summarize"]');
    if (aiBar && summarizeTab && !document.querySelector('.ep-ai-tab[data-tab="translate"]')) {
      const translateTab = document.createElement('button');
      translateTab.className = 'ep-ai-tab';
      translateTab.dataset.tab = 'translate';
      translateTab.innerHTML = '<i class="fa fa-language"></i><span>Translate</span>';
      aiBar.insertBefore(translateTab, summarizeTab);
    }

    const summarizePane = document.querySelector('.ep-ai-content[data-tab="summarize"]');
    if (summarizePane && !document.getElementById('epTranslateOutput')) {
      const translatePane = document.createElement('div');
      translatePane.className = 'ep-ai-content';
      translatePane.dataset.tab = 'translate';
      translatePane.innerHTML = `
        <button class="ep-ai-close" onclick="EP.closeAiPanel()" title="Close" aria-label="Close translate panel">&times;</button>
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px;">
          <label for="epTranslateSelect" style="font-size:12px;font-weight:600;color:#6b7280;">Language</label>
          <select id="epTranslateSelect" class="ep-tts-voice-select" title="Select translation language">
            <option value="en">English</option>
            <option value="hi">Hindi</option>
            <option value="mr">Marathi</option>
            <option value="gu">Gujarati</option>
            <option value="bn">Bengali</option>
            <option value="ta">Tamil</option>
            <option value="te">Telugu</option>
            <option value="kn">Kannada</option>
            <option value="ml">Malayalam</option>
            <option value="ur">Urdu</option>
          </select>
        </div>
        <div class="ep-summary-box" id="epTranslateOutput">
          <p>Click Translate to view this article in another language.</p>
        </div>
      `;
      summarizePane.parentNode.insertBefore(translatePane, summarizePane);
    }

    const articleDate = document.getElementById('epArtDate');
    if (articleDate && !document.getElementById('epVideoBtn')) {
      const videoBtn = document.createElement('button');
      videoBtn.id = 'epVideoBtn';
      videoBtn.className = 'ep-art-play-btn';
      videoBtn.type = 'button';
      videoBtn.style.display = 'none';
      videoBtn.style.marginTop = '10px';
      videoBtn.innerHTML = '<i class="fa fa-circle-play"></i> <span>Watch Video</span>';
      articleDate.insertAdjacentElement('afterend', videoBtn);
    }
  },

  cacheDOM() {
    this.el = {
      header: document.getElementById('epHeader'),
      collapseBtn: document.getElementById('epCollapseBtn'),
      nav: document.getElementById('epNav'),
      navList: document.getElementById('epNavList'),
      main: document.getElementById('epMain'),
      newsToggleBtn: document.getElementById('epNewsToggleBtn'),
      newsReopenBtn: document.getElementById('epNewsReopenBtn'),
      editionLanding: document.getElementById('epEditionLanding'),
      editionFilterButtons: document.querySelectorAll('.ep-edition-filter-btn'),
      editionGrid: document.getElementById('epEditionGrid'),
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
    this.el.dateBtn?.addEventListener('click', async () => await this.toggleCalendar());
    this.el.newsToggleBtn?.addEventListener('click', () => this.toggleNewsSidebar());
    this.el.newsReopenBtn?.addEventListener('click', () => this.toggleNewsSidebar());
    this.el.editionFilterButtons?.forEach(btn => {
      btn.addEventListener('click', () => this.setLandingLanguageFilter(btn.dataset.language || ''));
    });
    this.el.calendarOverlay?.addEventListener('click', async (e) => {
      if (e.target === this.el.calendarOverlay) await this.toggleCalendar(false);
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
    this.el.fitPage?.addEventListener('click', () => this.fitToWidth());
    this.el.fullscreen?.addEventListener('click', () => this.toggleFullscreen());

    // Drag-to-pan when zoomed in
    const viewer = this.el.viewer;
    if (viewer) {
      viewer.addEventListener('mousedown', (e) => {
        if (this.zoom <= this.getMinZoom() + 0.01) return;
        if (e.button !== 0) return;
        this.isDragging = true;
        this.dragStart = { x: e.clientX, y: e.clientY, scrollLeft: viewer.scrollLeft, scrollTop: viewer.scrollTop };
        viewer.classList.add('is-panning');
        e.preventDefault();
      });

      document.addEventListener('mousemove', (e) => {
        if (!this.isDragging) return;
        const dx = e.clientX - this.dragStart.x;
        const dy = e.clientY - this.dragStart.y;
        viewer.scrollLeft = this.dragStart.scrollLeft - dx;
        viewer.scrollTop = this.dragStart.scrollTop - dy;
      });

      document.addEventListener('mouseup', () => {
        if (!this.isDragging) return;
        this.isDragging = false;
        viewer.classList.remove('is-panning');
      });

      viewer.addEventListener('mouseleave', () => {
        if (this.isDragging) {
          this.isDragging = false;
          viewer.classList.remove('is-panning');
        }
      });
    }

    // Scroll buttons — scroll amount scales with zoom level
    this.el.scrollUp?.addEventListener('click', () => {
      const viewer = this.el.viewer;
      if (viewer) viewer.scrollBy({ top: -(250 * this.zoom), behavior: 'smooth' });
      window.scrollBy({ top: -(250 * this.zoom), behavior: 'smooth' });
    });
    this.el.scrollDown?.addEventListener('click', () => {
      const viewer = this.el.viewer;
      if (viewer) viewer.scrollBy({ top: 250 * this.zoom, behavior: 'smooth' });
      window.scrollBy({ top: 250 * this.zoom, behavior: 'smooth' });
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
      this.scheduleFitToWidth();
    });

    this.el.pageImg?.addEventListener('load', () => this.scheduleFitToWidth());

    // Reset zoom when navigating away
    window.addEventListener('pagehide', () => {
      document.documentElement.style.zoom = '';
      const paper = document.getElementById('epPaper');
      if (paper) paper.style.zoom = '';
      const container = document.getElementById('epPageContainer');
      if (container) container.style.zoom = '';
      const grid = document.getElementById('epBlockGrid');
      if (grid) grid.style.zoom = '';
    });

    // Prevent browser zoom anywhere on the ePaper page; route ALL Ctrl+scroll to custom zoom
    document.addEventListener('wheel', (e) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const delta = e.deltaY < 0 ? 0.1 : -0.1;
        this.setZoom(this.zoom + delta);
      }
    }, { passive: false });

    // Viewer wheel zoom (Ctrl+scroll handled above) + normal scroll passthrough
    const v = this.el.viewer;
    if (v) {

      // Pinch-to-zoom on touch
      let _lastDist = null;
      let _pinchGesture = false;
      v.addEventListener('touchstart', (e) => {
        if (e.touches.length === 2) {
          _pinchGesture = true;
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
      v.addEventListener('touchend', (e) => {
        if (e.touches.length < 2) _lastDist = null;
        if (e.touches.length === 0) _pinchGesture = false;
      }, { passive: true });
      v.addEventListener('touchcancel', () => {
        _lastDist = null;
        _pinchGesture = false;
      }, { passive: true });

      v._epWasPinching = () => _pinchGesture;
    }

    // Swipe left/right to change pages (single finger, only when not zoomed)
    {
      const rc = document.getElementById('epReaderContainer');
      let _swX = null, _swY = null, _swStartTs = 0;
      if (rc) {
        rc.addEventListener('touchstart', (e) => {
          if (e.touches.length !== 1) return;
          if (v && typeof v._epWasPinching === 'function' && v._epWasPinching()) return;
          _swX = e.touches[0].clientX;
          _swY = e.touches[0].clientY;
          _swStartTs = Date.now();
        }, { passive: true });
        rc.addEventListener('touchend', (e) => {
          if (_swX === null) return;
          const fitLevel = this.isMobileReader() ? this.baseFitZoom : 1;
          if (this.zoom > fitLevel + 0.05) { _swX = null; _swStartTs = 0; return; }
          const dx = e.changedTouches[0].clientX - _swX;
          const dy = e.changedTouches[0].clientY - _swY;
          const dt = Date.now() - _swStartTs;
          _swX = null;
          _swStartTs = 0;
          if (Math.abs(dx) < 72 || Math.abs(dx) <= Math.abs(dy) * 1.5 || dt > 700) return;
          dx < 0 ? this.changePage(1) : this.changePage(-1);
        }, { passive: true });
      }
    }

    // Double-tap on viewer to toggle zoom in/out
    {
      let _lastTap = 0;
      const vEl = this.el.viewer;
      if (vEl) {
        vEl.addEventListener('touchend', (e) => {
          if (e.changedTouches.length !== 1) return;
          if (typeof vEl._epWasPinching === 'function' && vEl._epWasPinching()) return;
          const now = Date.now();
          if (now - _lastTap < 300) {
            const fitLevel = this.isMobileReader() ? this.baseFitZoom : 1;
            const zoomInLevel = Math.min(2, this.maxZoom);
            this.setZoom(this.zoom > fitLevel + 0.1 ? fitLevel : zoomInLevel);
          }
          _lastTap = now;
        }, { passive: true });
      }
    }

    // Article panel back
    this.el.articleBack?.addEventListener('click', () => this.closeArticle());
    // Browser / phone Back button:
    //   1) if an article is open  -> close it (stay on the edition page)
    //   2) if Back lands on /epaper -> load the ePaper landing instead of the
    //      site home (the back target is set up by _setupEditionBackTarget()).
    window.addEventListener('popstate', () => {
      const panelOpen = this.el.articlePanel?.classList.contains('open');
      if (this.currentArticle || panelOpen) { this.closeArticle(true); return; }
      const isOnSubdomain = location.hostname.startsWith('epaper.');
      const landingPath = isOnSubdomain ? '/' : '/epaper';
      if (this._editionBackNav && (location.pathname === landingPath || location.pathname === '/epaper' || location.pathname === '/epaper/')) {
        window.location.href = landingPath;
      }
    });

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
    document.getElementById('epVideoBtn')?.addEventListener('click', () => {
      const videoUrl = this.currentArticle?.video_url || this.currentArticle?.video || '';
      this.playArticleVideo(videoUrl);
    });

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

    // Share Toolbar Menu dropdown toggle
    const shareBtn = document.getElementById('epShareBtn');
    const shareDropdown = document.getElementById('epShareDropdown');
    if (shareBtn && shareDropdown) {
      shareBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        shareDropdown.classList.toggle('show');
      });
      document.addEventListener('click', (e) => {
        if (!shareDropdown.contains(e.target) && !shareBtn.contains(e.target)) {
          shareDropdown.classList.remove('show');
        }
      });
    }
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
  updateDateButton(d) {
    const opts = { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' };
    if (this.el.dateBtnText) {
      this.el.dateBtnText.textContent = d.toLocaleDateString('en-IN', opts);
    }
  },

  setDate(d) {
    this.currentDate = d;
    this.updateDateButton(d);
    this.currentPage = 1;
    // Clear API cache when switching dates so fresh data loads
    const iso = this.formatDateISO(d);
    delete this._apiCache[`/api/epaper/edition/${iso}`];
    delete this._apiCache['/api/epaper/editions'];
    this.loadEditionForDate(d);
  },

  setLandingLanguageFilter(language = '') {
    this.landingLanguageFilter = language;
    this._landingShowAll = false;
    this.el.editionFilterButtons?.forEach(btn => {
      btn.classList.toggle('active', (btn.dataset.language || '') === this.landingLanguageFilter);
    });
    this.renderEditionLanding();
  },

  async renderEditionLanding() {
    const grid = this.el.editionGrid;
    if (!grid) return;

    const selectedLanguage = (this.landingLanguageFilter || '').trim().toLowerCase();
    const all = (Array.isArray(this.editions) ? this.editions : [])
      .filter(edition => edition && edition.published !== false)
      .filter(edition => !selectedLanguage || (edition.language || '').trim().toLowerCase() === selectedLanguage)
      .sort((a, b) => (b.date || '').localeCompare(a.date || ''));

    let published, hasMore;
    if (this._landingShowAll) {
      published = all;
      hasMore = false;
    } else if (selectedLanguage) {
      // Language filter active: show latest 3 of that language
      published = all.slice(0, 3);
      hasMore = all.length > 3;
    } else {
      // No filter: show latest 1 per language (Hindi, English, Marathi)
      const seenLangs = new Set();
      published = [];
      for (const e of all) {
        const lang = (e.language || 'Hindi').toLowerCase();
        if (!seenLangs.has(lang)) {
          seenLangs.add(lang);
          published.push(e);
        }
        if (published.length >= 3) break;
      }
      hasMore = all.length > published.length;
    }

    if (!published.length) {
      const emptyLabel = this.landingLanguageFilter || 'published';
      grid.innerHTML = `<div class="ep-edition-empty">No ${emptyLabel} editions are available right now.</div>`;
      if (!this.currentDate) {
        this.currentDate = new Date();
        this.updateDateButton(this.currentDate);
      }
      return;
    }

    if (!this.currentDate) {
      this.currentDate = new Date(`${published[0].date}T00:00:00`);
      this.updateDateButton(this.currentDate);
    }

    const visibleEntries = published.map((edition) => {
      const _prevSrc = edition.preview_image_url || edition.masthead_image_url || '';
      const previewUrl = _prevSrc ? this.optimizeCloudinaryUrl(_prevSrc, 640) : '';
      return {
        edition,
        previewUrl,
        totalPages: edition.total_pages || 0,
      };
    }).filter(entry => entry.totalPages > 0 || entry.previewUrl);

    if (!visibleEntries.length) {
      grid.innerHTML = '<div class="ep-edition-empty">No published editions with preview pages are available right now.</div>';
      return;
    }

    grid.innerHTML = '';

    visibleEntries.forEach(({ edition, previewUrl }) => {
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'ep-edition-card';
      card.dataset.date = edition.date || '';
      card.dataset.language = edition.language || '';

      const cover = document.createElement('div');
      cover.className = 'ep-edition-card-cover';

      const previewFrame = document.createElement('div');
      previewFrame.className = 'ep-edition-card-preview-frame';

      if (previewUrl) {
        const preview = document.createElement('img');
        preview.className = 'ep-edition-card-preview';
        preview.src = previewUrl;
        preview.alt = `${(edition.name || 'Edition').trim()} preview`;
        preview.loading = 'lazy';
        previewFrame.appendChild(preview);
      } else {
        const placeholder = document.createElement('div');
        placeholder.className = 'ep-edition-card-preview-placeholder';
        previewFrame.appendChild(placeholder);
      }

      cover.appendChild(previewFrame);

      const body = document.createElement('div');
      body.className = 'ep-edition-card-body';

      const title = document.createElement('div');
      title.className = 'ep-edition-card-title';
      title.textContent = this.getEditionCardTitle(edition);

      const subtitle = document.createElement('div');
      subtitle.className = 'ep-edition-card-subtitle';
      subtitle.textContent = this.formatEditionCardDate(edition.date);

      const langLabel = (edition.language || 'Edition').trim();
      const langKey = langLabel.toLowerCase();

      const language = document.createElement('div');
      language.className = `ep-edition-card-language ${this.getEditionLanguageClass(langLabel)}`;
      language.dataset.lang = langKey;
      language.textContent = langLabel;

      body.append(title, subtitle, language);

      card.append(cover, body);
      card.addEventListener('click', async () => {
        await this.openEditionCard(edition.date, edition.language || '');
      });

      grid.appendChild(card);
    });

    if (hasMore) {
      const remaining = all.length - published.length;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'ep-load-more-btn';
      btn.textContent = `Load ${remaining} more edition${remaining !== 1 ? 's' : ''}`;
      btn.addEventListener('click', () => {
        this._landingShowAll = true;
        this.renderEditionLanding();
      });
      grid.appendChild(btn);
    }
  },

  getEditionRequestUrl(edition) {
    const date = edition?.date || '';
    const lang = edition?.language || '';
    return lang
      ? `/api/epaper/edition/${date}?lang=${encodeURIComponent(lang)}`
      : `/api/epaper/edition/${date}`;
  },

  async fetchEditionCardDetail(edition) {
    try {
      const url = this.getEditionRequestUrl(edition);
      return await this._cachedFetch(url);
    } catch (e) {
      return null;
    }
  },

  getEditionCardPreviewUrl(detail) {
    const firstPage = detail?.pages?.[0];
    if (firstPage) {
      if (firstPage.page_image_url) return this.optimizeCloudinaryUrl(firstPage.page_image_url, 640);
      if (firstPage.image_path) return this.optimizeCloudinaryUrl(firstPage.image_path, 640);
    }
    return detail?.masthead_image_url ? this.optimizeCloudinaryUrl(detail.masthead_image_url, 640) : '';
  },

  getEditionCardTitle(edition) {
    const rawName = (edition?.name || '').trim();
    if (rawName) {
      return `${rawName} ${edition.language || ''}`.trim();
    }
    return `VidyarthiMitra ${edition.language || 'Edition'}`.trim();
  },

  getEditionLanguageClass(language) {
    const key = (language || '').trim().toLowerCase();
    if (key.includes('english')) return 'ep-lang-english';
    if (key.includes('hindi')) return 'ep-lang-hindi';
    if (key.includes('marathi')) return 'ep-lang-marathi';
    return 'ep-lang-default';
  },

  formatEditionCardDate(date) {
    if (!date) return 'Date';
    try {
      return new Date(`${date}T00:00:00`).toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      });
    } catch (e) {
      return date;
    }
  },

  async openEditionCard(date, lang = '') {
    if (!date) return;
    const url = lang
      ? `/api/epaper/edition/${date}?lang=${encodeURIComponent(lang)}`
      : `/api/epaper/edition/${date}`;
    this.setReaderMode(true);
    this.showLoadingSkeleton();
    try {
      const data = lang
        ? await fetch(url).then(r => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        : await this._cachedFetch(url);
      this.applyEditionData(data, true);
    } catch (e) {
      console.warn('Edition open error:', e);
      this.showDemoPage();
    }
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
    el.style.cssText = '';
    el.innerHTML = '';
    if (masthead) masthead.style.cssText = '';
    if (viewer) viewer.style.paddingTop = '';
    if (grid) grid.style.marginTop = '';
    if (pageNum === 1) this.applyMastheadImage(this.mastheadUrl || '');
    else document.body.classList.remove('has-masthead');
  },

  resolveFooterLinks(rawLinks) {
    const base = this.footerLinksDefault.map(item => ({ ...item }));
    if (!Array.isArray(rawLinks)) return base;
    rawLinks.forEach(item => {
      const key = item?.key || '';
      const target = base.find(link => link.key === key);
      if (target) {
        if (item.url) target.url = item.url;
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
      const href = item.url || '#';
      const label = item.key || 'link';
      return `<a class="ep-footer-link" href="${href}" target="_blank" rel="noopener" aria-label="${label}"><i class="${item.icon}"></i></a>`;
    }).join('');
  },

  formatDateISO(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  },

  getUTCDateKey(d) {
    const safe = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate(), 12));
    return [
      safe.getUTCFullYear(),
      String(safe.getUTCMonth() + 1).padStart(2, '0'),
      String(safe.getUTCDate()).padStart(2, '0'),
    ].join('-');
  },

  // ── Calendar ──
  calendarMonth: null,
  calendarYear: null,

  async toggleCalendar(show) {
    const overlay = this.el.calendarOverlay;
    if (!overlay) return;
    const isOpen = overlay.classList.contains('open');
    if (show === false || (show === undefined && isOpen)) {
      overlay.classList.remove('open');
    } else {
      this.calendarMonth = this.currentDate.getMonth();
      this.calendarYear = this.currentDate.getFullYear();
      // Ensure editions are loaded so days with editions can be marked
      if (!Array.isArray(this.editions) || this.editions.length === 0) {
        try { await this.loadEditions(); } catch (e) { /* ignore */ }
      }
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
    const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    if (this.el.calTitle) this.el.calTitle.textContent = `${months[this.calendarMonth]} ${this.calendarYear}`;

    const grid = this.el.calGrid;
    if (!grid) return;
    grid.innerHTML = '';

    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    dayNames.forEach(d => {
      const el = document.createElement('div');
      el.className = 'ep-cal-day-name';
      el.textContent = d;
      grid.appendChild(el);
    });

    const firstDay = new Date(Date.UTC(this.calendarYear, this.calendarMonth, 1)).getUTCDay();
    const daysInMonth = new Date(Date.UTC(this.calendarYear, this.calendarMonth + 1, 0)).getUTCDate();
    const todayKey = this.getUTCDateKey(new Date());
    const selectedKey = this.currentDate ? this.getUTCDateKey(this.currentDate) : '';

    for (let i = 0; i < firstDay; i++) {
      const el = document.createElement('div');
      grid.appendChild(el);
    }

    for (let day = 1; day <= daysInMonth; day++) {
      const el = document.createElement('div');
      el.className = 'ep-cal-day';
      el.textContent = day;

      const d = new Date(Date.UTC(this.calendarYear, this.calendarMonth, day));
      const utcKey = this.getUTCDateKey(d);
      const hasEdition = this.editions.some(e => e.date === utcKey && e.published !== false);

      if (utcKey === todayKey) el.classList.add('today');
      if (utcKey === selectedKey) el.classList.add('selected');

      // Only days that actually have a published edition are selectable.
      // Every other date (dates we didn't publish on, and future dates) is
      // disabled/greyed — you publish weekly, not daily.
      if (hasEdition) {
        el.classList.add('has-edition');
        el.addEventListener('click', async () => {
          this.setDate(new Date(this.calendarYear, this.calendarMonth, day));
          await this.toggleCalendar(false);
        });
      } else {
        el.classList.add('disabled');
      }
      grid.appendChild(el);
    }
  },

  // ── Data Loading ──
  async loadEditions() {
    try {
      const data = await this._cachedFetch('/api/epaper/editions');
      this.editions = Array.isArray(data) ? data : (data.editions || data.results || []);
    } catch (e) {
      console.warn('Could not load editions:', e);
      this.editions = [];
    }
    this.renderEditionLanding();
  },

  // ── Edition view counter ──
  formatViews(n) {
    n = Number(n) || 0;
    if (n >= 1000000) return (n / 1000000).toFixed(n % 1000000 ? 1 : 0) + 'M';
    if (n >= 1000)    return (n / 1000).toFixed(n % 1000 ? 1 : 0) + 'K';
    return String(n);
  },

  updateViewBadge(views) {
    const badge = document.getElementById('epViews');
    if (!badge) return;
    const num = badge.querySelector('.ep-views-num');
    if (num) num.textContent = this.formatViews(views);
    badge.style.display = 'inline-flex';
  },

  // Count this edition open (by date + language) and show the running total.
  // Only counts once per browser session to avoid refresh-spam inflating views.
  async registerEditionView() {
    const ed = this.currentEdition;
    if (!ed || !ed.date) return;
    const lang = ed.language || this.currentLanguage || '';
    const lsKey = `epv_${ed.date}_${lang}`;
    const THROTTLE_MS = 24 * 60 * 60 * 1000; // 24 hours
    const lastSeen = parseInt(localStorage.getItem(lsKey) || '0');
    const alreadyCounted = (Date.now() - lastSeen) < THROTTLE_MS;
    try {
      let views;
      if (alreadyCounted) {
        // Viewed within last 24h — fetch count without incrementing
        const res = await fetch(
          `/api/epaper/edition/${encodeURIComponent(ed.date)}/views?lang=${encodeURIComponent(lang)}`
        );
        if (!res.ok) return;
        const data = await res.json();
        views = data?.views;
      } else {
        const res = await fetch(
          `/api/epaper/edition/${encodeURIComponent(ed.date)}/view?lang=${encodeURIComponent(lang)}`,
          { method: 'POST', keepalive: true }
        );
        if (!res.ok) return;
        const data = await res.json();
        views = data?.views;
        localStorage.setItem(lsKey, String(Date.now()));
      }
      if (typeof views === 'number') this.updateViewBadge(views);
    } catch (e) { /* ignore network errors */ }
  },

  async loadEditionForDate(d) {
    const iso = this.formatDateISO(d);

    // Show loading skeleton immediately
    this.setReaderMode(true);
    this.showLoadingSkeleton();

    try {
      const data = await this._cachedFetch(`/api/epaper/edition/${iso}`);
      this.applyEditionData(data, true);
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
    this.setReaderMode(true);
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
    this.setReaderMode(true);
    this.showLoadingSkeleton();
    try {
      const data = await fetch(url).then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      });
      this.applyEditionData(data, true);
      this.el.navList?.querySelectorAll('.ep-nav-item').forEach(n => {
        n.classList.toggle('active', n.dataset.lang === this.currentLanguage);
      });
    } catch (e) {
      this.showToast('Edition not available');
    }
  },

  // ── Page Display ──
  showPage(num) {
    this.currentPage = Math.max(1, Math.min(num, this.totalPages));
    this.panOffset = { x: 0, y: 0 };
    this._resetPageScroll();
    this.updatePager();

    const page = this.pages[this.currentPage - 1];
    if (!page) return;

    this.updatePageHeader(page, this.currentPage);

    const viewer = this.el.viewer || document.getElementById('epViewer');
    if (viewer?.animate) {
      viewer.animate([{ opacity: 0.72 }, { opacity: 1 }], { duration: 180, easing: 'ease-out' });
    }
    document.getElementById('epEmptyState')?.style.setProperty('display', 'none');

    // Check if page uses new block format
    if (page.blocks && page.blocks.length > 0) {
      // Hide legacy elements
      if (this.el.pageContainer) this.el.pageContainer.style.display = 'none';
      this.renderBlockGrid(page.blocks, viewer, page.page_image_url || page.image_path || '');
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
          if (this.el.pageImg.complete) this.scheduleFitToWidth();
        }
        if (this.el.hotspotsLayer) this.el.hotspotsLayer.style.display = 'block';
        this.renderHotspots(page.articles || []);
      }

      const grid = document.getElementById('epBlockGrid');
      if (grid) grid.style.display = 'none';
    }

    // Scroll viewer to top when switching pages
    this._resetPageScroll();

    // Update thumbnail active state
    this.updateThumbActive();
    this.scheduleFitToWidth();
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
    if (block?.type === 'shape') return 'shape';
    return 'article';
  },

  buildShapeMarkup(block) {
    const fill = block.no_fill ? 'none' : (block.fill_color || '#cccccc');
    const stroke = block.stroke_color || '#111827';
    const sw = block.stroke_width || 0;
    const op = (block.opacity ?? 100) / 100;
    const cr = block.corner_radius || 0;
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
      const br = block.border_radius ?? 0;
      // Article boxes no longer draw a border in the reader view (the red boxes
      // looked bad over the page). The card stays fully clickable — link/hotspot
      // behaviour is unchanged; only the visible border is hidden.
      const borderCSS = '';
      const baseStyle = `position:absolute;left:${x}%;top:${y}%;width:${w}%;height:${h}%;border-radius:${br}px;${borderCSS}overflow:hidden;`;

      if (type === 'divider') {
        return `
              <div class="ep-block-divider-card" style="${baseStyle}">
                ${this.buildDividerMarkup(block)}
              </div>
            `;
      }

      if (type === 'shape') {
        const gotoPage = block.goto_page;
        if (gotoPage) {
          return `
                <div style="${baseStyle}cursor:pointer;" onclick="EP.showPage(${gotoPage})" title="Go to page ${gotoPage}">
                  ${this.buildShapeMarkup(block)}
                </div>
              `;
        }
        return `
              <div style="${baseStyle}pointer-events:none;">
                ${this.buildShapeMarkup(block)}
              </div>
            `;
      }

      const gotoPage = block.goto_page;
      const articleIndex = this.articles.push({
        ...block,
        headline: block.headline,
        sub_headline: block.sub_headline,
        body_text: block.body_text,
        body_html: block.body_html || '',
        category_label: block.category_label,
        article_image_url: block.image_url,
        gallery: this.filterGalleryImages(block.gallery || []),
        has_video: !!(block.has_video || block.video_url || block.video),
        video_url: block.video_url || block.video || '',
      }) - 1;

      // Optimize Cloudinary images: smaller width for card thumbnails
      const imgSrc = hasImg ? this.optimizeCloudinaryUrl(block.image_url, 400) : '';
      const clickHandler = gotoPage
        ? `onclick="EP.showPage(${gotoPage})" title="Go to page ${gotoPage}"`
        : `onclick="EP.openArticle(${articleIndex})" title="${block.headline || ''}"`;

      return `
            <div class="ep-block-card" ${clickHandler} style="${baseStyle}cursor:pointer;">
              ${hasImg ? `<img class="ep-block-img" src="${imgSrc}" alt="${block.headline || ''}" draggable="false" loading="lazy" style="width:100%;height:100%;object-fit:contain;display:block;">` : ''}
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
  isMobileReader() {
    return window.matchMedia('(max-width: 900px)').matches;
  },

  getViewerContentWidth() {
    if (this.isMobileReader() && this.isEditionOpen) {
      const paper = document.getElementById('epPaper');
      if (paper && paper.clientWidth > 0) return paper.clientWidth;
    }

    const viewer = this.el.viewer;
    if (!viewer) return 0;
    const style = getComputedStyle(viewer);
    const pad = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
    return Math.max(0, viewer.clientWidth - pad);
  },

  getActiveContentEl() {
    const grid = document.getElementById('epBlockGrid');
    if (grid && grid.style.display !== 'none') return grid;
    if (this.el.pageContainer && this.el.pageContainer.style.display !== 'none') {
      return this.el.pageContainer;
    }
    return this.el.pageContainer || grid || null;
  },

  getMinZoom() {
    return this.isMobileReader() ? this.baseFitZoom : this.minZoom;
  },

  _isReaderFullscreen() {
    const reader = document.getElementById('epReaderContainer');
    return !!(document.fullscreenElement && reader && document.fullscreenElement === reader);
  },

  _getScrollContainer() {
    if (this._isReaderFullscreen() && this.el.viewer) return this.el.viewer;
    if (document.body.classList.contains('ep-fullscreen') && this.el.viewer) return this.el.viewer;
    return window;
  },

  _resetPageScroll() {
    const viewer = this.el.viewer;
    if (viewer) {
      viewer.scrollLeft = 0;
      viewer.scrollTop = 0;
    }
    const reader = document.getElementById('epReaderContainer');
    if (reader) {
      reader.scrollLeft = 0;
      reader.scrollTop = 0;
    }
    if (this._isReaderFullscreen()) {
      window.scrollTo(0, 0);
    }
  },

  _initViewportFit() {
    const onChange = () => this._onViewportChange();
    window.addEventListener('resize', onChange);
    window.addEventListener('orientationchange', onChange);

    if (typeof ResizeObserver !== 'undefined') {
      this._viewerResizeObserver = new ResizeObserver(onChange);
      if (this.el.viewer) this._viewerResizeObserver.observe(this.el.viewer);
      const reader = document.getElementById('epReaderContainer');
      const paper = document.getElementById('epPaper');
      if (reader) this._viewerResizeObserver.observe(reader);
      if (paper) this._viewerResizeObserver.observe(paper);
    }
  },

  _onViewportChange() {
    clearTimeout(this._resizeTimer);
    this._resizeTimer = setTimeout(() => {
      if (!this.isEditionOpen) return;
      const fitLevel = this.getMinZoom();
      if (this.zoom <= fitLevel + 0.05) {
        this.fitToWidth();
      }
    }, 150);
  },

  scheduleFitToWidth() {
    if (this._fitRaf) cancelAnimationFrame(this._fitRaf);
    this._fitRaf = requestAnimationFrame(() => {
      this._fitRaf = requestAnimationFrame(() => {
        this._fitRaf = null;
        this.fitToWidth();
      });
    });
  },

  fitToWidth() {
    if (!this.isEditionOpen) return;

    if (!this.isMobileReader()) {
      this.zoom = 1;
      this.baseFitZoom = 1;
      this.applyTransform();
      this._updateZoomButtons();
      this._resetPageScroll();
      return;
    }

    const contentW = this.getViewerContentWidth();
    if (!contentW) return;

    this.zoom = 1;
    this.baseFitZoom = 1;
    this.applyTransform();
    this._correctUnderfill(contentW);
    this._updateZoomButtons();
    if (this.zoom <= this.getMinZoom() + 0.05) {
      this._resetPageScroll();
    }
  },

  _correctUnderfill(targetW) {
    const el = this.getActiveContentEl();
    if (!el) return;

    const actualW = el.getBoundingClientRect().width;
    if (actualW > 0 && actualW < targetW * 0.97) {
      const boost = targetW / actualW;
      this.zoom = Math.min(this.maxZoom, boost);
      this.baseFitZoom = this.zoom;
      this.applyTransform();
    }
  },

  _updateZoomButtons() {
    const minZ = this.getMinZoom();
    if (this.el.zoomOut) this.el.zoomOut.disabled = this.zoom <= minZ + 0.01;
    if (this.el.zoomIn) this.el.zoomIn.disabled = this.zoom >= this.maxZoom;
  },

  setZoom(level) {
    const oldZoom = this.zoom;
    const minZ = this.getMinZoom();
    const newZoom = Math.max(minZ, Math.min(this.maxZoom, level));
    if (oldZoom === newZoom) return;

    const contentEl = this.getActiveContentEl();
    if (!contentEl) {
      this.zoom = newZoom;
      this.applyTransform();
      this._updateZoomButtons();
      return;
    }

    // Determine the scroll container and viewport dimensions
    const scrollContainer = this._getScrollContainer();

    let screenCenterX;
    let screenCenterY;
    if (scrollContainer === window) {
      screenCenterX = window.innerWidth / 2;
      screenCenterY = window.innerHeight / 2;
    } else {
      const scRect = scrollContainer.getBoundingClientRect();
      screenCenterX = scRect.left + scrollContainer.clientWidth / 2;
      screenCenterY = scRect.top + scrollContainer.clientHeight / 2;
    }

    const containerRectBefore = contentEl.getBoundingClientRect();
    if (!containerRectBefore.width) {
      this.zoom = newZoom;
      this.applyTransform();
      this._updateZoomButtons();
      return;
    }

    const ratioX = (screenCenterX - containerRectBefore.left) / containerRectBefore.width;
    const ratioY = (screenCenterY - containerRectBefore.top) / containerRectBefore.height;

    this.zoom = newZoom;
    this.applyTransform();

    const containerRectAfter = contentEl.getBoundingClientRect();
    const newPointXOnScreen = containerRectAfter.left + (containerRectAfter.width * ratioX);
    const newPointYOnScreen = containerRectAfter.top + (containerRectAfter.height * ratioY);

    const diffX = newPointXOnScreen - screenCenterX;
    const diffY = newPointYOnScreen - screenCenterY;

    if (scrollContainer === window) {
      window.scrollBy({ left: diffX, top: diffY, behavior: 'auto' });
    } else {
      scrollContainer.scrollLeft += diffX;
      scrollContainer.scrollTop += diffY;
    }

    this._updateZoomButtons();
  },

  applyTransform() {
    const z = this.zoom;
    const contentW = this.getViewerContentWidth();
    const usePixelWidth = this.isMobileReader() && contentW > 0;
    const targetWidth = usePixelWidth ? `${contentW * z}px` : `${z * 100}%`;
    const fitLevel = this.getMinZoom();

    document.documentElement.style.zoom = '';
    const paper = document.getElementById('epPaper');
    if (paper) paper.style.zoom = '';

    if (this.el.viewer) {
      const needsPan = z > fitLevel + 0.01;
      if (needsPan) {
        this.el.viewer.style.justifyContent = 'flex-start';
        this.el.viewer.classList.add('can-pan');
      } else {
        this.el.viewer.style.justifyContent = this.isMobileReader() ? 'flex-start' : 'center';
        this.el.viewer.classList.remove('can-pan');
      }
    }

    const grid = document.getElementById('epBlockGrid');
    const container = this.el.pageContainer;

    if (grid) {
      grid.style.zoom = '';
      grid.style.width = targetWidth;
      grid.style.maxWidth = usePixelWidth ? 'none' : (z > 1 ? `${z * 860}px` : '');
    }
    if (container) {
      container.style.zoom = '';
      container.style.width = targetWidth;
      container.style.maxWidth = 'none';
    }
  },

  toggleFullscreen() {
    const reader = document.getElementById('epReaderContainer');
    if (!document.fullscreenElement) {
      document.body.classList.add('ep-fullscreen');
      reader?.requestFullscreen?.();
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
    const activeCard = container.querySelector('.ep-thumb-card.active');
    if (!activeCard) return;

    // Scroll only the thumb strip — scrollIntoView shifts fullscreen paper off-screen
    const cardLeft = activeCard.offsetLeft;
    const cardWidth = activeCard.offsetWidth;
    const containerWidth = container.clientWidth;
    const scrollTarget = cardLeft - (containerWidth / 2) + (cardWidth / 2);
    container.scrollTo({
      left: Math.max(0, scrollTarget),
      behavior: 'smooth',
    });
  },

  // ── Article Panel ──
  currentArticle: null,
  _origArticleTitle: null,
  _origArticleHTML: null,

  sanitizeArticleHTML(html) {
    if (!html) return '';

    const container = document.createElement('div');
    container.innerHTML = String(html);

    container.querySelectorAll('script, iframe, object, embed, meta, link, style, base').forEach(el => el.remove());

    container.querySelectorAll('*').forEach(el => {
      Array.from(el.attributes).forEach(attr => {
        const name = attr.name.toLowerCase();
        const value = String(attr.value || '');
        const normalized = value.replace(/[\u0000-\u0020\u007F]+/g, '').toLowerCase();
        const isImageDataUrl = name === 'src' && el.tagName === 'IMG' && normalized.startsWith('data:image/');

        if (name.startsWith('on') || name === 'srcdoc') {
          el.removeAttribute(attr.name);
        } else if ((name === 'href' || name === 'src' || name === 'xlink:href' || name === 'formaction')
          && (normalized.startsWith('javascript:') || normalized.startsWith('vbscript:') || (normalized.startsWith('data:') && !isImageDataUrl))) {
          el.removeAttribute(attr.name);
        }
      });
    });

    return container.innerHTML;
  },

  openArticle(index) {
    const art = this.articles[index];
    if (!art) return;
    this.currentArticle = art;

    // Add a DISTINCT history entry (URL hash) so the browser/phone Back button
    // closes this article and returns to the newspaper page — instead of leaving
    // the ePaper. A changed URL (#article) makes the Back/popstate event fire
    // reliably across browsers, and reading it back from location.hash is
    // self-correcting (no stale flag that can desync).
    if (!location.hash.includes('article')) {
      try {
        history.pushState({ epArticle: true }, '', location.pathname + location.search + '#article');
      } catch (e) {}
    }

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
    const gallery = this.filterGalleryImages(art.gallery || []);
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
          galHTML += `<img src="${img}" alt="Image ${i + 1}" class="ep-gallery-full-img" loading="lazy" onload="this.classList.add('loaded')" onclick="EP.openGalleryViewer(${index}, ${i})">`;
        });
        galHTML += '</div>';
      }

      if (art.body_html && art.body_html.length > 10) {
        this.el.articleText.innerHTML = galHTML + this.sanitizeArticleHTML(art.body_html || '');
      } else {
        this.el.articleText.innerHTML = galHTML + (art.body_text || '').split('\n').map(p => `<p>${p}</p>`).join('');
      }
    }

    // Save originals for translation restore
    this._origArticleTitle = art.headline || '';
    this._origArticleHTML = this.el.articleText ? this.el.articleText.innerHTML : '';

    // Reset AI tabs
    this.switchAiTab(null);
    this.stopTTS();
    this.updateReadingTime();

    this.el.articlePanel?.classList.add('open');
    if (this.el.articlePanel) this.el.articlePanel.scrollTop = 0;
    document.body.style.overflow = 'hidden';

    // Show video button if article has video
    const vidBtn = document.getElementById('epVideoBtn');
    const videoUrl = art.video_url || art.video || '';
    if (vidBtn) vidBtn.style.display = (art.has_video || videoUrl) ? 'inline-flex' : 'none';

    this.trackEvent('article_read', { headline: art.headline, category: art.category_label });
  },

  // Gallery lightbox viewer
  openGalleryViewer(artIndex, imgIndex) {
    const art = this.articles[artIndex];
    if (!art || !art.gallery) return;
    const imgs = this.filterGalleryImages(art.gallery);
    if (!imgs.length) return;
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

  closeArticle(fromPopstate = false) {
    this.el.articlePanel?.classList.remove('open');
    document.body.style.overflow = '';
    this.stopTTS();
    this.currentArticle = null;
    // Remove the #article history entry. On popstate the entry is already gone
    // (user pressed Back), so don't navigate again; otherwise pop it so the URL
    // and history return to the clean newspaper page.
    if (!fromPopstate && location.hash.includes('article')) {
      try { history.back(); } catch (e) {}
    }
  },

  // ── AI Tabs ──
  switchAiTab(tab) {
    this.el.aiTabs?.forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    this.el.aiContents?.forEach(c => c.classList.toggle('active', c.dataset.tab === tab));

    if (tab === 'summarize') this.summarizeArticle();
    if (tab === 'translate') {
      this._autoSetTranslateLang();
      this.translateArticle();
    }
  },

  // Collapse/hide the open Translate/Summarize/Share panel without leaving the
  // article (the × / minimise button).
  closeAiPanel() {
    this.el.aiTabs?.forEach(t => t.classList.remove('active'));
    this.el.aiContents?.forEach(c => c.classList.remove('active'));
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
      'gu-IN-NiranjanNeural': 'gu', 'gu-IN-DhwaniNeural': 'gu',
      'bn-IN-BashkarNeural': 'bn', 'bn-IN-TanishaaNeural': 'bn',
      'ta-IN-ValluvarNeural': 'ta', 'ta-IN-PallaviNeural': 'ta',
      'te-IN-MohanNeural': 'te', 'te-IN-ShrutiNeural': 'te',
      'kn-IN-GaganNeural': 'kn', 'kn-IN-SapnaNeural': 'kn',
      'ml-IN-MidhunNeural': 'ml', 'ml-IN-SobhanaNeural': 'ml',
      'ur-IN-SalmanNeural': 'ur', 'ur-PK-AsadNeural': 'ur', 'ur-PK-UzmaNeural': 'ur',
      'en-IN-PrabhatNeural': 'en', 'en-IN-NeerjaNeural': 'en',
    };
    const lang = VOICE_LANG[voiceVal] || '';

    // Restore originals on Auto
    if (!lang) {
      if (this.el.articleTitle) this.el.articleTitle.textContent = this._origArticleTitle || '';
      if (this.el.articleText) this.el.articleText.innerHTML = this._origArticleHTML || '';
      this.showToast('Restored original language');
      return;
    }

    this.showToast('<i class="fa fa-sync fa-spin"></i> Translating...');

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
      const newBody = bData.translated_text || bodyText;

      if (this.el.articleTitle) this.el.articleTitle.textContent = newTitle;
      if (this.el.articleText) {
        this.el.articleText.innerHTML = newBody
          .split(/\n+/)
          .filter(p => p.trim())
          .map(p => `<p>${p}</p>`)
          .join('');
      }

      const langNames = { hi: 'हिंदी', mr: 'मराठी', en: 'English' };
      this.showToast(`<i class="fa fa-check-circle" style="color:#22c55e"></i> Translated to ${langNames[lang] || lang}`);
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
      const marathiWords = ['\u0906\u0939\u0947', '\u0928\u093E\u0939\u0940', '\u0906\u0923\u093F', '\u092E\u0932\u093E', '\u0906\u092A\u0923', '\u0939\u094B\u0924\u0947', '\u0915\u0947\u0932\u0947', '\u091D\u093E\u0932\u0947', '\u092E\u094D\u0939\u0923\u093E\u0932\u0947', '\u092E\u0939\u093E\u0930\u093E\u0937\u094D\u091F\u094D\u0930'];
      const hindiWords = ['\u0939\u0948', '\u0928\u0939\u0940\u0902', '\u0914\u0930', '\u0925\u093E', '\u0939\u0948\u0902', '\u092F\u0939', '\u0915\u0939\u093E', '\u092C\u0924\u093E\u092F\u093E', '\u0907\u0938\u0938\u0947'];
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

  filterGalleryImages(gallery) {
    if (!Array.isArray(gallery)) return [];
    return gallery
      .map(img => String(img || '').trim())
      .filter(Boolean);
  },

  _splitSentences(text) {
    text = text.replace(/\s+/g, ' ').trim();
    if (!text) return [];
    const matches = text.match(/[^.!?\u0964]+(?:[.!?\u0964]+(?=\s|$)|$)/g) || [];
    return matches.map(s => s.trim()).filter(Boolean);
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
      if (n >= 10000000) return `${(n / 10000000).toFixed(1)} करोड़ रुपये`;
      if (n >= 100000) return `${(n / 100000).toFixed(1)} लाख रुपये`;
      if (n >= 1000) return `${(n / 1000).toFixed(0)} हज़ार रुपये`;
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

    // Resume from pause
    if (this._voice.paused && this._voice.audio) {
      this._voice.audio.play();
      this._voice.paused = false;
      this._voice.playing = true;
      this._voiceUpdatePlayIcon();
      return;
    }

    const displayedTitle = this.el.articleTitle?.textContent || '';
    const displayedBody = (this.el.articleText?.innerText || this.el.articleText?.textContent || '')
      .replace(/[\r\n]+/g, ' ').replace(/ +/g, ' ').trim();
    const rawText = (displayedTitle + '। ' + displayedBody).trim() || this._getArticleText();
    if (!rawText) { this.showToast('No text to read'); return; }

    // Cancel any in-flight request before starting a new one
    if (this._voice.abortController) {
      this._voice.abortController.abort();
      this._voice.abortController = null;
    }

    this.voiceStop();
    this._voice.loading = true;
    this._voice.abortController = new AbortController();

    if (this.el.voiceBar) this.el.voiceBar.classList.add('loading', 'topbar');
    if (this.el.voiceTitle) this.el.voiceTitle.textContent = displayedTitle || this.currentArticle.headline || 'Article';
    if (this.el.ttsStartBtn) { this.el.ttsStartBtn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> <span>Loading...</span>'; this.el.ttsStartBtn.classList.add('loading'); }
    this._voiceUpdatePlayIcon();
    this._prepareHighlight();

    let textToRead = this._preprocessTTSText(rawText);
    let rateStr = '+0%';
    let pitchStr = '+0Hz';
    if (rateStr === '+0%' && this._voice.rate !== 1) {
      const pct = Math.round((this._voice.rate - 1) * 100);
      rateStr = pct >= 0 ? `+${pct}%` : `${pct}%`;
    }
    this._voice.text = textToRead;

    try {
      const res = await fetch('/api/epaper/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: textToRead, voice: this._voice.selectedVoice || '', rate: rateStr, pitch: pitchStr }),
        signal: this._voice.abortController.signal,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || 'TTS request failed');
      }

      // Try progressive streaming via MediaSource (plays on first chunk, ~300ms)
      // Fallback to full blob if MediaSource unavailable (Safari)
      let audio;
      const canStream = typeof MediaSource !== 'undefined'
        && MediaSource.isTypeSupported('audio/mpeg')
        && res.body;

      if (canStream) {
        audio = await this._createStreamingAudio(res, this._voice.abortController.signal);
      } else {
        const blob = await res.blob();
        audio = new Audio(URL.createObjectURL(blob));
      }

      // Guard: stop was called while we were loading
      if (!this._voice.loading) { audio.pause(); return; }

      this._voice.audio = audio;
      this._attachAudioListeners(audio);
      await audio.play();

      if (this.el.voiceBar) this.el.voiceBar.classList.remove('loading');
      this._voice.playing = true;
      this._voice.paused = false;
      this._voice.loading = false;
      this._voice.abortController = null;
      if (this.el.ttsStartBtn) { this.el.ttsStartBtn.innerHTML = '<i class="fa fa-play"></i> <span>Play</span>'; this.el.ttsStartBtn.classList.remove('loading'); }
      this._voiceUpdatePlayIcon();
      this.showToast('<i class="fa fa-volume-up"></i> Now playing');
      this.trackEvent('voice_play', { article: this.currentArticle?.headline, voice: this._voice.selectedVoice || 'auto' });

    } catch (err) {
      if (err.name === 'AbortError') return; // intentionally cancelled
      console.error('TTS Error:', err);
      this._voice.loading = false;
      this._voice.abortController = null;
      if (this.el.ttsStartBtn) { this.el.ttsStartBtn.innerHTML = '<i class="fa fa-play"></i> <span>Play</span>'; this.el.ttsStartBtn.classList.remove('loading'); }
      if (this.el.voiceBar) this.el.voiceBar.classList.remove('loading', 'topbar');
      if (this.el.ttsPrompt) this.el.ttsPrompt.style.display = '';
      this._clearHighlight();
      this._voiceUpdatePlayIcon();
      // Fallback: use browser's built-in Web Speech API
      if (window.speechSynthesis) {
        this._voicePlayBrowser(rawText);
      } else {
        this.showToast('Voice generation failed. Try again.');
      }
    }
  },

  _voicePlayBrowser(text) {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    const voice = this._voice.selectedVoice || '';
    utter.lang = voice.startsWith('mr') ? 'mr-IN'
               : voice.startsWith('en') ? 'en-IN'
               : 'hi-IN';
    utter.rate = Math.min(this._voice.rate || 0.9, 1.2);
    utter.pitch = 1.0;
    // Try to match a system voice for the language
    const voices = window.speechSynthesis.getVoices();
    const match = voices.find(v => v.lang === utter.lang)
               || voices.find(v => v.lang.startsWith(utter.lang.split('-')[0]));
    if (match) utter.voice = match;

    utter.onstart = () => {
      this._voice.playing = true;
      if (this.el.ttsStartBtn) this.el.ttsStartBtn.innerHTML = '<i class="fa fa-stop"></i> <span>Stop</span>';
      if (this.el.voiceBar) this.el.voiceBar.classList.add('topbar');
      if (this.el.voiceTitle) this.el.voiceTitle.textContent = 'Playing…';
      this.showToast('Playing with browser voice');
    };
    utter.onend = utter.onerror = () => {
      this._voice.playing = false;
      window.speechSynthesis.cancel();
      if (this.el.ttsStartBtn) { this.el.ttsStartBtn.innerHTML = '<i class="fa fa-play"></i> <span>Play</span>'; this.el.ttsStartBtn.classList.remove('loading'); }
      if (this.el.voiceBar) this.el.voiceBar.classList.remove('loading', 'topbar');
      this._voiceUpdatePlayIcon();
    };
    this._voice._utterance = utter;
    // Voices may not be loaded yet — wait if needed
    if (voices.length === 0) {
      window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.onvoiceschanged = null;
        const v2 = window.speechSynthesis.getVoices();
        const m2 = v2.find(v => v.lang === utter.lang) || v2.find(v => v.lang.startsWith(utter.lang.split('-')[0]));
        if (m2) utter.voice = m2;
        window.speechSynthesis.speak(utter);
      };
    } else {
      window.speechSynthesis.speak(utter);
    }
  },

  // Attach standard listeners to an Audio element
  _attachAudioListeners(audio) {
    audio.addEventListener('loadedmetadata', () => {
      this._voice.loading = false;
      if (this.el.voiceDuration) this.el.voiceDuration.textContent = this._formatTime(audio.duration || 0);
      this._voiceUpdatePlayIcon();
    });
    audio.addEventListener('timeupdate', () => {
      this._voiceUpdateUI();
      this._highlightAt(audio.currentTime, audio.duration);
    });
    audio.addEventListener('ended', () => { this._clearHighlight(); this._voiceFinished(); });
    audio.addEventListener('error', () => {
      this.showToast('Audio playback error');
      this._voiceFinished();
    });
  },

  // Build a streaming Audio element using MediaSource — starts playing on first chunk
  _createStreamingAudio(res, signal) {
    return new Promise((resolve, reject) => {
      const ms = new MediaSource();
      const audioUrl = URL.createObjectURL(ms);
      const audio = new Audio(audioUrl);
      audio.preload = 'auto';

      let resolved = false;
      const timer = setTimeout(() => reject(new Error('MediaSource timeout')), 15000);

      ms.addEventListener('sourceopen', async () => {
        let sb;
        try {
          sb = ms.addSourceBuffer('audio/mpeg');
          sb.mode = 'sequence';
        } catch (e) {
          clearTimeout(timer);
          reject(e);
          return;
        }

        const reader = res.body.getReader();
        let closed = false;

        const endStream = () => {
          if (closed) return;
          closed = true;
          try { ms.endOfStream(); } catch (_) {}
        };

        const appendNext = async () => {
          if (signal?.aborted) { endStream(); return; }
          let chunk;
          try {
            chunk = await reader.read();
          } catch (e) {
            endStream();
            return;
          }
          if (chunk.done) { endStream(); return; }

          if (sb.updating) {
            await new Promise(r => sb.addEventListener('updateend', r, { once: true }));
          }
          if (ms.readyState !== 'open') return;
          try {
            sb.appendBuffer(chunk.value);
          } catch (e) {
            endStream();
            return;
          }

          if (!resolved) {
            resolved = true;
            clearTimeout(timer);
            resolve(audio);
          }
        };

        sb.addEventListener('updateend', () => { if (!closed) appendNext(); });
        appendNext();
      }, { once: true });
    });
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
    this.showToast('<i class="fa fa-check-circle" style="color:#22c55e"></i> Finished reading');
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
    // Cancel any pending TTS fetch
    if (this._voice.abortController) {
      this._voice.abortController.abort();
      this._voice.abortController = null;
    }
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
    const text = this._getArticleText();
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
        const summary = data.summary;
        if (Array.isArray(summary) && summary.length) {
          this.el.summaryOutput.innerHTML = `<h4>AI Summary</h4><ul>${summary.map(p => `<li>${p}</li>`).join('')}</ul>`;
        } else if (typeof summary === 'string' && summary.trim()) {
          this.el.summaryOutput.innerHTML = `<h4>AI Summary</h4><p>${summary}</p>`;
        } else {
          this.el.summaryOutput.innerHTML = '<p>Summary unavailable.</p>';
        }
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
    this.showToast('<i class="fa fa-download"></i> Downloading audio...');
  },

  // ── Save Edition as PDF ──
  // ── Helper: wait for page images to load ──
  async waitPageToLoad() {
    return new Promise(resolve => {
      const grid = document.getElementById('epBlockGrid');
      if (grid && grid.style.display !== 'none') {
        const imgs = Array.from(grid.querySelectorAll('img.ep-block-img'));
        if (imgs.length === 0) {
          setTimeout(resolve, 300);
          return;
        }
        let loadedCount = 0;
        const checkResolve = () => {
          loadedCount++;
          if (loadedCount === imgs.length) resolve();
        };
        imgs.forEach(img => {
          if (img.complete) {
            checkResolve();
          } else {
            img.addEventListener('load', checkResolve, { once: true });
            img.addEventListener('error', checkResolve, { once: true });
          }
        });
        setTimeout(resolve, 3000); // 3s fallback limit
      } else {
        const img = document.getElementById('epPageImg');
        if (img && img.style.display !== 'none' && img.src) {
          if (img.complete) {
            resolve();
          } else {
            img.addEventListener('load', () => resolve(), { once: true });
            img.addEventListener('error', () => resolve(), { once: true });
            setTimeout(resolve, 3000); // 3s fallback limit
          }
        } else {
          setTimeout(resolve, 300);
        }
      }
    });
  },

  // ── Helper: show full screen progress loader ──
  showPdfLoader(show, text = '') {
    let loader = document.getElementById('epPdfLoader');
    if (!loader) {
      loader = document.createElement('div');
      loader.id = 'epPdfLoader';
      loader.style.cssText = `
        position: fixed;
        inset: 0;
        background: rgba(15, 15, 18, 0.96);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        z-index: 9999;
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.3s ease;
        backdrop-filter: blur(8px);
      `;
      loader.innerHTML = `
        <div style="text-align: center; color: #fff; font-family: var(--ep-font);">
          <div style="width: 64px; height: 64px; border: 4px solid rgba(255,255,255,0.1); border-top: 4px solid var(--ep-orange); border-radius: 50%; animation: epSpin 1s linear infinite; margin: 0 auto 24px;"></div>
          <h3 style="font-size: 20px; font-weight: 700; margin-bottom: 8px; letter-spacing: 0.5px;">Generating Edition PDF</h3>
          <p id="epPdfLoaderText" style="color: rgba(255,255,255,0.6); font-size: 14px; margin-bottom: 24px;">Preparing pages...</p>
          <button onclick="EP.cancelPDF()" style="padding: 10px 28px; background: transparent; border: 1.5px solid rgba(255,255,255,0.3); border-radius: 8px; color: rgba(255,255,255,0.7); font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s;" onmouseover="this.style.borderColor='#ff6600';this.style.color='#ff6600'" onmouseout="this.style.borderColor='rgba(255,255,255,0.3)';this.style.color='rgba(255,255,255,0.7)'">Cancel</button>
        </div>
      `;
      document.body.appendChild(loader);
    }

    if (show) {
      loader.style.opacity = '1';
      loader.style.pointerEvents = 'auto';
      const textEl = document.getElementById('epPdfLoaderText');
      if (textEl) textEl.textContent = text;
    } else {
      loader.style.opacity = '0';
      loader.style.pointerEvents = 'none';
    }
  },

  // ── Save Edition as PDF ──
  savePDF() {
    this.compilePDF();
  },

  _loadScript(src) {
    return new Promise((resolve, reject) => {
      if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
      const s = document.createElement('script');
      s.src = src; s.async = true;
      s.onload = resolve; s.onerror = reject;
      document.head.appendChild(s);
    });
  },

  // Load an image URL → { dataURL, width, height } using a canvas (no html2canvas).
  // Requires the server to send CORS headers — Cloudinary does by default.
  _loadImageToCanvas(url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        const c = document.createElement('canvas');
        c.width  = img.naturalWidth;
        c.height = img.naturalHeight;
        const ctx = c.getContext('2d');
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, c.width, c.height);
        ctx.drawImage(img, 0, 0);
        resolve({ dataURL: c.toDataURL('image/jpeg', 0.97), width: img.naturalWidth, height: img.naturalHeight });
      };
      img.onerror = () => reject(new Error(`Failed to load image: ${url}`));
      // Cache-bust only if needed; normally Cloudinary CDN is fine as-is
      img.src = url;
    });
  },

  async compilePDF() {
    if (!this.pages.length) { this.showToast('No edition pages available'); return; }
    if (typeof window.jspdf === 'undefined') {
      this.showToast('Loading PDF library…');
      try {
        await this._loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js');
      } catch (e) { this.showToast('Failed to load PDF library'); return; }
    }

    this._pdfCancelled = false;
    try {
      const { jsPDF } = window.jspdf;
      const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
      const W = 210, H = 297;
      let firstPage = true;

      for (let i = 0; i < this.pages.length; i++) {
        if (this._pdfCancelled) { this.showToast('PDF cancelled.'); return; }
        this.showPdfLoader(true, `Downloading page ${i + 1} of ${this.pages.length}…`);

        const page = this.pages[i];
        const imageUrl = page.page_image_url || page.image_path || page.image_url || '';
        if (!imageUrl || imageUrl.toLowerCase().endsWith('.pdf')) continue;

        let imgInfo;
        try {
          imgInfo = await this._loadImageToCanvas(imageUrl);
        } catch (imgErr) {
          console.warn(`[PDF] Page ${i + 1} image load failed, skipping:`, imgErr);
          continue;
        }

        if (this._pdfCancelled) { this.showToast('PDF cancelled.'); return; }

        // Fit image into A4 (preserve aspect ratio, centre on page)
        const ar = imgInfo.width / imgInfo.height;
        const pa = W / H;
        let iw = W, ih = H, ix = 0, iy = 0;
        if (ar > pa) { ih = W / ar; iy = (H - ih) / 2; }
        else         { iw = H * ar; ix = (W - iw) / 2; }

        if (!firstPage) pdf.addPage();
        firstPage = false;
        // 'NONE' = no extra jsPDF compression on top of our already-JPEG data
        pdf.addImage(imgInfo.dataURL, 'JPEG', ix, iy, iw, ih, undefined, 'NONE');
      }

      if (firstPage) { this.showToast('No downloadable pages found.'); return; }

      const title = this.currentEdition?.name || 'Vidyarthi Mitra E-Paper';
      pdf.save(`${title}.pdf`);
      this.showToast('PDF downloaded!');
    } catch (err) {
      if (!this._pdfCancelled) {
        console.error('PDF export failed:', err);
        this.showToast('PDF export failed: ' + err.message);
      }
    } finally {
      this._pdfCancelled = false;
      this.showPdfLoader(false);
    }
  },

  cancelPDF() {
    this._pdfCancelled = true;
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

  shareEdition(platform) {
    const title = this.currentEdition?.name || document.title || 'Vidyarthi Mitra E-Paper';
    const date = this.currentEdition?.date;
    const url = date
      ? `${window.location.origin}/epaper/${date}`
      : window.location.href;
    const text = encodeURIComponent(title + ' - ' + url);

    const urls = {
      whatsapp: `https://wa.me/?text=${text}`,
      twitter: `https://twitter.com/intent/tweet?text=${text}`,
      facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`,
    };

    if (urls[platform]) {
      window.open(urls[platform], '_blank', 'width=600,height=400');
    } else {
      navigator.clipboard?.writeText(url);
      this.showToast('Link copied!');
    }
    this.trackEvent('share_edition', { platform, edition: title });

    // Close the dropdown after selection
    document.getElementById('epShareDropdown')?.classList.remove('show');
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
    if (this._toastTimer) clearTimeout(this._toastTimer);
    this.el.toast.innerHTML = msg;
    this.el.toast.classList.add('show');
    const duration = Math.max(1800, Math.min(5200, 1400 + String(msg || '').trim().length * 35));
    this._toastTimer = setTimeout(() => {
      this.el.toast.classList.remove('show');
      this._toastTimer = null;
    }, duration);
  },

  // ── News Sidebar ──
  async loadNewsSidebar() {
    const container = document.getElementById('epNewsCards');
    if (!container) return;
    const fallbackHtml = '<p style="color:#6b7280;font-size:12px;padding:8px 0">Unable to load news right now</p>';
    try {
      // Fetch a large pool so we can pick 2 per category
      const res = await fetch('/api/news?limit=60&category=all');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const pool = Array.isArray(data?.articles) ? data.articles : [];
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
      if (!picked.length) { container.innerHTML = '<p style="color:#6b7280;font-size:12px;padding:8px 0">No news available</p>'; return; }

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
      container.innerHTML = fallbackHtml;
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
document.addEventListener('DOMContentLoaded', () => {
  if (window._epInitialized) return;
  window._epInitialized = true;
  EP.init();
});
