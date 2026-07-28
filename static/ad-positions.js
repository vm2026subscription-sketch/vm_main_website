/* Advertisement Position Configuration — CRUD + activate/deactivate.
   All dimensions & validation rules live in the DB; this page manages them. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const PLAT = { website: "Website", mobile: "Mobile App", both: "Both" };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }
  function toast(m) { const t = $("toast"); t.textContent = m; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 2800); }

  let _cache = {};

  async function load() {
    const tb = $("posRows");
    try {
      const res = await fetch("/api/v1/admin/positions");
      if (res.status === 401) { location.href = "/epaper-admin/login"; return; }
      const data = await res.json();
      const rows = data.positions || [];
      _cache = {}; rows.forEach((p) => { _cache[p.id] = p; });
      tb.innerHTML = rows.length ? rows.map(rowHtml).join("")
        : '<tr><td colspan="9" class="empty">No positions yet.</td></tr>';
    } catch (e) {
      tb.innerHTML = '<tr><td colspan="9" class="empty">Failed to load. ' + esc(e.message) + "</td></tr>";
    }
  }

  function rowHtml(p) {
    const types = (p.allowed_types || []).map((t) => `<span class="badge badge-type">${esc(t)}</span>`).join(" ");
    const val = p.validation_enabled ? '<span class="badge badge-on">ON</span>' : '<span class="badge badge-off">OFF</span>';
    const st = p.is_active ? '<span class="badge badge-on">Active</span>' : '<span class="badge badge-off">Inactive</span>';
    const toggleLabel = p.is_active ? "Deactivate" : "Activate";
    const toggleIcon = p.is_active ? "fa-toggle-off" : "fa-toggle-on";
    const delDisabled = p.in_use ? "disabled title='In use by ads — cannot delete'" : "title='Delete'";
    return `<tr>
      <td><span class="badge badge-plat">${PLAT[p.platform] || p.platform}</span></td>
      <td><strong>${esc(p.name)}</strong><br><span style="font-size:11px;color:#9a938a">${esc(p.slug)}</span></td>
      <td>${p.resolution || "—"}</td>
      <td>${esc(p.aspect_ratio || "—")}</td>
      <td>${types || "—"}</td>
      <td>${p.max_file_size_mb ? p.max_file_size_mb + " MB" : "—"}</td>
      <td>${val}</td>
      <td>${st}</td>
      <td><div class="actions">
        <button class="btn btn-ghost btn-sm" onclick="Pos.toggle(${p.id})" title="${toggleLabel}"><i class="fa ${toggleIcon}"></i></button>
        <button class="btn btn-ghost btn-sm" onclick="Pos.openEdit(${p.id})" title="Edit"><i class="fa fa-pen"></i></button>
        <button class="btn btn-danger btn-sm" onclick="Pos.remove(${p.id})" ${delDisabled}><i class="fa fa-trash"></i></button>
      </div></td></tr>`;
  }

  function autoRatio() {
    const w = parseInt($("pWidth").value, 10), h = parseInt($("pHeight").value, 10);
    if (w > 0 && h > 0 && !$("pRatio").dataset.touched) {
      const g = gcd(w, h);
      $("pRatio").value = `${w / g}:${h / g}`;
    }
  }
  function gcd(a, b) { return b ? gcd(b, a % b) : a; }

  function getChecks(containerId) {
    return Array.from($(containerId).querySelectorAll("input:checked")).map((c) => c.value);
  }
  function setChecks(containerId, values) {
    const set = new Set(values || []);
    $(containerId).querySelectorAll("input").forEach((c) => { c.checked = set.has(c.value); });
  }

  function openCreate() {
    $("modalTitle").innerHTML = '<i class="fa fa-plus-circle"></i> New Position';
    $("pId").value = ""; $("pName").value = ""; $("pPlatform").value = "website";
    $("pWidth").value = ""; $("pHeight").value = ""; $("pRatio").value = ""; delete $("pRatio").dataset.touched;
    setChecks("pTypes", ["image"]); setChecks("pFormats", []);
    $("pMaxSize").value = 25; $("pMaxVideo").value = ""; $("pMaxAudio").value = "";
    $("pValidation").checked = true; $("pActive").checked = true;
    $("modal").classList.add("open");
  }

  function openEdit(id) {
    const p = _cache[id]; if (!p) return;
    $("modalTitle").innerHTML = '<i class="fa fa-pen"></i> Edit Position';
    $("pId").value = p.id; $("pName").value = p.name || ""; $("pPlatform").value = p.platform || "website";
    $("pWidth").value = p.rec_width || ""; $("pHeight").value = p.rec_height || "";
    $("pRatio").value = p.aspect_ratio || ""; $("pRatio").dataset.touched = "1";
    setChecks("pTypes", p.allowed_types); setChecks("pFormats", p.allowed_formats);
    $("pMaxSize").value = p.max_file_size_mb || "";
    $("pMaxVideo").value = p.max_video_duration || ""; $("pMaxAudio").value = p.max_audio_duration || "";
    $("pValidation").checked = !!p.validation_enabled; $("pActive").checked = !!p.is_active;
    $("modal").classList.add("open");
  }
  function closeModal() { $("modal").classList.remove("open"); }

  async function save() {
    const id = $("pId").value;
    const payload = {
      name: $("pName").value.trim(),
      platform: $("pPlatform").value,
      rec_width: $("pWidth").value ? parseInt($("pWidth").value, 10) : null,
      rec_height: $("pHeight").value ? parseInt($("pHeight").value, 10) : null,
      aspect_ratio: $("pRatio").value.trim(),
      allowed_types: getChecks("pTypes"),
      allowed_formats: getChecks("pFormats"),
      max_file_size_mb: $("pMaxSize").value ? parseInt($("pMaxSize").value, 10) : null,
      max_video_duration: $("pMaxVideo").value ? parseInt($("pMaxVideo").value, 10) : null,
      max_audio_duration: $("pMaxAudio").value ? parseInt($("pMaxAudio").value, 10) : null,
      validation_enabled: $("pValidation").checked,
      is_active: $("pActive").checked,
    };
    if (!payload.name) { toast("Position name is required"); return; }
    if (!payload.allowed_types.length) { toast("Select at least one advertisement type"); return; }
    $("saveBtn").disabled = true;
    const url = id ? `/api/v1/admin/positions/${id}` : "/api/v1/admin/positions";
    try {
      const res = await fetch(url, { method: id ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const data = await res.json();
      if (data.success) { toast(id ? "Position updated" : "Position created"); closeModal(); load(); }
      else toast(data.error || "Save failed");
    } catch (e) { toast("Save failed: " + e.message); }
    finally { $("saveBtn").disabled = false; }
  }

  async function toggle(id) {
    try {
      const res = await fetch(`/api/v1/admin/positions/${id}/toggle`, { method: "POST" });
      const data = await res.json();
      if (data.success) load(); else toast(data.error || "Failed");
    } catch (e) { toast("Failed: " + e.message); }
  }

  async function remove(id) {
    if (!confirm("Delete this position? Only allowed if no ad uses it.")) return;
    try {
      const res = await fetch(`/api/v1/admin/positions/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (data.success) { toast("Deleted"); load(); } else toast(data.error || "Delete failed");
    } catch (e) { toast("Delete failed: " + e.message); }
  }

  // Mark ratio as manually edited so autoRatio stops overwriting it.
  document.addEventListener("input", (e) => { if (e.target.id === "pRatio") e.target.dataset.touched = "1"; });
  document.addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

  window.Pos = { load, openCreate, openEdit, closeModal, save, toggle, remove, autoRatio };
  load();
})();
