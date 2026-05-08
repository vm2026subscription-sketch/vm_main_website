/* ═══════════════════════════════════════════════
   blog.js  —  Vidyarthi Mitra Live Blog Filter
   Place in:  static/js/blog.js
   ═══════════════════════════════════════════════

   How it works:
   1. Listens to category <select> and search <input>
   2. Calls Flask API endpoint  /api/blogs?category=&search=
   3. Re-renders the card grid without full page reload
   4. Updates the browser URL so refresh keeps the filter
   ═══════════════════════════════════════════════ */

(function () {
  "use strict";

  /* ── DOM refs ── */
  const categoryFilter = document.getElementById("categoryFilter");
  const searchInput    = document.getElementById("searchInput");
  const container      = document.getElementById("blogContainer");

  /* Nothing to do on non-blog pages */
  if (!categoryFilter || !searchInput || !container) return;

  /* ── Debounce timer ── */
  let debounceTimer = null;

  /* ════════════════════════════════════════
     fetchBlogs — call API, render results
     ════════════════════════════════════════ */
  function fetchBlogs() {
    const category = categoryFilter.value;
    const search   = searchInput.value.trim();

    /* Keep browser URL in sync (no page reload) */
    const url = new URL(window.location.href);
    url.searchParams.set("category", category);
    url.searchParams.set("search",   search);
    window.history.replaceState(null, "", url.toString());

    /* Show loading state */
    container.style.opacity = "0.5";

    /* Hit Flask JSON endpoint */
    fetch(`/api/blogs?category=${encodeURIComponent(category)}&search=${encodeURIComponent(search)}`)
      .then(function (res) {
        if (!res.ok) throw new Error("Network error: " + res.status);
        return res.json();
      })
      .then(function (blogs) {
        renderCards(blogs);
        container.style.opacity = "1";
      })
      .catch(function (err) {
        console.error("Blog fetch error:", err);
        container.style.opacity = "1";
      });
  }

  /* ════════════════════════════════════════
     renderCards — build HTML from JSON array
     ════════════════════════════════════════ */
  function renderCards(blogs) {
    if (!blogs || !blogs.length) {
      container.innerHTML = `
        <div class="no-results">
          <p>No blogs found. Try a different search or category.</p>
        </div>`;
      return;
    }

    container.innerHTML = blogs.map(function (blog) {
      return `
        <div class="blog-card ${esc(blog.category)}" data-category="${esc(blog.category)}">

          <img
            src="/static/${esc(blog.image)}"
            alt="${esc(blog.title)}"
            onerror="this.src='/static/logo.png'"
          >

          <div class="blog-content">
            <span class="tag ${esc(blog.category)}">${esc(blog.tag)}</span>
            <h3>${esc(blog.title)}</h3>
            <p>${esc(blog.summary)}</p>
            <a href="/blogs/${blog.id}">
              <button>Read More</button>
            </a>
          </div>

        </div>`;
    }).join("");
  }

  /* ════════════════════════════════════════
     esc — HTML-escape to prevent XSS
     ════════════════════════════════════════ */
  function esc(str) {
    return String(str)
      .replace(/&/g,  "&amp;")
      .replace(/</g,  "&lt;")
      .replace(/>/g,  "&gt;")
      .replace(/"/g,  "&quot;")
      .replace(/'/g,  "&#39;");
  }

  /* ════════════════════════════════════════
     Event listeners
     ════════════════════════════════════════ */

  /* Category dropdown — instant filter */
  categoryFilter.addEventListener("change", fetchBlogs);

  /* Search input — debounced 350ms */
  searchInput.addEventListener("input", function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(fetchBlogs, 350);
  });

  /* Clear search on Escape key */
  searchInput.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      searchInput.value = "";
      fetchBlogs();
    }
  });

})();
/* ═══════════════════════════════════════════════════
   BLOG DATA  —  Add new blogs here (id must be unique)
   ═══════════════════════════════════════════════════ */

const BLOG_DATA = [
  {
    id: 1,
    category: "result",
    tag: "RESULT",
    image: "blog1.jpg",
    title: "Maharashtra SSC Result 2026",
    summary: "SSC results expected soon. Check official updates and cutoff trends.",
    full: `The Maharashtra State Board of Secondary and Higher Secondary Education (MSBSHSE) is set to declare the SSC Class 10 Result 2025 in June on mahresult.nic.in and sscresult.mkcl.org.
Students who appeared in the March 2025 board exams can check results using their roll number and mother's name.
The overall passing percentage has remained above 95% for the last three consecutive years.
District-wise and division-wise merit lists will be published alongside the main result.
Students securing above 90% will be eligible for state-level scholarships.
Physical marksheets will be distributed by respective schools within 14 working days of the declaration.
Students can apply for re-verification of marks within 10 days by paying a prescribed fee online.
Re-assessment (photocopy of answer sheet) requests must be submitted through the school principal.
Compartment exams for students who fail in 1–2 subjects are scheduled for July 2025.
Students passing compartment will receive a fresh marksheet with no distinction on result type.
The board has introduced SMS-based result alerts — register your mobile number on the MSBSHSE portal.
DigiLocker integration allows students to download digitally signed marksheets instantly.
School-level toppers will be felicitated at a state ceremony in August 2025.
Students planning to apply for FYJC admissions must note that merit lists will be based on SSC percentage.
CET Cell Maharashtra will use SSC marks for Class 11 centralised admission (FYJC CAP) rounds.
Queries and grievances can be raised via the MSBSHSE helpline: 020-25705183.
Special provisions apply for visually impaired and differently abled candidates regarding result formats.
Students who appeared via the open school scheme can check results on the same portal.
A dedicated result analytics dashboard showing subject-wise pass rates will be live on result day.
All students are advised to take screenshots and download PDFs as server load peaks on result day.`
  },
  {
    id: 2,
    category: "admission",
    tag: "ADMISSION",
    image: "blog2.jpg",
    title: "NEET UG 2026 Registration",
    summary: "Complete registration process, eligibility & important dates.",
    full: `NEET UG 2025 registrations are open on the National Testing Agency portal at neet.nta.nic.in.
The exam is the single national entrance test for MBBS, BDS, BAMS, BHMS, and other medical UG programmes.
Eligibility requires Class 12 pass with Physics, Chemistry, and Biology — minimum 50% for general, 40% for reserved.
The upper age limit has been removed following a Supreme Court order; there is no longer a 25-year cap.
Application fee: ₹1,700 (General), ₹1,600 (General-EWS/OBC), ₹1,000 (SC/ST/PwD/Third Gender).
Documents needed: Class 10 & 12 certificates, Aadhaar card, passport-size photo, and scanned signature.
Photo dimensions must be 10 KB–200 KB in JPG format with a white background.
Admit cards will be released 10 days before the exam date on the NTA portal.
The exam is conducted in offline pen-and-paper (OMR) mode at 550+ cities across India.
Duration is 3 hours 20 minutes for 200 MCQs across Physics (50), Chemistry (50), and Biology (100).
Marking scheme: +4 for correct, –1 for incorrect; unanswered questions carry no penalty.
NTA will release the official answer key within 5 days of the exam for candidate challenge.
Results are published as percentile-based scores (NTA Score) alongside raw scores.
Counselling is conducted by MCC (Medical Counselling Committee) for 15% All India Quota seats.
State quota seats (85%) are filled via respective state counselling authorities.
AIIMS and JIPMER institutions are now part of NEET counselling — no separate exam required.
Candidates can appear in NEET unlimited times as there is no attempt cap after the 2022 court ruling.
International Indian students and NRIs must apply under the NRI/OCI category through MCC directly.
The NEET 2025 syllabus is based on the revised NCERT framework; verify chapter inclusions on NTA website.
For any discrepancies in admit card details, contact NTA helpdesk: 011-40759000 before the exam.`
  },
  {
    id: 3,
    category: "exam",
    tag: "EXAM",
    image: "blog3.jpg",
    title: "JEE Main 2026 Admit Card",
    summary: "Admit card download link and exam-day guidelines.",
    full: `JEE Main 2026 Session 2 Admit Card is available for download at jeemain.nta.nic.in using Application Number and Date of Birth.
The Joint Entrance Examination (Main) is the gateway to NITs, IIITs, CFTIs, and state engineering colleges.
Session 1 was conducted in January; Session 2 is scheduled for April 2025 across CBT mode.
The admit card mentions exam centre name, address, shift timing, and important exam-day rules.
Candidates must reach the exam centre at least 60 minutes before the gate closing time.
Items not allowed: mobile phones, calculators, smart watches, wallets, and any electronic device.
Allowed items: admit card printout (in colour), valid government photo ID, and a transparent water bottle.
Rough work must be done on the sheet provided at the centre — no personal rough paper allowed.
JEE Main Paper 1 (B.E./B.Tech) has 90 questions: 30 each in Physics, Chemistry, Mathematics.
Each subject has 20 MCQs (–1 for wrong) and 10 Numerical Value questions (no negative marking).
The exam is 3 hours; PwD candidates get an additional 60 minutes.
Your best percentile across both sessions will be used for NIT/IIIT admissions via JoSAA counselling.
Top 2.5 lakh qualifiers from JEE Main are eligible to appear for JEE Advanced 2025 (IIT admissions).
Results are expected within 2–3 weeks post-exam and will be available as NTA Score + percentile.
City Intimation Slip was released before the admit card — candidates used it to plan travel.
Biometric attendance (fingerprint + photo) is taken at the exam centre before entering the hall.
Students should cross-check name, date of birth, and category on the admit card immediately upon download.
Any discrepancy must be reported to NTA via the official helpdesk before the exam date.
JoSAA 2025 counselling for IIT/NIT/IIIT seat allotment will begin in June after JEE Advanced results.
Keep 3–4 printouts of the admit card safe — it is required during counselling document verification too.`
  },
  {
    id: 4,
    category: "exam",
    tag: "EXAM",
    image: "blog4.jpg",
    title: "MHT-CET Mock Seat Allotment",
    summary: "Check provisional allotment and understand counselling rounds.",
    full: `The State Common Entrance Test Cell (CET Cell) Maharashtra has released the MHT-CET 2025 mock seat allotment on cetcell.mahacet.org.
The mock round is a simulation to help students understand how the actual CAP (Centralised Admission Process) will work.
No fees are to be paid and no reporting is required during the mock round — it is purely informational.
Students should log in using their CET application number and password to view their provisional allotment.
The allotment is based on the option form filled during registration and the merit/percentile score.
Carefully review whether the allotted college and branch match your preferences before the actual CAP round.
After the mock round, candidates can revise their option form before the first official CAP Round begins.
Option form advice: fill at least 50–100 preferences spanning multiple colleges and branches for best results.
Documents required for physical reporting after actual allotment: HSC marksheet, CET scorecard, domicile certificate, caste certificate (if applicable), and Aadhaar card.
Original documents plus 2 self-attested photocopies must be carried to the Facilitation Centre.
CAP Round 1 will be followed by Round 2 and then Institute Level rounds for remaining seats.
Candidates who get a seat in Round 1 can choose to 'Freeze' (accept) or opt for 'Float' (upgrade if better seat available).
Choosing 'Float' means you retain the current seat and automatically upgrade if a better option becomes available.
Candidates who cancel their seat after reporting will be charged a cancellation fee per government rules.
Minority, NRI, and J&K migrant candidates have separate quota seats outside the CAP process.
Top colleges in MHT-CET CAP include VJTI Mumbai, COEP Pune, SPIT Mumbai, and PICT Pune.
Cutoff percentiles for top branches (CS, AI&DS) at premier colleges are typically above 99 percentile.
Students scoring below 60 percentile should explore lateral entry and direct second year diploma pathways.
MHT-CET results are valid only for the current academic year — scores cannot be carried forward.
For help, call CET Cell helpline: 022-22016157 or visit the nearest Facilitation Centre in your district.`
  },
  {
    id: 5,
    category: "career",
    tag: "CAREER",
    image: "blog5.jpg",
    title: "Top Career Options After 12th",
    summary: "Explore engineering, medical, commerce & skill-based careers.",
    full: `After Class 12, students stand at one of the most important crossroads of their academic life, and the right choice can define their entire career trajectory.
Science students with PCM background can pursue B.Tech, BE, B.Arch, BCA, or B.Sc in Physics, Mathematics, or Computer Science.
Science students with PCB background have options in MBBS, BDS, BAMS, BHMS, B.Pharm, B.Sc Nursing, and Paramedical courses.
Commerce students can aim for CA (Chartered Accountancy), CS (Company Secretary), BBA, B.Com, or Economics Honours programmes.
Arts/Humanities students have diverse options including BA in Psychology, Political Science, Journalism, Social Work, and Fine Arts.
Law (5-year integrated BA LLB) is accessible to students from all three streams and leads to one of India's most respected professions.
Design careers — Fashion Design, Interior Design, Graphic Design, UI/UX Design — require a portfolio and entrance exams like NID and UCEED.
Skill-based short-term courses in Digital Marketing, Data Analytics, Web Development, and Video Editing are increasingly industry-valued.
Defence services — Army, Navy, Air Force — recruit through NDA, CDS, and AFCAT for Class 12 graduates below age 19–25.
Hotel Management (NCHMCT JEE) is a lucrative option for students interested in hospitality, culinary arts, and tourism management.
Merchant Navy is a high-earning career path available after 12th PCM via sponsorship through shipping companies and IMU CET.
Animation and VFX programmes from MAAC, Arena, and NIFt equip students for careers in film, gaming, and advertising.
Journalism and Mass Communication programmes (BJMC) open doors to media, PR, content creation, and corporate communication.
EdTech and self-learning platforms like Coursera, NPTEL, and LinkedIn Learning offer certifications that complement any degree.
Students unsure of their path should take aptitude-based career counselling tests before committing to a stream.
Scholarship portals like NSP (National Scholarship Portal) and Mahadbt offer financial support to meritorious and EWS students.
Gap year planning: a structured gap year for competitive exam preparation (JEE, NEET, UPSC) is increasingly normalised and accepted.
Entrepreneurship cells at IITs and IIMs offer startup incubation support even for early-stage student-founders.
International study options — UK, Canada, Germany, Australia — are accessible through IELTS/TOEFL and university-specific scholarships.
The most successful careers are built at the intersection of passion, market demand, and available opportunity — explore all three before deciding.`
  }
];


/* ═══════════════════════════════════════════════════
   renderAllCards()  —  builds cards from BLOG_DATA
   and injects them into #blogContainer
   ═══════════════════════════════════════════════════ */

function renderAllCards(data) {
  const container = document.getElementById("blogContainer");
  if (!container) return;

  container.innerHTML = data.map(function (blog) {
    return `
      <div class="blog-card ${blog.category}" data-id="${blog.id}" data-category="${blog.category}">

        <img
          src="/static/${blog.image}"
          alt="${blog.title}"
          onerror="this.src='/static/logo.png'"
        >

        <div class="blog-content">
          <span class="tag ${blog.category}">${blog.tag}</span>
          <h3>${blog.title}</h3>
          <p>${blog.summary}</p>
          <button onclick="openModal(${blog.id})">Read More</button>
        </div>

      </div>`;
  }).join("");
}


/* ═══════════════════════════════════════════════════
   MODAL  —  shows full blog content on Read More click
   ═══════════════════════════════════════════════════ */

/* Inject modal HTML once into the page */
(function injectModal() {
  const modal = document.createElement("div");
  modal.id = "blogModal";
  modal.innerHTML = `
    <div class="modal-overlay" onclick="closeModal()"></div>
    <div class="modal-box">
      <button class="modal-close" onclick="closeModal()">&#10005;</button>
      <span class="modal-tag" id="modalTag"></span>
      <h2 id="modalTitle"></h2>
      <p  id="modalSummary"></p>
      <hr style="margin:1rem 0;border:none;border-top:1px solid #eee">
      <div id="modalBody"></div>
    </div>`;
  document.body.appendChild(modal);

  /* Modal styles injected via JS so no extra CSS file needed */
  const style = document.createElement("style");
  style.textContent = `
    #blogModal {
      display: none; position: fixed; inset: 0; z-index: 9999;
      align-items: center; justify-content: center;
    }
    #blogModal.open { display: flex; }
    .modal-overlay {
      position: absolute; inset: 0;
      background: rgba(0,0,0,0.55); backdrop-filter: blur(3px);
    }
    .modal-box {
      position: relative; z-index: 1;
      background: #fff; border-radius: 16px;
      width: min(720px, 92vw); max-height: 80vh;
      overflow-y: auto; padding: 2rem 2rem 2.5rem;
      box-shadow: 0 20px 60px rgba(0,0,0,0.25);
      animation: slideUp .25s ease;
    }
    @keyframes slideUp {
      from { transform: translateY(30px); opacity: 0; }
      to   { transform: translateY(0);    opacity: 1; }
    }
    .modal-close {
      position: absolute; top: 1rem; right: 1rem;
      background: #f1ede8; border: none; border-radius: 50%;
      width: 32px; height: 32px; font-size: 14px;
      cursor: pointer; display: flex; align-items: center; justify-content: center;
      transition: background .2s;
    }
    .modal-close:hover { background: #e0dbd4; }
    .modal-tag {
      display: inline-block; font-size: .69rem; font-weight: 700;
      letter-spacing: .07em; text-transform: uppercase;
      padding: 3px 10px; border-radius: 6px; margin-bottom: .75rem;
    }
    .modal-tag.result    { background:#fce8e8; color:#c0392b; }
    .modal-tag.exam      { background:#e8f4fd; color:#1558a7; }
    .modal-tag.admission { background:#e6fdf4; color:#0d7a4e; }
    .modal-tag.career    { background:#fff0e6; color:#c2560a; }
    #modalTitle {
      font-family: 'Poppins', sans-serif;
      font-size: clamp(1.1rem, 3vw, 1.45rem);
      font-weight: 600; margin-bottom: .5rem; line-height: 1.35;
    }
    #modalSummary {
      font-size: .9rem; color: #888; font-style: italic; margin-bottom: .25rem;
    }
    #modalBody { font-size: .93rem; color: #333; line-height: 1.85; }
    #modalBody p { margin-bottom: .6rem; }
  `;
  document.head.appendChild(style);
})();


/* Opens modal and fills content */
function openModal(id) {
  const blog = BLOG_DATA.find(function (b) { return b.id === id; });
  if (!blog) return;

  document.getElementById("modalTag").textContent  = blog.tag;
  document.getElementById("modalTag").className    = "modal-tag " + blog.category;
  document.getElementById("modalTitle").textContent   = blog.title;
  document.getElementById("modalSummary").textContent = blog.summary;

  /* Each line of full content becomes a paragraph */
  document.getElementById("modalBody").innerHTML =
    blog.full.trim().split("\n").map(function (line) {
      return line.trim() ? "<p>" + line.trim() + "</p>" : "";
    }).join("");

  document.getElementById("blogModal").classList.add("open");
  document.body.style.overflow = "hidden";
}

/* Closes modal */
function closeModal() {
  document.getElementById("blogModal").classList.remove("open");
  document.body.style.overflow = "";
}

/* Close on Escape key */
document.addEventListener("keydown", function (e) {
  if (e.key === "Escape") closeModal();
});


/* ═══════════════════════════════════════════════════
   FILTER  —  category select + search input
   ═══════════════════════════════════════════════════ */

function applyFilter() {
  const category = document.getElementById("categoryFilter").value;
  const search   = document.getElementById("searchInput").value.toLowerCase().trim();

  const filtered = BLOG_DATA.filter(function (blog) {
    const matchCat    = category === "all" || blog.category === category;
    const matchSearch = !search  ||
      blog.title.toLowerCase().includes(search) ||
      blog.summary.toLowerCase().includes(search);
    return matchCat && matchSearch;
  });

  renderAllCards(filtered);
}

/* ── Wire up on DOM ready ── */
document.addEventListener("DOMContentLoaded", function () {
  renderAllCards(BLOG_DATA);

  const catFilter   = document.getElementById("categoryFilter");
  const searchInput = document.getElementById("searchInput");

  if (catFilter)   catFilter.addEventListener("change", applyFilter);
  if (searchInput) {
    let debounce;
    searchInput.addEventListener("input", function () {
      clearTimeout(debounce);
      debounce = setTimeout(applyFilter, 300);
    });
    searchInput.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { searchInput.value = ""; applyFilter(); }
    });
  }
});