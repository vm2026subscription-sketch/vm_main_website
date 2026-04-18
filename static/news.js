/* ══════════════════════════════════════════════════
   VIDYARTHI MITRA — NEWS PAGE LOGIC
   news.js
══════════════════════════════════════════════════ */

/* ── DATA ──────────────────────────────────────── */
const articles = [
  {
   id: 0, 
    cat: 'admission', 
    emoji: '🏛️',
    bgCls: 'bg-admission', 
    badgeCls: 'admission', 
    label: 'Admissions 2026', 
    hot: true,
    title: 'DTE Maharashtra Admissions 2026–27: CAP Phase 1 Portal Now Live',
    excerpt: 'DTE has launched the 2026 Engineering admission portal. Document verification is now mandatory via the new e-Scrutiny system.',
    date: '10 mins ago', 
    read: '6 min read', 
    views: '31.2k',
    body: 'The Directorate of Technical Education (DTE) Maharashtra has released the updated 2026 guidelines for the Engineering and Technology Centralized Admission Process (CAP). Candidates who qualified via MHT-CET or JEE Main 2026 must adhere to the new "Double-Verification" protocol, which includes both an e-Scrutiny and a physical verification stage for high-demand branches like AI and Data Science. The 2026 option form allows for a maximum of 300 choices. Experts strongly recommend that students prioritize autonomous institutes first, given the 2025 shift in placement trends. Crucially, the "Auto-Freeze" feature remains active; if a student is allotted their first preference, they must accept the seat and will not be eligible for subsequent rounds. The window for Round 1 option entry is scheduled to close on April 15, 2026.'
  },
  {
    id: 2, cat: 'exams', emoji: '📝',
    bgCls: 'bg-exam', badgeCls: 'exams', label: 'Exams', hot: false,
    title:   'NEET UG 2026 Registration — Portal Opening in January',
    excerpt: 'NTA has finalized the NEET 2026 schedule. Registration for the nationwide medical entrance starts early next year.',
    date: '6 hours ago', read: '4 min read', views: '18.2k',
    body: 'The National Testing Agency (NTA) is preparing to open the NEET UG 2026 Application window in the second week of January 2026. Aspirants seeking admission to MBBS, BDS, and Ayush courses must prepare their documents, including Aadhar-linked mobile numbers and scanned certificates. Eligibility remains 10+2 with PCB (50% for Gen). The exam is tentatively scheduled for the first Sunday of May 2026.'
  },
  {
    id: 3, cat: 'exams', emoji: '🎯',
    bgCls: 'bg-exam', badgeCls: 'exams', label: 'Exams', hot: true,
    title:   'JEE Main 2026 Session 1 — Admit Cards Released Today',
    excerpt: 'NTA has activated the download link for JEE Main 2026 January Session Hall Tickets. Check your exam center details.',
    date: '8 hours ago', read: '3 min read', views: '14.5k',
    body: 'The JEE Main 2026 Session 1 Admit Cards are now live on jeemain.nta.nic.in. Candidates must log in using their 2026 application credentials. This year, NTA has introduced enhanced biometric security at centers. Ensure your hall ticket has a clear photograph and signature. The Session 1 exam window begins in late January across 500+ cities.'
  },
  {
    id: 4, cat: 'admission', emoji: '🎓',
    bgCls: 'bg-admission', badgeCls: 'admission', label: 'Admissions', hot: false,
    title:   'MHT-CET 2026 Mock Allotment — New AI Branch Trends',
    excerpt: 'The State CET Cell has released the 2026 mock list. AI and Data Science branches see a 15% surge in preference.',
    date: '10 hours ago', read: '4 min read', views: '11.3k',
    body: 'The 2026 Mock Seat Allotment for Maharashtra Engineering admissions shows a massive shift toward specialized tech branches. The State CET Cell released this provisional list to help students gauge their chances at top colleges like COEP and VJTI. Candidates have 48 hours to rearrange their option forms based on these mock results before the final Round 1 locking.'
  },
  {
    id: 5, cat: 'govt', emoji: '👮',
    bgCls: 'bg-exam', badgeCls: 'govt', label: 'Govt Jobs', hot: false,
    title:   'SSC GD Constable 2026 — Mega Recruitment Drive Announced',
    excerpt: 'Staff Selection Commission announces 45,000+ vacancies for GD Constable. 10th pass candidates can apply now.',
    date: '12 hours ago', read: '3 min read', views: '9.4k',
    body: 'The 2026 SSC GD Constable notification has been released, targeting recruitment for CAPFs including BSF, CISF, and CRPF. With over 45,000 posts, this is one of the largest drives for 2026. The Computer-Based Exam is scheduled for March 2026. Applicants must be between 18-23 years of age as of January 1, 2026.'
  },
  {
    id: 6, cat: 'govt', emoji: '🚔',
    bgCls: 'bg-govt', badgeCls: 'govt', label: 'Govt Jobs', hot: false,
    title:   'Maharashtra Police Bharti 2026 — New Physical Standards Applied',
    excerpt: 'The 2026 recruitment cycle introduces updated physical test parameters. Check the revised schedule here.',
    date: '1 day ago', read: '2 min read', views: '8.9k',
    body: 'The Home Department of Maharashtra has commenced the 2026 Police Bharti physical tests. A new computerized timing system for the 1600m run has been implemented to ensure transparency. Candidates are required to bring digital copies of their documents for instant e-verification at the ground.'
  },
  {
    id: 7, cat: 'scholar', emoji: '💰',
    bgCls: 'bg-scholar', badgeCls: 'scholar', label: 'Scholarship', hot: false,
    title:   'MahaDBT 2026-27 Scholarship — Fresh Applications Open',
    excerpt: 'The Maharashtra State Scholarship portal is now accepting fresh applications for the 2026-27 academic year.',
    date: '1 day ago', read: '3 min read', views: '7.2k',
    body: 'Students enrolled in professional and non-professional courses for the 2026 session can now apply for MahaDBT scholarships. The portal has been updated to support automatic income certificate fetching via DigiLocker. Ensure your Aadhaar is linked to your bank account for Direct Benefit Transfer (DBT).'
  },
  {
    id: 8, cat: 'exams', emoji: '📚',
    bgCls: 'bg-exam', badgeCls: 'exams', label: 'Exams', hot: false,
    title:   'CBSE Board Exams 2026 — New Exam Pattern Implemented',
    excerpt: 'CBSE introduces more competency-based questions for the 2026 Class 10 & 12 board examinations.',
    date: '2 days ago', read: '3 min read', views: '6.7k',
    body: 'Following the latest National Education Policy (NEP) guidelines, the CBSE 2026 Board Exams will feature 50% competency-based questions. Practical exams for the 2025-26 session will start on January 1, 2026. Students can download the updated 2026 sample papers from cbse.gov.in.'
  },
  {
    id: 9, cat: 'exams', emoji: '⚔️',
    bgCls: 'bg-exam', badgeCls: 'exams', label: 'Exams', hot: false,
    title:   'UPSC NDA (I) 2026 — Notification and Eligibility Criteria Out',
    excerpt: 'UPSC releases the 2026 calendar for Defence services. Both male and female candidates can register from December.',
    date: '2 days ago', read: '4 min read', views: '6.1k',
    body: 'The Union Public Service Commission has officially notified the NDA & NA (I) 2026 exam. The written test will take place in April 2026. Class 12 students appearing in 2026 are eligible to apply. The syllabus for the Mathematics and GAT papers remains consistent with previous years.'
  },
  {
    id: 10, cat: 'exams', emoji: '🔬',
    bgCls: 'bg-exam', badgeCls: 'exams', label: 'Exams', hot: false,
    title:   'GATE 2026 — Organizing Institute and Exam Dates Announced',
    excerpt: 'The 2026 Graduate Aptitude Test in Engineering (GATE) details are out. Check the new paper combinations.',
    date: '2 days ago', read: '2 min read', views: '5.5k',
    body: 'The organizing committee for GATE 2026 has released the information brochure. The exam will be held over two weekends in February 2026. Two new humanities-focused papers have been added to the existing 30 subjects. GATE 2026 scores will be vital for 2027 PSU recruitments.'
  },
  {
    id: 11, cat: 'exams', emoji: '💼',
    bgCls: 'bg-exam', badgeCls: 'exams', label: 'Exams', hot: false,
    title:   'CAT 2026 — Registration Trends Show Record High Applicants',
    excerpt: 'Management entrance CAT 2026 sees a 10% rise in registrations. Experts share last-minute prep strategy.',
    date: '3 days ago', read: '6 min read', views: '5.1k',
    body: 'CAT 2026 registrations have crossed previous records, indicating high competition for the 2027-29 MBA batch at IIMs. The exam is scheduled for November 2026. Mock tests suggest a slightly tougher Logical Reasoning section this year compared to 2025.'
  },
  {
    id: 12, cat: 'admission', emoji: '⚖️',
    bgCls: 'bg-admission', badgeCls: 'admission', label: 'Admissions', hot: false,
    title:   'CLAT 2026 Result — Merit List and Counselling Schedule',
    excerpt: 'Consortium of NLUs has published CLAT 2026 scores. Centralized counselling for Law admissions begins shortly.',
    date: '3 days ago', read: '3 min read', views: '4.8k',
    body: 'The CLAT 2026 results are now available for UG and PG Law programs. Top NLUs are expected to have a higher cut-off this year due to the moderate difficulty level of the English section. Registration for the 2026-27 Law Counselling will start next Monday.'
  },
  {
    id: 13, cat: 'govt', emoji: '🚂',
    bgCls: 'bg-govt', badgeCls: 'govt', label: 'Govt Jobs', hot: false,
    title:   'Railway RRB 2026 — NTPC & Group D Notification Expected',
    excerpt: 'Indian Railways to announce 30,000+ vacancies for various RRB posts in the first quarter of 2026.',
    date: '3 days ago', read: '3 min read', views: '4.2k',
    body: 'Major RRBs are finalizing the 2026 recruitment calendar. Sources suggest a significant increase in safety-category posts (Loco Pilot and Technicians). Applicants are advised to keep their caste and EWS certificates updated as per the 2026 format.'
  },
  {
    id: 14, cat: 'govt', emoji: '🏦',
    bgCls: 'bg-govt', badgeCls: 'govt', label: 'Govt Jobs', hot: false,
    title:   'IBPS 2026 Exam Calendar — PO, Clerk & RRB Dates',
    excerpt: 'IBPS has released the tentative schedule for the 2026-27 banking recruitment cycle.',
    date: '4 days ago', read: '3 min read', views: '3.9k',
    body: 'The Institute of Banking Personnel Selection has outlined the 2026 exam window. IBPS Clerk 2026 Prelims are set for August, followed by PO in October. This cycle will recruit for 11 participating public sector banks.'
  },
  {
    id: 15, cat: 'exams', emoji: '📊',
    bgCls: 'bg-exam', badgeCls: 'exams', label: 'Exams', hot: false,
    title:   'UGC NET 2026 — Application for Junior Research Fellowship',
    excerpt: 'The 2026 session of UGC NET introduces three new subjects. Apply before the February deadline.',
    date: '4 days ago', read: '2 min read', views: '3.5k',
    body: 'NTA has updated the UGC NET 2026 portal. In accordance with the 2026 PhD regulations, a NET score will now be mandatory for PhD admissions in all Central Universities. The exam remains a computer-based test (CBT).'
  },
  {
    id: 16, cat: 'scholar', emoji: '🏆',
    bgCls: 'bg-scholar', badgeCls: 'scholar', label: 'Scholarship', hot: false,
    title:   'AICTE 2026 Support Schemes — Funding for Innovation Projects',
    excerpt: 'AICTE launches a new scholarship for students working on AI and Sustainability projects in 2026.',
    date: '5 days ago', read: '3 min read', views: '3.2k',
    body: 'The AICTE 2026-27 initiative aims to fund 5,000 student-led research projects. Eligible technical students can apply for a grant of up to ₹50,000. Applications must be submitted through the Institutional head by March 2026.'
  },
  {
    id: 17, cat: 'admission', emoji: '🏫',
    bgCls: 'bg-admission', badgeCls: 'admission', label: 'Admissions', hot: false,
    title:   'FYJC 2026 Maharashtra — Part 1 Registration for 11th Admission',
    excerpt: 'The 2026 Centralized Admission Process for 11th Standard has officially kicked off in Maharashtra.',
    date: '5 days ago', read: '4 min read', views: '2.9k',
    body: 'Students who appeared for the March 2026 SSC exams can now start the FYJC 2026 registration process. Part 1 (Basic Details) must be completed before the results are declared. Verification will be handled by secondary schools online.'
  },
  {
    id: 18, cat: 'exams', emoji: '📉',
    bgCls: 'bg-exam', badgeCls: 'exams', label: 'Exams', hot: false,
    title:   '2026 Engineering Cut-off Forecast — Impact of New Seat Matrix',
    excerpt: 'Vidyarthi Mitra experts analyze how the 2026 increase in seat intake will affect admission cut-offs.',
    date: '6 days ago', read: '7 min read', views: '2.5k',
    body: 'With over 10,000 new seats added in the 2026-27 academic year, cut-offs for traditional branches like IT and Electronics are expected to stabilize. However, Core AI branches remain highly competitive. Refer to our 2026 Rank Predictor for personalized insights.'
  }
];

/* ── STATE ─────────────────────────────────────── */
let activeCat    = 'all';
let searchQuery  = '';
let bookmarks    = new Set();
let currentModal = null;
const PAGE_SIZE  = 9;
let pageCount    = PAGE_SIZE;

/* ══════════════════════════════════════════════════
   FILTER & RENDER
══════════════════════════════════════════════════ */
function getFiltered() {
  return articles.filter(a => {
    const q        = searchQuery.toLowerCase();
    const matchCat = activeCat === 'all' || a.cat === activeCat;
    const matchQ   = !q
      || a.title.toLowerCase().includes(q)
      || a.excerpt.toLowerCase().includes(q)
      || a.label.toLowerCase().includes(q);
    return matchCat && matchQ;
  });
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
    card.innerHTML = `
      <div class="card-stripe ${a.cat}"></div>
      <div class="card-thumb ${a.bgCls}">
        ${a.emoji}
        <div class="card-thumb-badge ${a.badgeCls}">${a.label}</div>
        ${a.hot ? '<div class="card-hot">Hot</div>' : ''}
      </div>
      <div class="card-body">
        <div class="card-headline">${a.title}</div>
        <div class="card-excerpt">${a.excerpt}</div>
      </div>
      <div class="card-footer">
        <div class="card-meta-info">
          <div class="card-time"><i class="fa fa-clock"></i>${a.date}</div>
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
        <button class="btn-read-more" onclick="openModal(${a.id})">
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
    showToast('✅ Article saved!');
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
  const t = title || (currentModal !== null ? articles[currentModal].title : 'Vidyarthi Mitra News');
  if (navigator.share) {
    navigator.share({ title: t, url: window.location.href });
  } else {
    navigator.clipboard.writeText(window.location.href)
      .then(() => showToast('🔗 Link copied to clipboard!'));
  }
}

/* ══════════════════════════════════════════════════
   MODAL
══════════════════════════════════════════════════ */
function openModal(id) {
  const a = articles.find(x => x.id === id);
  if (!a) return;
  currentModal = id;

  document.getElementById('mCat').textContent   = a.label;
  document.getElementById('mTitle').textContent  = a.title;
  document.getElementById('mDate').textContent   = a.date;
  document.getElementById('mRead').textContent   = a.read;
  document.getElementById('mViews').textContent  = a.views + ' views';
  document.getElementById('mBody').innerHTML     = a.body;

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
    showToast('✅ Article saved!');
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
  document.getElementById('toastMsg').textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

/* ══════════════════════════════════════════════════
   EVENT LISTENERS
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
  document.getElementById('searchInput').addEventListener('input', function () {
    searchQuery = this.value.trim();
    pageCount   = PAGE_SIZE;
    renderGrid();
  });

  /* Load more button */
  document.getElementById('loadMoreBtn').addEventListener('click', function () {
    pageCount += PAGE_SIZE;
    renderGrid();
  });

  /* Modal close button */
  document.getElementById('modalClose').addEventListener('click', closeModal);

  /* Modal background click */
  document.getElementById('modalBg').addEventListener('click', function (e) {
    if (e.target === this) closeModal();
  });

  /* Escape key */
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
  });

  /* Set current date in masthead */
  document.getElementById('currentDate').textContent = new Date().toLocaleDateString('en-IN', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
  });

  /* Initial render */
  renderGrid();
});
function validateSubscription() {
  const emailInput = document.getElementById('nlEmail');
  const emailValue = emailInput.value.trim();

  // Basic validation: Check if empty
  if (emailValue === "") {
    showToast("Please enter your email address.");
    emailInput.focus();
    return;
  }

  // Optional: Check for valid email format
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailPattern.test(emailValue)) {
    showToast("Please enter a valid email.");
    return;
  }

  // If valid, show the success message
  showToast('Subscribed! Check your inbox.');
  emailInput.value = ""; // Clear the field
}