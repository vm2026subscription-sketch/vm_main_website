/* ═══════════════════════════════════════════════════════════
   entrance-exams.js — Vidyarthi Mitra | All Interactive Logic
   ═══════════════════════════════════════════════════════════ */

// ── ALL EXAM DATA FOR SEARCH ──────────────────────────────
const ALL_EXAMS = [
  // Engineering
  { name: 'JEE Main',      body: 'NITs, IIITs & GFTIs',          level: 'National',       cat: 'Engineering' },
  { name: 'JEE Advanced',  body: 'Gateway to IITs',               level: 'National',       cat: 'Engineering' },
  { name: 'BITSAT',        body: 'BITS Pilani, Goa, Hyderabad',   level: 'National',       cat: 'Engineering' },
  { name: 'VITEEE',        body: 'VIT University Admissions',     level: 'National',       cat: 'Engineering' },
  { name: 'SRMJEEE',       body: 'SRM Joint Engineering',         level: 'National',       cat: 'Engineering' },
  { name: 'MHT-CET',       body: 'Maharashtra Engineering',       level: 'State',          cat: 'Engineering' },
  { name: 'KCET',          body: 'Karnataka Engineering',         level: 'State',          cat: 'Engineering' },
  { name: 'WBJEE',         body: 'West Bengal Engineering',       level: 'State',          cat: 'Engineering' },
  { name: 'COMEDK',        body: 'Karnataka Private Colleges',    level: 'State',          cat: 'Engineering' },
  { name: 'GUJCET',        body: 'Gujarat Engineering',           level: 'State',          cat: 'Engineering' },
  { name: 'AP EAMCET',     body: 'AP Engineering Admissions',     level: 'State',          cat: 'Engineering' },
  { name: 'TS EAMCET',     body: 'Telangana Engineering',         level: 'State',          cat: 'Engineering' },
  { name: 'KEAM',          body: 'Kerala Engineering',            level: 'State',          cat: 'Engineering' },
  { name: 'UPSEE',         body: 'Uttar Pradesh Engineering',     level: 'State',          cat: 'Engineering' },
  { name: 'TANCET',        body: 'Tamil Nadu Engineering PG',     level: 'State',          cat: 'Engineering' },
  { name: 'OJEE',          body: 'Odisha Engineering',            level: 'State',          cat: 'Engineering' },
  { name: 'HPCET',         body: 'Himachal Pradesh Engineering',  level: 'State',          cat: 'Engineering' },
  { name: 'RPET',          body: 'Rajasthan Engineering',         level: 'State',          cat: 'Engineering' },
  { name: 'MERI Mumbai',   body: 'Marine Engineering',            level: 'National',       cat: 'Engineering' },
  { name: 'TNEA',          body: 'Tamil Nadu UG Engineering',     level: 'State',          cat: 'Engineering' },

  // Medical
  { name: 'NEET-UG',       body: 'MBBS, BDS, BAMS, BHMS',        level: 'National',       cat: 'Medical' },
  { name: 'NEET-PG',       body: 'MD, MS, PG Diploma',           level: 'Postgraduate',   cat: 'Medical' },
  { name: 'NEET-SS',       body: 'DM/MCh Super Specialty',       level: 'Super Specialty',cat: 'Medical' },
  { name: 'AIIMS PG',      body: 'AIIMS Postgraduate',           level: 'National',       cat: 'Medical' },
  { name: 'JIPMER',        body: 'JIPMER Puducherry',            level: 'National',       cat: 'Medical' },
  { name: 'FMGE',          body: 'Foreign Medical Graduate',     level: 'National',       cat: 'Medical' },
  { name: 'INI-CET',       body: 'AIIMS, JIPMER, PGIMER',        level: 'National',       cat: 'Medical' },
  { name: 'PGIMER',        body: 'PGI Chandigarh',               level: 'National',       cat: 'Medical' },
  { name: 'BHU PMT',       body: 'BHU Medical Admissions',       level: 'National',       cat: 'Medical' },
  { name: 'NIMHANS',       body: 'Mental Health Science',        level: 'National',       cat: 'Medical' },

  // Law
  { name: 'CLAT',          body: '25 NLU Admissions',            level: 'National',       cat: 'Law' },
  { name: 'AILET',         body: 'NLU Delhi',                    level: 'National',       cat: 'Law' },
  { name: 'LSAT India',    body: 'Private Law Colleges',         level: 'International',  cat: 'Law' },
  { name: 'MH-CET Law',    body: 'Maharashtra Law',              level: 'State',          cat: 'Law' },
  { name: 'SLAT',          body: 'Symbiosis Law School',         level: 'National',       cat: 'Law' },
  { name: 'ILICAT',        body: 'Indian Law Institute',         level: 'National',       cat: 'Law' },
  { name: 'LFAT',          body: 'Lloyd Law College',            level: 'National',       cat: 'Law' },

  // Defence
  { name: 'NDA',           body: 'Army, Navy, Air Force',        level: 'Defence',        cat: 'Defence' },
  { name: 'CDS',           body: 'IMA, INA, AFA, OTA',          level: 'Defence',        cat: 'Defence' },
  { name: 'AFCAT',         body: 'Air Force Entry',              level: 'Defence',        cat: 'Defence' },
  { name: 'INET',          body: 'Indian Navy Officer',          level: 'Defence',        cat: 'Defence' },
  { name: 'MNS',           body: 'Military Nursing Service',     level: 'Defence',        cat: 'Defence' },
  { name: 'TES',           body: 'Army Technical Entry',         level: 'Defence',        cat: 'Defence' },
  { name: 'SSB',           body: 'Officer Selection Interview',  level: 'Defence',        cat: 'Defence' },
  { name: 'Coast Guard',   body: 'Navik & Asst Commandant',      level: 'Defence',        cat: 'Defence' },

  // Management
  { name: 'CAT',           body: '20 IIMs + Top B-Schools',      level: 'National',       cat: 'Management' },
  { name: 'XAT',           body: 'XLRI & 150+ B-Schools',        level: 'National',       cat: 'Management' },
  { name: 'CMAT',          body: 'AICTE MBA Colleges',           level: 'National',       cat: 'Management' },
  { name: 'SNAP',          body: 'Symbiosis MBA',                level: 'National',       cat: 'Management' },
  { name: 'IIFT',          body: 'International Business MBA',   level: 'National',       cat: 'Management' },
  { name: 'MAT',           body: '600+ MBA Colleges',            level: 'National',       cat: 'Management' },
  { name: 'NMAT',          body: 'NMIMS & Partners',             level: 'National',       cat: 'Management' },
  { name: 'ATMA',          body: 'AIMS Member Institutes',       level: 'National',       cat: 'Management' },
  { name: 'MICAT',         body: 'MICA Ahmedabad',               level: 'National',       cat: 'Management' },
  { name: 'IRMASAT',       body: 'Rural Management IRMA',        level: 'National',       cat: 'Management' },
  { name: 'TISSNET',       body: 'TISS Mumbai',                  level: 'National',       cat: 'Management' },
  { name: 'GMAT',          body: 'Global B-Schools',             level: 'International',  cat: 'Management' },

  // Banking
  { name: 'IBPS PO',       body: 'PSU Bank Officers',            level: 'Banking',        cat: 'Banking' },
  { name: 'IBPS Clerk',    body: 'PSU Bank Clerks',              level: 'Banking',        cat: 'Banking' },
  { name: 'SBI PO',        body: 'SBI Officers',                 level: 'Banking',        cat: 'Banking' },
  { name: 'SBI Clerk',     body: 'SBI Associates',               level: 'Banking',        cat: 'Banking' },
  { name: 'RBI Grade B',   body: 'RBI Officers',                 level: 'Banking',        cat: 'Banking' },
  { name: 'NABARD',        body: 'Grade A & B Officers',         level: 'Banking',        cat: 'Banking' },
  { name: 'IBPS SO',       body: 'Specialist Officers',          level: 'Banking',        cat: 'Banking' },
  { name: 'LIC AAO',       body: 'LIC Asst Admin Officer',       level: 'Banking',        cat: 'Banking' },
  { name: 'SEBI Grade A',  body: 'Securities & Exchange Board',  level: 'Banking',        cat: 'Banking' },
  { name: 'IPPB Officer',  body: 'India Post Payments Bank',     level: 'Banking',        cat: 'Banking' },

  // Civil Services
  { name: 'UPSC CSE',      body: 'IAS, IPS, IFS',                level: 'UPSC',           cat: 'Civil Services' },
  { name: 'SSC CGL',       body: 'Central Govt Group B C',       level: 'National',       cat: 'Civil Services' },
  { name: 'SSC CHSL',      body: 'LDC, JSA, PA Posts',           level: 'National',       cat: 'Civil Services' },
  { name: 'MPSC',          body: 'Maharashtra State Services',   level: 'State',          cat: 'Civil Services' },
  { name: 'UPSC IES',      body: 'Engineering Services Govt',    level: 'UPSC',           cat: 'Civil Services' },
  { name: 'CAPF AC',       body: 'BSF, CRPF, CISF, ITBP',        level: 'UPSC',           cat: 'Civil Services' },
  { name: 'RPSC RAS',      body: 'Rajasthan Admin Services',     level: 'State',          cat: 'Civil Services' },
  { name: 'TNPSC',         body: 'Tamil Nadu Group I–IV',        level: 'State',          cat: 'Civil Services' },

  // Design
  { name: 'NATA',          body: 'Architecture Admissions',      level: 'National',       cat: 'Design & Architecture' },
  { name: 'JEE B.Arch',    body: 'Architecture via JEE Paper 2', level: 'National',       cat: 'Design & Architecture' },
  { name: 'UCEED',         body: 'IIT B.Des Programs',           level: 'National',       cat: 'Design & Architecture' },
  { name: 'CEED',          body: 'IIT M.Des Programs',           level: 'National',       cat: 'Design & Architecture' },
  { name: 'NID DAT',       body: 'NID Ahmedabad',                level: 'National',       cat: 'Design & Architecture' },
  { name: 'NIFT',          body: 'Fashion Technology',           level: 'National',       cat: 'Design & Architecture' },
  { name: 'Pearl Academy', body: 'Design & Fashion Programs',    level: 'National',       cat: 'Design & Architecture' },
  { name: 'SEED',          body: 'Symbiosis Design Programs',    level: 'National',       cat: 'Design & Architecture' },

  // Pharmacy
  { name: 'GPAT',          body: 'M.Pharm Admissions',           level: 'National',       cat: 'Pharmacy' },
  { name: 'NIPER JEE',     body: 'NIPER Institutes',             level: 'National',       cat: 'Pharmacy' },
  { name: 'MHT-CET Pharm', body: 'Maharashtra Pharmacy',         level: 'State',          cat: 'Pharmacy' },
  { name: 'TS EAMCET Pharm',body: 'Telangana Pharmacy',          level: 'State',          cat: 'Pharmacy' },
  { name: 'PUCET Pharma',  body: 'Punjab University Pharmacy',   level: 'State',          cat: 'Pharmacy' },

  // Hotel Management
  { name: 'NCHMCT JEE',    body: 'IHMs across India',            level: 'National',       cat: 'Hotel Management' },
  { name: 'IIHM eCHAT',    body: 'IIHM Colleges Nationwide',     level: 'National',       cat: 'Hotel Management' },
  { name: 'AIMA UGAT',     body: 'Hotel Mgmt + UG Programs',     level: 'National',       cat: 'Hotel Management' },
  { name: 'MAH HM CET',    body: 'Maharashtra Hotel Mgmt',       level: 'State',          cat: 'Hotel Management' },

  // Agriculture
  { name: 'ICAR AIEEA',    body: 'Agricultural Universities',    level: 'National',       cat: 'Agriculture' },
  { name: 'UPCATET',       body: 'UP Agricultural Universities', level: 'State',          cat: 'Agriculture' },
  { name: 'TNAU',          body: 'Tamil Nadu Agricultural Univ', level: 'State',          cat: 'Agriculture' },
  { name: 'RAWE',          body: 'Rural Agri Work Experience',   level: 'National',       cat: 'Agriculture' },
  { name: 'OUAT',          body: 'Odisha Univ of Agri & Tech',   level: 'State',          cat: 'Agriculture' },

  // Science & Research
  { name: 'JAM',           body: 'IIT M.Sc. Admissions',         level: 'National',       cat: 'Science & Research' },
  { name: 'GATE',          body: 'PG Engineering + PSU Jobs',    level: 'National',       cat: 'Science & Research' },
  { name: 'CSIR NET',      body: 'JRF / Lectureship in Science', level: 'National',       cat: 'Science & Research' },
  { name: 'UGC NET',       body: 'Lectureship + JRF 100 Subjects',level: 'National',      cat: 'Science & Research' },
  { name: 'JEST',          body: 'Physics / Neuroscience PhD',   level: 'National',       cat: 'Science & Research' },
  { name: 'TIFR GS',       body: 'TIFR PhD Programs',            level: 'National',       cat: 'Science & Research' },
  { name: 'KVPY',          body: 'Scholarship for Science',      level: 'National',       cat: 'Science & Research' },
];

// ── LIVE SEARCH ───────────────────────────────────────────
function liveSearch() {
  const q   = document.getElementById('examInput').value.trim().toLowerCase();
  const out = document.getElementById('searchResults');

  if (!q) { out.innerHTML = ''; return; }

  const matches = ALL_EXAMS.filter(e =>
    e.name.toLowerCase().includes(q) ||
    e.body.toLowerCase().includes(q) ||
    e.cat.toLowerCase().includes(q)
  );

  if (!matches.length) {
    out.innerHTML = `
      <div class="search-result-item">
        <span class="sri-name">No exams found for "${q}"</span>
      </div>`;
    return;
  }

  out.innerHTML = matches.slice(0, 8).map(e => `
    <div class="search-result-item">
      <div>
        <div class="sri-name">${e.name}</div>
        <div class="sri-cat">${e.cat} · ${e.body}</div>
      </div>
      <span class="sri-level">${e.level}</span>
    </div>
  `).join('');
}

// Debounced keyup listener on search input
document.getElementById('examInput').addEventListener('keyup', function (e) {
  clearTimeout(this._debounce);
  this._debounce = setTimeout(liveSearch, 250);
  if (e.key === 'Enter') liveSearch();
});

// ── FILTER TABS ───────────────────────────────────────────
document.querySelectorAll('.filter-tab').forEach(function (tab) {
  tab.addEventListener('click', function () {
    // Update active tab
    document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
    this.classList.add('active');

    const filter = this.dataset.filter;

    // Show / hide sections
    document.querySelectorAll('.exam-section').forEach(function (sec) {
      if (filter === 'all' || sec.dataset.category === filter) {
        sec.style.display = '';
        sec.style.animation = 'fadeIn .4s ease';
      } else {
        sec.style.display = 'none';
      }
    });

    // Smooth scroll to the target section
    if (filter !== 'all') {
      const target = document.getElementById('sec-' + filter);
      if (target) {
        setTimeout(function () {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
      }
    }
  });
});

// ── SCROLL REVEAL (IntersectionObserver) ─────────────────
const revealObserver = new IntersectionObserver(function (entries) {
  entries.forEach(function (entry) {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
    }
  });
}, { threshold: 0.08 });

document.querySelectorAll('.reveal').forEach(function (el) {
  revealObserver.observe(el);
});
