/* ══════════════════════════════════════════════════
   Vidyarthi Mitra E-Paper Viewer JS
   ══════════════════════════════════════════════════ */

const EP = {
  // State
  currentDate: null,
  currentPage: 1,
  totalPages: 1,
  zoom: 1,
  minZoom: 0.5,
  maxZoom: 4,
  isDragging: false,
  dragStart: { x: 0, y: 0 },
  panOffset: { x: 0, y: 0 },
  editions: [],
  pages: [],
  articles: [],
  ttsUtterance: null,
  ttsPlaying: false,

  footerLinksDefault: [
    { key: 'search', icon: 'fa fa-magnifying-glass', url: '/epaper' },
    { key: 'whatsapp', icon: 'fab fa-whatsapp', url: 'https://wa.me/?text=Vidyarthi%20Mitra%20E-Paper' },
    { key: 'facebook', icon: 'fab fa-facebook-f', url: 'https://www.facebook.com/' },
    { key: 'x', icon: 'fab fa-x-twitter', url: 'https://x.com/' },
  ],

  // DOM refs
  el: {},

  init() {
    this.cacheDOM();
    this.bindEvents();
    this.renderFooterLinks(this.footerLinksDefault);
    this.setDate(new Date());
    this.loadEditions();
  },

  cacheDOM() {
    this.el = {
      header: document.getElementById('epHeader'),
      collapseBtn: document.getElementById('epCollapseBtn'),
      nav: document.getElementById('epNav'),
      navList: document.getElementById('epNavList'),
      main: document.getElementById('epMain'),
      paper: document.getElementById('epPaper'),
      viewer: document.getElementById('epViewer'),
      pageContainer: document.getElementById('epPageContainer'),
      pageImg: document.getElementById('epPageImg'),
      hotspotsLayer: document.getElementById('epHotspots'),
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
      ttsPlay: document.getElementById('epTtsPlay'),
      ttsProgress: document.getElementById('epTtsProgress'),
      ttsSpeed: document.getElementById('epTtsSpeed'),
      translateSelect: document.getElementById('epTranslateSelect'),
      translateOutput: document.getElementById('epTranslateOutput'),
      summaryOutput: document.getElementById('epSummaryOutput'),
      toast: document.getElementById('epToast'),
      mastheadImg: document.getElementById('epMastheadImg'),
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

    // Zoom
    this.el.zoomIn?.addEventListener('click', () => this.setZoom(this.zoom + 0.25));
    this.el.zoomOut?.addEventListener('click', () => this.setZoom(this.zoom - 0.25));
    this.el.fitPage?.addEventListener('click', () => this.setZoom(1));
    this.el.fullscreen?.addEventListener('click', () => this.toggleFullscreen());

    // Viewer pan/drag
    const v = this.el.viewer;
    if (v) {
      v.addEventListener('mousedown', (e) => this.startDrag(e));
      v.addEventListener('mousemove', (e) => this.onDrag(e));
      v.addEventListener('mouseup', () => this.endDrag());
      v.addEventListener('mouseleave', () => this.endDrag());
      v.addEventListener('wheel', (e) => {
        if (e.ctrlKey || e.metaKey) {
          e.preventDefault();
          this.setZoom(this.zoom + (e.deltaY < 0 ? 0.15 : -0.15));
        }
      }, { passive: false });
      v.addEventListener('touchstart', (e) => this.startDrag(e.touches[0]), { passive: true });
      v.addEventListener('touchmove', (e) => {
        if (this.zoom > 1) {
          e.preventDefault();
          this.onDrag(e.touches[0]);
        }
      }, { passive: false });
      v.addEventListener('touchend', () => this.endDrag());
    }

    // Article panel back
    this.el.articleBack?.addEventListener('click', () => this.closeArticle());

    // AI tabs
    this.el.aiTabs?.forEach(tab => {
      tab.addEventListener('click', () => this.switchAiTab(tab.dataset.tab));
    });

    // TTS
    this.el.ttsPlay?.addEventListener('click', () => this.toggleTTS());
    this.el.ttsSpeed?.addEventListener('click', () => this.cycleTTSSpeed());

    // Translate
    this.el.translateSelect?.addEventListener('change', () => this.translateArticle());

    // Keyboard
    document.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft') this.changePage(-1);
      if (e.key === 'ArrowRight') this.changePage(1);
      if (e.key === 'Escape') this.closeArticle();
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

  applyMastheadImage(url) {
    if (!this.el.mastheadImg) return;
    const existingImg = this.el.mastheadImg.querySelector('img');
    if (url) {
      this.el.mastheadImg.querySelector('.ep-masthead-canvas')?.remove();
      let img = existingImg;
      if (!img) {
        img = document.createElement('img');
        img.alt = 'E-Paper Header';
        this.el.mastheadImg.prepend(img);
      }
      img.src = url;
      document.body.classList.add('has-masthead');
    } else {
      existingImg?.remove();
      document.body.classList.remove('has-masthead');
    }
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
        base.push({
          key: key || 'link',
          url: item.url,
          icon: item.icon || 'fa fa-link',
        });
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
    this.loadEditionForDate(d);
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
      const res = await fetch('/api/epaper/editions');
      if (res.ok) {
        const data = await res.json();
        this.editions = Array.isArray(data) ? data : (data.editions || data.results || []);
      }
    } catch (e) { console.warn('Could not load editions:', e); }
  },

  async loadEditionForDate(d) {
    const iso = this.formatDateISO(d);
    try {
      const res = await fetch(`/api/epaper/edition/${iso}`);
      if (!res.ok) {
        console.warn('EP: Edition not found:', iso, res.status);
        this.showDemoPage();
        return;
      }
      const data = await res.json();
      this.pages = (data.pages || []).slice().sort((a, b) => {
        const ap = Number(a && (a.page_number !== undefined && a.page_number !== null
          ? a.page_number
          : (a.page_no !== undefined && a.page_no !== null ? a.page_no : a.page)) || 0);
        const bp = Number(b && (b.page_number !== undefined && b.page_number !== null
          ? b.page_number
          : (b.page_no !== undefined && b.page_no !== null ? b.page_no : b.page)) || 0);
        if (ap && bp) return ap - bp;
        return 0;
      });
      this.totalPages = this.pages.length || 1;
      this.applyMastheadImage(data.masthead_image_url || '');
      this.renderFooterLinks(data.footer_links || this.footerLinksDefault);
      this.renderCategories(this.pages);
      this.showPage(1);
    } catch (e) {
      console.warn('Edition load error:', e);
      this.showDemoPage();
    }
  },

  showDemoPage() {
    // Show a placeholder when no real data
    this.totalPages = 1;
    this.pages = [];
    this.applyMastheadImage('');
    this.renderFooterLinks(this.footerLinksDefault);
    if (this.el.pageImg) {
      this.el.pageImg.src = '';
      this.el.pageImg.alt = 'No edition available';
    }
    if (this.el.hotspotsLayer) this.el.hotspotsLayer.innerHTML = '';
    this.updatePager();
    this.showToast('इस तारीख का संस्करण उपलब्ध नहीं है');
  },

  // ── Categories ──
  renderCategories(pages) {
    if (!this.el.navList) return;
    const cats = ['मुख पृष्ठ'];
    pages.forEach(p => {
      if (p.category && !cats.includes(p.category)) cats.push(p.category);
    });

    this.el.navList.innerHTML = cats.map((c, i) =>
      `<a class="ep-nav-item ${i === 0 ? 'active' : ''}" data-cat="${c}" data-page="${i + 1}">${c}</a>`
    ).join('');

    this.el.navList.querySelectorAll('.ep-nav-item').forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        this.el.navList.querySelectorAll('.ep-nav-item').forEach(n => n.classList.remove('active'));
        item.classList.add('active');
        const pg = parseInt(item.dataset.page) || 1;
        this.showPage(pg);
      });
    });
  },

  // ── Page Display ──
  showPage(num) {
    this.currentPage = Math.max(1, Math.min(num, this.totalPages));
    this.setZoom(1);
    this.panOffset = { x: 0, y: 0 };
    this.applyTransform();
    this.updatePager();

    const page = this.pages[this.currentPage - 1];
    if (!page) {
      console.warn('EP: Page not found at index', this.currentPage - 1);
      return;
    }

    const viewer = this.el.viewer || document.getElementById('epViewer');

    const pageImage = page.page_image_url || page.image_path || page.page_image || '';
    const overlayArticles = this.overlayArticlesForPage(page);

    if (pageImage) {
      if (this.el.pageContainer) this.el.pageContainer.style.display = '';
      if (this.el.pageImg) {
        this.el.pageImg.style.display = 'block';
        this.el.pageImg.src = pageImage;
        this.triggerPageFlip(this.el.pageImg);
      }
      if (this.el.hotspotsLayer) this.el.hotspotsLayer.style.display = 'block';
      this.renderHotspots(overlayArticles);
      const grid = document.getElementById('epBlockGrid');
      if (grid) grid.style.display = 'none';
    } else if (page.blocks && page.blocks.length > 0) {
      if (this.el.pageContainer) this.el.pageContainer.style.display = 'none';
      this.renderBlockGrid(page.blocks, viewer);
      const grid = document.getElementById('epBlockGrid');
      const canvas = grid?.querySelector('.ep-canvas-viewer');
      if (canvas) this.triggerPageFlip(canvas);
    }
  },

  triggerPageFlip(el) {
    if (!el) return;
    el.classList.remove('ep-flip');
    void el.offsetWidth;
    el.classList.add('ep-flip');
  },

  changePage(dir) {
    this.showPage(this.currentPage + dir);
  },

  overlayArticlesForPage(page) {
    if (page.blocks && page.blocks.length) return page.blocks;
    if (page.layout_json && page.layout_json.length) {
      const articlesById = new Map((page.articles || []).map(article => [String(article.article_id || article.id), article]));
      return page.layout_json.map(region => ({
        ...(articlesById.get(String(region.article_id)) || {}),
        ...region,
      }));
    }
    return page.articles || [];
  },

  updatePager() {
    if (this.el.pageInfo) this.el.pageInfo.textContent = `${this.currentPage} / ${this.totalPages}`;
    if (this.el.prevPage) this.el.prevPage.disabled = this.currentPage <= 1;
    if (this.el.nextPage) this.el.nextPage.disabled = this.currentPage >= this.totalPages;
  },

  // ── Block Grid (NEW) ──
  renderBlockGrid(blocks, viewer) {
    let grid = document.getElementById('epBlockGrid');
    if (!grid) {
      grid = document.createElement('div');
      grid.id = 'epBlockGrid';
      grid.className = 'ep-block-grid';
      (viewer || document.getElementById('epViewer'))?.appendChild(grid);
    }
    grid.style.display = 'block';

    this.articles = blocks.map(b => ({
      ...b,
      headline: b.headline,
      sub_headline: b.sub_headline,
      body_text: b.body_text,
      body_html: b.body_html || '',
      category_label: b.category_label,
      article_image_url: b.image_url,
      gallery: b.gallery || [],
    }));

    // Canvas is 800x1000 in admin — use percentage-based positioning
    const CANVAS_W = 800;
    let maxY = 400;
    blocks.forEach(b => {
      const bottom = (b.y || 0) + (b.h || 150);
      if (bottom > maxY) maxY = bottom;
    });
    const canvasH = Math.max(maxY + 20, 500);
    const aspectRatio = (canvasH / CANVAS_W * 100).toFixed(2);

    grid.innerHTML = `
      <div class="ep-canvas-viewer" style="position:relative;width:100%;padding-bottom:${aspectRatio}%;background:#fff;border-radius:10px;box-shadow:0 4px 30px rgba(0,0,0,.12);">
        ${blocks.map((b, i) => {
          const hasImg = b.image_url && b.image_url.length > 10;
          const x = ((b.x || 0) / CANVAS_W * 100).toFixed(2);
          const y = ((b.y || 0) / canvasH * 100).toFixed(2);
          const w = ((b.w || 200) / CANVAS_W * 100).toFixed(2);
          const h = ((b.h || 150) / canvasH * 100).toFixed(2);
          const bw = b.border_width ?? 0;
          const br = b.border_radius ?? 10;
          const bc = b.border_color || '#e41e26';
          const bs = b.border_style || 'solid';
          const borderCSS = bw > 0 ? `border:${bw}px ${bs} ${bc};` : '';
          const style = `position:absolute;left:${x}%;top:${y}%;width:${w}%;height:${h}%;border-radius:${br}px;${borderCSS}overflow:hidden;cursor:pointer;`;
          return `
            <div class="ep-block-card" onclick="EP.openArticle(${i})" title="${b.headline || ''}" style="${style}">
              ${hasImg ? `<img class="ep-block-img" src="${b.image_url}" alt="${b.headline || ''}" draggable="false" style="width:100%;height:100%;object-fit:cover;display:block;">` : `
                <div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#f3f4f6,#e5e7eb);color:#d1d5db;font-size:28px;">
                  <i class="fa fa-newspaper"></i>
                </div>
              `}
              <div style="position:absolute;bottom:0;left:0;right:0;background:linear-gradient(transparent,rgba(0,0,0,.85));padding:12px 10px 8px;color:#fff;">
                ${b.category_label ? `<span style="font-size:9px;font-weight:700;text-transform:uppercase;color:rgba(255,255,255,.7);display:block;margin-bottom:2px;">${b.category_label}</span>` : ''}
                <strong style="font-size:13px;line-height:1.3;display:block;">${b.headline || 'Untitled'}</strong>
                ${b.sub_headline ? `<span style="font-size:10px;color:rgba(255,255,255,.6);display:block;margin-top:2px;">${b.sub_headline}</span>` : ''}
              </div>
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
      const region = this.normalizeRegion(art);
      if (!region) return;
      const hs = document.createElement('div');
      hs.className = 'ep-hotspot';
      if (art.has_video && art.video_url) hs.classList.add('has-video');
      hs.style.left = region.x + '%';
      hs.style.top = region.y + '%';
      hs.style.width = region.w + '%';
      hs.style.height = region.h + '%';
      hs.title = art.headline || 'Read article';
      hs.addEventListener('click', (event) => {
        event.stopPropagation();
        this.openArticle(i);
      });
      this.el.hotspotsLayer.appendChild(hs);
    });
  },

  normalizeRegion(art) {
    const CANVAS_W = 800;
    const CANVAS_H = 1000;
    if (art.x !== undefined || art.y !== undefined) {
      return {
        x: Math.max(0, Math.min(100, ((Number(art.x) || 0) / CANVAS_W) * 100)).toFixed(3),
        y: Math.max(0, Math.min(100, ((Number(art.y) || 0) / CANVAS_H) * 100)).toFixed(3),
        w: Math.max(1, Math.min(100, ((Number(art.width ?? art.w) || 200) / CANVAS_W) * 100)).toFixed(3),
        h: Math.max(1, Math.min(100, ((Number(art.height ?? art.h) || 150) / CANVAS_H) * 100)).toFixed(3),
      };
    }
    if (art.click_region_x !== undefined) {
      return {
        x: Number(art.click_region_x || 0).toFixed(3),
        y: Number(art.click_region_y || 0).toFixed(3),
        w: Number(art.click_region_w || 20).toFixed(3),
        h: Number(art.click_region_h || 15).toFixed(3),
      };
    }
    return null;
  },

  // ── Zoom / Pan ──
  setZoom(level) {
    this.zoom = Math.max(this.minZoom, Math.min(this.maxZoom, level));
    if (this.el.viewer) {
      this.el.viewer.classList.toggle('can-pan', this.zoom > 1);
    }
    this.applyTransform();
  },

  applyTransform() {
    if (!this.el.pageContainer) return;
    this.el.pageContainer.style.transform = `translate(${this.panOffset.x}px, ${this.panOffset.y}px) scale(${this.zoom})`;
  },

  startDrag(e) {
    if (this.zoom <= 1) return;
    this.isDragging = true;
    this.dragStart = { x: e.clientX - this.panOffset.x, y: e.clientY - this.panOffset.y };
  },

  onDrag(e) {
    if (!this.isDragging) return;
    this.panOffset.x = e.clientX - this.dragStart.x;
    this.panOffset.y = e.clientY - this.dragStart.y;
    this.applyTransform();
  },

  endDrag() { this.isDragging = false; },

  toggleFullscreen() {
    const target = this.el.paper || this.el.viewer || document.body;
    if (!document.fullscreenElement) {
      target.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  },

  // ── Article Panel ──
  currentArticle: null,

  openArticle(index) {
    const art = this.articles[index];
    if (!art) return;
    const articleId = art.article_id || art.id;
    if (articleId !== undefined && articleId !== null && articleId !== '') {
      window.location.href = `/article/${encodeURIComponent(articleId)}`;
      return;
    }
    this.currentArticle = art;

    if (this.el.articleCategory) this.el.articleCategory.textContent = art.category_label || 'News';
    if (this.el.articleTitle) this.el.articleTitle.textContent = art.headline || '';
    if (this.el.articleDate) this.el.articleDate.textContent = art.created_at || this.formatDateISO(this.currentDate);
    if (this.el.articleImg) {
      if (art.article_image_url || art.image_url) {
        this.el.articleImg.src = art.article_image_url || art.image_url;
        this.el.articleImg.style.display = 'block';
      } else {
        this.el.articleImg.style.display = 'none';
      }
    }

    // Rich HTML content or plain text
    if (this.el.articleText) {
      if (art.body_html && art.body_html.length > 10) {
        this.el.articleText.innerHTML = art.body_html;
      } else {
        this.el.articleText.innerHTML = (art.body_text || '').split('\n').map(p => `<p>${p}</p>`).join('');
      }

      // Append gallery images
      const gallery = art.gallery || [];
      if (gallery.length > 0) {
        let galHTML = '<div class="ep-article-gallery">';
        gallery.forEach((img, i) => {
          galHTML += `<img src="${img}" alt="Image ${i+1}" class="ep-gallery-img" onclick="EP.openGalleryViewer(${index}, ${i})">`;
        });
        galHTML += '</div>';
        this.el.articleText.innerHTML += galHTML;
      }
    }

    // Reset AI tabs
    this.switchAiTab(null);
    this.stopTTS();

    this.el.articlePanel?.classList.add('open');
    document.body.style.overflow = 'hidden';
    
    // Scroll to top of article panel for fresh reading UX
    if (this.el.articlePanel) {
      this.el.articlePanel.scrollTop = 0;
    }

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
      document.body.appendChild(overlay);
    }

    this._galImgs = imgs;
    this._galIdx = imgIndex;
    this._showGalImg();
    overlay.classList.add('open');
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
    const overlay = document.getElementById('epGalleryOverlay');
    if (overlay) overlay.classList.remove('open');
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
    if (tab === 'translate') this.translateArticle();
  },

  // ── TTS ──
  ttsRate: 1,
  ttsPaused: false,

  detectLang(text) {
    const hindi = (text.match(/[\u0900-\u097F]/g) || []).length;
    const total = text.length;
    if (hindi / total > 0.3) return 'hi-IN';
    return 'en-US';
  },

  toggleTTS() {
    if (!this.currentArticle) return;

    if (this.ttsPaused && 'speechSynthesis' in window) {
      speechSynthesis.resume();
      this.ttsPaused = false;
      this.ttsPlaying = true;
      this.updateTTSUI();
      return;
    }

    if (this.ttsPlaying) {
      if ('speechSynthesis' in window) {
        speechSynthesis.pause();
        this.ttsPaused = true;
        this.ttsPlaying = false;
        this.updateTTSUI();
      }
      return;
    }

    // Build full text: headline + sub_headline + body content
    const art = this.currentArticle;
    let text = '';
    if (art.headline) text += art.headline + '। ';
    if (art.sub_headline) text += art.sub_headline + '। ';
    // Use body_text (plain text from Quill), fall back to extracting from body_html
    if (art.body_text && art.body_text.trim()) {
      text += art.body_text;
    } else if (art.body_html) {
      // Strip HTML tags to get plain text
      const tmp = document.createElement('div');
      tmp.innerHTML = art.body_html;
      text += tmp.textContent || tmp.innerText || '';
    }
    text = text.trim();
    if (!text) return;

    if ('speechSynthesis' in window) {
      speechSynthesis.cancel();
      this.ttsUtterance = new SpeechSynthesisUtterance(text);
      this.ttsUtterance.lang = this.detectLang(text);
      this.ttsUtterance.rate = this.ttsRate;
      this.ttsUtterance.onend = () => {
        this.ttsPlaying = false;
        this.ttsPaused = false;
        this.updateTTSUI();
        if (this.el.ttsProgress) this.el.ttsProgress.value = 100;
      };
      this.ttsUtterance.onboundary = (e) => {
        if (e.charIndex && this.el.ttsProgress) {
          const pct = Math.round((e.charIndex / text.length) * 100);
          this.el.ttsProgress.value = pct;
        }
      };
      speechSynthesis.speak(this.ttsUtterance);
      this.ttsPlaying = true;
      this.ttsPaused = false;
      this.updateTTSUI();
      this.showToast('Reading article...');
      this.trackEvent('tts_play', { article: this.currentArticle?.headline, lang: this.ttsUtterance.lang });
    } else {
      this.showToast('TTS is not supported in this browser');
    }
  },

  stopTTS() {
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    this.ttsPlaying = false;
    this.ttsPaused = false;
    if (this.el.ttsProgress) this.el.ttsProgress.value = 0;
    this.updateTTSUI();
  },

  cycleTTSSpeed() {
    const speeds = [0.75, 1, 1.25, 1.5, 2];
    const idx = speeds.indexOf(this.ttsRate);
    this.ttsRate = speeds[(idx + 1) % speeds.length];
    if (this.el.ttsSpeed) this.el.ttsSpeed.textContent = this.ttsRate + 'x';
    if (this.ttsPlaying || this.ttsPaused) {
      const wasPlaying = this.ttsPlaying;
      this.stopTTS();
      if (wasPlaying) this.toggleTTS();
    }
  },

  updateTTSUI() {
    if (this.el.ttsPlay) {
      this.el.ttsPlay.innerHTML = this.ttsPlaying
        ? '<i class="fa fa-pause"></i>'
        : '<i class="fa fa-play"></i>';
    }
  },

  // ── Translate ──
  async translateArticle() {
    if (!this.currentArticle || !this.el.translateOutput) return;
    const lang = this.el.translateSelect?.value || 'en';
    const text = this.currentArticle.body_text || this.currentArticle.headline || '';
    if (!text) return;

    this.el.translateOutput.innerHTML = '<div class="ep-summary-loading"><div class="spinner"></div>Translating...</div>';

    try {
      const res = await fetch('/api/epaper/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, target_lang: lang })
      });
      if (res.ok) {
        const data = await res.json();
        this.el.translateOutput.textContent = data.translated_text || text;
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
        this.el.summaryOutput.innerHTML = `<h4>AI Summary</h4><ul>${points.map(p => `<li>${p}</li>`).join('')}</ul>`;
      } else {
        this.el.summaryOutput.innerHTML = '<p>Summary unavailable.</p>';
      }
    } catch (e) {
      this.el.summaryOutput.innerHTML = '<p>Summarization service unavailable.</p>';
    }
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

  // ── Analytics ──
  trackEvent(action, params = {}) {
    if (typeof gtag === 'function') {
      gtag('event', action, { event_category: 'epaper', ...params });
    }
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
};

document.addEventListener('DOMContentLoaded', () => EP.init());
