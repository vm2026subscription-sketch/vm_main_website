/* ── VidyarthiMitra Admission Page – main.js ── */

document.addEventListener('DOMContentLoaded', function () {

  /* ── Extra cards data for Load More (2026-27) ── */
  const extraCards = [
    {
      title: 'TATA INSTITUTE OF SOCIAL SCIENCES ADMISSIONS 2026-27',
      date: '1st February 2026',
      tags: ['M.A', 'Ph.D', 'MSW']
    },
    {
      title: 'UNIVERSITY OF MUMBAI DISTANCE EDUCATION ADMISSIONS 2026-27',
      date: '28th January 2026',
      tags: ['BA', 'B.Com', 'M.Com']
    },
    {
      title: 'INSTITUTE OF MANAGEMENT TECHNOLOGY NAGPUR MBA ADMISSIONS 2026',
      date: '25th January 2026',
      tags: ['MBA', 'PGDM']
    },
    {
      title: 'COEP TECHNOLOGICAL UNIVERSITY ADMISSIONS 2026-27',
      date: '20th January 2026',
      tags: ['B.Tech', 'M.Tech', 'Ph.D']
    },
    {
      title: 'SP JAIN INSTITUTE OF MANAGEMENT AND RESEARCH ADMISSIONS 2026',
      date: '15th January 2026',
      tags: ['PGDM', 'Executive MBA']
    },
    {
      title: 'COLLEGE OF ENGINEERING PUNE ADMISSIONS 2026-27',
      date: '10th January 2026',
      tags: ['B.Tech', 'M.Tech', 'Ph.D']
    },
    {
      title: 'FERGUSSON COLLEGE PUNE ADMISSIONS 2026-27',
      date: '5th January 2026',
      tags: ['BA', 'B.Sc', 'B.Com']
    },
    {
      title: 'SAVITRIBAI PHULE PUNE UNIVERSITY ADMISSIONS 2026-27',
      date: '2nd January 2026',
      tags: ['UG', 'PG', 'Ph.D']
    },
    {
      title: 'DR. D.Y. PATIL MEDICAL COLLEGE ADMISSIONS 2026-27',
      date: '28th December 2025',
      tags: ['MBBS', 'MD', 'MS']
    },
    {
      title: 'VJTI MUMBAI ADMISSIONS 2026-27 NOW OPEN',
      date: '20th December 2025',
      tags: ['B.Tech', 'M.Tech']
    },
    {
      title: 'XAVIER INSTITUTE OF COMMUNICATIONS ADMISSIONS 2026',
      date: '15th December 2025',
      tags: ['PG Diploma', 'Mass Comm']
    },
    {
      title: 'SYMBIOSIS INTERNATIONAL UNIVERSITY ADMISSIONS 2026-27',
      date: '10th December 2025',
      tags: ['MBA', 'BBA', 'LLB', 'B.Tech']
    }
  ];

  let loaded = false;
  const grid = document.getElementById('cardsGrid');
  const loadMoreBtn = document.getElementById('loadMoreBtn');

  /* ── Build a card HTML string ── */
  function buildCard(card) {
    const tagsHTML = card.tags.map(function (tag, i) {
      const sep = i < card.tags.length - 1
        ? '<span class="tag-sep">|</span>'
        : '';
      return '<span class="adm-tag">' + tag + '</span>' + sep;
    }).join('');

    return (
      '<div class="adm-card">' +
        '<div class="adm-card-title">' + card.title + '</div>' +
        '<hr class="adm-card-divider"/>' +
        '<div class="adm-card-date">' +
          '<span class="cal-icon">&#128197;</span> ' + card.date +
        '</div>' +
        '<div class="adm-card-tags">' + tagsHTML + '</div>' +
        '<button class="read-more-btn" onclick="handleReadMore(this)">READ MORE</button>' +
      '</div>'
    );
  }

  /* ── Load More ── */
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', function () {
      if (loaded) return;
      loaded = true;

      extraCards.forEach(function (card) {
        const div = document.createElement('div');
        div.innerHTML = buildCard(card);
        grid.appendChild(div.firstChild);
      });

      loadMoreBtn.textContent = 'NO MORE RESULTS';
      loadMoreBtn.disabled = true;
    });
  }

  /* ── Scroll to Top ── */
  const scrollTopBtn = document.getElementById('scrollTop');
  if (scrollTopBtn) {
    scrollTopBtn.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    /* Show/hide scroll button based on scroll position */
    window.addEventListener('scroll', function () {
      if (window.scrollY > 300) {
        scrollTopBtn.style.opacity = '1';
        scrollTopBtn.style.pointerEvents = 'auto';
      } else {
        scrollTopBtn.style.opacity = '0';
        scrollTopBtn.style.pointerEvents = 'none';
      }
    });

    /* Hide initially */
    scrollTopBtn.style.opacity = '0';
    scrollTopBtn.style.transition = 'opacity 0.3s';
    scrollTopBtn.style.pointerEvents = 'none';
  }

  /* ── Trending: All button resets active state ── */
  const allBtn = document.getElementById('allBtn');
  const trendingLinks = document.querySelectorAll('.trending-box a');

  if (allBtn) {
    allBtn.addEventListener('click', function () {
      allBtn.style.background = '#e55a00';
      trendingLinks.forEach(function (a) {
        a.style.fontWeight = '400';
        a.style.color = '#006fa6';
      });
    });
  }

  trendingLinks.forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault();
      /* Dim All button */
      if (allBtn) allBtn.style.background = '#aaa';
      /* Highlight clicked link */
      trendingLinks.forEach(function (link) {
        link.style.fontWeight = '400';
        link.style.color = '#006fa6';
      });
      a.style.fontWeight = '700';
      a.style.color = '#e55a00';
    });
  });

  /* ── Read More button handler ── */
  window.handleReadMore = function (btn) {
    const title = btn.closest('.adm-card').querySelector('.adm-card-title').textContent;
    alert('Opening details for:\n\n' + title);
  };

  /* ── Attach Read More to existing cards ── */
  document.querySelectorAll('.read-more-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      window.handleReadMore(btn);
    });
  });

  /* ── Navbar search icon ── */
  const searchIcon = document.getElementById('searchIcon');
  if (searchIcon) {
    searchIcon.addEventListener('click', function () {
      const query = prompt('Search VidyarthiMitra 2026-27:');
      if (query && query.trim()) {
        alert('Searching for: ' + query.trim());
      }
    });
  }
}); 
