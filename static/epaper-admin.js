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
  CANVAS_H: 1000,
  HEADER_W: 1100,
  HEADER_H: 140,

  _undoStack: [],

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

    // Ctrl+Z undo
    document.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key === 'z') {
        const tag = document.activeElement?.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || document.activeElement?.isContentEditable) return;
        e.preventDefault();
        this.undo();
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
    try {
      this._pushUndo();
      const imageUrl = await this.uploadImage(file);
      this.editionMeta.masthead_image_url = imageUrl;
      this.renderMastheadPreview();
      this.showToast('Header image uploaded');
    } catch (e) {
      alert(e.message || 'Image upload failed');
    }
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

    for (let i = blocks.length - 1; i >= 0; i--) {
      const b = blocks[i];
      const bx = (b.x || 0) * scale;
      const by = (b.y || 0) * scale;
      const bw = (b.w || 200) * scale;
      const bh = (b.h || 150) * scale;

      // Click inside block → start drag
      if (mx >= bx && mx <= bx + bw && my >= by && my <= by + bh) {
        this._pushUndo();
        this.dragging = true;
        this.activeBlockIdx = i;
        this.dragOffset = { x: mx / scale - (b.x || 0), y: my / scale - (b.y || 0) };
        this.renderCanvas();
        this.showBlockEditor(i);
        e.preventDefault();
        return;
      }
    }

    // Click empty area → deselect
    this.activeBlockIdx = null;
    this.renderCanvas();
    document.getElementById('blockEditor').style.display = 'none';
    document.getElementById('noBlockMsg').style.display = 'block';
  },

  onCanvasMouseMove(e) {
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
      // Clamp
      nx = Math.max(0, Math.min(nx, this.CANVAS_W - (block.w || 200)));
      ny = Math.max(0, Math.min(ny, this.CANVAS_H - (block.h || 150)));
      block.x = Math.round(nx);
      block.y = Math.round(ny);
      this.renderCanvas();
      this.updateSizeInputs();
    }

    if (this.resizing) {
      const dx = (e.clientX - this.resizeStart.mx) / scale;
      const dy = (e.clientY - this.resizeStart.my) / scale;
      const minW = 60;
      const minH = 40;

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
    this.dragging = false;
    this.resizing = false;
    this.resizeStart = null;
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
    block.x = parseInt(document.getElementById('blkX').value) || 0;
    block.y = parseInt(document.getElementById('blkY').value) || 0;
    block.w = Math.max(60, parseInt(document.getElementById('blkW').value) || 200);
    block.h = Math.max(40, parseInt(document.getElementById('blkH').value) || 150);
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
      const hasImg = b.image_url && b.image_url.length > 10;
      const isActive = i === this.activeBlockIdx;
      const bw = b.border_width ?? 0;
      const br = b.border_radius ?? 0;
      const bc = b.border_color || '#e41e26';
      const bs = b.border_style || 'solid';
      const borderCSS = bw > 0 ? `border:${bw}px ${bs} ${bc};` : '';

      return `
        <div class="epc-block ${isActive ? 'active' : ''}" data-idx="${i}"
             style="left:${x}px;top:${y}px;width:${w}px;height:${h}px;border-radius:0;${borderCSS}">
          ${hasImg ? `<img src="${b.image_url}" alt="" draggable="false">` : `
            <div class="epc-empty"><i class="fa fa-image"></i></div>
          `}
          <div class="epc-label">
            ${b.category_label ? `<span class="epc-cat">${b.category_label}</span>` : ''}
            <span class="epc-title">${b.headline || 'Untitled'}</span>
          </div>
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
    list.innerHTML = this.editions.map(ed => `
      <div class="epa-edition-card">
        <div class="epa-edition-info">
          <strong>${ed.date}</strong>
          <span>${ed.name || 'Untitled'}</span>
          <span class="epa-badge">${ed.language || 'Hindi'}</span>
          <span style="color:var(--muted);font-size:12px">${ed.total_pages || 0} pages</span>
        </div>
        <button class="epa-btn epa-btn-sm epa-btn-primary" onclick="EPAdmin.editEdition('${ed.date}')">
          <i class="fa fa-edit"></i> Edit
        </button>
      </div>
    `).join('');
  },

  async editEdition(date) {
    try {
      const res = await fetch(`/api/epaper/edition/${date}`);
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
        }
      });

      document.getElementById('edDate').value = data.date;
      document.getElementById('edName').value = data.name || '';
      document.getElementById('edLang').value = data.language || 'Hindi';
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
      masthead_image_url: this.editionMeta.masthead_image_url || '',
      footer_links: this.editionMeta.footer_links || [],
      pages: this.pages.map(p => ({
        page_number: p.page_number, category: p.category || 'मुख पृष्ठ',
        image_path: p.page_image_url || p.image_path || '',
        page_image_url: p.page_image_url || p.image_path || '',
        layout_json: (p.blocks || []).map(b => ({
          article_id: b.article_id || b.id,
          x: b.x || 0,
          y: b.y || 0,
          width: b.w || b.width || 200,
          height: b.h || b.height || 150,
        })),
        blocks: (p.blocks || []).map(b => ({
          id: b.id, article_id: b.article_id || b.id, headline: b.headline, title: b.headline, sub_headline: b.sub_headline,
          body_text: b.body_text, body_html: b.body_html || '',
          author: b.author || 'Vidyarthi Mitra Desk',
          category_label: b.category_label, category: b.category_label,
          image_url: b.image_url, image: b.image_url,
          gallery: b.gallery || [],
          x: b.x || 0, y: b.y || 0, w: b.w || 200, h: b.h || 150, width: b.w || 200, height: b.h || 150,
          border_width: b.border_width ?? 0, border_radius: b.border_radius ?? 0,
          border_color: b.border_color || '#e41e26', border_style: b.border_style || 'solid',
        })),
        articles: (p.blocks || []).map(b => ({
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
      else { const e = await res.json(); alert(e.error || 'Save failed'); }
    } catch (e) { alert('Network error'); }
  },

  async deleteEdition() {
    if (!this.currentEdition) return;
    if (!confirm(`Delete ${this.currentEdition.date}?`)) return;
    try {
      await fetch(`/api/epaper/admin/edition/${this.currentEdition.date}`, { method: 'DELETE' });
      this.currentEdition = null; this.pages = [];
      document.getElementById('builderSection').style.display = 'none';
      this.loadEditions(); this.showToast('Deleted');
    } catch (e) { alert('Failed'); }
  },

  // ══════ PAGES ══════

  addPage() {
    this._pushUndo();
    this.pages.push({ page_number: this.pages.length + 1, category: 'मुख पृष्ठ', blocks: [] });
    this.renderPageTabs(); this.openPage(this.pages.length - 1);
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
      <div class="epa-page-tab ${i === this.currentPageIdx ? 'active' : ''}" onclick="EPAdmin.openPage(${i})">
        Page ${i + 1}
        ${this.pages.length > 1 ? `<span onclick="event.stopPropagation(); EPAdmin.deletePage(${i})" style="margin-left:6px;cursor:pointer;opacity:.6">×</span>` : ''}
      </div>
    `).join('') + `<div class="epa-page-add" onclick="EPAdmin.addPage()"><i class="fa fa-plus"></i> Add Page</div>`;
  },
  openPage(idx) {
    this.currentPageIdx = idx; this.activeBlockIdx = null;
    this.renderPageTabs(); this.renderCanvas();
    document.getElementById('blockEditor').style.display = 'none';
    document.getElementById('noBlockMsg').style.display = 'block';
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

  removeBlock(idx) {
    if (!confirm('Delete this block?')) return;
    this._pushUndo();
    this.pages[this.currentPageIdx].blocks.splice(idx, 1);
    this.activeBlockIdx = null;
    this.renderCanvas();
    document.getElementById('blockEditor').style.display = 'none';
    document.getElementById('noBlockMsg').style.display = 'block';
  },

  deleteBlock() { if (this.activeBlockIdx !== null) this.removeBlock(this.activeBlockIdx); },

  // ══════ BLOCK EDITOR ══════

  showBlockEditor(idx) {
    const block = this.pages[this.currentPageIdx]?.blocks?.[idx];
    if (!block) return;
    document.getElementById('blockEditor').style.display = 'block';
    document.getElementById('noBlockMsg').style.display = 'none';

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

    // Position & size
    document.getElementById('blkX').value = block.x || 0;
    document.getElementById('blkY').value = block.y || 0;
    document.getElementById('blkW').value = block.w || 200;
    document.getElementById('blkH').value = block.h || 150;

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

  saveBlock() {
    if (this.activeBlockIdx === null) return;
    const block = this.pages[this.currentPageIdx]?.blocks?.[this.activeBlockIdx];
    if (!block) return;
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

    this.renderCanvas();
    this.showToast('✅ Block saved');
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
