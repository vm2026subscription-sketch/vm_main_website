/* ══════════════════════════════════════════════════
   VIDYARTHI MITRA — NEWS PAGE LOGIC (Dynamic RSS)
   news.js
══════════════════════════════════════════════════ */

/* ── DATA ──────────────────────────────────────── */
let allArticles  = [];

/* ── STATE ─────────────────────────────────────── */
let activeCat    = 'all';
let searchQuery  = '';
let bookmarks    = new Set();
let currentModal = null;
const PAGE_SIZE  = 9;
let pageCount    = PAGE_SIZE;

/* Category mapping: API -> UI */
const categoryMap = {
  "entrance": { ui: "entrance", label: "Entrance Exams", img: "https://images.unsplash.com/photo-1546410531-bd4cb0153f3e?auto=format&fit=crop&w=400&q=80", bgCls: "bg-exam" },
  "results": { ui: "results", label: "Results", img: "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?auto=format&fit=crop&w=400&q=80", bgCls: "bg-exam" },
  "admissions": { ui: "admissions", label: "Admissions", img: "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?auto=format&fit=crop&w=400&q=80", bgCls: "bg-admission" },
  "govtjobs": { ui: "govtjobs", label: "Govt Jobs", img: "https://images.unsplash.com/photo-1589829085413-56de8ae18c73?auto=format&fit=crop&w=400&q=80", bgCls: "bg-govt" },
  "scholarship": { ui: "scholarship", label: "Scholarships", img: "https://images.unsplash.com/photo-1532619675605-1ede6c2ed2b0?auto=format&fit=crop&w=400&q=80", bgCls: "bg-scholar" },
  "latest": { ui: "latest", label: "Latest News", img: "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=400&q=80", bgCls: "bg-exam" }
};

/* ══════════════════════════════════════════════════
   FETCH NEWS FROM API
══════════════════════════════════════════════════ */
async function fetchNews() {
  try {
    console.log('Fetching news from /api/news...');
    const response = await fetch('/api/news');
    console.log('Response status:', response.status);
    if (!response.ok) throw new Error(`API error: ${response.status}`);
    
    const data = await response.json();
    console.log('API response:', data);
    
    if (!data.success || !data.articles) {
      console.error('Invalid API response:', data);
      showToast('Failed to load news');
      return;
    }
    
    console.log('Articles count:', data.articles.length);
    
    // Transform API articles to UI format
    allArticles = data.articles.map((article, idx) => {
      const catInfo = categoryMap[article.category] || categoryMap.admissions;
      console.log(`Article ${idx}: category=${article.category}, mapped=${catInfo.ui}`);
      
      // Format date
      const dateObj = new Date(article.date);
      const now = new Date();
      const diffMs = now - dateObj;
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMs / 3600000);
      const diffDays = Math.floor(diffMs / 86400000);
      
      let dateStr;
      if (diffMins < 1) dateStr = "Just now";
      else if (diffMins < 60) dateStr = `${diffMins} min${diffMins !== 1 ? 's' : ''} ago`;
      else if (diffHours < 24) dateStr = `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
      else if (diffDays < 7) dateStr = `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
      const fallbackImgs = [
        'https://media.istockphoto.com/id/2177186284/photo/may-i-answer-your-question-professor.jpg?s=612x612&w=0&k=20&c=q7jhVUW8r3K6GJESS_5L8QS_4wOuRSb1ChfHsK_7aJI=',
        'https://img.jagranjosh.com/imported/images/E/Articles/Tips-to-Focus-Better-on-Your-Studies-Body-Image.webp',
        'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcR064b87YTte8BtmZRUcceOKfi-V7LmTVwvtA&s'
      ];
      let imgUrl = fallbackImgs[idx % fallbackImgs.length];
      const titleLower = article.title ? article.title.toLowerCase() : '';
      const descLower = article.desc ? article.desc.toLowerCase() : '';
      if (titleLower.includes('neet') || descLower.includes('neet')) {
        imgUrl = 'https://csacademy.in/wp-content/uploads/2021/05/blog-image10.jpg';
      } else if (titleLower.includes('jee') || descLower.includes('jee')) {
        imgUrl = 'https://www.shutterstock.com/image-photo/jee-joint-entrance-examination-conducted-260nw-2279191817.jpg';
      } else if (titleLower.includes('nda') || descLower.includes('nda')) {
        imgUrl = 'https://i.pinimg.com/736x/74/fa/7f/74fa7f7cb31d44075a8c7cc76f6da589.jpg';
      } else if (titleLower.includes('result') || descLower.includes('result')) {
        imgUrl = 'https://img.freepik.com/free-photo/results-evaluate-progress-outcome-productivity-concept_53876-121131.jpg';
      }

      return {
        id: idx,
        cat: catInfo.ui,
        img: imgUrl,
        bgCls: catInfo.bgCls,
        badgeCls: catInfo.ui,
        label: catInfo.label,
        hot: diffHours < 4,  // Mark as hot if within 4 hours
        title: article.title,
        excerpt: article.desc,
        date: dateStr,
        read: "3 min read",
        views: Math.floor(Math.random() * 50) + "k",  // Placeholder views
        body: article.desc || "No additional details available.",
        link: article.link,
        source: article.source
      };
    });
    
    console.log('Transformed articles:', allArticles.length);
    
    // Initial render
    renderGrid();
    console.log(`Loaded ${allArticles.length} articles`);
  } catch (error) {
    console.error('Error fetching news:', error);
    showToast('Unable to load news. Please refresh the page.');
  }
}

/* ══════════════════════════════════════════════════
   FILTER & RENDER
══════════════════════════════════════════════════ */
function getFiltered() {
  return allArticles.filter(a => {
    const q        = searchQuery.toLowerCase();
    const matchCat = activeCat === 'all' || a.cat === activeCat;
    const matchQ   = !q
      || a.title.toLowerCase().includes(q)
      || a.excerpt.toLowerCase().includes(q)
      || a.label.toLowerCase().includes(q)
      || a.source.toLowerCase().includes(q);
    return matchCat && matchQ;
  });
}

function openArticleDetail(id) {
  const article = allArticles.find(item => item.id === id);
  if (!article || !article.link) {
    openModal(id);
    return;
  }
  window.location.href = `/news/detail/${encodeURIComponent(article.link)}`;
}

function renderGrid() {
  const grid     = document.getElementById('newsGrid');
  const empty    = document.getElementById('emptyState');
  const lmWrap   = document.getElementById('loadMoreWrap');
  const count    = document.getElementById('visibleCount');
  const filtered = getFiltered();
  const toShow   = filtered.slice(0, pageCount);

  count.textContent = filtered.length;
  grid.innerHTML    = '';

  if (filtered.length === 0) {
    empty.classList.add('show');
    lmWrap.style.display = 'none';
    return;
  }
  empty.classList.remove('show');

  toShow.forEach((a, i) => {
    const card = document.createElement('div');
    card.className = 'news-card';
    card.style.animationDelay = (i * 0.05) + 's';
    card.onclick = () => openArticleDetail(a.id);
    card.innerHTML = `
      <div class="card-stripe ${a.cat}"></div>
      <div class="card-thumb ${a.bgCls}" style="padding: 0;">
        <img src="${a.img}" alt="News Thumbnail" style="width: 100%; height: 100%; object-fit: cover;">
        <div class="card-thumb-badge ${a.badgeCls}">${a.label}</div>
        ${a.hot ? '<div class="card-hot">Hot</div>' : ''}
      </div>
      <div class="card-body">
        <div class="card-source" style="font-size: 11px; color: #888; margin-bottom: 6px;">
          <i class="fa fa-globe"></i> ${a.source}
        </div>
        <div class="card-headline">${a.title}</div>
        <div class="card-excerpt">${a.excerpt}</div>
      </div>
      <div class="card-footer">
        <div class="card-meta-info">
          <div class="card-time"><i class="fa fa-clock"></i> ${a.date}</div>
          <div class="card-read">${a.read}</div>
        </div>
        <div class="card-actions">
          <button class="btn-action ${bookmarks.has(a.id) ? 'bookmarked' : ''}"
                  onclick="toggleBookmark(event, ${a.id})" title="Save">
            <i class="fa${bookmarks.has(a.id) ? '' : '-regular'} fa-bookmark"></i>
          </button>
          <button class="btn-action"
                  onclick="shareCard(event, '${a.title.replace(/'/g, '&#39;')}')" title="Share">
            <i class="fa fa-share-alt"></i>
          </button>
        </div>
        <button class="btn-read-more" onclick="event.stopPropagation(); openArticleDetail(${a.id})">
          Read <i class="fa fa-arrow-right"></i>
        </button>
      </div>
    `;
    grid.appendChild(card);
  });

  lmWrap.style.display = filtered.length > pageCount ? 'block' : 'none';
}

/* ══════════════════════════════════════════════════
   BOOKMARK
══════════════════════════════════════════════════ */
function toggleBookmark(e, id) {
  e.stopPropagation();
  if (bookmarks.has(id)) {
    bookmarks.delete(id);
    showToast('Removed from saved articles');
  } else {
    bookmarks.add(id);
    showToast('<i class="fa fa-check-circle" style="color:#22c55e"></i> Article saved!');
  }
  renderGrid();
}

/* ══════════════════════════════════════════════════
   SHARE
══════════════════════════════════════════════════ */
function shareCard(e, title) {
  e.stopPropagation();
  shareArticle(title);
}

function shareArticle(title) {
  const t = title || (currentModal !== null ? allArticles[currentModal].title : 'Vidyarthi Mitra News');
  if (navigator.share) {
    navigator.share({ title: t, url: window.location.href });
  } else {
    navigator.clipboard.writeText(window.location.href)
      .then(() => showToast('<i class="fa fa-link"></i> Link copied to clipboard!'));
  }
}

/* ══════════════════════════════════════════════════
   MODAL
══════════════════════════════════════════════════ */
function openModal(id) {
  const a = allArticles.find(x => x.id === id);
  if (!a) return;
  currentModal = id;

  document.getElementById('mCat').textContent   = a.label;
  document.getElementById('mTitle').textContent  = a.title;
  document.getElementById('mDate').textContent   = a.date;
  document.getElementById('mRead').textContent   = a.read;
  document.getElementById('mViews').textContent  = a.views + ' views';
  
  // Display description + source + link
  let bodyHtml = `<p>${a.excerpt}</p>`;
  if (a.source) {
    bodyHtml += `<p style="margin-top: 16px; font-size: 12px; color: #666;">
      <strong>Source:</strong> ${a.source}
    </p>`;
  }
  if (a.link) {
    bodyHtml += `<p style="margin-top: 8px;">
      <a href="${a.link}" target="_blank" style="color: var(--primary); text-decoration: none;">
        Read full article on source site →
      </a>
    </p>`;
  }
  document.getElementById('mBody').innerHTML = bodyHtml;

  const fullBtn = document.getElementById('mFullArticleBtn');
  if (fullBtn) {
    if (a.link) {
      fullBtn.style.display = 'inline-flex';
      fullBtn.textContent = 'Open detailed story';
      fullBtn.onclick = () => {
        window.location.href = `/news/detail/${encodeURIComponent(a.link)}`;
      };
    } else {
      fullBtn.style.display = 'none';
    }
  }

  updateModalBookmark();
  document.getElementById('modalBg').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  document.getElementById('modalBg').classList.remove('open');
  document.body.style.overflow = '';
  currentModal = null;
}

function toggleModalBookmark() {
  if (currentModal === null) return;
  if (bookmarks.has(currentModal)) {
    bookmarks.delete(currentModal);
    showToast('Removed from saved articles');
  } else {
    bookmarks.add(currentModal);
    showToast('<i class="fa fa-check-circle" style="color:#22c55e"></i> Article saved!');
  }
  updateModalBookmark();
  renderGrid();
}

function updateModalBookmark() {
  const btn = document.getElementById('mBookmarkBtn');
  if (!btn || currentModal === null) return;
  const saved   = bookmarks.has(currentModal);
  btn.innerHTML = saved ? '<i class="fa fa-bookmark"></i> Saved' : '<i class="fa fa-bookmark"></i> Save';
  btn.style.color = saved ? 'var(--orange)' : '';
}

/* ══════════════════════════════════════════════════
   TOAST
══════════════════════════════════════════════════ */
function showToast(msg) {
  const t = document.getElementById('toast');
  document.getElementById('toastMsg').innerHTML = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

/* ══════════════════════════════════════════════════
   EVENT LISTENERS & INITIALIZATION
══════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', function () {

  /* Category tab buttons */
  document.querySelectorAll('.cat-btn').forEach(btn => {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      activeCat = this.dataset.cat;
      pageCount = PAGE_SIZE;
      renderGrid();
    });
  });

  /* Search input */
  const searchInput = document.getElementById('searchInput');
  if (searchInput) {
    searchInput.addEventListener('input', function () {
      searchQuery = this.value.trim();
      pageCount   = PAGE_SIZE;
      renderGrid();
    });
  }

  /* Tag pills */
  document.querySelectorAll('.tag-pill').forEach(pill => {
    pill.addEventListener('click', function(e) {
      e.preventDefault();
      // Remove emoji/extra text if any
      const tagText = this.textContent.replace(/[^\w\s-]/gi, '').trim();
      if (searchInput) {
        searchInput.value = tagText;
        searchQuery = tagText;
        pageCount = PAGE_SIZE;
        renderGrid();
        // Optional: Scroll to news grid
        document.getElementById('newsGrid')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  /* Most Read items */
  document.querySelectorAll('.story-list-item').forEach(item => {
    item.addEventListener('click', function() {
      const title = this.querySelector('h5').textContent.trim();
      if (searchInput) {
        searchInput.value = title;
        searchQuery = title;
        pageCount = PAGE_SIZE;
        renderGrid();
        document.getElementById('newsGrid')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  /* Load more button */
  const loadMoreBtn = document.getElementById('loadMoreBtn');
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', function () {
      pageCount += PAGE_SIZE;
      renderGrid();
    });
  }

  /* Modal close button */
  const modalClose = document.getElementById('modalClose');
  if (modalClose) {
    modalClose.addEventListener('click', closeModal);
  }

  /* Modal background click */
  const modalBg = document.getElementById('modalBg');
  if (modalBg) {
    modalBg.addEventListener('click', function (e) {
      if (e.target === this) closeModal();
    });
  }

  /* Escape key */
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
  });






  /* Fetch and display news */
  fetchNews();
});

function validateSubscription() {
  const emailInput = document.getElementById('nlEmail');
  const emailValue = emailInput.value.trim();

  if (emailValue === "") {
    showToast("Please enter your email address.");
    emailInput.focus();
    return;
  }

  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailPattern.test(emailValue)) {
    showToast("Please enter a valid email.");
    return;
  }

  showToast('Subscribed! Check your inbox.');
  emailInput.value = "";
}


