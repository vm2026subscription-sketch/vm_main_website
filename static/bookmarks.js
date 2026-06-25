/* ──────────────────────────────────────────────────────────────────
 * Shared bookmark / save behaviour for colleges & universities.
 *
 * Markup contract — any element with class `vm-bookmark-btn` and:
 *   data-type = "college" | "university"
 *   data-name = display name (used as the unique key per user)
 *   data-url  = link back to the item (optional)
 *
 * Works with dynamically inserted cards (live college search, university
 * pagination) via event delegation + a MutationObserver.
 * ────────────────────────────────────────────────────────────────── */
(function () {
  "use strict";

  var LOGIN_URL = "/login";
  var API_URL = "/api/bookmarks";
  var saved = Object.create(null); // key "type|name" -> true

  function keyOf(type, name) {
    return (type || "") + "|" + (name || "");
  }

  function markSavedState(btn) {
    var k = keyOf(btn.getAttribute("data-type"), btn.getAttribute("data-name"));
    if (saved[k]) {
      setLabel(btn, "Saved <i class=\"fa fa-check\"></i>", true);
    }
  }

  function setLabel(btn, text, isSaved) {
    var label = btn.querySelector(".vm-bookmark-label");
    if (label) {
      label.innerHTML = text;
    }
    var icon = btn.querySelector("i");
    if (icon) {
      icon.className = isSaved ? "fa-solid fa-bookmark" : "fa-regular fa-bookmark";
    }
    if (isSaved) {
      btn.classList.add("vm-bookmarked");
      btn.setAttribute("aria-pressed", "true");
    }
  }

  function markAll(root) {
    var scope = root && root.querySelectorAll ? root : document;
    var btns = scope.querySelectorAll(".vm-bookmark-btn");
    for (var i = 0; i < btns.length; i++) {
      markSavedState(btns[i]);
    }
  }

  function loadSaved() {
    fetch(API_URL, { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (r.status === 401) return null; // not logged in — fine
        return r.ok ? r.json() : null;
      })
      .then(function (data) {
        if (!data || !data.success || !data.bookmarks) return;
        data.bookmarks.forEach(function (b) {
          saved[keyOf(b.item_type, b.item_name)] = true;
        });
        markAll(document);
      })
      .catch(function () { /* network issue — leave buttons in default state */ });
  }

  function saveBookmark(btn) {
    var type = btn.getAttribute("data-type");
    var name = btn.getAttribute("data-name");
    var url = btn.getAttribute("data-url") || "";

    if (saved[keyOf(type, name)]) {
      flash(btn, "Already Saved");
      return;
    }

    btn.classList.add("vm-bookmark-loading");

    fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_type: type, item_name: name, item_url: url })
    })
      .then(function (r) {
        if (r.status === 401) {
          // Not logged in — send to login, then bring them back here.
          window.location.href = LOGIN_URL + "?next=" + encodeURIComponent(window.location.pathname + window.location.search);
          return null;
        }
        return r.ok ? r.json() : null;
      })
      .then(function (data) {
        btn.classList.remove("vm-bookmark-loading");
        if (!data || !data.success) return;
        saved[keyOf(type, name)] = true;
        if (data.status === "already_saved") {
          setLabel(btn, "Already Saved", true);
        } else {
          setLabel(btn, "Saved <i class=\"fa fa-check\"></i>", true);
        }
      })
      .catch(function () {
        btn.classList.remove("vm-bookmark-loading");
      });
  }

  function flash(btn, text) {
    var label = btn.querySelector(".vm-bookmark-label");
    if (!label) return;
    var prev = label.innerHTML;
    label.innerHTML = text;
    window.setTimeout(function () {
      if (!saved[keyOf(btn.getAttribute("data-type"), btn.getAttribute("data-name"))]) {
        label.innerHTML = prev;
      }
    }, 1500);
  }

  // Event delegation — handles cards added after page load too.
  document.addEventListener("click", function (e) {
    var btn = e.target.closest ? e.target.closest(".vm-bookmark-btn") : null;
    if (!btn) return;
    // The university card is an <a>; stop it from navigating.
    e.preventDefault();
    e.stopPropagation();
    saveBookmark(btn);
  });

  // Keyboard support for non-button (span) triggers.
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var btn = e.target.closest ? e.target.closest(".vm-bookmark-btn") : null;
    if (!btn) return;
    e.preventDefault();
    saveBookmark(btn);
  });

  document.addEventListener("DOMContentLoaded", loadSaved);

  // Re-mark buttons when cards are re-rendered (live search / pagination).
  if (window.MutationObserver) {
    var pending = null;
    var observer = new MutationObserver(function () {
      window.clearTimeout(pending);
      pending = window.setTimeout(function () { markAll(document); }, 150);
    });
    document.addEventListener("DOMContentLoaded", function () {
      observer.observe(document.body, { childList: true, subtree: true });
    });
  }
})();
