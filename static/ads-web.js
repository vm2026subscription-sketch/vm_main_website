/* Website advertisement loader.
 *
 * Drop a slot anywhere on a page:
 *   <div class="vm-ad-slot" data-position="homepage_top"></div>
 *
 * This script finds every slot, lazy-loads the highest-priority active ad for
 * that position (platform=website|both), renders it, tracks an impression when
 * it scrolls into view, and routes taps through the click-tracking redirect.
 * Nothing is hardcoded — all content comes from /api/v1/ads.
 */
(function () {
  "use strict";

  var API = "/api/v1/ads";

  function fetchAd(position) {
    var url = API + "?platform=website&position=" + encodeURIComponent(position) + "&limit=1";
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (d) { return (d && d.ads && d.ads[0]) || null; })
      .catch(function () { return null; });
  }

  function trackImpression(id) {
    // Fire-and-forget; keepalive lets it survive navigation.
    try {
      fetch(API + "/" + id + "/impression", { method: "POST", keepalive: true });
    } catch (e) { /* ignore */ }
  }

  function clickHref(ad) {
    return ad.click_url || (API + "/" + ad.id + "/click");
  }

  function buildImage(ad) {
    var img = document.createElement("img");
    img.src = ad.media_url || ad.image_url;
    img.alt = ad.title || "Advertisement";
    img.loading = "lazy"; // native lazy loading + CDN image optimization
    img.decoding = "async";
    img.className = "vm-ad-img";
    // Redirect URL is optional: only make it clickable when a target exists.
    if (ad.redirect_url) {
      var a = document.createElement("a");
      a.href = clickHref(ad);
      a.target = "_blank";
      a.rel = "noopener sponsored";
      a.className = "vm-ad-link";
      a.setAttribute("aria-label", ad.title || "Advertisement");
      a.appendChild(img);
      return a;
    }
    return img;
  }

  function buildVideo(ad) {
    var v = document.createElement("video");
    v.src = ad.media_url;
    v.className = "vm-ad-video";
    v.controls = true;          // play controls
    v.preload = "metadata";     // lazy: don't fetch the whole file up front
    v.playsInline = true;
    if (ad.thumbnail) v.poster = ad.thumbnail; // poster thumbnail, no autoplay
    return v;
  }

  function buildAudio(ad) {
    var wrap = document.createElement("div");
    wrap.className = "vm-ad-audio";
    if (ad.title) {
      var t = document.createElement("div");
      t.className = "vm-ad-audio-title";
      t.textContent = ad.title;
      wrap.appendChild(t);
    }
    var a = document.createElement("audio");
    a.src = ad.media_url;
    a.controls = true;          // play/pause + progress bar (native)
    a.preload = "none";         // lazy: fetch only on play
    wrap.appendChild(a);
    return wrap;
  }

  function buildCta(ad) {
    var a = document.createElement("a");
    a.href = clickHref(ad);
    a.target = "_blank";
    a.rel = "noopener sponsored";
    a.className = "vm-ad-cta";
    a.textContent = "Learn more →";
    return a;
  }

  function renderAd(slot, ad) {
    slot.innerHTML = "";
    slot.classList.add("vm-ad-loaded");

    var node;
    if (ad.ad_type === "video" && ad.media_url) node = buildVideo(ad);
    else if (ad.ad_type === "audio" && ad.media_url) node = buildAudio(ad);
    else node = buildImage(ad); // image (or backward-compatible fallback)
    slot.appendChild(node);

    // Video/audio players can't be wrapped in a link (it would block controls),
    // so surface an optional call-to-action when a redirect URL is set.
    if ((ad.ad_type === "video" || ad.ad_type === "audio") && ad.redirect_url) {
      slot.appendChild(buildCta(ad));
    }

    // Small "Ad" marker for transparency
    var tag = document.createElement("span");
    tag.className = "vm-ad-tag";
    tag.textContent = "Ad";
    slot.appendChild(tag);

    // Track impression once the ad is actually visible.
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) {
            trackImpression(ad.id);
            io.disconnect();
          }
        });
      }, { threshold: 0.5 });
      io.observe(slot);
    } else {
      trackImpression(ad.id);
    }
  }

  function renderPlaceholder(slot) {
    if (slot.getAttribute("data-placeholder") === "true") {
      slot.innerHTML = '<div class="vm-ad-placeholder">Advertisement</div>';
    } else {
      slot.style.display = "none"; // collapse empty slots to avoid gaps
    }
  }

  function loadSlot(slot) {
    if (slot.getAttribute("data-loaded") === "1") return;
    slot.setAttribute("data-loaded", "1");
    var position = slot.getAttribute("data-position");
    if (!position) return;
    fetchAd(position).then(function (ad) {
      var hasMedia = ad && (ad.media_url || ad.image_url);
      if (hasMedia) renderAd(slot, ad);
      else renderPlaceholder(slot);
    });
  }

  function init() {
    var slots = document.querySelectorAll(".vm-ad-slot[data-position]");
    if (!slots.length) return;

    // Lazy: only fetch a slot's ad when it nears the viewport.
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries, obs) {
        entries.forEach(function (en) {
          if (en.isIntersecting) {
            loadSlot(en.target);
            obs.unobserve(en.target);
          }
        });
      }, { rootMargin: "300px" });
      slots.forEach(function (s) { io.observe(s); });
    } else {
      slots.forEach(loadSlot);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
