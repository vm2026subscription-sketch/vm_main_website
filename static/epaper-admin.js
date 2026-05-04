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

  // Drag state
  dragging: false,
  resizing: false,
  dragOffset: { x: 0, y: 0 },
  resizeStart: null,

  CANVAS_W: 800,
  CANVAS_H: 1000,

  init() {
    this.loadEditions();
    this.bindEvents();
    this.initQuill();
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

    // Canvas drag events
    const canvas = document.getElementById('pageCanvas');
    if (canvas) {
      canvas.addEventListener('mousedown', e => this.onCanvasMouseDown(e));
      document.addEventListener('mousemove', e => this.onCanvasMouseMove(e));
      document.addEventListener('mouseup', e => this.onCanvasMouseUp(e));
    }
  },

  // ══════ CANVAS DRAG & DROP ══════

  onCanvasMouseDown(e) {
    const canvas = document.getElementById('pageCanvas');
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const scale = rect.width / this.CANVAS_W;

    // Check if clicking a resize handle
    const page = this.pages[this.currentPageIdx];
    if (!page) return;
    const blocks = page.blocks || [];

    for (let i = blocks.length - 1; i >= 0; i--) {
      const b = blocks[i];
      const bx = (b.x || 0) * scale;
      const by = (b.y || 0) * scale;
      const bw = (b.w || 200) * scale;
      const bh = (b.h || 150) * scale;

      // Resize handle (bottom-right corner, 14x14)
      if (mx >= bx + bw - 14 && mx <= bx + bw + 4 && my >= by + bh - 14 && my <= by + bh + 4) {
        this.resizing = true;
        this.activeBlockIdx = i;
        this.resizeStart = { mx: e.clientX, my: e.clientY, w: b.w || 200, h: b.h || 150 };
        this.renderCanvas();
        this.showBlockEditor(i);
        e.preventDefault();
        return;
      }

      // Click inside block → start drag
      if (mx >= bx && mx <= bx + bw && my >= by && my <= by + bh) {
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
      block.w = Math.max(60, Math.round(this.resizeStart.w + dx));
      block.h = Math.max(40, Math.round(this.resizeStart.h + dy));
      // Clamp to canvas
      if ((block.x || 0) + block.w > this.CANVAS_W) block.w = this.CANVAS_W - (block.x || 0);
      if ((block.y || 0) + block.h > this.CANVAS_H) block.h = this.CANVAS_H - (block.y || 0);
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
    block.x = parseInt(document.getElementById('blkX').value) || 0;
    block.y = parseInt(document.getElementById('blkY').value) || 0;
    block.w = Math.max(60, parseInt(document.getElementById('blkW').value) || 200);
    block.h = Math.max(40, parseInt(document.getElementById('blkH').value) || 150);
    this.renderCanvas();
  },

  // ══════ CANVAS RENDERING ══════

  renderCanvas() {
    const container = document.getElementById('pageCanvas');
    if (!container) return;
    const page = this.pages[this.currentPageIdx];
    if (!page) return;
    const blocks = page.blocks || [];

    container.innerHTML = blocks.map((b, i) => {
      const x = b.x || 0, y = b.y || 0, w = b.w || 200, h = b.h || 150;
      const hasImg = b.image_url && b.image_url.length > 10;
      const isActive = i === this.activeBlockIdx;
      const bw = b.border_width ?? 0;
      const br = b.border_radius ?? 10;
      const bc = b.border_color || '#e41e26';
      const bs = b.border_style || 'solid';
      const borderCSS = bw > 0 ? `border:${bw}px ${bs} ${bc};` : '';

      return `
        <div class="epc-block ${isActive ? 'active' : ''}" data-idx="${i}"
             style="left:${x}px;top:${y}px;width:${w}px;height:${h}px;border-radius:${br}px;${borderCSS}">
          ${hasImg ? `<img src="${b.image_url}" alt="" draggable="false">` : `
            <div class="epc-empty"><i class="fa fa-image"></i></div>
          `}
          <div class="epc-label">
            ${b.category_label ? `<span class="epc-cat">${b.category_label}</span>` : ''}
            <span class="epc-title">${b.headline || 'Untitled'}</span>
          </div>
          <span class="epc-num">${i + 1}</span>
          <button class="epc-del" onmousedown="event.stopPropagation(); EPAdmin.removeBlock(${i})"><i class="fa fa-times"></i></button>
          ${isActive ? '<div class="epc-resize"></div>' : ''}
          <span class="epc-dims">${w}×${h}</span>
        </div>
      `;
    }).join('') + `
      <button class="epc-add-btn" onclick="EPAdmin.addBlock()"><i class="fa fa-plus"></i> Add Article</button>
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

      // Migrate old format
      this.pages.forEach(p => {
        if (!p.blocks) {
          p.blocks = (p.articles || []).map((a, i) => ({
            id: a.id || Date.now() + i,
            headline: a.headline || '', sub_headline: a.sub_headline || '',
            body_text: a.body_text || '', body_html: a.body_html || '',
            category_label: a.category_label || '',
            image_url: a.article_image_url || a.image_url || '',
            gallery: a.gallery || [],
            x: (a.width_pct ? (a.width_pct / 100) * this.CANVAS_W * i * 0.3 : i * 210) || 0,
            y: 0, w: a.width_pct ? (a.width_pct / 100) * this.CANVAS_W : 200,
            h: a.height_px || 150,
            border_width: a.border_width ?? 0, border_radius: a.border_radius ?? 10,
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

    const payload = {
      date, name: name || `Edition ${date}`, language: lang,
      pages: this.pages.map(p => ({
        page_number: p.page_number, category: p.category || 'मुख पृष्ठ',
        blocks: (p.blocks || []).map(b => ({
          id: b.id, headline: b.headline, sub_headline: b.sub_headline,
          body_text: b.body_text, body_html: b.body_html || '',
          category_label: b.category_label, image_url: b.image_url,
          gallery: b.gallery || [],
          x: b.x || 0, y: b.y || 0, w: b.w || 200, h: b.h || 150,
          border_width: b.border_width ?? 0, border_radius: b.border_radius ?? 10,
          border_color: b.border_color || '#e41e26', border_style: b.border_style || 'solid',
        })),
        articles: (p.blocks || []).map(b => ({
          id: b.id, headline: b.headline, sub_headline: b.sub_headline,
          body_text: b.body_text, body_html: b.body_html || '',
          category_label: b.category_label, article_image_url: b.image_url,
          image_url: b.image_url, gallery: b.gallery || [],
          x: b.x, y: b.y, w: b.w, h: b.h,
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
    this.pages.push({ page_number: this.pages.length + 1, category: 'मुख पृष्ठ', blocks: [] });
    this.renderPageTabs(); this.openPage(this.pages.length - 1);
  },
  deletePage(idx) {
    if (this.pages.length <= 1) return;
    if (!confirm(`Delete page ${idx + 1}?`)) return;
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
    const page = this.pages[this.currentPageIdx];
    if (!page) return;
    if (!page.blocks) page.blocks = [];
    const count = page.blocks.length;
    page.blocks.push({
      id: Date.now(),
      headline: '', sub_headline: '', body_text: '', body_html: '',
      category_label: '', image_url: '', gallery: [],
      x: 10 + (count % 3) * 270, y: 10 + Math.floor(count / 3) * 170,
      w: 250, h: 150,
      border_width: 0, border_radius: 10, border_color: '#e41e26', border_style: 'solid',
    });
    this.activeBlockIdx = page.blocks.length - 1;
    this.renderCanvas();
    this.showBlockEditor(this.activeBlockIdx);
  },

  removeBlock(idx) {
    if (!confirm('Delete this block?')) return;
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
    document.getElementById('blkBorderRadius').value = block.border_radius ?? 10;
    document.getElementById('blkBorderColor').value = block.border_color || '#e41e26';
    document.getElementById('blkBorderStyle').value = block.border_style || 'solid';
    document.getElementById('bwVal').textContent = (block.border_width ?? 0) + 'px';
    document.getElementById('brVal').textContent = (block.border_radius ?? 10) + 'px';
    this.updateBorderPreview();
    this.renderGallery();
  },

  saveBlock() {
    if (this.activeBlockIdx === null) return;
    const block = this.pages[this.currentPageIdx]?.blocks?.[this.activeBlockIdx];
    if (!block) return;

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
    block.border_radius = parseInt(document.getElementById('blkBorderRadius').value) || 10;
    block.border_color = document.getElementById('blkBorderColor').value || '#e41e26';
    block.border_style = document.getElementById('blkBorderStyle').value || 'solid';

    this.renderCanvas();
    this.showToast('✅ Block saved');
  },

  handleBlockImage(file) {
    if (!file?.type.startsWith('image/') || this.activeBlockIdx === null) return;
    const reader = new FileReader();
    reader.onload = e => {
      const block = this.pages[this.currentPageIdx]?.blocks?.[this.activeBlockIdx];
      if (block) {
        block.image_url = e.target.result;
        this.renderCanvas();
        document.getElementById('blockImageLabel').innerHTML = `<img src="${block.image_url}" alt="">`;
      }
    };
    reader.readAsDataURL(file);
  },

  // Gallery
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
  addGalleryImage(file) {
    if (!file?.type.startsWith('image/') || this.activeBlockIdx === null) return;
    const reader = new FileReader();
    reader.onload = e => {
      const block = this.pages[this.currentPageIdx]?.blocks?.[this.activeBlockIdx];
      if (block) { if (!block.gallery) block.gallery = []; block.gallery.push(e.target.result); this.renderGallery(); }
    };
    reader.readAsDataURL(file);
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
