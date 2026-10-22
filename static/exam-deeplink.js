/*!
 * exam-deeplink.js - Direct QR links for entrance exam cards.
 *
 * Example:
 *   /entrance-exams?exam=mht-cet
 */
(function () {
  'use strict';

  var FOCUS_ONLY = true;

  var EXAM_DETAILS = {
    'mht-cet': {
      overview: 'MHT-CET is Maharashtra state entrance exam for admission to engineering, pharmacy and agriculture courses.',
      eligibility: 'Students who have passed or are appearing for Class 12 with the required Physics, Chemistry and Mathematics/Biology subjects can apply. Exact eligibility depends on the course and current CET Cell rules.',
      pattern: 'Computer-based test with separate Physics-Chemistry and Mathematics/Biology sections. Questions are objective type and the marking scheme follows the current official information brochure.',
      syllabus: 'Physics, Chemistry and Mathematics or Biology based mainly on the Maharashtra State Board Class 11 and Class 12 syllabus.',
      dates: 'Check the current year notification for registration, admit card, exam, answer key and result dates.',
      preparation: 'Complete the State Board syllabus, solve timed MCQs, revise formulas regularly and practise previous MHT-CET style papers.'
    },
    'jee-main': {
      overview: 'JEE Main is the national entrance exam for NITs, IIITs, GFTIs and eligibility for JEE Advanced.',
      eligibility: 'Candidates should meet the current NTA criteria for the relevant year and course. Class 12 subjects and passing-year rules apply.',
      pattern: 'Computer-based objective examination with subject-wise sections for Mathematics, Physics and Chemistry. The exact paper and marking scheme are published by NTA.',
      syllabus: 'Physics, Chemistry and Mathematics from the prescribed NTA syllabus.',
      dates: 'Registration, session dates, city intimation, admit card and result dates are announced by NTA in the yearly notice.',
      preparation: 'Build concepts from NCERT, practise chapter-wise questions, take full mock tests and analyse every mistake.'
    },
    'neet-ug': {
      overview: 'NEET-UG is the national entrance exam for undergraduate medical, dental, AYUSH and related admissions.',
      eligibility: 'Candidates must satisfy the current NTA and counselling authority requirements, including Class 12 subjects and age rules applicable to the admission year.',
      pattern: 'Pen-and-paper objective examination covering Physics, Chemistry and Biology. The current information bulletin defines the duration, questions and marking scheme.',
      syllabus: 'Physics, Chemistry and Biology based on the prescribed NTA/NCERT syllabus.',
      dates: 'Always verify registration, correction window, admit card, exam and result dates in the current NTA notification.',
      preparation: 'Read NCERT thoroughly, revise Biology repeatedly, maintain an error notebook and practise full-length tests.'
    },
    'cat': {
      overview: 'CAT is the national management entrance exam used by IIMs and many other business schools.',
      eligibility: 'Graduates or final-year students meeting the current CAT notification criteria can apply. Category-wise rules are specified in the official notice.',
      pattern: 'Computer-based test covering VARC, DILR and QA. Section timing and marking details are notified for each exam cycle.',
      syllabus: 'Reading comprehension, verbal ability, data interpretation, logical reasoning, arithmetic, algebra, geometry and related aptitude topics.',
      dates: 'Registration, admit card, exam and result dates are published in the annual CAT notification.',
      preparation: 'Read daily, build arithmetic fundamentals, practise DILR sets and take sectional tests before full mocks.'
    },
    'clat': {
      overview: 'CLAT is the common law entrance exam for participating National Law Universities and related undergraduate and postgraduate programmes.',
      eligibility: 'Eligibility depends on the UG or PG programme and the current Consortium of NLUs notification.',
      pattern: 'Objective paper with English, Current Affairs and General Knowledge, Legal Reasoning, Logical Reasoning and Quantitative Techniques sections.',
      syllabus: 'Reading comprehension, current affairs, legal principles, logical reasoning and basic quantitative techniques.',
      dates: 'Registration, admit card, exam, answer key and counselling dates are announced by the Consortium each year.',
      preparation: 'Follow current affairs daily, practise passage-based questions and take timed section-wise mocks.'
    }
  };

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, function (character) {
      return {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }[character];
    });
  }

  function isDetailsView() {
    try {
      return new URLSearchParams(window.location.search).get('details') === '1';
    } catch (error) {
      return false;
    }
  }

  function slugify(value) {
    return String(value || '')
      .toLowerCase()
      .replace(/&/g, ' and ')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  function requestedSlug() {
    var slug = '';
    try {
      slug = slugify(new URLSearchParams(window.location.search).get('exam') || '');
    } catch (error) {
      // URLSearchParams is unavailable in very old browsers.
    }

    if (!slug && window.location.hash.indexOf('#exam-') === 0) {
      var hash = window.location.hash.slice(6);
      try {
        hash = decodeURIComponent(hash);
      } catch (error) {
        // Keep the raw hash when it is not valid URI text.
      }
      slug = slugify(hash);
    }

    if (!slug) {
      var pathMatch = window.location.pathname.match(/\/entrance-exams\/([^/]+)\/?$/i);
      if (pathMatch) slug = slugify(pathMatch[1]);
    }

    return slug;
  }

  function injectStyles() {
    if (document.getElementById('examDeepLinkCSS')) return;

    var style = document.createElement('style');
    style.id = 'examDeepLinkCSS';
    style.textContent = [
      'body.exam-focus .hero, body.exam-focus .search-section,',
      'body.exam-focus .filter-bar, body.exam-focus .exam-sections,',
      'body.exam-focus .prep-section, body.exam-focus .career-section {',
      '  display: none !important;',
      '}',
      '.exam-focus-panel { display: flex; justify-content: center; align-items: flex-start;',
      '  min-height: calc(100vh - 160px); padding: 110px 20px 60px; background: #050a15; }',
      '.exam-focus-inner { width: 100%; max-width: 460px; display: flex;',
      '  flex-direction: column; gap: 18px; }',
      '.exam-focus-label { font-family: Inter, sans-serif; font-weight: 800;',
      '  font-size: .8rem; letter-spacing: .08em; text-transform: uppercase; color: #ff6600; }',
      '.exam-focus-slot .exam-card { animation: examFocusGlow 1.8s ease; }',
      '.exam-focus-info { color: #e2e8f0; font-family: Inter, sans-serif; }',
      '.exam-focus-meta { color: #ff6600; font-size: .75rem; font-weight: 800;',
      '  letter-spacing: .08em; text-transform: uppercase; margin-bottom: 8px; }',
      '.exam-focus-info h2 { color: #fff; font-size: 1.65rem; margin: 0 0 8px; }',
      '.exam-focus-description { color: #cbd5e1; line-height: 1.6; margin: 0 0 18px; }',
      '.exam-focus-info article { border-top: 1px solid rgba(255,255,255,.1); padding: 15px 0; }',
      '.exam-focus-info article h3 { color: #ff8a45; font-size: 1rem; margin: 0 0 6px; }',
      '.exam-focus-info article p { color: #cbd5e1; line-height: 1.6; margin: 0; }',
      '.exam-focus-note { color: #94a3b8; font-size: .82rem; line-height: 1.5; margin: 8px 0 0; }',
      '.exam-focus-all { display: inline-flex; align-items: center; justify-content: center; gap: 8px;',
      '  padding: 13px 20px; border-radius: 12px; text-decoration: none;',
      '  font-family: Inter, sans-serif; font-weight: 800; font-size: .95rem;',
      '  background: #ff6600; color: #050a15; transition: all .2s ease; }',
      '.exam-focus-all:hover { background: #e05500; transform: translateY(-2px); }',
      'body.light-mode .exam-focus-panel { background: #f8fafc; }',
      'body.light-mode .exam-focus-label { color: #c2410c; }',
      'body.light-mode .exam-focus-info, body.light-mode .exam-focus-info h2 { color: #0f172a; }',
      'body.light-mode .exam-focus-description, body.light-mode .exam-focus-info article p { color: #475569; }',
      'body.light-mode .exam-focus-info article { border-top-color: #cbd5e1; }',
      'body.light-mode .exam-focus-note { color: #64748b; }',
      'body.light-mode .exam-focus-all { background: #c2410c; color: #fff; }',
      '@keyframes examFocusGlow { 0%, 100% { box-shadow: 0 10px 30px rgba(0,0,0,.2); }',
      '  35% { box-shadow: 0 0 0 4px rgba(255,102,0,.35), 0 15px 35px rgba(255,102,0,.25); } }'
    ].join('\n');
    document.head.appendChild(style);
  }

  function showFocusedExam(card) {
    injectStyles();
    document.body.classList.add('exam-focus');

    var panel = document.createElement('section');
    panel.id = 'examFocus';
    panel.className = 'exam-focus-panel';
    panel.innerHTML = [
      '<div class="exam-focus-inner">',
      '<div class="exam-focus-label"><i class="fas fa-qrcode"></i> Scanned exam</div>',
      '<div class="exam-focus-slot"></div>',
      '<a class="exam-focus-all" href="' + window.location.pathname + '">',
      '<i class="fas fa-th-large"></i> View all 150+ exams</a>',
      '</div>'
    ].join('');

    var clone = card.cloneNode(true);
    clone.removeAttribute('id');
    var clonedLink = clone.querySelector('.exam-link');
    if (clonedLink) {
      clonedLink.target = '_self';
      clonedLink.removeAttribute('rel');
      clonedLink.href = '/entrance-exams/' + card.getAttribute('data-exam');
    }
    panel.querySelector('.exam-focus-slot').appendChild(clone);

    var anchor = document.querySelector('.hero') || document.querySelector('.exam-sections');
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(panel, anchor);
    } else {
      document.body.insertBefore(panel, document.body.firstChild);
    }

    var title = card.querySelector('.exam-abbr');
    var description = card.querySelector('.exam-name');
    var slug = card.getAttribute('data-exam');
    var detail = EXAM_DETAILS[slug];
    var body = card.querySelector('.exam-body');
    var category = card.closest('.exam-section');
    var detailSections = [
      ['Overview', detail ? detail.overview : (body ? body.textContent.trim() : 'Exam information and admission guidance.')],
      ['Eligibility', detail ? detail.eligibility : 'Refer to the latest exam notification for eligibility, subjects and qualifying requirements.'],
      ['Exam pattern', detail ? detail.pattern : 'The exam pattern, duration and marking scheme are published in the latest official notification.'],
      ['Syllabus', detail ? detail.syllabus : 'Check the latest syllabus notification for the current admission year.'],
      ['Important dates', detail ? detail.dates : 'Check the current notification for registration, exam and result dates.'],
      ['Preparation tips', detail ? detail.preparation : 'Make a study plan, revise the syllabus and practise previous-year questions and mock tests.']
    ];
    var info = document.createElement('section');
    info.id = 'exam-info';
    info.className = 'exam-focus-info';
    info.innerHTML = [
      '<div class="exam-focus-meta">',
      category ? escapeHtml(category.querySelector('.section-title').textContent.replace(/\d+$/, '').trim()) : 'Entrance Exam',
      '</div>',
      '<h2>About ' + escapeHtml(title ? title.textContent.trim() : 'this exam') + '</h2>',
      '<p class="exam-focus-description">' + escapeHtml(description ? description.textContent.trim() : '') + '</p>',
      detailSections.map(function (section) {
        return '<article><h3>' + section[0] + '</h3><p>' + escapeHtml(section[1]) + '</p></article>';
      }).join(''),
      '<p class="exam-focus-note">Dates and eligibility can change every year. Please verify the latest admission notification before applying.</p>'
    ].join('');
    panel.querySelector('.exam-focus-inner').insertBefore(info, panel.querySelector('.exam-focus-all'));

    if (title) {
      document.title = title.textContent.trim()
        + (description ? ' - ' + description.textContent.trim() : '')
        + ' | VidyarthiMitra.org';
    }
    window.scrollTo(0, 0);
  }

  function init() {
    var cards = document.querySelectorAll('.exam-card');
    var cardsBySlug = {};

    for (var i = 0; i < cards.length; i += 1) {
      var card = cards[i];
      var title = card.querySelector('.exam-abbr');
      if (!title) continue;

      var baseSlug = slugify(title.textContent);
      if (!baseSlug) continue;

      var slug = baseSlug;
      var suffix = 2;
      while (cardsBySlug[slug]) {
        slug = baseSlug + '-' + suffix;
        suffix += 1;
      }

      cardsBySlug[slug] = card;
      card.id = 'exam-' + slug;
      card.setAttribute('data-exam', slug);

      var detailsLink = card.querySelector('.exam-link');
      if (detailsLink) {
        detailsLink.setAttribute('data-official-href', detailsLink.href);
        detailsLink.href = '/entrance-exams/' + slug;
        detailsLink.target = '_self';
        detailsLink.removeAttribute('rel');
      }
    }

    var slug = requestedSlug();
    if (!slug || !cardsBySlug[slug]) return;

    if (FOCUS_ONLY || isDetailsView()) {
      showFocusedExam(cardsBySlug[slug]);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
