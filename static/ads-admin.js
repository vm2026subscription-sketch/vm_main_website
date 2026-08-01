/* Advertisements admin — CRUD, filters, preview, analytics.
   Image / Video / Audio types. Positions + their validation rules come from the
   Position Configuration API (/api/v1/positions) — nothing is hardcoded. */
(function () {
  "use strict";

  const PLAT_LABELS = { website: "Website", mobile: "Mobile App", both: "Both" };
  const TYPE_ICON = { image: "fa-image", video: "fa-video", audio: "fa-volume-up" };
  const TYPE_CFG = {
    image: { label: "Banner Image", accept: "image/jpeg,image/png,image/webp" },
    video: { label: "Video (MP4)", accept: "video/mp4" },
    audio: { label: "Audio", accept: "audio/mpeg,audio/aac,audio/wav,.mp3,.aac,.wav" },
  };

  // Loaded from the Position Configuration API.
  let POS_CFG = {};   // slug -> config
  let POS_NAME = {};  // slug -> display name

  const $ = (id) => document.getElementById(id);
  let _debounceTimer = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }
  function posName(slug) { return POS_NAME[slug] || slug || "—"; }
  function platLabel(p) { return PLAT_LABELS[p] || p; }
  function toast(msg) {
    const t = $("toast"); t.textContent = msg; t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 2800);
  }

  // ── Load positions (config for the whole page) ──
  async function loadPositions() {
    try {
      const res = await fetch("/api/v1/positions");
      const data = await res.json();
      POS_CFG = {}; POS_NAME = {};
      (data.positions || []).forEach((p) => { POS_CFG[p.slug] = p; POS_NAME[p.slug] = p.name; });
    } catch (e) { /* leave empty */ }
    fillFilterPositions();
  }

  function fillFilterPositions() {
    const sel = $("fPosition");
    const slugs = Object.keys(POS_CFG);
    sel.innerHTML = '<option value="">All</option>' +
      slugs.map((s) => `<option value="${s}">${esc(posName(s))}</option>`).join("");
  }

  // ── Form: positions for the selected platform (exact platform match) ──
  function syncPositions() {
    const plat = $("adPlatform").value;
    const list = Object.values(POS_CFG)
      .filter((p) => p.platform === plat && p.is_active)
      .sort((a, b) => a.name.localeCompare(b.name));
    const current = $("adPosition").value;
    $("adPosition").innerHTML = '<option value="">— select —</option>' +
      list.map((p) => `<option value="${p.slug}">${esc(p.name)}</option>`).join("");
    if (list.some((p) => p.slug === current)) $("adPosition").value = current;
    onPositionChange();
  }

  function currentType() { return $("adType").value || "image"; }
  function currentCfg() { return POS_CFG[$("adPosition").value] || null; }
  function mediaUrlOf(type) {
    return (type === "image" ? $("adImageUrl").value : $("adMediaUrl").value) || "";
  }

  // Restrict the Type dropdown to the position's allowed types.
  function rebuildTypeOptions() {
    const cfg = currentCfg();
    const allowed = (cfg && cfg.allowed_types && cfg.allowed_types.length) ? cfg.allowed_types : ["image", "video", "audio"];
    const cur = $("adType").value;
    const names = { image: "Image", video: "Video", audio: "Audio" };
    $("adType").innerHTML = allowed.map((t) => `<option value="${t}">${names[t]}</option>`).join("");
    $("adType").value = allowed.includes(cur) ? cur : allowed[0];
  }

  function onPositionChange() {
    rebuildTypeOptions();
    renderPosConfig();
    syncType();
  }

  function renderPosConfig() {
    const cfg = currentCfg();
    const box = $("posConfig");
    if (!cfg) { box.style.display = "none"; box.innerHTML = ""; return; }
    const dur = [];
    if (cfg.max_video_duration) dur.push(`Video ≤ ${cfg.max_video_duration}s`);
    if (cfg.max_audio_duration) dur.push(`Audio ≤ ${cfg.max_audio_duration}s`);
    const item = (k, v) => `<div class="pc-item"><span class="pc-k">${k}</span><span class="pc-v">${v}</span></div>`;
    box.innerHTML = `<div class="pc-grid">
      ${item("Recommended", cfg.resolution || "—")}
      ${item("Aspect Ratio", esc(cfg.aspect_ratio || "—"))}
      ${item("Allowed Types", (cfg.allowed_types || []).join(", ") || "—")}
      ${item("Allowed Formats", (cfg.allowed_formats || []).join(", ").toUpperCase() || "—")}
      ${item("Max File Size", cfg.max_file_size_mb ? cfg.max_file_size_mb + " MB" : "—")}
      ${item("Max Duration", dur.join(" · ") || "—")}
      ${item("Validation", cfg.validation_enabled ? '<span class="pc-v">ON</span>' : '<span class="pc-off">OFF (warnings only)</span>')}
    </div>`;
    box.style.display = "block";
  }

  function syncType() {
    const type = currentType();
    $("mediaLabel").textContent = TYPE_CFG[type].label;
    $("adMediaFile").setAttribute("accept", TYPE_CFG[type].accept);
    $("thumbRow").style.display = type === "video" ? "" : "none";
    updateMediaHint();
    renderMediaPreview();
  }

  function updateMediaHint() {
    const type = currentType();
    const cfg = currentCfg();
    let h = "";
    if (type === "audio") h = "Audio file.";
    else if (type === "video") h = "Video, plays with controls (no autoplay).";
    else h = "Image banner.";
    if (cfg) {
      const fmts = (cfg.allowed_formats || []).join(", ").toUpperCase();
      if (cfg.resolution && type === "image") h += ` Recommended ${cfg.resolution}px.`;
      if (fmts) h += ` Allowed: ${fmts}.`;
      if (cfg.max_file_size_mb) h += ` Max ${cfg.max_file_size_mb} MB.`;
    }
    $("mediaHint").textContent = h;
  }

  function pickMedia() { $("adMediaFile").click(); }

  function useMediaLink() {
    const url = $("adMediaLink").value.trim();
    const type = currentType();
    if (type === "image") { $("adImageUrl").value = url; $("adMediaUrl").value = ""; }
    else { $("adMediaUrl").value = url; $("adDuration").value = ""; }
    renderMediaPreview();
  }
  function useThumbLink() { $("adThumbnail").value = $("adThumbLink").value.trim(); renderMediaPreview(); }

  function renderMediaPreview() {
    const type = currentType();
    const url = mediaUrlOf(type);
    const img = $("uploadPreview"), vid = $("uploadVideoPrev"), aud = $("uploadAudioPrev"), ph = $("uploadPh");
    img.style.display = vid.style.display = aud.style.display = "none";
    try { vid.pause(); aud.pause(); } catch (e) {}
    if (!url) { ph.style.display = "block"; }
    else if (type === "image") {
      img.src = url; img.style.display = "block"; ph.style.display = "none";
      img.onload = function () { showMetaClient({ width: img.naturalWidth, height: img.naturalHeight }, "image"); };
    } else if (type === "video") {
      vid.src = url;
      const poster = $("adThumbnail").value; if (poster) vid.setAttribute("poster", poster);
      vid.onloadedmetadata = function () {
        if (isFinite(vid.duration) && vid.duration > 0) $("adDuration").value = Math.round(vid.duration);
        showMetaClient({ width: vid.videoWidth, height: vid.videoHeight, duration: Math.round(vid.duration || 0) }, "video");
      };
      vid.style.display = "block"; ph.style.display = "none";
    } else {
      aud.src = url;
      aud.onloadedmetadata = function () {
        if (isFinite(aud.duration) && aud.duration > 0) $("adDuration").value = Math.round(aud.duration);
        showMetaClient({ duration: Math.round(aud.duration || 0) }, "audio");
      };
      aud.style.display = "block"; ph.style.display = "none";
    }
    const thumb = $("adThumbnail").value;
    if (thumb) { $("thumbPreview").src = thumb; $("thumbPreview").style.display = "block"; $("thumbPh").style.display = "none"; }
    else { $("thumbPreview").style.display = "none"; $("thumbPh").style.display = "block"; }
  }

  // Show media metadata + match status (from client-read values, e.g. links).
  function showMetaClient(meta, type) {
    const cfg = currentCfg();
    let match = true;
    const parts = [];
    if (meta.width && meta.height) {
      parts.push(`<span class="mm-chip">${meta.width}×${meta.height}px</span>`);
      if (cfg && cfg.rec_width && cfg.rec_height && (meta.width !== cfg.rec_width || meta.height !== cfg.rec_height)) match = false;
    }
    if (meta.duration) {
      parts.push(`<span class="mm-chip">${meta.duration}s</span>`);
      const lim = type === "video" ? (cfg && cfg.max_video_duration) : (cfg && cfg.max_audio_duration);
      if (lim && meta.duration > lim) parts.push(`<span class="mm-warn">exceeds ${lim}s limit</span>`);
    }
    let status = "";
    if (type === "image" && cfg && cfg.rec_width) {
      status = match ? '<span class="mm-ok">✓ Matches recommended</span>' : '<span class="mm-warn">⚠ Different resolution</span>';
    }
    $("mediaMeta").innerHTML = parts.length || status
      ? `<div class="mm-row">${parts.join(" ")} ${status}</div>` : "";
  }

  // Show media metadata after a server upload (authoritative).
  function showMetaServer(data, type) {
    const parts = [];
    if (data.width && data.height) parts.push(`<span class="mm-chip">${data.width}×${data.height}px</span>`);
    if (data.size_mb) parts.push(`<span class="mm-chip">${data.size_mb} MB</span>`);
    if (data.format) parts.push(`<span class="mm-chip">${String(data.format).toUpperCase()}</span>`);
    if (data.duration) parts.push(`<span class="mm-chip">${data.duration}s</span>`);
    let status = "";
    if (type === "image" && currentCfg() && currentCfg().rec_width) {
      status = data.match ? '<span class="mm-ok">✓ Matches recommended</span>' : '<span class="mm-warn">⚠ Different resolution</span>';
    }
    const warns = (data.warnings || []).map((w) => `<div class="mm-warn">⚠ ${esc(w)}</div>`).join("");
    $("mediaMeta").innerHTML = `<div class="mm-row">${parts.join(" ")} ${status}</div>${warns}`;
  }

  async function uploadMedia(input) {
    const file = input.files[0];
    if (!file) return;
    const type = currentType();
    $("uploadPh").textContent = "Uploading…"; $("uploadPh").style.display = "block";
    ["uploadPreview", "uploadVideoPrev", "uploadAudioPrev"].forEach((id) => { $(id).style.display = "none"; });
    const fd = new FormData();
    fd.append("file", file);
    fd.append("type", type);
    fd.append("position", $("adPosition").value || "");   // drives server-side validation
    try {
      const res = await fetch("/api/v1/admin/ads/upload", { method: "POST", body: fd });
      const data = await res.json();
      if (data.success && data.url) {
        if (type === "image") { $("adImageUrl").value = data.url; $("adMediaUrl").value = ""; }
        else {
          $("adMediaUrl").value = data.url;
          $("adDuration").value = data.duration || "";
          if (data.thumbnail && !$("adThumbnail").value) { $("adThumbnail").value = data.thumbnail; $("adThumbLink").value = data.thumbnail; }
        }
        $("adMediaLink").value = data.url;
        renderMediaPreview();
        showMetaServer(data, type);
      } else {
        toast(data.error || "Upload rejected");
        $("uploadPh").textContent = "Click to upload";
        if (data.error) $("mediaMeta").innerHTML = `<div class="mm-warn">✕ ${esc(data.error)}</div>`;
      }
    } catch (e) {
      toast("Upload failed: " + e.message);
      $("uploadPh").textContent = "Click to upload";
    } finally { input.value = ""; }
  }

  async function uploadThumb(input) {
    const file = input.files[0];
    if (!file) return;
    $("thumbPh").textContent = "Uploading…";
    const fd = new FormData();
    fd.append("file", file); fd.append("type", "image");
    try {
      const res = await fetch("/api/v1/admin/ads/upload", { method: "POST", body: fd });
      const data = await res.json();
      if (data.success && data.url) { $("adThumbnail").value = data.url; $("adThumbLink").value = data.url; renderMediaPreview(); }
      else { toast(data.error || "Upload failed"); $("thumbPh").textContent = "Click to upload poster"; }
    } catch (e) { toast("Upload failed: " + e.message); $("thumbPh").textContent = "Click to upload poster"; }
    finally { input.value = ""; }
  }

  // ── List + analytics ──
  let _cache = {};
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
      const ads = data.ads || []; const t = data.totals || {};
      $("statTotal").textContent = t.count || 0;
      $("statImpr").textContent = (t.impressions || 0).toLocaleString();
      $("statClicks").textContent = (t.clicks || 0).toLocaleString();
      $("statCtr").textContent = (t.ctr || 0) + "%";
      ads.forEach((a) => { _cache[a.id] = a; });
      tbody.innerHTML = ads.length ? ads.map(rowHtml).join("")
        : '<tr><td colspan="12" class="empty">No advertisements found.</td></tr>';
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="12" class="empty">Failed to load. ' + esc(e.message) + "</td></tr>";
    }
  }
  function debouncedLoad() { clearTimeout(_debounceTimer); _debounceTimer = setTimeout(load, 300); }

  function statusBadge(s) {
    const cls = { active: "badge-active", inactive: "badge-inactive", expired: "badge-expired", scheduled: "badge-scheduled" }[s] || "badge-inactive";
    return `<span class="badge ${cls}">${esc(s)}</span>`;
  }
  function fmtDate(d) { return d ? esc(d) : "—"; }
  function typeThumb(ad) {
    const src = ad.thumbnail || (ad.ad_type === "image" ? ad.image_url : "");
    if (src) return `<img class="thumb" src="${esc(src)}" loading="lazy" alt="">`;
    return `<div class="thumb" style="display:flex;align-items:center;justify-content:center;color:#bbb"><i class="fa ${TYPE_ICON[ad.ad_type] || "fa-image"}"></i></div>`;
  }
  function rowHtml(ad) {
    const dates = (ad.start_date || ad.end_date) ? `${fmtDate(ad.start_date)} → ${fmtDate(ad.end_date)}` : "Always";
    const lastShown = ad.last_displayed_at ? esc(ad.last_displayed_at.replace("T", " ").slice(0, 16)) : "—";
    const typeIcon = `<i class="fa ${TYPE_ICON[ad.ad_type] || "fa-image"}" title="${esc(ad.ad_type)}" style="color:#9a938a;margin-right:6px"></i>`;
    return `<tr>
      <td>${typeThumb(ad)}</td>
      <td>${typeIcon}<strong>${esc(ad.title)}</strong></td>
      <td><span class="badge badge-plat">${platLabel(ad.platform)}</span></td>
      <td>${esc(posName(ad.position))}</td>
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
      </div></td></tr>`;
  }

  async function fetchOne(id) {
    if (_cache[id]) return _cache[id];
    const res = await fetch("/api/v1/admin/ads");
    const data = await res.json();
    (data.ads || []).forEach((a) => { _cache[a.id] = a; });
    return _cache[id];
  }

  function resetMedia() {
    ["adImageUrl", "adMediaUrl", "adDuration", "adThumbnail", "adMediaLink", "adThumbLink"].forEach((id) => { $(id).value = ""; });
    $("uploadPh").textContent = "Click to upload"; $("thumbPh").textContent = "Click to upload poster";
    $("mediaMeta").innerHTML = "";
  }

  function openCreate() {
    $("modalTitle").innerHTML = '<i class="fa fa-plus-circle"></i> New Advertisement';
    $("adId").value = ""; $("adTitle").value = "";
    resetMedia();
    $("adRedirect").value = "";
    $("adPlatform").value = "website";
    syncPositions();
    $("adPriority").value = 0; $("adStart").value = ""; $("adEnd").value = ""; $("adActive").checked = true;
    $("modal").classList.add("open");
  }

  async function openEdit(id) {
    const ad = await fetchOne(id);
    if (!ad) { toast("Ad not found"); return; }
    $("modalTitle").innerHTML = '<i class="fa fa-pen"></i> Edit Advertisement';
    $("adId").value = ad.id; $("adTitle").value = ad.title || "";
    resetMedia();
    $("adPlatform").value = ad.platform || "website";
    syncPositions();
    $("adPosition").value = ad.position || "";
    onPositionChange();
    $("adType").value = ad.ad_type || "image";
    $("adImageUrl").value = ad.image_url || "";
    $("adMediaUrl").value = ad.media_url || "";
    $("adDuration").value = ad.duration || "";
    $("adThumbnail").value = ad.thumbnail || "";
    $("adMediaLink").value = (ad.ad_type === "image" ? ad.image_url : ad.media_url) || "";
    $("adThumbLink").value = ad.thumbnail || "";
    $("adRedirect").value = ad.redirect_url || "";
    $("adPriority").value = ad.priority || 0;
    $("adStart").value = ad.start_date || ""; $("adEnd").value = ad.end_date || "";
    $("adActive").checked = !!ad.active;
    syncType();
    $("modal").classList.add("open");
  }
  function closeModal() { $("modal").classList.remove("open"); }

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
      start_date: $("adStart").value, end_date: $("adEnd").value,
      active: $("adActive").checked,
    };
    if (!payload.title) { toast("Title is required"); return; }
    if (type !== "image" && !payload.media_url) { toast("Please add the " + type + " file/link"); return; }
    $("saveBtn").disabled = true;
    const url = id ? `/api/v1/admin/ads/${id}` : "/api/v1/admin/ads";
    try {
      const res = await fetch(url, { method: id ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const data = await res.json();
      if (data.success) { toast(id ? "Advertisement updated" : "Advertisement created"); closeModal(); _cache = {}; load(); }
      else toast(data.error || "Save failed");
    } catch (e) { toast("Save failed: " + e.message); }
    finally { $("saveBtn").disabled = false; }
  }

  async function remove(id) {
    if (!confirm("Delete this advertisement? This cannot be undone.")) return;
    try {
      const res = await fetch(`/api/v1/admin/ads/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (data.success) { toast("Deleted"); _cache = {}; load(); } else toast(data.error || "Delete failed");
    } catch (e) { toast("Delete failed: " + e.message); }
  }

  function mediaPreviewHtml(ad) {
    if (ad.ad_type === "video" && ad.media_url) {
      const poster = ad.thumbnail ? ` poster="${esc(ad.thumbnail)}"` : "";
      return `<video class="preview-img" src="${esc(ad.media_url)}"${poster} controls preload="metadata" style="width:100%"></video>`;
    }
    if (ad.ad_type === "audio" && ad.media_url) return `<audio src="${esc(ad.media_url)}" controls preload="none" style="width:100%"></audio>`;
    if (ad.image_url) return `<img class="preview-img" src="${esc(ad.image_url)}" alt="">`;
    return '<div class="empty">No media</div>';
  }
  async function preview(id) {
    const ad = await fetchOne(id); if (!ad) return;
    const dur = ad.duration ? ` • ${ad.duration}s` : "";
    $("previewBody").innerHTML = `${mediaPreviewHtml(ad)}
      <div style="margin-top:12px;font-size:14px">
        <p><strong>${esc(ad.title)}</strong> <span class="badge badge-plat" style="margin-left:6px">${esc(ad.ad_type)}${dur}</span></p>
        <p style="color:#6b645b;font-size:13px;margin-top:6px">${platLabel(ad.platform)} • ${esc(posName(ad.position))} • Priority ${ad.priority}</p>
        <p style="font-size:13px;margin-top:6px">Redirect: ${ad.redirect_url ? `<a href="${esc(ad.redirect_url)}" target="_blank" rel="noopener">${esc(ad.redirect_url)}</a>` : "—"}</p>
        <p style="font-size:13px;margin-top:6px">${ad.impressions} impressions • ${ad.clicks} clicks • ${ad.ctr}% CTR</p>
      </div>`;
    $("previewModal").classList.add("open");
  }
  function closePreview() { $("previewModal").classList.remove("open"); }

  document.addEventListener("click", (e) => {
    if (e.target.id === "modal") closeModal();
    if (e.target.id === "previewModal") closePreview();
  });

  window.Ads = {
    load, debouncedLoad, syncPositions, onPositionChange, syncType, updateMediaHint,
    pickMedia, useMediaLink, useThumbLink, uploadMedia, uploadThumb,
    openCreate, openEdit, closeModal, save, remove, preview, closePreview,
  };

  // Init: positions first (drives labels + form), then the ads list.
  loadPositions().then(() => { syncPositions(); load(); });
})();
