/* Advertisements admin — CRUD, filters, preview, analytics.
   Supports Image / Video / Audio advertisement types.
   Talks to /api/v1/admin/ads (session-protected). Media upload goes to
   /api/v1/admin/ads/upload (image/video/audio, validated + compressed). */
(function () {
  "use strict";

  const POSITIONS = window.AD_POSITIONS || { website: [], mobile: [] };
  const POS_LABELS = {
    homepage_top: "Homepage Top", homepage_middle: "Homepage Middle",
    sidebar: "Sidebar", footer: "Footer", article_page: "Article Page",
    home_top: "Home Top", home_middle: "Home Middle",
    home_bottom: "Home Bottom", between_epaper_cards: "Between ePaper Cards",
    top: "Top (both)", middle: "Middle (both)", bottom: "Bottom (both)",
  };
  const PLAT_LABELS = { website: "Website", mobile: "Mobile App", both: "Both" };
  const TYPE_ICON = { image: "fa-image", video: "fa-video", audio: "fa-volume-up" };
  const TYPE_CFG = {
    image: { label: "Banner Image", hint: "JPG, PNG or WebP. Auto-optimized via CDN.", accept: "image/jpeg,image/png,image/webp" },
    video: { label: "Video (MP4)", hint: "MP4 only. Compressed on upload. Plays with controls (no autoplay).", accept: "video/mp4" },
    audio: { label: "Audio (MP3)", hint: "MP3 only. Compressed on upload.", accept: "audio/mpeg,.mp3" },
  };

  const $ = (id) => document.getElementById(id);
  let _debounceTimer = null;

  function label(map, key) { return map[key] || key || "—"; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }
  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 2600);
  }

  // ── Filter position dropdown ──
  function fillFilterPositions() {
    const sel = $("fPosition");
    const all = [...POSITIONS.website, ...POSITIONS.mobile, ...(POSITIONS.both || [])];
    sel.innerHTML = '<option value="">All</option>' +
      all.map((p) => `<option value="${p}">${label(POS_LABELS, p)}</option>`).join("");
  }

  // ── Form position dropdown (depends on platform) ──
  // Website → website slots, Mobile → mobile slots, Both → common slots
  // (Top/Middle/Bottom) that render in the equivalent place on each platform.
  function syncPositions() {
    const plat = $("adPlatform").value;
    const list = POSITIONS[plat] || [];
    const current = $("adPosition").value;
    $("adPosition").innerHTML = '<option value="">— none —</option>' +
      list.map((p) => `<option value="${p}">${label(POS_LABELS, p)}</option>`).join("");
    if (list.includes(current)) $("adPosition").value = current;
  }

  // ── Advertisement type (image / video / audio) ──
  function currentType() { return $("adType").value || "image"; }
  function mediaUrlOf(type) {
    return (type === "image" ? $("adImageUrl").value : $("adMediaUrl").value) || "";
  }

  function syncType() {
    const type = currentType();
    const cfg = TYPE_CFG[type];
    $("mediaLabel").textContent = cfg.label;
    $("mediaHint").textContent = cfg.hint;
    $("adMediaFile").setAttribute("accept", cfg.accept);
    $("thumbRow").style.display = type === "video" ? "" : "none";
    renderMediaPreview();
  }

  function pickMedia() { $("adMediaFile").click(); }

  // Use a pasted direct link instead of uploading a file.
  function useMediaLink() {
    const url = $("adMediaLink").value.trim();
    const type = currentType();
    if (type === "image") { $("adImageUrl").value = url; $("adMediaUrl").value = ""; }
    else { $("adMediaUrl").value = url; $("adDuration").value = ""; } // re-read duration from the link
    renderMediaPreview();
  }

  function useThumbLink() {
    $("adThumbnail").value = $("adThumbLink").value.trim();
    renderMediaPreview();
  }

  function renderMediaPreview() {
    const type = currentType();
    const url = mediaUrlOf(type);
    const img = $("uploadPreview"), vid = $("uploadVideoPrev"), aud = $("uploadAudioPrev"), ph = $("uploadPh");
    img.style.display = vid.style.display = aud.style.display = "none";
    try { vid.pause(); aud.pause(); } catch (e) {}
    if (!url) { ph.style.display = "block"; }
    else if (type === "image") { img.src = url; img.style.display = "block"; ph.style.display = "none"; }
    else if (type === "video") {
      vid.src = url;
      const poster = $("adThumbnail").value;
      if (poster) vid.setAttribute("poster", poster);
      // Auto-read duration from the media itself (works for uploads AND links).
      vid.onloadedmetadata = function () {
        if (isFinite(vid.duration) && vid.duration > 0) $("adDuration").value = Math.round(vid.duration);
      };
      vid.style.display = "block"; ph.style.display = "none";
    } else {
      aud.src = url;
      aud.onloadedmetadata = function () {
        if (isFinite(aud.duration) && aud.duration > 0) $("adDuration").value = Math.round(aud.duration);
      };
      aud.style.display = "block"; ph.style.display = "none";
    }

    // Thumbnail preview
    const thumb = $("adThumbnail").value;
    if (thumb) { $("thumbPreview").src = thumb; $("thumbPreview").style.display = "block"; $("thumbPh").style.display = "none"; }
    else { $("thumbPreview").style.display = "none"; $("thumbPh").style.display = "block"; }
  }

  // ── Media upload (image/video/audio) ──
  async function uploadMedia(input) {
    const file = input.files[0];
    if (!file) return;
    const type = currentType();
    $("uploadPh").textContent = "Uploading…";
    $("uploadPh").style.display = "block";
    ["uploadPreview", "uploadVideoPrev", "uploadAudioPrev"].forEach((id) => { $(id).style.display = "none"; });
    const fd = new FormData();
    fd.append("file", file);
    fd.append("type", type);
    try {
      const res = await fetch("/api/v1/admin/ads/upload", { method: "POST", body: fd });
      const data = await res.json();
      if (data.success && data.url) {
        if (type === "image") { $("adImageUrl").value = data.url; $("adMediaUrl").value = ""; }
        else {
          $("adMediaUrl").value = data.url;
          $("adDuration").value = data.duration || "";
          if (data.thumbnail && !$("adThumbnail").value) {
            $("adThumbnail").value = data.thumbnail;
            $("adThumbLink").value = data.thumbnail;
          }
        }
        $("adMediaLink").value = data.url; // reflect the uploaded file as a link too
        renderMediaPreview();
      } else {
        toast(data.error || "Upload failed");
        $("uploadPh").textContent = "Click to upload";
      }
    } catch (e) {
      toast("Upload failed: " + e.message);
      $("uploadPh").textContent = "Click to upload";
    } finally {
      input.value = "";
    }
  }

  async function uploadThumb(input) {
    const file = input.files[0];
    if (!file) return;
    $("thumbPh").textContent = "Uploading…";
    const fd = new FormData();
    fd.append("file", file);
    fd.append("type", "image");
    try {
      const res = await fetch("/api/v1/admin/ads/upload", { method: "POST", body: fd });
      const data = await res.json();
      if (data.success && data.url) { $("adThumbnail").value = data.url; $("adThumbLink").value = data.url; renderMediaPreview(); }
      else { toast(data.error || "Upload failed"); $("thumbPh").textContent = "Click to upload poster"; }
    } catch (e) {
      toast("Upload failed: " + e.message); $("thumbPh").textContent = "Click to upload poster";
    } finally {
      input.value = "";
    }
  }

  // ── Load list + analytics ──
  async function load() {
    const params = new URLSearchParams();
    const q = $("fSearch").value.trim();
    if (q) params.set("q", q);
    if ($("fPlatform").value) params.set("platform", $("fPlatform").value);
    if ($("fPosition").value) params.set("position", $("fPosition").value);
    if ($("fStatus").value) params.set("status", $("fStatus").value);

    const tbody = $("adRows");
    try {
      const res = await fetch("/api/v1/admin/ads?" + params.toString());
      if (res.status === 401) { location.href = "/epaper-admin/login"; return; }
      const data = await res.json();
      const ads = data.ads || [];
      const t = data.totals || {};
      $("statTotal").textContent = t.count || 0;
      $("statImpr").textContent = (t.impressions || 0).toLocaleString();
      $("statClicks").textContent = (t.clicks || 0).toLocaleString();
      $("statCtr").textContent = (t.ctr || 0) + "%";
      ads.forEach((a) => { _cache[a.id] = a; });
      if (!ads.length) {
        tbody.innerHTML = '<tr><td colspan="12" class="empty">No advertisements found.</td></tr>';
        return;
      }
      tbody.innerHTML = ads.map(rowHtml).join("");
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="12" class="empty">Failed to load. ' + esc(e.message) + "</td></tr>";
    }
  }

  function debouncedLoad() {
    clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(load, 300);
  }

  function statusBadge(s) {
    const cls = { active: "badge-active", inactive: "badge-inactive", expired: "badge-expired", scheduled: "badge-scheduled" }[s] || "badge-inactive";
    return `<span class="badge ${cls}">${esc(s)}</span>`;
  }
  function fmtDate(d) { return d ? esc(d) : "—"; }

  function typeThumb(ad) {
    // A representative thumbnail for the row.
    const src = ad.thumbnail || (ad.ad_type === "image" ? ad.image_url : "");
    if (src) return `<img class="thumb" src="${esc(src)}" loading="lazy" alt="">`;
    const icon = TYPE_ICON[ad.ad_type] || "fa-image";
    return `<div class="thumb" style="display:flex;align-items:center;justify-content:center;color:#bbb"><i class="fa ${icon}"></i></div>`;
  }

  function rowHtml(ad) {
    const dates = (ad.start_date || ad.end_date)
      ? `${fmtDate(ad.start_date)} → ${fmtDate(ad.end_date)}` : "Always";
    const lastShown = ad.last_displayed_at ? esc(ad.last_displayed_at.replace("T", " ").slice(0, 16)) : "—";
    const typeIcon = `<i class="fa ${TYPE_ICON[ad.ad_type] || "fa-image"}" title="${esc(ad.ad_type)}" style="color:#9a938a;margin-right:6px"></i>`;
    return `<tr>
      <td>${typeThumb(ad)}</td>
      <td>${typeIcon}<strong>${esc(ad.title)}</strong></td>
      <td><span class="badge badge-plat">${label(PLAT_LABELS, ad.platform)}</span></td>
      <td>${label(POS_LABELS, ad.position)}</td>
      <td>${ad.priority}</td>
      <td style="font-size:12px">${dates}</td>
      <td>${statusBadge(ad.status)}</td>
      <td>${(ad.impressions || 0).toLocaleString()}</td>
      <td>${(ad.clicks || 0).toLocaleString()}</td>
      <td>${ad.ctr || 0}%</td>
      <td style="font-size:11px;color:#6b645b">${lastShown}</td>
      <td><div class="actions">
        <button class="btn btn-ghost btn-sm" title="Preview" onclick='Ads.preview(${ad.id})'><i class="fa fa-eye"></i></button>
        <button class="btn btn-ghost btn-sm" title="Edit" onclick='Ads.openEdit(${ad.id})'><i class="fa fa-pen"></i></button>
        <button class="btn btn-danger btn-sm" title="Delete" onclick='Ads.remove(${ad.id})'><i class="fa fa-trash"></i></button>
      </div></td>
    </tr>`;
  }

  // ── Cache of loaded ads for edit/preview ──
  let _cache = {};
  async function fetchOne(id) {
    if (_cache[id]) return _cache[id];
    const res = await fetch("/api/v1/admin/ads");
    const data = await res.json();
    (data.ads || []).forEach((a) => { _cache[a.id] = a; });
    return _cache[id];
  }

  // ── Modal reset helpers ──
  function resetMedia() {
    $("adImageUrl").value = "";
    $("adMediaUrl").value = "";
    $("adDuration").value = "";
    $("adThumbnail").value = "";
    $("adMediaLink").value = "";
    $("adThumbLink").value = "";
    $("uploadPh").textContent = "Click to upload";
    $("thumbPh").textContent = "Click to upload poster";
  }

  function openCreate() {
    $("modalTitle").innerHTML = '<i class="fa fa-plus-circle"></i> New Advertisement';
    $("adId").value = "";
    $("adTitle").value = "";
    $("adType").value = "image";
    resetMedia();
    $("adRedirect").value = "";
    $("adPlatform").value = "website";
    syncPositions();
    $("adPriority").value = 0;
    $("adStart").value = "";
    $("adEnd").value = "";
    $("adActive").checked = true;
    syncType();
    $("modal").classList.add("open");
  }

  async function openEdit(id) {
    const ad = await fetchOne(id);
    if (!ad) { toast("Ad not found"); return; }
    $("modalTitle").innerHTML = '<i class="fa fa-pen"></i> Edit Advertisement';
    $("adId").value = ad.id;
    $("adTitle").value = ad.title || "";
    $("adType").value = ad.ad_type || "image";
    resetMedia();
    $("adImageUrl").value = ad.image_url || "";
    $("adMediaUrl").value = ad.media_url || "";
    $("adDuration").value = ad.duration || "";
    $("adThumbnail").value = ad.thumbnail || "";
    // Show the current media/poster link in the link boxes so it can be edited.
    $("adMediaLink").value = (ad.ad_type === "image" ? ad.image_url : ad.media_url) || "";
    $("adThumbLink").value = ad.thumbnail || "";
    $("adRedirect").value = ad.redirect_url || "";
    $("adPlatform").value = ad.platform || "website";
    syncPositions();
    $("adPosition").value = ad.position || "";
    $("adPriority").value = ad.priority || 0;
    $("adStart").value = ad.start_date || "";
    $("adEnd").value = ad.end_date || "";
    $("adActive").checked = !!ad.active;
    syncType();
    $("modal").classList.add("open");
  }

  function closeModal() { $("modal").classList.remove("open"); }

  // ── Save (create or update) ──
  async function save() {
    const id = $("adId").value;
    const type = currentType();
    const payload = {
      title: $("adTitle").value.trim(),
      advertisement_type: type,
      image_url: $("adImageUrl").value.trim(),
      media_url: $("adMediaUrl").value.trim(),
      thumbnail: $("adThumbnail").value.trim(),
      duration: $("adDuration").value ? parseInt($("adDuration").value, 10) : null,
      redirect_url: $("adRedirect").value.trim(),
      platform: $("adPlatform").value,
      position: $("adPosition").value,
      priority: parseInt($("adPriority").value || "0", 10),
      start_date: $("adStart").value,
      end_date: $("adEnd").value,
      active: $("adActive").checked,
    };
    if (!payload.title) { toast("Title is required"); return; }
    if (type !== "image" && !payload.media_url) { toast("Please upload the " + type + " file"); return; }

    $("saveBtn").disabled = true;
    const url = id ? `/api/v1/admin/ads/${id}` : "/api/v1/admin/ads";
    const method = id ? "PUT" : "POST";
    try {
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.success) {
        toast(id ? "Advertisement updated" : "Advertisement created");
        closeModal();
        _cache = {};
        load();
      } else {
        toast(data.error || "Save failed");
      }
    } catch (e) {
      toast("Save failed: " + e.message);
    } finally {
      $("saveBtn").disabled = false;
    }
  }

  async function remove(id) {
    if (!confirm("Delete this advertisement? This cannot be undone.")) return;
    try {
      const res = await fetch(`/api/v1/admin/ads/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (data.success) { toast("Deleted"); _cache = {}; load(); }
      else toast(data.error || "Delete failed");
    } catch (e) {
      toast("Delete failed: " + e.message);
    }
  }

  // ── Preview ──
  function mediaPreviewHtml(ad) {
    if (ad.ad_type === "video" && ad.media_url) {
      const poster = ad.thumbnail ? ` poster="${esc(ad.thumbnail)}"` : "";
      return `<video class="preview-img" src="${esc(ad.media_url)}"${poster} controls preload="metadata" style="width:100%"></video>`;
    }
    if (ad.ad_type === "audio" && ad.media_url) {
      return `<audio src="${esc(ad.media_url)}" controls preload="none" style="width:100%"></audio>`;
    }
    if (ad.image_url) return `<img class="preview-img" src="${esc(ad.image_url)}" alt="">`;
    return '<div class="empty">No media</div>';
  }

  async function preview(id) {
    const ad = await fetchOne(id);
    if (!ad) return;
    const dur = ad.duration ? ` • ${ad.duration}s` : "";
    $("previewBody").innerHTML = `
      ${mediaPreviewHtml(ad)}
      <div style="margin-top:12px;font-size:14px">
        <p><strong>${esc(ad.title)}</strong> <span class="badge badge-plat" style="margin-left:6px">${esc(ad.ad_type)}${dur}</span></p>
        <p style="color:#6b645b;font-size:13px;margin-top:6px">
          ${label(PLAT_LABELS, ad.platform)} • ${label(POS_LABELS, ad.position)} • Priority ${ad.priority}
        </p>
        <p style="font-size:13px;margin-top:6px">Redirect: ${ad.redirect_url ? `<a href="${esc(ad.redirect_url)}" target="_blank" rel="noopener">${esc(ad.redirect_url)}</a>` : "—"}</p>
        <p style="font-size:13px;margin-top:6px">${ad.impressions} impressions • ${ad.clicks} clicks • ${ad.ctr}% CTR</p>
      </div>`;
    $("previewModal").classList.add("open");
  }
  function closePreview() { $("previewModal").classList.remove("open"); }

  // Close modals on backdrop click
  document.addEventListener("click", (e) => {
    if (e.target.id === "modal") closeModal();
    if (e.target.id === "previewModal") closePreview();
  });

  // Expose
  window.Ads = {
    load, debouncedLoad, syncPositions, syncType, pickMedia,
    useMediaLink, useThumbLink, uploadMedia, uploadThumb,
    openCreate, openEdit, closeModal,
    save, remove, preview, closePreview,
  };

  // Init
  fillFilterPositions();
  syncPositions();
  syncType();
  load();
})();
