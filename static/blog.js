(function () {
  "use strict";

  const categoryFilter = document.getElementById("categoryFilter");
  const searchInput = document.getElementById("searchInput");
  const container = document.getElementById("blogContainer");

  if (!categoryFilter || !searchInput || !container) {
    return;
  }

  let debounceTimer = null;

  function esc(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function syncUrl(category, search) {
    const url = new URL(window.location.href);
    url.searchParams.set("category", category);
    if (search) {
      url.searchParams.set("search", search);
    } else {
      url.searchParams.delete("search");
    }
    window.history.replaceState(null, "", url.toString());
  }

  function renderCards(blogs) {
    if (!blogs || !blogs.length) {
      container.innerHTML = '<div class="no-results"><p>No blogs found. Try a different search or category.</p></div>';
      return;
    }

    container.innerHTML = blogs.map(function (blog) {
      const blogId = esc(blog.id);
      const category = esc(blog.category || "blog");
      const image = esc(blog.image || "logo.png");
      const title = esc(blog.title || "Untitled");
      const summary = esc(blog.summary || "");
      const tag = esc(blog.tag || blog.category || "BLOG");

      return `
        <article class="blog-card ${category}" data-category="${category}">
          <img src="/static/${image}" alt="${title}" class="blog-card-img" loading="lazy" onerror="this.src='/static/logo.png'">
          <div class="blog-content">
            <span class="tag ${category}">${tag}</span>
            <h3>${title}</h3>
            <p>${summary}</p>
            <a class="read-more-btn" href="/blogs/${blogId}">Read More <i class="fa fa-arrow-right" style="margin-left: 6px;"></i></a>
          </div>
        </article>`;
    }).join("");
  }

  function fetchBlogs() {
    const category = categoryFilter.value.trim();
    const search = searchInput.value.trim();

    syncUrl(category, search);
    container.style.opacity = "0.6";

    let url = '/api/blogs';
    const params = new URLSearchParams();
    if (category && category !== 'all') {
      params.set('category', category);
    }
    if (search) {
      params.set('search', search);
    }
    if ([...params].length) {
      url += '?' + params.toString();
    }

    fetch(url)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Network error: " + response.status);
        }
        return response.json();
      })
      .then(function (blogs) {
        renderCards(blogs);
        container.style.opacity = "1";
      })
      .catch(function (error) {
        console.error("Blog fetch error:", error);
        container.innerHTML = '<div class="no-results"><p>Unable to load blogs right now. Please try again.</p></div>';
        container.style.opacity = "1";
      });
  }

  categoryFilter.addEventListener("change", fetchBlogs);

  searchInput.addEventListener("input", function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(fetchBlogs, 300);
  });

  searchInput.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      searchInput.value = "";
      fetchBlogs();
    }
  });

  const params = new URLSearchParams(window.location.search);
  const category = params.get("category");
  const search = params.get("search");

  if (category) {
    categoryFilter.value = category;
  }
  if (search) {
    searchInput.value = search;
  }

  fetchBlogs();
})();
