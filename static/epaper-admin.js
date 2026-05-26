/* ══════════════════════════════════════════════════
   E-Paper Admin — Free-form Drag & Drop Page Builder
   Complete control over position & size
   ══════════════════════════════════════════════════ */

const EPAdmin = {
  editions: [],
  currentEdition: null,
  pages: [],
  currentPageIdx: 0,
  activeBlockIdx: null,
  quill: null,
  editionMeta: {
    masthead_image_url: '',
    footer_links: [],
  },
  headerActiveIdx: null,
  headerDragging: false,
  headerResizing: false,
  headerDragOffset: { x: 0, y: 0 },
  headerResizeStart: null,

  // Drag state
  dragging: false,
  resizing: false,
  dragOffset: { x: 0, y: 0 },
  resizeStart: null,

  CANVAS_W: 800,
  CANVAS_H: 1131, // A4 at 800px wide (800 × √2)
  HEADER_W: 1100,
  HEADER_H: 140,
  SNAP_THRESHOLD: 6,

  _undoStack: [],
  _guides: [],

  _pushUndo() {
    this._undoStack.push(JSON.parse(JSON.stringify({ pages: this.pages, editionMeta: this.editionMeta })));
    if (this._undoStack.length > 50) this._undoStack.shift();
  },

  undo() {
    if (!this._undoStack.length) { this.showToast('Nothing to undo'); return; }
    const snap = this._undoStack.pop();
    this.pages = snap.pages;
    this.editionMeta = snap.editionMeta;
    this.activeBlockIdx = null;
    this.currentPageIdx = Math.min(this.currentPageIdx, this.pages.length - 1);
    this.renderCanvas();
    this.renderPageTabs();
    this.renderMastheadPreview();
    this.populateFooterLinkInputs();
    if (this.editionMeta.header_items) this.renderHeaderCanvas();
    document.getElementById('blockEditor').style.display = 'none';
    document.getElementById('noBlockMsg').style.display = 'block';
    this.showToast('↩ Undone');
  },

  init() {
    this.loadEditions();
    this.bindEvents();
    this.initQuill();
    this.initEditionMeta();
  },

  initQuill() {
    this.quill = new Quill('#quillEditor', {
      theme: 'snow',
      placeholder: 'Write article content here...',
      modules: {
        toolbar: [
          [{ header: [1, 2, 3, false] }],
          ['bold', 'italic', 'underline', 'strike'],
          [{ color: [] }, { background: [] }],
          [{ list: 'ordered' }, { list: 'bullet' }],
          [{ align: [] }],
          ['blockquote', 'link', 'image'],
          ['clean'],
        ],
      },
    });
  },

  bindEvents() {
    document.getElementById('editionForm')?.addEventListener('submit', e => { e.preventDefault(); this.saveEdition(); });
    document.getElementById('blockForm')?.addEventListener('submit', e => { e.preventDefault(); this.saveBlock(); });
    document.getElementById('deleteEditionBtn')?.addEventListener('click', () => this.deleteEdition());
    document.getElementById('pageImageInput')?.addEventListener('change', e => {
      const file = e.target.files?.[0];
      if (file) this.handlePageImage(file);
      e.target.value = '';
    });
    document.getElementById('clearPageImageBtn')?.addEventListener('click', () => {
      const page = this.pages[this.currentPageIdx];
      if (!page) return;
      this._pushUndo();
      page.page_image_url = '';
      page.image_path = '';
      this.renderCanvas();
      this.showToast('Page image cleared');
    });

    // Thumbnail upload
    const imgUpload = document.getElementById('blockImageUpload');
    const imgInput = document.getElementById('blockImageInput');
    if (imgUpload && imgInput) {
      imgUpload.addEventListener('click', () => imgInput.click());
      imgInput.addEventListener('change', () => { if (imgInput.files.length) this.handleBlockImage(imgInput.files[0]); });
    }

    // Gallery upload
    const galInput = document.getElementById('galleryInput');
    if (galInput) {
      galInput.addEventListener('change', () => {
        Array.from(galInput.files).forEach(f => this.addGalleryImage(f));
        galInput.value = '';
      });
    }

    const mastheadUploadBtn = document.getElementById('mastheadUploadBtn');
    const mastheadInput = document.getElementById('mastheadInput');
    const mastheadClearBtn = document.getElementById('mastheadClearBtn');
    if (mastheadUploadBtn && mastheadInput) {
      mastheadUploadBtn.addEventListener('click', () => mastheadInput.click());
      mastheadInput.addEventListener('change', () => {
        const file = mastheadInput.files?.[0];
        if (file) this.handleMastheadImage(file);
        mastheadInput.value = '';
      });
    }
    if (mastheadClearBtn) {
      mastheadClearBtn.addEventListener('click', () => this.clearMastheadImage());
    }

    ['footerLinkSearch', 'footerLinkWhatsapp', 'footerLinkFacebook', 'footerLinkX'].forEach(id => {
      const input = document.getElementById(id);
      if (input) input.addEventListener('change', () => this.syncEditionMetaFromInputs());
    });

    const addHeaderLogoBtn = document.getElementById('addHeaderLogoBtn');
    if (addHeaderLogoBtn) addHeaderLogoBtn.addEventListener('click', () => this.addHeaderLogo());
    const addHeaderTextBtn = document.getElementById('addHeaderTextBtn');
    if (addHeaderTextBtn) addHeaderTextBtn.addEventListener('click', () => this.addHeaderText());
    const removeHeaderItemBtn = document.getElementById('removeHeaderItemBtn');
    if (removeHeaderItemBtn) removeHeaderItemBtn.addEventListener('click', () => this.removeHeaderItem());

    const hdrText = document.getElementById('hdrText');
    if (hdrText) hdrText.addEventListener('input', () => this.applyHeaderInputs());
    const hdrFontSize = document.getElementById('hdrFontSize');
    if (hdrFontSize) hdrFontSize.addEventListener('input', () => this.applyHeaderInputs());
    const hdrColor = document.getElementById('hdrColor');
    if (hdrColor) hdrColor.addEventListener('input', () => this.applyHeaderInputs());

    const hdrLogoUploadBtn = document.getElementById('hdrLogoUploadBtn');
    const hdrLogoInput = document.getElementById('hdrLogoInput');
    if (hdrLogoUploadBtn && hdrLogoInput) {
      hdrLogoUploadBtn.addEventListener('click', () => hdrLogoInput.click());
      hdrLogoInput.addEventListener('change', () => {
        const file = hdrLogoInput.files?.[0];
        if (file) this.handleHeaderLogoImage(file);
        hdrLogoInput.value = '';
      });
    }

    // Ctrl+Z undo, Ctrl+D duplicate
    document.addEventListener('keydown', e => {
      const tag = document.activeElement?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || document.activeElement?.isContentEditable) return;
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key === 'z') {
        e.preventDefault();
        this.undo();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
        e.preventDefault();
        this.duplicateBlock();
      }
    });

    // Canvas drag events
    const canvas = document.getElementById('pageCanvas');
    if (canvas) {
      canvas.addEventListener('mousedown', e => this.onCanvasMouseDown(e));
      document.addEventListener('mousemove', e => this.onCanvasMouseMove(e));
      document.addEventListener('mouseup', e => this.onCanvasMouseUp(e));
      
      // Event delegation for Add Article button (works across all page redraws)
      canvas.addEventListener('click', (e) => {
        const addBtn = e.target.closest('.epc-add-btn');
        if (addBtn && addBtn.getAttribute('data-action') === 'add-block') {
          e.stopPropagation();
          this.addBlock();
        }
      });
    }

    const headerCanvas = document.getElementById('headerCanvas');
    if (headerCanvas) {
      headerCanvas.addEventListener('mousedown', e => this.onHeaderMouseDown(e));
      document.addEventListener('mousemove', e => this.onHeaderMouseMove(e));
      document.addEventListener('mouseup', () => this.onHeaderMouseUp());
    }
  },

  defaultFooterLinks() {
    return [
      { key: 'search', url: '/epaper' },
      { key: 'whatsapp', url: 'https://wa.me/?text=Vidyarthi%20Mitra%20E-Paper' },
      { key: 'facebook', url: 'https://www.facebook.com/' },
      { key: 'x', url: 'https://x.com/' },
    ];
  },

  initEditionMeta() {
    this.editionMeta = {
      masthead_image_url: '',
      footer_links: this.defaultFooterLinks(),
    };
    this.renderMastheadPreview();
    this.populateFooterLinkInputs();
  },

  loadEditionMeta(data) {
    const footerLinks = Array.isArray(data.footer_links) && data.footer_links.length
      ? data.footer_links
      : this.defaultFooterLinks();
    this.editionMeta = {
      masthead_image_url: data.masthead_image_url || '',
      footer_links: footerLinks,
    };
    this.renderMastheadPreview();
    this.populateFooterLinkInputs();
  },

  syncEditionMetaFromInputs() {
    const search = document.getElementById('footerLinkSearch')?.value || '';
    const whatsapp = document.getElementById('footerLinkWhatsapp')?.value || '';
    const facebook = document.getElementById('footerLinkFacebook')?.value || '';
    const x = document.getElementById('footerLinkX')?.value || '';
    this.editionMeta.footer_links = [
      { key: 'search', url: search },
      { key: 'whatsapp', url: whatsapp },
      { key: 'facebook', url: facebook },
      { key: 'x', url: x },
    ];
  },

  populateFooterLinkInputs() {
    const links = new Map((this.editionMeta.footer_links || []).map(item => [item.key, item.url]));
    const setValue = (id, key) => {
      const input = document.getElementById(id);
      if (input) input.value = links.get(key) || '';
    };
    setValue('footerLinkSearch', 'search');
    setValue('footerLinkWhatsapp', 'whatsapp');
    setValue('footerLinkFacebook', 'facebook');
    setValue('footerLinkX', 'x');
  },

  renderMastheadPreview() {
    const container = document.getElementById('mastheadPreview');
    if (!container) return;
    const url = this.editionMeta.masthead_image_url || '';
    if (!url) {
      container.innerHTML = '<span class="epa-masthead-placeholder">No header image</span>';
      return;
    }
    container.innerHTML = `<img src="${url}" alt="Masthead">`;
  },

  async handleMastheadImage(file) {
    if (!file?.type.startsWith('image/')) return;
    this._pushUndo();
    // Store as data URL directly — avoids server filesystem write (works on Vercel)
    const reader = new FileReader();
    reader.onload = (e) => {
      this.editionMeta.masthead_image_url = e.target.result;
      this.renderMastheadPreview();
      this.showToast('Header image ready');
    };
    reader.readAsDataURL(file);
  },

  clearMastheadImage() {
    this._pushUndo();
    this.editionMeta.masthead_image_url = '';
    this.renderMastheadPreview();
    this.showToast('Header image cleared');
  },

  renderHeaderCanvas() {
    const canvas = document.getElementById('headerCanvas');
    if (!canvas) return;
    const items = this.editionMeta.header_items || [];
    canvas.innerHTML = items.map((item, idx) => {
      const x = item.x ?? 10;
      const y = item.y ?? 10;
      const w = item.w ?? 120;
      const h = item.h ?? 60;
      const isActive = idx === this.headerActiveIdx;
      const content = item.type === 'text'
        ? `<div class="epa-header-text" style="font-size:${item.font_size || 36}px;color:${item.color || '#111827'};font-family:'Noto Serif',serif;">${item.text || 'Newspaper Title'}</div>`
        : `<img src="${item.image_url || ''}" alt="">`;
      return `
        <div class="epa-header-item ${isActive ? 'active' : ''}" data-idx="${idx}" style="left:${x}px;top:${y}px;width:${w}px;height:${h}px;">
          ${content}
          ${isActive ? `
            <div class="epa-header-handle" data-handle="nw"></div>
            <div class="epa-header-handle" data-handle="ne"></div>
            <div class="epa-header-handle" data-handle="se"></div>
            <div class="epa-header-handle" data-handle="sw"></div>
          ` : ''}
        </div>
      `;
    }).join('');
  },

  addHeaderLogo() {
    this._pushUndo();
    const items = this.editionMeta.header_items || [];
    items.push({
      id: Date.now(),
      type: 'logo',
      x: 20, y: 20, w: 140, h: 80,
      image_url: '',
    });
    this.editionMeta.header_items = items;
    this.headerActiveIdx = items.length - 1;
    this.renderHeaderCanvas();
    this.updateHeaderInputs();
  },

  addHeaderText() {
    this._pushUndo();
    const items = this.editionMeta.header_items || [];
    items.push({
      id: Date.now(),
      type: 'text',
      x: 200, y: 20, w: 600, h: 80,
      text: 'Vidyarthi Mitra',
      font_size: 48,
      color: '#111827',
    });
    this.editionMeta.header_items = items;
    this.headerActiveIdx = items.length - 1;
    this.renderHeaderCanvas();
    this.updateHeaderInputs();
  },

  removeHeaderItem() {
    if (this.headerActiveIdx === null) return;
    this._pushUndo();
    this.editionMeta.header_items.splice(this.headerActiveIdx, 1);
    this.headerActiveIdx = null;
    this.renderHeaderCanvas();
    this.updateHeaderInputs();
  },

  updateHeaderInputs() {
    const item = this.editionMeta.header_items?.[this.headerActiveIdx];
    const textInput = document.getElementById('hdrText');
    const fontInput = document.getElementById('hdrFontSize');
    const colorInput = document.getElementById('hdrColor');
    if (!item) {
      if (textInput) textInput.value = '';
      if (fontInput) fontInput.value = 36;
      if (colorInput) colorInput.value = '#111827';
      return;
    }
    if (textInput) textInput.value = item.text || '';
    if (fontInput) fontInput.value = item.font_size || 36;
    if (colorInput) colorInput.value = item.color || '#111827';
  },

  applyHeaderInputs() {
    const item = this.editionMeta.header_items?.[this.headerActiveIdx];
    if (!item || item.type !== 'text') return;
    const textInput = document.getElementById('hdrText');
    const fontInput = document.getElementById('hdrFontSize');
    const colorInput = document.getElementById('hdrColor');
    item.text = textInput?.value || item.text || '';
    item.font_size = parseInt(fontInput?.value || item.font_size || 36, 10);
    item.color = colorInput?.value || item.color || '#111827';
    this.renderHeaderCanvas();
  },

  async handleHeaderLogoImage(file) {
    if (!file?.type.startsWith('image/') || this.headerActiveIdx === null) return;
    try {
      const imageUrl = await this.uploadImage(file);
      const item = this.editionMeta.header_items?.[this.headerActiveIdx];
      if (item && item.type === 'logo') {
        item.image_url = imageUrl;
        this.renderHeaderCanvas();
        this.showToast('Logo uploaded');
      }
    } catch (e) {
      alert(e.message || 'Image upload failed');
    }
  },

  onHeaderMouseDown(e) {
    const canvas = document.getElementById('headerCanvas');
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const scale = rect.width / this.HEADER_W;
    const items = this.editionMeta.header_items || [];

    const handleEl = e.target.closest('.epa-header-handle');
    if (handleEl) {
      const itemEl = handleEl.closest('.epa-header-item');
      const idx = itemEl ? parseInt(itemEl.dataset.idx, 10) : NaN;
      const item = Number.isNaN(idx) ? null : items[idx];
      if (!item) return;
      this._pushUndo();
      this.headerResizing = true;
      this.headerActiveIdx = idx;
      this.headerResizeStart = {
        mx: e.clientX,
        my: e.clientY,
        x: item.x || 0,
        y: item.y || 0,
        w: item.w || 120,
        h: item.h || 60,
        handle: handleEl.dataset.handle || 'se',
      };
      this.renderHeaderCanvas();
      this.updateHeaderInputs();
      e.preventDefault();
      return;
    }

    for (let i = items.length - 1; i >= 0; i--) {
      const it = items[i];
      const x = (it.x || 0) * scale;
      const y = (it.y || 0) * scale;
      const w = (it.w || 120) * scale;
      const h = (it.h || 60) * scale;
      if (mx >= x && mx <= x + w && my >= y && my <= y + h) {
        this._pushUndo();
        this.headerDragging = true;
        this.headerActiveIdx = i;
        this.headerDragOffset = { x: mx / scale - (it.x || 0), y: my / scale - (it.y || 0) };
        this.renderHeaderCanvas();
        this.updateHeaderInputs();
        e.preventDefault();
        return;
      }
    }

    this.headerActiveIdx = null;
    this.renderHeaderCanvas();
    this.updateHeaderInputs();
  },

  onHeaderMouseMove(e) {
    if (!this.headerDragging && !this.headerResizing) return;
    const canvas = document.getElementById('headerCanvas');
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const scale = rect.width / this.HEADER_W;
    const item = this.editionMeta.header_items?.[this.headerActiveIdx];
    if (!item) return;

    if (this.headerDragging) {
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      let nx = mx / scale - this.headerDragOffset.x;
      let ny = my / scale - this.headerDragOffset.y;
      nx = Math.max(0, Math.min(nx, this.HEADER_W - (item.w || 120)));
      ny = Math.max(0, Math.min(ny, this.HEADER_H - (item.h || 60)));
      item.x = Math.round(nx);
      item.y = Math.round(ny);
      this.renderHeaderCanvas();
    }

    if (this.headerResizing) {
      const dx = (e.clientX - this.headerResizeStart.mx) / scale;
      const dy = (e.clientY - this.headerResizeStart.my) / scale;
      let nx = this.headerResizeStart.x;
      let ny = this.headerResizeStart.y;
      let nw = this.headerResizeStart.w;
      let nh = this.headerResizeStart.h;
      const handle = this.headerResizeStart.handle || 'se';
      const minW = 40;
      const minH = 30;

      if (handle.includes('e')) nw = this.headerResizeStart.w + dx;
      if (handle.includes('s')) nh = this.headerResizeStart.h + dy;
      if (handle.includes('w')) { nw = this.headerResizeStart.w - dx; nx = this.headerResizeStart.x + dx; }
      if (handle.includes('n')) { nh = this.headerResizeStart.h - dy; ny = this.headerResizeStart.y + dy; }

      if (nw < minW) { if (handle.includes('w')) nx -= (minW - nw); nw = minW; }
      if (nh < minH) { if (handle.includes('n')) ny -= (minH - nh); nh = minH; }

      nx = Math.max(0, Math.min(nx, this.HEADER_W - nw));
      ny = Math.max(0, Math.min(ny, this.HEADER_H - nh));
      nw = Math.min(nw, this.HEADER_W - nx);
      nh = Math.min(nh, this.HEADER_H - ny);

      item.x = Math.round(nx);
      item.y = Math.round(ny);
      item.w = Math.round(nw);
      item.h = Math.round(nh);
      this.renderHeaderCanvas();
    }
  },

  onHeaderMouseUp() {
    this.headerDragging = false;
    this.headerResizing = false;
    this.headerResizeStart = null;
  },

  // ══════ SMART ALIGNMENT GUIDES ══════

  _getSnapPositions(excludeIdx) {
    const page = this.pages[this.currentPageIdx];
    const blocks = page?.blocks || [];
    const xs = new Set([0, this.CANVAS_W, Math.round(this.CANVAS_W / 2)]);
    const ys = new Set([0, this.CANVAS_H, Math.round(this.CANVAS_H / 2)]);
    blocks.forEach((b, i) => {
      if (i === excludeIdx) return;
      const bx = b.x || 0, by = b.y || 0, bw = b.w || 200, bh = b.h || 150;
      xs.add(bx); xs.add(bx + bw); xs.add(Math.round(bx + bw / 2));
      ys.add(by); ys.add(by + bh); ys.add(Math.round(by + bh / 2));
    });
    return { xs: [...xs], ys: [...ys] };
  },

  _applySnap(nx, ny, bw, bh, excludeIdx) {
    const T = this.SNAP_THRESHOLD;
    const { xs, ys } = this._getSnapPositions(excludeIdx);
    const guides = [];

    const xCandidates = [
      { edge: nx,           offset: 0 },
      { edge: nx + bw,      offset: bw },
      { edge: nx + bw / 2,  offset: bw / 2 },
    ];
    let bestXDist = T + 1, bestXSnap = null;
    for (const { edge, offset } of xCandidates) {
      for (const sx of xs) {
        const d = Math.abs(edge - sx);
        if (d < bestXDist) { bestXDist = d; bestXSnap = { x: sx - offset, guide: sx }; }
      }
    }
    if (bestXSnap) { nx = bestXSnap.x; guides.push({ type: 'v', pos: bestXSnap.guide }); }

    const yCandidates = [
      { edge: ny,           offset: 0 },
      { edge: ny + bh,      offset: bh },
      { edge: ny + bh / 2,  offset: bh / 2 },
    ];
    let bestYDist = T + 1, bestYSnap = null;
    for (const { edge, offset } of yCandidates) {
      for (const sy of ys) {
        const d = Math.abs(edge - sy);
        if (d < bestYDist) { bestYDist = d; bestYSnap = { y: sy - offset, guide: sy }; }
      }
    }
    if (bestYSnap) { ny = bestYSnap.y; guides.push({ type: 'h', pos: bestYSnap.guide }); }

    return { x: nx, y: ny, guides };
  },

  _renderGuides(lines) {
    const container = document.getElementById('pageCanvas');
    if (!container) return;
    container.querySelectorAll('.epc-guide').forEach(el => el.remove());
    lines.forEach(line => {
      const el = document.createElement('div');
      if (line.type === 'v') {
        el.className = 'epc-guide epc-guide-v';
        el.style.left = line.pos + 'px';
      } else {
        el.className = 'epc-guide epc-guide-h';
        el.style.top = line.pos + 'px';
      }
      container.appendChild(el);
    });
  },

  _computeGapIndicators(dragged, blocks, excludeIdx) {
    const gaps = [];
    const { x: dx, y: dy, w: dw, h: dh } = dragged;
    for (let i = 0; i < blocks.length; i++) {
      if (i === excludeIdx) continue;
      const b = blocks[i];
      const bx = b.x || 0, by = b.y || 0, bw = b.w || 200, bh = b.h || 150;

      // Horizontal gap — only if blocks have overlapping Y range
      const yA = Math.max(dy, by), yB = Math.min(dy + dh, by + bh);
      if (yB > yA) {
        const midY = Math.round((yA + yB) / 2);
        if (bx >= dx + dw) {
          gaps.push({ type: 'gap-h', x1: dx + dw, x2: bx, y: midY, dist: Math.round(bx - (dx + dw)) });
        } else if (bx + bw <= dx) {
          gaps.push({ type: 'gap-h', x1: bx + bw, x2: dx, y: midY, dist: Math.round(dx - (bx + bw)) });
        }
      }

      // Vertical gap — only if blocks have overlapping X range
      const xA = Math.max(dx, bx), xB = Math.min(dx + dw, bx + bw);
      if (xB > xA) {
        const midX = Math.round((xA + xB) / 2);
        if (by >= dy + dh) {
          gaps.push({ type: 'gap-v', y1: dy + dh, y2: by, x: midX, dist: Math.round(by - (dy + dh)) });
        } else if (by + bh <= dy) {
          gaps.push({ type: 'gap-v', y1: by + bh, y2: dy, x: midX, dist: Math.round(dy - (by + bh)) });
        }
      }
    }
    return gaps;
  },

  _renderGapIndicators(gaps) {
    const container = document.getElementById('pageCanvas');
    if (!container) return;
    container.querySelectorAll('.epc-gap').forEach(el => el.remove());
    gaps.forEach(gap => {
      const el = document.createElement('div');
      el.className = 'epc-gap';
      if (gap.type === 'gap-h') {
        const w = gap.x2 - gap.x1;
        if (w <= 0) return;
        el.style.cssText = `left:${gap.x1}px;top:${gap.y - 0.5}px;width:${w}px;height:1px;`;
        const lbl = document.createElement('span');
        lbl.className = 'epc-gap-label';
        lbl.textContent = gap.dist + 'px';
        lbl.style.cssText = 'left:50%;top:-9px;transform:translateX(-50%);';
        el.appendChild(lbl);
      } else {
        const h = gap.y2 - gap.y1;
        if (h <= 0) return;
        el.style.cssText = `top:${gap.y1}px;left:${gap.x - 0.5}px;width:1px;height:${h}px;`;
        const lbl = document.createElement('span');
        lbl.className = 'epc-gap-label';
        lbl.textContent = gap.dist + 'px';
        lbl.style.cssText = 'top:50%;left:5px;transform:translateY(-50%);';
        el.appendChild(lbl);
      }
      container.appendChild(el);
    });
  },

  // ══════ CANVAS DRAG & DROP ══════

  onCanvasMouseDown(e) {
    const canvas = document.getElementById('pageCanvas');
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const scale = rect.width / this.CANVAS_W;

    // Do not deselect or re-render if clicking the Add Article button
    if (e.target.closest('.epc-add-btn')) return;

    // Check if clicking a resize handle
    const page = this.pages[this.currentPageIdx];
    if (!page) return;
    const blocks = page.blocks || [];

    const handleEl = e.target.closest('.epc-resize-handle');
    if (handleEl) {
      const blockEl = handleEl.closest('.epc-block');
      const idx = blockEl ? parseInt(blockEl.dataset.idx, 10) : NaN;
      const b = Number.isNaN(idx) ? null : blocks[idx];
      if (!b) return;

      this._pushUndo();
      this.resizing = true;
      this.activeBlockIdx = idx;
      this.resizeStart = {
        mx: e.clientX,
        my: e.clientY,
        x: b.x || 0,
        y: b.y || 0,
        w: b.w || 200,
        h: b.h || 150,
        handle: handleEl.dataset.handle || 'se',
      };
      this.renderCanvas();
      this.showBlockEditor(idx);
      e.preventDefault();
      return;
    }

    // Use event delegation — whichever block DOM element is under the cursor wins
    // This respects visual stacking and handles thin shapes (e.g. 6px lines) correctly
    const clickedBlockEl = e.target.closest('.epc-block');
    if (clickedBlockEl) {
      const idx = parseInt(clickedBlockEl.dataset.idx, 10);
      const b = Number.isNaN(idx) ? null : blocks[idx];
      if (b) {
        this._pushUndo();
        this.dragging = true;
        this.activeBlockIdx = idx;
        this.dragOffset = { x: mx / scale - (b.x || 0), y: my / scale - (b.y || 0) };
        this.renderCanvas();
        this.showBlockEditor(idx);
        e.preventDefault();
        return;
      }
    }

    // Click/drag on empty area — if page has a background image, start draw-to-hotspot
    const hasPageImage = !!(page?.page_image_url || page?.image_path);
    if (hasPageImage) {
      this.activeBlockIdx = null;
      this.renderCanvas();
      document.getElementById('blockEditor').style.display = 'none';
      document.getElementById('noBlockMsg').style.display = 'block';
      this._drawStart = { mx, my, scale };
      this._drawing = true;
      e.preventDefault();
      return;
    }

    // Click empty area → deselect
    this.activeBlockIdx = null;
    this.renderCanvas();
    document.getElementById('blockEditor').style.display = 'none';
    document.getElementById('noBlockMsg').style.display = 'block';
  },

  onCanvasMouseMove(e) {
    if (this._drawing && this._drawStart) {
      const canvas = document.getElementById('pageCanvas');
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const scale = rect.width / this.CANVAS_W;
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const x0 = this._drawStart.mx / scale;
      const y0 = this._drawStart.my / scale;
      const x1 = mx / scale;
      const y1 = my / scale;
      this._drawRect = {
        x: Math.round(Math.min(x0, x1)),
        y: Math.round(Math.min(y0, y1)),
        w: Math.round(Math.abs(x1 - x0)),
        h: Math.round(Math.abs(y1 - y0)),
      };
      // Update preview overlay (canvas innerHTML is stable — no renderCanvas call needed)
      let pr = canvas.querySelector('.epc-draw-preview');
      if (!pr) { pr = document.createElement('div'); pr.className = 'epc-draw-preview'; canvas.appendChild(pr); }
      pr.style.cssText = `position:absolute;left:${this._drawRect.x * scale}px;top:${this._drawRect.y * scale}px;width:${this._drawRect.w * scale}px;height:${this._drawRect.h * scale}px;border:2px dashed #ff6600;background:rgba(255,102,0,.08);pointer-events:none;box-sizing:border-box;z-index:999;`;
      return;
    }
    if (!this.dragging && !this.resizing) return;
    const canvas = document.getElementById('pageCanvas');
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const scale = rect.width / this.CANVAS_W;
    const page = this.pages[this.currentPageIdx];
    const block = page?.blocks?.[this.activeBlockIdx];
    if (!block) return;

    if (this.dragging) {
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      let nx = mx / scale - this.dragOffset.x;
      let ny = my / scale - this.dragOffset.y;
      // Clamp to canvas bounds
      nx = Math.max(0, Math.min(nx, this.CANVAS_W - (block.w || 200)));
      ny = Math.max(0, Math.min(ny, this.CANVAS_H - (block.h || 150)));
      // Smart snap
      const snapped = this._applySnap(nx, ny, block.w || 200, block.h || 150, this.activeBlockIdx);
      block.x = Math.round(snapped.x);
      block.y = Math.round(snapped.y);
      this._guides = snapped.guides;
      this.renderCanvas();
      this._renderGuides(this._guides);
      const gaps = this._computeGapIndicators(
        { x: block.x, y: block.y, w: block.w || 200, h: block.h || 150 },
        page?.blocks || [], this.activeBlockIdx
      );
      this._renderGapIndicators(gaps);
      this.updateSizeInputs();
    }

    if (this.resizing) {
      const dx = (e.clientX - this.resizeStart.mx) / scale;
      const dy = (e.clientY - this.resizeStart.my) / scale;
      const isShapeBlock = block.type === 'shape';
      const minW = isShapeBlock ? 2 : 60;
      const minH = isShapeBlock ? 2 : 40;

      let nx = this.resizeStart.x;
      let ny = this.resizeStart.y;
      let nw = this.resizeStart.w;
      let nh = this.resizeStart.h;
      const handle = this.resizeStart.handle || 'se';

      if (handle.includes('e')) {
        nw = this.resizeStart.w + dx;
      }
      if (handle.includes('s')) {
        nh = this.resizeStart.h + dy;
      }
      if (handle.includes('w')) {
        nw = this.resizeStart.w - dx;
        nx = this.resizeStart.x + dx;
      }
      if (handle.includes('n')) {
        nh = this.resizeStart.h - dy;
        ny = this.resizeStart.y + dy;
      }

      if (nw < minW) {
        if (handle.includes('w')) nx -= (minW - nw);
        nw = minW;
      }
      if (nh < minH) {
        if (handle.includes('n')) ny -= (minH - nh);
        nh = minH;
      }

      if (nx < 0) {
        if (handle.includes('w')) {
          nw += nx;
          nx = 0;
        } else {
          nx = 0;
        }
      }
      if (ny < 0) {
        if (handle.includes('n')) {
          nh += ny;
          ny = 0;
        } else {
          ny = 0;
        }
      }
      if (nx + nw > this.CANVAS_W) {
        nw = this.CANVAS_W - nx;
      }
      if (ny + nh > this.CANVAS_H) {
        nh = this.CANVAS_H - ny;
      }

      nw = Math.max(minW, nw);
      nh = Math.max(minH, nh);

      if (nx + nw > this.CANVAS_W) nx = this.CANVAS_W - nw;
      if (ny + nh > this.CANVAS_H) ny = this.CANVAS_H - nh;

      block.x = Math.round(nx);
      block.y = Math.round(ny);
      block.w = Math.round(nw);
      block.h = Math.round(nh);
      this.renderCanvas();
      this.updateSizeInputs();
    }
  },

  onCanvasMouseUp() {
    if (this._drawing) {
      this._drawing = false;
      const canvas = document.getElementById('pageCanvas');
      if (canvas) { const pr = canvas.querySelector('.epc-draw-preview'); if (pr) pr.remove(); }
      const r = this._drawRect;
      this._drawRect = null;
      this._drawStart = null;
      if (r && r.w > 20 && r.h > 20) {
        // Create a new article block at the drawn position
        const page = this.pages[this.currentPageIdx];
        if (!page) return;
        if (!page.blocks) page.blocks = [];
        this._pushUndo();
        page.blocks.push({
          id: Date.now(),
          article_id: Date.now(),
          headline: '', sub_headline: '', body_text: '', body_html: '',
          category_label: '', image_url: '', gallery: [],
          x: r.x, y: r.y, w: r.w, h: r.h,
          border_width: 1, border_radius: 0, border_color: '#e41e26', border_style: 'solid',
        });
        this.activeBlockIdx = page.blocks.length - 1;
        this.renderCanvas();
        this.showBlockEditor(this.activeBlockIdx);
        this.showToast('Hotspot created — fill in article details');
      }
      return;
    }
    this.dragging = false;
    this.resizing = false;
    this.resizeStart = null;
    this._guides = [];
    this._renderGuides([]);
    this._renderGapIndicators([]);
  },

  updateSizeInputs() {
    const block = this.pages[this.currentPageIdx]?.blocks?.[this.activeBlockIdx];
    if (!block) return;
    const xi = document.getElementById('blkX');
    const yi = document.getElementById('blkY');
    const wi = document.getElementById('blkW');
    const hi = document.getElementById('blkH');
    if (xi) xi.value = block.x || 0;
    if (yi) yi.value = block.y || 0;
    if (wi) wi.value = block.w || 200;
    if (hi) hi.value = block.h || 150;
  },

  applySizeInputs() {
    if (this.activeBlockIdx === null) return;
    const block = this.pages[this.currentPageIdx]?.blocks?.[this.activeBlockIdx];
    if (!block) return;
    this._pushUndo();
    const isShapeBlock = block.type === 'shape';
    block.x = parseInt(document.getElementById('blkX').value) || 0;
    block.y = parseInt(document.getElementById('blkY').value) || 0;
    block.w = Math.max(isShapeBlock ? 2 : 60, parseInt(document.getElementById('blkW').value) || (isShapeBlock ? 10 : 200));
    block.h = Math.max(isShapeBlock ? 2 : 40, parseInt(document.getElementById('blkH').value) || (isShapeBlock ? 10 : 150));
    this.renderCanvas();
  },

  fitBlockToImage() {
    const block = this.pages[this.currentPageIdx]?.blocks?.[this.activeBlockIdx];
    if (!block || !block.image_url) return;

    const img = new Image();
    img.onload = () => {
      const maxW = this.CANVAS_W - (block.x || 0);
      const maxH = this.CANVAS_H - (block.y || 0);
      let targetW = img.naturalWidth || block.w || 200;
      let targetH = img.naturalHeight || block.h || 150;

      if (targetW > maxW || targetH > maxH) {
        const scale = Math.min(maxW / targetW, maxH / targetH);
        targetW = Math.floor(targetW * scale);
        targetH = Math.floor(targetH * scale);
      }

      block.w = Math.max(60, targetW);
      block.h = Math.max(40, targetH);
      this.renderCanvas();
      this.updateSizeInputs();
    };
    img.onerror = () => {
      this.showToast('Could not load image to fit.');
    };
    img.src = block.image_url;
  },

  // ══════ CANVAS RENDERING ══════

  renderCanvas() {
    const container = document.getElementById('pageCanvas');
    if (!container) return;
    const page = this.pages[this.currentPageIdx];
    if (!page) return;
    const blocks = page.blocks || [];

    const pageUrl = page.page_image_url || page.image_path || '';
    const isPdf = pageUrl.toLowerCase().endsWith('.pdf');
    container.classList.toggle('has-page-image', Boolean(pageUrl));
    container.style.backgroundImage = (!isPdf && pageUrl) ? `url("${pageUrl}")` : '';

    const pdfBg = isPdf
      ? `<iframe class="epc-pdf-bg" src="${pageUrl}" style="position:absolute;inset:0;width:100%;height:100%;border:none;pointer-events:none;z-index:0;"></iframe>`
      : '';

    container.innerHTML = pdfBg + blocks.map((b, i) => {
      const x = b.x || 0, y = b.y || 0, w = b.w || 200, h = b.h || 150;
      const isActive = i === this.activeBlockIdx;
      const isShape = b.type === 'shape';

      const gotoPageBadge = b.goto_page
        ? `<span style="position:absolute;bottom:3px;left:4px;background:rgba(0,0,0,.65);color:#fff;font-size:8px;padding:1px 4px;border-radius:3px;pointer-events:none;z-index:10;"><i class="fa fa-link" style="font-size:7px"></i> P${b.goto_page}</span>`
        : '';

      let innerContent;
      if (isShape) {
        innerContent = this._renderShapeContent(b) + gotoPageBadge;
      } else {
        const previewSrc = (b.image_url && b.image_url.length > 10) ? b.image_url : (b.gallery?.[0] || '');
        const hasImg = Boolean(previewSrc);
        innerContent = (hasImg ? `<img src="${previewSrc}" alt="" draggable="false">` : `<div class="epc-empty"><i class="fa fa-image"></i></div>`) +
          `<div class="epc-label">
            ${b.category_label ? `<span class="epc-cat">${b.category_label}</span>` : ''}
            <span class="epc-title">${b.headline || 'Untitled'}</span>
          </div>` + gotoPageBadge;
      }

      const articleBorderCSS = !isShape && (b.border_width ?? 0) > 0
        ? `border:${b.border_width}px ${b.border_style || 'solid'} ${b.border_color || '#e41e26'};`
        : '';
      const overflowCSS = isShape ? 'overflow:visible;' : 'overflow:hidden;';

      return `
        <div class="epc-block ${isActive ? 'active' : ''}${isShape ? ' epc-shape' : ''}" data-idx="${i}"
             style="left:${x}px;top:${y}px;width:${w}px;height:${h}px;border-radius:0;${articleBorderCSS}${overflowCSS}">
          ${innerContent}
          <span class="epc-num">${i + 1}</span>
          <button class="epc-del" onmousedown="event.stopPropagation(); EPAdmin.removeBlock(${i})"><i class="fa fa-times"></i></button>
          ${isActive ? `
            <div class="epc-resize-handle" data-handle="nw"></div>
            <div class="epc-resize-handle" data-handle="n"></div>
            <div class="epc-resize-handle" data-handle="ne"></div>
            <div class="epc-resize-handle" data-handle="e"></div>
            <div class="epc-resize-handle" data-handle="se"></div>
            <div class="epc-resize-handle" data-handle="s"></div>
            <div class="epc-resize-handle" data-handle="sw"></div>
            <div class="epc-resize-handle" data-handle="w"></div>
          ` : ''}
          <span class="epc-dims">${w}×${h}</span>
        </div>
      `;
    }).join('') + `
      <button class="epc-add-btn" data-action="add-block"><i class="fa fa-plus"></i> Add Article</button>
    `;
  },

  // ══════ EDITIONS ══════

  async loadEditions() {
    try {
      const res = await fetch('/api/epaper/editions');
      const data = await res.json();
      this.editions = data.editions || [];
      this.renderEditionsList();
    } catch (e) { console.error(e); }
  },

  renderEditionsList() {
    const list = document.getElementById('editionsList');
    if (!list) return;
    if (!this.editions.length) { list.innerHTML = '<div class="epa-empty">No editions yet.</div>'; return; }
    list.innerHTML = this.editions.slice().sort((a, b) => b.date.localeCompare(a.date)).map(ed => {
      const isPublished = ed.published !== false;
      const pubBadge = isPublished
        ? `<span style="background:#fff7ed;color:#c2410c;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">✓ Published</span>`
        : `<span style="background:#fef9c3;color:#854d0e;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">Draft</span>`;
      return `
        <div class="epa-edition-card">
          <div class="epa-edition-info">
            <strong>${ed.date}</strong>
            <span>${ed.name || 'Untitled'}</span>
            <span class="epa-badge">${ed.language || 'Hindi'}</span>
            <span style="color:var(--muted);font-size:12px">${ed.total_pages || 0} pages</span>
            ${pubBadge}
          </div>
          <div class="epa-edition-actions" style="display:flex;gap:6px;flex-shrink:0;flex-wrap:wrap;">
            <button class="epa-btn epa-btn-sm epa-btn-primary" onclick="EPAdmin.editEdition('${ed.date}', '${ed.language || 'Hindi'}')">
              <i class="fa fa-edit"></i> Edit
            </button>
            <button class="epa-btn epa-btn-sm" style="background:#fff7ed;color:#c2410c;border:1px solid #fed7aa;" onclick="EPAdmin.openBackupPanel('${ed.date}', '${ed.language || 'Hindi'}')">
              <i class="fa fa-history"></i> Restore
            </button>
            <button class="epa-btn epa-btn-sm ${isPublished ? 'epa-btn-danger' : 'epa-btn-success'}"
              onclick="EPAdmin.togglePublish('${ed.date}', ${!isPublished}, '${ed.language || 'Hindi'}')">
              <i class="fa fa-${isPublished ? 'eye-slash' : 'eye'}"></i> ${isPublished ? 'Unpublish' : 'Publish'}
            </button>
            <button class="epa-btn epa-btn-sm epa-btn-danger" onclick="EPAdmin.deleteEditionByDate('${ed.date}', '${ed.language || 'Hindi'}')">
              <i class="fa fa-trash"></i> Delete
            </button>
          </div>
        </div>
      `;
    }).join('');
  },

  async openBackupPanel(date, lang) {
    const section = document.getElementById('backupSection');
    const listEl  = document.getElementById('backupList');
    if (!section || !listEl) return;
    section.style.display = 'block';
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    listEl.innerHTML = '<div class="epa-empty"><i class="fa fa-spinner fa-spin"></i> Loading backups...</div>';

    try {
      const res = await fetch(`/api/epaper/admin/backups?date=${encodeURIComponent(date)}&lang=${encodeURIComponent(lang)}`);
      const data = await res.json();
      const backups = data.backups || [];
      if (!backups.length) {
        listEl.innerHTML = '<div class="epa-empty">Koi backup nahi mila. Abhi "Save All Changes" click karo — pehla backup ban jaayega.</div>';
        return;
      }
      listEl.innerHTML = backups.map((b, i) => {
        const dt = new Date(b.saved_at);
        const dateStr = dt.toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' });
        const timeStr = dt.toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit' });
        return `
          <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border:1px solid #e2e8f0;border-radius:10px;margin-bottom:8px;background:${i===0?'#fff7ed':'#fff'};">
            <div>
              <div style="font-weight:700;font-size:14px;color:#0f172a;">${b.name || b.date} <span style="font-weight:400;color:#64748b;font-size:12px;">(${b.language})</span></div>
              <div style="font-size:12px;color:#64748b;margin-top:3px;">
                <i class="fa fa-clock"></i> ${dateStr} at ${timeStr}
                &nbsp;·&nbsp; <i class="fa fa-file"></i> ${b.pages} pages
                ${i===0 ? ' &nbsp;<span style="background:#fff7ed;color:#c2410c;padding:1px 7px;border-radius:6px;font-size:11px;font-weight:700;">Latest</span>' : ''}
              </div>
            </div>
            <button class="epa-btn epa-btn-sm epa-btn-success" onclick="EPAdmin.restoreBackup(${b.id}, '${b.name || b.date}')">
              <i class="fa fa-undo"></i> Restore
            </button>
          </div>`;
      }).join('');
    } catch (e) {
      listEl.innerHTML = '<div class="epa-empty" style="color:#ef4444;">Backup load nahi hua. Dobara try karo.</div>';
    }
  },

  closeBackupPanel() {
    const section = document.getElementById('backupSection');
    if (section) section.style.display = 'none';
  },

  async restoreBackup(backupId, name) {
    if (!confirm(`"${name}" ko restore karein? Current edition ki jagah yeh version aa jaayega.`)) return;
    try {
      const res = await fetch(`/api/epaper/admin/backups/${backupId}/restore`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        this.showToast('✅ ' + (data.message || 'Edition restore ho gayi!'));
        this.closeBackupPanel();
        this.loadEditions();
      } else {
        alert('Restore failed: ' + (data.error || 'Unknown error'));
      }
    } catch (e) {
      alert('Network error: ' + e.message);
    }
  },

  async togglePublish(date, publish, lang) {
    const langParam = lang ? `?lang=${encodeURIComponent(lang)}` : '';
    try {
      const res = await fetch(`/api/epaper/admin/edition/${date}/publish${langParam}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ published: publish }),
      });
      if (res.ok) {
        this.showToast(publish ? '✅ Edition published!' : '⚠ Edition unpublished');
        this.loadEditions();
      } else {
        const err = await res.json().catch(() => ({}));
        this.showToast('Error: ' + (err.error || 'Failed'));
      }
    } catch (e) {
      this.showToast('Network error');
    }
  },

  async editEdition(date, lang) {
    const langParam = lang ? `?lang=${encodeURIComponent(lang)}` : '';
    try {
      const res = await fetch(`/api/epaper/admin/edition/${date}${langParam}`);
      if (!res.ok) { alert('Not found'); return; }
      const data = await res.json();
      this.currentEdition = data;
      this.pages = data.pages || [];

      this.loadEditionMeta(data);

      // Migrate old format
      this.pages.forEach(p => {
        if (!p.blocks) {
          p.blocks = (p.articles || []).map((a, i) => ({
            id: a.id || Date.now() + i,
            type: a.type || 'article',
            article_id: a.article_id || a.id || Date.now() + i,
            headline: a.headline || '', sub_headline: a.sub_headline || '',
            body_text: a.body_text || '', body_html: a.body_html || '',
            category_label: a.category_label || '',
            image_url: a.article_image_url || a.image_url || '',
            gallery: a.gallery || [],
            x: a.x ?? ((a.width_pct ? (a.width_pct / 100) * this.CANVAS_W * i * 0.3 : i * 210) || 0),
            y: a.y ?? 0,
            w: a.w || a.width || (a.width_pct ? (a.width_pct / 100) * this.CANVAS_W : 200),
            h: a.h || a.height || a.height_px || 150,
            border_width: a.border_width ?? 0, border_radius: a.border_radius ?? 0,
            border_color: a.border_color || '#e41e26', border_style: a.border_style || 'solid',
          }));
        } else {
          // Ensure shape blocks loaded from JSON have type set
          p.blocks.forEach(b => {
            if (!b.type && b.shape_type) b.type = 'shape';
          });
        }
      });

      document.getElementById('edDate').value = data.date;
      document.getElementById('edName').value = data.name || '';
      document.getElementById('edLang').value = data.language || 'Hindi';
      document.getElementById('edStatus').value = (data.published !== false) ? 'published' : 'draft';
      if (!this.pages.length) this.addPage();
      document.getElementById('builderSection').style.display = 'block';
      document.getElementById('deleteEditionBtn').style.display = 'inline-flex';
      this.renderPageTabs();
      this.openPage(0);
      document.getElementById('builderSection').scrollIntoView({ behavior: 'smooth' });
    } catch (e) { alert('Error loading edition'); }
  },

  async saveEdition() {
    const date = document.getElementById('edDate').value;
    const name = document.getElementById('edName').value;
    const lang = document.getElementById('edLang').value;
    const status = document.getElementById('edStatus').value;
    if (!date) { alert('Date required'); return; }
    this.syncEditionMetaFromInputs();
    try {
      await this.ensureUploadedImages();
    } catch (e) {
      alert(e.message || 'Image upload failed');
      return;
    }

    const payload = {
      date, name: name || `Edition ${date}`, language: lang,
      published: status === 'published',
      masthead_image_url: this.editionMeta.masthead_image_url || '',
      footer_links: this.editionMeta.footer_links || [],
      pages: this.pages.map(p => ({
        page_number: p.page_number, category: p.category || 'मुख पृष्ठ',
        date_range: p.date_range || '',
        image_path: p.page_image_url || p.image_path || '',
        page_image_url: p.page_image_url || p.image_path || '',
        layout_json: (p.blocks || []).map(b => ({
          article_id: b.article_id || b.id,
          x: b.x || 0,
          y: b.y || 0,
          width: b.w || b.width || 200,
          height: b.h || b.height || 150,
        })),
        blocks: (p.blocks || []).map(b => {
          const base = { id: b.id, type: b.type || 'article', x: b.x || 0, y: b.y || 0, w: b.w || 200, h: b.h || 150, width: b.w || 200, height: b.h || 150 };
          if (b.type === 'shape') {
            return { ...base, shape_type: b.shape_type, fill_color: b.fill_color, stroke_color: b.stroke_color, stroke_width: b.stroke_width, opacity: b.opacity, corner_radius: b.corner_radius, no_fill: b.no_fill, goto_page: b.goto_page || null };
          }
          return { ...base, article_id: b.article_id || b.id, headline: b.headline, title: b.headline, sub_headline: b.sub_headline, body_text: b.body_text, body_html: b.body_html || '', author: b.author || 'Vidyarthi Mitra Desk', category_label: b.category_label, category: b.category_label, image_url: b.image_url, image: b.image_url, gallery: b.gallery || [], border_width: b.border_width ?? 0, border_radius: b.border_radius ?? 0, border_color: b.border_color || '#e41e26', border_style: b.border_style || 'solid', goto_page: b.goto_page || null };
        }),
        articles: (p.blocks || []).filter(b => b.type !== 'shape').map(b => ({
          id: b.id, article_id: b.article_id || b.id, headline: b.headline, title: b.headline, sub_headline: b.sub_headline,
          body_text: b.body_text, body_html: b.body_html || '',
          author: b.author || 'Vidyarthi Mitra Desk',
          category_label: b.category_label, category: b.category_label,
          article_image_url: b.image_url,
          image_url: b.image_url, image: b.image_url, gallery: b.gallery || [],
          x: b.x, y: b.y, w: b.w, h: b.h, width: b.w, height: b.h,
          border_width: b.border_width, border_radius: b.border_radius,
          border_color: b.border_color, border_style: b.border_style,
        })),
      })),
    };

    try {
      const res = await fetch('/api/epaper/admin/edition', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) { this.showToast('✅ Edition saved!'); this.loadEditions(); }
      else {
        let msg = `Save failed (${res.status})`;
        try { const e = await res.json(); msg = e.error || msg; } catch {}
        alert(msg);
      }
    } catch (e) { alert('Network error: ' + e.message); }
  },

  async deleteEdition() {
    if (!this.currentEdition) return;
    if (!confirm(`Delete ${this.currentEdition.date}?`)) return;
    const lang = this.currentEdition.language || 'Hindi';
    const langParam = `?lang=${encodeURIComponent(lang)}`;
    try {
      await fetch(`/api/epaper/admin/edition/${this.currentEdition.date}${langParam}`, { method: 'DELETE' });
      this.currentEdition = null; this.pages = [];
      document.getElementById('builderSection').style.display = 'none';
      this.loadEditions(); this.showToast('Deleted');
    } catch (e) { alert('Failed'); }
  },

  async deleteEditionByDate(date, lang) {
    if (!confirm(`Delete edition ${date}${lang ? ` (${lang})` : ''}? This cannot be undone.`)) return;
    const langParam = lang ? `?lang=${encodeURIComponent(lang)}` : '';
    try {
      const res = await fetch(`/api/epaper/admin/edition/${date}${langParam}`, { method: 'DELETE' });
      if (!res.ok) { this.showToast('Delete failed'); return; }
      // If this edition is currently open in the builder, close it
      if (this.currentEdition?.date === date && (!lang || this.currentEdition?.language === lang)) {
        this.currentEdition = null; this.pages = [];
        document.getElementById('builderSection').style.display = 'none';
      }
      this.loadEditions(); this.showToast('Edition deleted');
    } catch (e) { this.showToast('Delete failed'); }
  },

  // ══════ PAGES ══════

  addPage() {
    if (this.pages.length === 0) {
      this._pushUndo();
      this.pages.push({ page_number: 1, category: 'मुख पृष्ठ', date_range: '', blocks: [] });
      this.renderPageTabs(); this.openPage(0);
      return;
    }
    // Pages 2+ — ask for category + date range
    const modal = document.getElementById('epaAddPageModal');
    if (!modal) {
      this._pushUndo();
      this.pages.push({ page_number: this.pages.length + 1, category: 'News', date_range: '', blocks: [] });
      this.renderPageTabs(); this.openPage(this.pages.length - 1);
      return;
    }
    document.getElementById('newPageCategory').value = '';
    document.getElementById('newPageDateRange').value = '';
    modal.style.display = 'flex';
    setTimeout(() => document.getElementById('newPageCategory').focus(), 50);
    const doAdd = () => {
      const category = document.getElementById('newPageCategory').value.trim() || 'News';
      const dateRange = document.getElementById('newPageDateRange').value.trim() || '';
      modal.style.display = 'none';
      off();
      this._pushUndo();
      this.pages.push({ page_number: this.pages.length + 1, category, date_range: dateRange, blocks: [] });
      this.renderPageTabs(); this.openPage(this.pages.length - 1);
    };
    const doCancel = () => { modal.style.display = 'none'; off(); };
    const onKey = (e) => { if (e.key === 'Enter') doAdd(); if (e.key === 'Escape') doCancel(); };
    const off = () => {
      document.getElementById('epaAddPageConfirm').removeEventListener('click', doAdd);
      document.getElementById('epaAddPageCancel').removeEventListener('click', doCancel);
      document.removeEventListener('keydown', onKey);
    };
    document.getElementById('epaAddPageConfirm').addEventListener('click', doAdd);
    document.getElementById('epaAddPageCancel').addEventListener('click', doCancel);
    document.addEventListener('keydown', onKey);
  },
  deletePage(idx) {
    if (this.pages.length <= 1) return;
    if (!confirm(`Delete page ${idx + 1}?`)) return;
    this._pushUndo();
    this.pages.splice(idx, 1);
    this.pages.forEach((p, i) => p.page_number = i + 1);
    this.renderPageTabs(); this.openPage(Math.min(idx, this.pages.length - 1));
  },
  renderPageTabs() {
    const tabs = document.getElementById('pageTabs');
    if (!tabs) return;
    tabs.innerHTML = this.pages.map((p, i) => `
      <div class="epa-page-tab ${i === this.currentPageIdx ? 'active' : ''}" data-idx="${i}">
        Page ${i + 1}
        ${this.pages.length > 1 ? `<span class="epa-tab-del" data-idx="${i}" style="margin-left:6px;cursor:pointer;opacity:.6">×</span>` : ''}
      </div>
    `).join('') + `<div class="epa-page-add" onclick="EPAdmin.addPage()"><i class="fa fa-plus"></i> Add Page</div>`;

    tabs.querySelectorAll('.epa-page-tab').forEach(tab => {
      const i = parseInt(tab.dataset.idx);

      tab.addEventListener('click', e => {
        if (e.target.classList.contains('epa-tab-del')) {
          EPAdmin.deletePage(parseInt(e.target.dataset.idx));
        } else if (!EPAdmin._didDrag) {
          EPAdmin.openPage(i);
        }
        EPAdmin._didDrag = false;
      });

      tab.draggable = true;

      tab.addEventListener('dragstart', e => {
        EPAdmin._dragSrcIdx = i;
        EPAdmin._didDrag = false;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(i));
        setTimeout(() => { tab.style.opacity = '0.4'; }, 0);
      });

      tab.addEventListener('dragover', e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (i !== EPAdmin._dragSrcIdx) tab.classList.add('drag-over');
      });

      tab.addEventListener('dragleave', () => tab.classList.remove('drag-over'));

      tab.addEventListener('drop', e => {
        e.preventDefault();
        e.stopPropagation();
        const src = EPAdmin._dragSrcIdx;
        if (src == null || src === i) return;
        EPAdmin._didDrag = true;
        const moved = EPAdmin.pages.splice(src, 1)[0];
        EPAdmin.pages.splice(i, 0, moved);
        EPAdmin.pages.forEach((p, n) => p.page_number = n + 1);
        EPAdmin.currentPageIdx = i;
        EPAdmin._dragSrcIdx = null;
        EPAdmin.renderPageTabs();
        EPAdmin.renderCanvas();
      });

      tab.addEventListener('dragend', () => {
        EPAdmin._dragSrcIdx = null;
        tabs.querySelectorAll('.epa-page-tab').forEach(t => {
          t.style.opacity = '';
          t.classList.remove('drag-over');
        });
      });
    });
  },

  openPage(idx) {
    this.currentPageIdx = idx; this.activeBlockIdx = null;
    this.renderPageTabs(); this.renderCanvas();
    document.getElementById('blockEditor').style.display = 'none';
    document.getElementById('noBlockMsg').style.display = 'block';
    this.updatePageMetaUI();
  },
  updatePageMetaUI() {
    const row = document.getElementById('pageMetaRow');
    if (!row) return;
    const idx = this.currentPageIdx;
    if (idx === 0) { row.style.display = 'none'; return; }
    row.style.display = 'block';
    const page = this.pages[idx];
    document.getElementById('pageCategoryInput').value = page?.category || '';
    document.getElementById('pageDateRangeInput').value = page?.date_range || '';
    this._refreshPageHeaderPreview();
  },
  _refreshPageHeaderPreview() {
    const idx = this.currentPageIdx;
    const page = this.pages[idx];
    if (!page) return;
    const num = String(idx + 1).padStart(2, '0');
    const cat = (page.category || 'SECTION').toUpperCase();
    const dr = page.date_range || '';
    const numEl = document.getElementById('prevPageNum');
    const catEl = document.getElementById('prevPageCat');
    const dateEl = document.getElementById('prevPageDate');
    if (numEl) numEl.textContent = num;
    if (catEl) catEl.textContent = cat;
    if (dateEl) dateEl.textContent = dr;
  },
  savePageMeta() {
    const page = this.pages[this.currentPageIdx];
    if (!page) return;
    const catEl = document.getElementById('pageCategoryInput');
    const drEl = document.getElementById('pageDateRangeInput');
    if (catEl) page.category = catEl.value;
    if (drEl) page.date_range = drEl.value;
    this._refreshPageHeaderPreview();
  },

  // ══════ BLOCK CRUD ══════

  addBlock() {
    this._pushUndo();
    let page = this.pages[this.currentPageIdx];
    if (!page) {
      this.addPage();
      page = this.pages[this.currentPageIdx];
      if (!page) return;
    }
    if (!page.blocks) page.blocks = [];
    const count = page.blocks.length;
    page.blocks.push({
      id: Date.now(),
      article_id: Date.now(),
      headline: '', sub_headline: '', body_text: '', body_html: '',
      category_label: '', image_url: '', gallery: [],
      x: 10 + (count % 3) * 270, y: 10 + Math.floor(count / 3) * 170,
      w: 250, h: 150,
      border_width: 0, border_radius: 0, border_color: '#e41e26', border_style: 'solid',
    });
    this.activeBlockIdx = page.blocks.length - 1;
    this.renderCanvas();
    this.showBlockEditor(this.activeBlockIdx);
  },

  addShape(shapeType) {
    let page = this.pages[this.currentPageIdx];
    if (!page) { this.addPage(); page = this.pages[this.currentPageIdx]; }
    if (!page) { this.showToast('No page selected'); return; }
    this._pushUndo();
    if (!page.blocks) page.blocks = [];
    const sizes = {
      'line-h':   { w: 400, h: 6 },
      'line-v':   { w: 6, h: 300 },
      'rect':     { w: 220, h: 140 },
      'circle':   { w: 160, h: 160 },
      'triangle': { w: 160, h: 140 },
      'arrow':    { w: 240, h: 40 },
    };
    const { w, h } = sizes[shapeType] || { w: 160, h: 160 };
    page.blocks.push({
      id: Date.now(),
      type: 'shape',
      shape_type: shapeType,
      x: Math.round((this.CANVAS_W - w) / 2),
      y: Math.round((this.CANVAS_H - h) / 2),
      w, h,
      fill_color: '#e41e26',
      stroke_color: '#111827',
      stroke_width: 0,
      no_fill: false,
      opacity: 100,
      corner_radius: 0,
    });
    this.activeBlockIdx = page.blocks.length - 1;
    this.renderCanvas();
    this.showBlockEditor(this.activeBlockIdx);
    this.showToast('Shape added — drag to reposition');
  },

  _renderShapeContent(b) {
    const fill = b.no_fill ? 'none' : (b.fill_color || '#e41e26');
    const stroke = b.stroke_color || '#111827';
    const sw = b.stroke_width || 0;
    const op = (b.opacity ?? 100) / 100;
    const cr = b.corner_radius || 0;

    switch (b.shape_type) {
      case 'rect':
        return `<div style="width:100%;height:100%;background:${fill};border:${sw}px solid ${sw > 0 ? stroke : 'transparent'};border-radius:${cr}%;opacity:${op};box-sizing:border-box;"></div>`;
      case 'circle':
        return `<div style="width:100%;height:100%;background:${fill};border:${sw}px solid ${sw > 0 ? stroke : 'transparent'};border-radius:50%;opacity:${op};box-sizing:border-box;"></div>`;
      case 'line-h':
        return `<div style="width:100%;height:100%;background:${fill === 'none' ? stroke : fill};border-radius:${cr}%;opacity:${op};"></div>`;
      case 'line-v':
        return `<div style="width:100%;height:100%;background:${fill === 'none' ? stroke : fill};border-radius:${cr}%;opacity:${op};"></div>`;
      case 'triangle': {
        const svgSw = sw > 0 ? `stroke="${stroke}" stroke-width="${sw * 2}" stroke-linejoin="round"` : '';
        return `<svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none" style="opacity:${op};display:block;"><polygon points="50,2 98,98 2,98" fill="${fill}" ${svgSw}/></svg>`;
      }
      case 'arrow': {
        const arFill = fill === 'none' ? 'transparent' : fill;
        return `<svg width="100%" height="100%" viewBox="0 0 120 40" preserveAspectRatio="none" style="opacity:${op};display:block;overflow:visible;"><path d="M2 20 H90 M78 5 L110 20 L78 35" fill="none" stroke="${arFill === 'transparent' ? stroke : arFill}" stroke-width="${Math.max(2, sw + 3)}" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
      }
      default:
        return `<div style="width:100%;height:100%;background:${fill};opacity:${op};"></div>`;
    }
  },

  removeBlock(idx) {
    if (!confirm('Delete this block?')) return;
    this._pushUndo();
    this.pages[this.currentPageIdx].blocks.splice(idx, 1);
    this.activeBlockIdx = null;
    this.renderCanvas();
    document.getElementById('blockEditor').style.display = 'none';
    document.getElementById('noBlockMsg').style.display = 'block';
  },

  duplicateBlock() {
    if (this.activeBlockIdx === null) return;
    const page = this.pages[this.currentPageIdx];
    if (!page) return;
    this._pushUndo();
    const orig = page.blocks[this.activeBlockIdx];
    const clone = JSON.parse(JSON.stringify(orig));
    clone.id = Date.now();
    if (clone.article_id) clone.article_id = Date.now() + 1;
    clone.x = Math.min((orig.x || 0) + 20, this.CANVAS_W - (orig.w || 200));
    clone.y = Math.min((orig.y || 0) + 20, this.CANVAS_H - (orig.h || 150));
    page.blocks.push(clone);
    this.activeBlockIdx = page.blocks.length - 1;
    this.renderCanvas();
    this.showBlockEditor(this.activeBlockIdx);
    this.showToast('Duplicated — Ctrl+D');
  },

  deleteBlock() { if (this.activeBlockIdx !== null) this.removeBlock(this.activeBlockIdx); },

  // ══════ BLOCK EDITOR ══════

  showBlockEditor(idx) {
    const block = this.pages[this.currentPageIdx]?.blocks?.[idx];
    if (!block) return;
    document.getElementById('blockEditor').style.display = 'block';
    document.getElementById('noBlockMsg').style.display = 'none';

    const isShape = block.type === 'shape';
    document.getElementById('shapeEditorSection').style.display = isShape ? 'block' : 'none';
    document.getElementById('blockImageSection').style.display = isShape ? 'none' : 'block';
    document.getElementById('blockBorderSection').style.display = isShape ? 'none' : 'block';
    document.getElementById('blockArticleSection').style.display = isShape ? 'none' : 'block';

    // Position & size (always shown)
    const wInput = document.getElementById('blkW');
    const hInput = document.getElementById('blkH');
    wInput.min = isShape ? '2' : '60';
    hInput.min = isShape ? '2' : '40';
    document.getElementById('blkX').value = block.x || 0;
    document.getElementById('blkY').value = block.y || 0;
    wInput.value = block.w || (isShape ? 10 : 200);
    hInput.value = block.h || (isShape ? 10 : 150);

    // Page link (all blocks)
    document.getElementById('blkGotoPage').value = block.goto_page || '';

    if (isShape) {
      // Populate shape inputs
      document.getElementById('shapeType').value = block.shape_type || 'rect';
      document.getElementById('shapeFill').value = block.fill_color || '#e41e26';
      document.getElementById('shapeStroke').value = block.stroke_color || '#111827';
      document.getElementById('shapeStrokeWidth').value = block.stroke_width || 0;
      document.getElementById('shapeStrokeVal').textContent = (block.stroke_width || 0) + 'px';
      document.getElementById('shapeOpacity').value = block.opacity ?? 100;
      document.getElementById('shapeOpacityVal').textContent = (block.opacity ?? 100) + '%';
      document.getElementById('shapeCornerRadius').value = block.corner_radius || 0;
      document.getElementById('shapeCornerVal').textContent = (block.corner_radius || 0) + '%';
      document.getElementById('shapeNoFill').checked = !!block.no_fill;
      // Show corner radius only for rect
      const showCorner = ['rect', 'circle'].includes(block.shape_type || '');
      document.getElementById('shapeCornerGroup').style.display = showCorner ? '' : 'none';
      return;
    }

    // Article block
    document.getElementById('blkArticleId').value = block.article_id || block.id || '';
    document.getElementById('blkHeadline').value = block.headline || '';
    document.getElementById('blkSubheadline').value = block.sub_headline || '';
    document.getElementById('blkCategory').value = block.category_label || '';

    if (block.body_html) this.quill.root.innerHTML = block.body_html;
    else if (block.body_text) this.quill.setText(block.body_text);
    else this.quill.setText('');

    const label = document.getElementById('blockImageLabel');
    if (block.image_url && block.image_url.length > 10)
      label.innerHTML = `<img src="${block.image_url}" alt="">`;
    else
      label.innerHTML = '<i class="fa fa-cloud-upload-alt"></i>Upload image';

    // Border
    document.getElementById('blkBorderWidth').value = block.border_width ?? 0;
    document.getElementById('blkBorderRadius').value = block.border_radius ?? 0;
    document.getElementById('blkBorderColor').value = block.border_color || '#e41e26';
    document.getElementById('blkBorderStyle').value = block.border_style || 'solid';
    document.getElementById('bwVal').textContent = (block.border_width ?? 0) + 'px';
    document.getElementById('brVal').textContent = (block.border_radius ?? 0) + 'px';
    this.updateBorderPreview();
    this.renderGallery();
  },

  applyShapeInputs() {
    if (this.activeBlockIdx === null) return;
    const block = this.pages[this.currentPageIdx]?.blocks?.[this.activeBlockIdx];
    if (!block || block.type !== 'shape') return;
    block.shape_type = document.getElementById('shapeType').value;
    block.fill_color = document.getElementById('shapeFill').value;
    block.stroke_color = document.getElementById('shapeStroke').value;
    block.stroke_width = parseInt(document.getElementById('shapeStrokeWidth').value) || 0;
    block.opacity = parseInt(document.getElementById('shapeOpacity').value) || 100;
    block.corner_radius = parseInt(document.getElementById('shapeCornerRadius').value) || 0;
    block.no_fill = document.getElementById('shapeNoFill').checked;
    // Show corner radius only for rect/circle
    const showCorner = ['rect', 'circle'].includes(block.shape_type);
    document.getElementById('shapeCornerGroup').style.display = showCorner ? '' : 'none';
    this.renderCanvas();
  },

  saveBlock() {
    if (this.activeBlockIdx === null) return;
    const block = this.pages[this.currentPageIdx]?.blocks?.[this.activeBlockIdx];
    if (!block) return;
    if (block.type === 'shape') { this.showToast('Shape properties auto-saved'); return; }
    this._pushUndo();

    block.article_id = document.getElementById('blkArticleId').value || block.id;
    block.headline = document.getElementById('blkHeadline').value;
    block.sub_headline = document.getElementById('blkSubheadline').value;
    block.category_label = document.getElementById('blkCategory').value;
    block.body_html = this.quill.root.innerHTML;
    block.body_text = this.quill.getText().trim();
    block.x = parseInt(document.getElementById('blkX').value) || 0;
    block.y = parseInt(document.getElementById('blkY').value) || 0;
    block.w = Math.max(60, parseInt(document.getElementById('blkW').value) || 200);
    block.h = Math.max(40, parseInt(document.getElementById('blkH').value) || 150);
    block.border_width = parseInt(document.getElementById('blkBorderWidth').value) || 0;
    block.border_radius = parseInt(document.getElementById('blkBorderRadius').value) || 0;
    block.border_color = document.getElementById('blkBorderColor').value || '#e41e26';
    block.border_style = document.getElementById('blkBorderStyle').value || 'solid';
    const gotoVal = parseInt(document.getElementById('blkGotoPage').value);
    block.goto_page = gotoVal >= 1 ? gotoVal : null;

    this.renderCanvas();
    this.showToast('✅ Block saved');
  },

  applyGotoPage() {
    if (this.activeBlockIdx === null) return;
    const block = this.pages[this.currentPageIdx]?.blocks?.[this.activeBlockIdx];
    if (!block) return;
    const gotoVal = parseInt(document.getElementById('blkGotoPage').value);
    block.goto_page = gotoVal >= 1 ? gotoVal : null;
  },

  async uploadImage(file) {
    const form = new FormData();
    form.append('image', file);
    const res = await fetch('/api/epaper/admin/upload-image', {
      method: 'POST',
      body: form,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Image upload failed');
    return data.url;
  },

  dataUrlToFile(dataUrl, fallbackName = 'epaper-image.png') {
    const parts = dataUrl.split(',');
    const meta = parts[0] || '';
    const mime = (meta.match(/data:(.*?);base64/) || [])[1] || 'image/png';
    const ext = (mime.split('/')[1] || 'png').replace('jpeg', 'jpg');
    const binary = atob(parts[1] || '');
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new File([bytes], fallbackName.replace(/\.[^.]+$/, '') + '.' + ext, { type: mime });
  },

  async uploadDataUrl(dataUrl, name) {
    return this.uploadImage(this.dataUrlToFile(dataUrl, name));
  },

  async ensureUploadedImages() {
    // Upload masthead if still a local data URL (not yet on Cloudinary)
    if (this.editionMeta.masthead_image_url?.startsWith('data:image/')) {
      this.editionMeta.masthead_image_url = await this.uploadDataUrl(
        this.editionMeta.masthead_image_url, 'masthead.png'
      );
    }
    for (const page of this.pages) {
      if (page.page_image_url?.startsWith('data:image/') || page.page_image_url?.startsWith('data:application/pdf')) {
        const ext = page.page_image_url.startsWith('data:application/pdf') ? 'pdf' : 'png';
        page.page_image_url = await this.uploadDataUrl(page.page_image_url, `page-${page.page_number}.${ext}`);
        page.image_path = page.page_image_url;
      }
      if (page.image_path?.startsWith('data:image/') || page.image_path?.startsWith('data:application/pdf')) {
        const ext = page.image_path.startsWith('data:application/pdf') ? 'pdf' : 'png';
        page.image_path = await this.uploadDataUrl(page.image_path, `page-${page.page_number}.${ext}`);
        page.page_image_url = page.image_path;
      }
      for (const block of (page.blocks || [])) {
        if (block.image_url?.startsWith('data:image/')) {
          block.image_url = await this.uploadDataUrl(block.image_url, `article-${block.article_id || block.id}.png`);
        }
        if (Array.isArray(block.gallery)) {
          for (let i = 0; i < block.gallery.length; i++) {
            if (block.gallery[i]?.startsWith('data:image/')) {
              block.gallery[i] = await this.uploadDataUrl(block.gallery[i], `gallery-${block.article_id || block.id}-${i}.png`);
            }
          }
        }
      }
    }
  },

  async handleBlockImage(file) {
    const isPdf = file?.type === 'application/pdf' || file?.name?.toLowerCase().endsWith('.pdf');
    if (!file?.type.startsWith('image/') && !isPdf) return;
    if (this.activeBlockIdx === null) return;
    try {
      const imageUrl = await this.uploadImage(file);
      const block = this.pages[this.currentPageIdx]?.blocks?.[this.activeBlockIdx];
      if (block) {
        block.image_url = imageUrl;
        if (!isPdf) {
          // Auto-resize block height to match image's natural aspect ratio (no white bars, no cropping)
          const img = new Image();
          img.onload = () => {
            if (img.naturalWidth && img.naturalHeight) {
              const newH = Math.round((block.w || 200) * img.naturalHeight / img.naturalWidth);
              block.h = Math.max(40, Math.min(newH, this.CANVAS_H - (block.y || 0)));
              this.renderCanvas();
              this.updateSizeInputs();
            }
          };
          img.src = imageUrl;
        }
        this.renderCanvas();
        const label = document.getElementById('blockImageLabel');
        if (isPdf) {
          label.innerHTML = `<i class="fa fa-file-pdf" style="font-size:32px;color:#e41e26"></i><span style="font-size:11px;display:block;margin-top:4px">${file.name}</span>`;
        } else {
          label.innerHTML = `<img src="${imageUrl}" alt="">`;
        }
        this.showToast(isPdf ? 'PDF uploaded' : 'Article image uploaded');
      }
    } catch (e) {
      alert(e.message || 'Upload failed');
    }
  },

  async handlePageImage(file) {
    const isPdf = file?.type === 'application/pdf' || file?.name?.toLowerCase().endsWith('.pdf');
    if (!file?.type.startsWith('image/') && !isPdf) return;
    try {
      const imageUrl = await this.uploadImage(file);
      const page = this.pages[this.currentPageIdx];
      if (!page) return;
      page.page_image_url = imageUrl;
      page.image_path = imageUrl;
      this.renderCanvas();
      this.showToast(isPdf ? 'PDF uploaded' : 'Page image uploaded');
    } catch (e) {
      alert(e.message || 'Upload failed');
    }
  },

  async handlePdfToPages(file) {
    if (!file || file.type !== 'application/pdf') return;
    const statusEl = document.getElementById('pdfToPageStatus');
    if (statusEl) { statusEl.style.display = ''; statusEl.textContent = 'Uploading PDF…'; }
    try {
      const fd = new FormData();
      fd.append('pdf', file);
      const res = await fetch('/api/epaper/admin/pdf-to-pages', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || 'Conversion failed');
      const urls = data.pages || [];
      if (!urls.length) throw new Error('No pages returned');
      this._pushUndo();
      // Replace all current pages with PDF pages
      this.pages = urls.map((url, i) => ({
        page_number: i + 1,
        category: i === 0 ? 'मुख पृष्ठ' : 'News',
        date_range: '',
        page_image_url: url,
        image_path: url,
        blocks: [],
      }));
      this.currentPageIdx = 0;
      this.renderPageTabs();
      this.openPage(0);
      if (statusEl) { statusEl.textContent = `${urls.length} pages imported!`; setTimeout(() => { statusEl.style.display = 'none'; }, 3000); }
      this.showToast(`${urls.length} pages imported from PDF`);
    } catch (e) {
      if (statusEl) { statusEl.textContent = `Error: ${e.message}`; }
      this.showToast('PDF import failed: ' + e.message);
    }
  },

  renderGallery() {
    const container = document.getElementById('articleGallery');
    if (!container) return;
    const block = this.pages[this.currentPageIdx]?.blocks?.[this.activeBlockIdx];
    const gallery = block?.gallery || [];
    container.innerHTML = gallery.map((img, i) => `
      <div class="epb-gallery-item">
        <img src="${img}" alt="">
        <button class="epb-gal-del" onclick="event.stopPropagation(); EPAdmin.removeGalleryImage(${i})"><i class="fa fa-times"></i></button>
      </div>
    `).join('') + `<div class="epb-gal-add" onclick="document.getElementById('galleryInput').click()"><i class="fa fa-plus"></i></div>`;
  },

  async addGalleryImage(file) {
    if (!file?.type.startsWith('image/') || this.activeBlockIdx === null) return;
    try {
      const imageUrl = await this.uploadImage(file);
      const block = this.pages[this.currentPageIdx]?.blocks?.[this.activeBlockIdx];
      if (block) {
        if (!block.gallery) block.gallery = [];
        block.gallery.push(imageUrl);
        this.renderGallery();
        this.showToast('Gallery image uploaded');
      }
    } catch (e) {
      alert(e.message || 'Image upload failed');
    }
  },

  removeGalleryImage(idx) {
    const block = this.pages[this.currentPageIdx]?.blocks?.[this.activeBlockIdx];
    if (block?.gallery) { block.gallery.splice(idx, 1); this.renderGallery(); }
  },

  updateBorderPreview() {
    const p = document.getElementById('borderPreview');
    if (!p) return;
    p.style.border = `${document.getElementById('blkBorderWidth').value}px ${document.getElementById('blkBorderStyle').value} ${document.getElementById('blkBorderColor').value}`;
    p.style.borderRadius = `${document.getElementById('blkBorderRadius').value}px`;
  },

  showToast(msg) {
    const t = document.getElementById('adminToast');
    if (!t) return;
    t.textContent = msg; t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2500);
  },
};

document.addEventListener('DOMContentLoaded', () => EPAdmin.init());
