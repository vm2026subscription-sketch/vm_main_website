function riskClass(label) {
  return String(label || "").toLowerCase().replace(/\s+/g, "-");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatNumber(value, digits = 2) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "N/A";
  return numeric.toFixed(digits);
}

function renderResultsTable(recommendations, startIndex = 1) {
  const tbody = document.getElementById("resultsTableBody");
  if (!tbody) return;

  if (!recommendations.length) {
    tbody.innerHTML = '<tr><td colspan="13" class="empty-table-cell">No colleges found for this selection.</td></tr>';
    return;
  }

  tbody.innerHTML = recommendations.map((college, index) => {
    const website = college.website
      ? `<a href="${escapeHtml(college.website)}" target="_blank" rel="noopener">Visit</a>`
      : '<span class="muted-cell">N/A</span>';

    return `
      <tr>
        <td>${startIndex + index}</td>
        <td>
          <strong>${escapeHtml(college.college || "College")}</strong>
          <span>${escapeHtml(college.college_code || "N/A")}</span>
        </td>
        <td>${escapeHtml(college.branch || "-")}</td>
        <td>${escapeHtml(college.category || "-")}</td>
        <td>${escapeHtml(college.gender_label || college.gender || "-")}</td>
        <td>${formatNumber(college.final_cutoff)}</td>
        <td>${college.cap_1_cutoff === null || college.cap_1_cutoff === undefined ? "-" : formatNumber(college.cap_1_cutoff)}</td>
        <td>${college.cap_2_cutoff === null || college.cap_2_cutoff === undefined ? "-" : formatNumber(college.cap_2_cutoff)}</td>
        <td>${college.cap_3_cutoff === null || college.cap_3_cutoff === undefined ? "-" : formatNumber(college.cap_3_cutoff)}</td>
        <td>${college.cap_4_cutoff === null || college.cap_4_cutoff === undefined ? "-" : formatNumber(college.cap_4_cutoff)}</td>
        <td>${college.gap === null || college.gap === undefined ? "-" : formatNumber(college.gap)}</td>
        <td>${college.best_rank || "N/A"}</td>
        <td>${website}</td>
      </tr>
    `;
  }).join("");
}

function renderPagination(pagination, onPageChange) {
  const nav = document.getElementById("predictorPagination");
  if (!nav) return;

  if (!pagination || pagination.total_pages <= 1) {
    nav.hidden = true;
    nav.innerHTML = "";
    return;
  }

  nav.hidden = false;
  const page = Number(pagination.page || 1);
  const totalPages = Number(pagination.total_pages || 1);
  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);
  const pageButtons = [];

  for (let current = start; current <= end; current += 1) {
    pageButtons.push(`<button type="button" class="${current === page ? "active" : ""}" data-page="${current}">${current}</button>`);
  }

  nav.innerHTML = `
    <button type="button" ${page <= 1 ? "disabled" : ""} data-page="${page - 1}">Previous</button>
    ${start > 1 ? '<span class="pagination-ellipsis">...</span>' : ''}
    ${pageButtons.join("")}
    ${end < totalPages ? '<span class="pagination-ellipsis">...</span>' : ''}
    <button type="button" ${page >= totalPages ? "disabled" : ""} data-page="${page + 1}">Next</button>
  `;

  nav.querySelectorAll("button[data-page]").forEach((button) => {
    button.addEventListener("click", () => onPageChange(Number(button.dataset.page)));
  });
}

function setPaymentCta(visible) {
  const cta = document.getElementById("paymentCta");
  if (cta) cta.hidden = !visible;
}

function loadRazorpayCheckout() {
  if (window.Razorpay) return Promise.resolve();

  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      if (window.Razorpay) {
        resolve();
        return;
      }
      reject(new Error("Razorpay checkout could not load. Please check your internet connection and try again."));
    }, 10000);
    const finish = () => {
      window.clearTimeout(timeout);
      if (window.Razorpay) {
        resolve();
        return;
      }
      reject(new Error("Razorpay checkout could not load. Please check your internet connection and try again."));
    };
    const existingScript = document.querySelector('script[src="https://checkout.razorpay.com/v1/checkout.js"]');
    if (existingScript) {
      existingScript.addEventListener("load", finish, { once: true });
      existingScript.addEventListener("error", finish, { once: true });
      if (existingScript.dataset.loaded === "true" || existingScript.readyState === "complete") {
        finish();
      }
      return;
    }

    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => {
      script.dataset.loaded = "true";
      finish();
    };
    script.onerror = finish;
    document.head.appendChild(script);
  });
}

function setActiveTab(tabName) {
  document.querySelectorAll("[data-tab-panel]").forEach((panel) => {
    const isActive = panel.dataset.tabPanel === tabName;
    panel.hidden = !isActive;
    panel.classList.toggle("active", isActive);
  });

  document.querySelectorAll("[data-tab-trigger]").forEach((trigger) => {
    trigger.classList.toggle("active", trigger.dataset.tabTrigger === tabName);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("collegePredictorForm");
  const top20Form = document.getElementById("top20FilterForm");
  const alertBox = document.getElementById("predictorAlert");
  const title = document.getElementById("resultsTitle");
  const meta = document.getElementById("resultsMeta");
  const unlockButton = document.getElementById("unlockFullListBtn");
  const paymentStatus = document.getElementById("paymentStatus");
  let lastPayload = null;
  let lastTop20Filters = {};
  let top20Loaded = false;

  function showAlert(message) {
    if (!alertBox) return;
    alertBox.textContent = message || "Unable to load results.";
    alertBox.hidden = false;
    alertBox.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function clearAlert() {
    if (!alertBox) return;
    alertBox.hidden = true;
    alertBox.textContent = "";
  }

  function setPaymentStatus(message) {
    if (!paymentStatus) return;
    paymentStatus.textContent = message || "";
  }

  function setUnlockButtonLoading(isLoading, label = "Unlock for ₹100") {
    if (!unlockButton) return;
    unlockButton.disabled = isLoading;
    unlockButton.textContent = label;
  }

  async function fetchTop20() {
    if (!top20Form) return;
    const button = top20Form.querySelector('button[type="submit"]');
    const payload = Object.fromEntries(new FormData(top20Form).entries());
    lastTop20Filters = payload;
    clearAlert();
    renderPagination(null, fetchPrediction);
    setPaymentCta(false);

    if (button) {
      button.disabled = true;
      button.textContent = "Loading top 20...";
    }

    try {
      const response = await fetch("/api/top-cutoff-colleges", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();

      if (!result.success) {
        showAlert(result.error);
        renderResultsTable([]);
        return;
      }

      renderResultsTable(result.recommendations || []);
      setPaymentCta(Boolean(result.locked_full_list));
      if (title) title.textContent = "Top 20 Colleges";
      if (meta) {
        const filters = [];
        if (result.filters?.branch) filters.push(result.filters.branch);
        if (result.filters?.category) filters.push(result.filters.category);
        if (result.filters?.gender_label) filters.push(result.filters.gender_label);
        meta.textContent = filters.length
          ? `Highest to lowest cutoff for ${filters.join(", ")}. Showing free top 20.`
          : "Highest to lowest cutoff across available B.Tech CAP data. Showing free top 20.";
      }
      top20Loaded = true;
      document.getElementById("top-colleges")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      showAlert("Something went wrong while loading top 20 colleges.");
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = "Show Top 20";
      }
    }
  }

  async function fetchFullCutoffList(page = 1) {
    const payload = {
      ...lastTop20Filters,
      page,
      per_page: 100,
    };
    clearAlert();

    try {
      const response = await fetch("/api/full-cutoff-colleges", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();

      if (!result.success) {
        showAlert(result.error || "Unable to load full cutoff list.");
        return;
      }

      const pagination = result.pagination || {};
      const currentPage = Number(pagination.page || 1);
      const perPage = Number(pagination.per_page || 100);
      const start = result.total_matches ? ((currentPage - 1) * perPage) + 1 : 1;
      renderResultsTable(result.recommendations || [], start);
      renderPagination(result.pagination, fetchFullCutoffList);
      setPaymentCta(false);
      if (title) title.textContent = "Full Cutoff List";
      if (meta) {
        const end = Math.min(currentPage * perPage, result.total_matches || 0);
        meta.textContent = `Unlocked list: showing ${start}-${end} of ${result.total_matches} cutoff rows from all available CAP rounds.`;
      }
    } catch (error) {
      showAlert("Something went wrong while loading the full cutoff list.");
    }
  }

  async function startRazorpayUnlock() {
    clearAlert();
    setPaymentStatus("Preparing secure checkout...");
    setUnlockButtonLoading(true, "Creating order...");

    try {
      await loadRazorpayCheckout();

      if (!window.Razorpay) {
        throw new Error("Razorpay checkout did not load.");
      }

      const orderResponse = await fetch("/api/cutoff-payment/order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(lastTop20Filters || {}),
      });
      const orderResult = await orderResponse.json();

      if (!orderResult.success) {
        showAlert(orderResult.error || "Unable to create Razorpay order.");
        setPaymentStatus("Order creation failed.");
        return;
      }

      setPaymentStatus("Opening Razorpay checkout...");
      setUnlockButtonLoading(true, "Checkout open...");

      const options = {
        key: orderResult.key_id,
        amount: orderResult.order.amount,
        currency: orderResult.order.currency || "INR",
        name: "Vidyarthi Mitra",
        description: "Full cutoff list access",
        order_id: orderResult.order.id,
        theme: { color: "#ff6600" },
        handler: async function (response) {
          setPaymentStatus("Verifying payment...");
          setUnlockButtonLoading(true, "Verifying...");
          const verifyResponse = await fetch("/api/cutoff-payment/verify", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(response),
          });
          const verifyResult = await verifyResponse.json();

          if (!verifyResult.success) {
            showAlert(verifyResult.error || "Payment verification failed.");
            setPaymentStatus("Payment verification failed.");
            setUnlockButtonLoading(false);
            return;
          }

          setPaymentStatus("Payment verified. Loading full list...");
          await fetchFullCutoffList(1);
          setPaymentStatus("");
        },
        modal: {
          ondismiss: function () {
            setUnlockButtonLoading(false);
            setPaymentStatus("Checkout closed before payment.");
          },
        },
      };

      const checkout = new window.Razorpay(options);
      checkout.open();
    } catch (error) {
      showAlert(error?.message || "Something went wrong while starting Razorpay checkout.");
      setPaymentStatus("Checkout could not start.");
      setUnlockButtonLoading(false);
    }
  }

  async function fetchPrediction(page = 1) {
    if (!form) return;
    const button = form.querySelector('button[type="submit"]');
    const formData = new FormData(form);
    const payload = Object.fromEntries(formData.entries());
    payload.page = page;
    lastPayload = payload;
    clearAlert();
    setPaymentCta(false);

    if (button) {
      button.disabled = true;
      button.textContent = "Finding colleges...";
    }

    try {
      const response = await fetch("/api/college-predictor", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();

      if (!result.success) {
        showAlert(result.error || "Unable to predict colleges.");
        renderResultsTable([]);
        renderPagination(null, fetchPrediction);
        return;
      }

      const pagination = result.pagination || {};
      const currentPage = Number(pagination.page || 1);
      const perPage = Number(pagination.per_page || 20);
      const tableStart = result.total_matches ? ((currentPage - 1) * perPage) + 1 : 1;
      renderResultsTable(result.recommendations || [], tableStart);
      renderPagination(result.pagination, fetchPrediction);

      if (title) title.textContent = "Predicted Colleges";
      if (meta) {
        const start = result.total_matches ? ((currentPage - 1) * perPage) + 1 : 0;
        const end = Math.min(currentPage * perPage, result.total_matches || 0);
        meta.textContent = `Showing ${start}-${end} of ${result.total_matches} colleges for ${result.student_input.percentile} percentile, ${result.student_input.category}, ${result.student_input.gender_label}.`;
      }
      document.getElementById("top-colleges")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      showAlert("Something went wrong while predicting colleges.");
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = "Show Predicted Colleges";
      }
    }
  }

  document.querySelectorAll("[data-tab-trigger]").forEach((trigger) => {
    trigger.addEventListener("click", (event) => {
      const tab = trigger.dataset.tabTrigger;
      if (!tab) return;
      event.preventDefault();
      setActiveTab(tab);
      if (tab === "top20" && !top20Loaded) fetchTop20();
      document.getElementById(tab === "top20" ? "top20-cutoffs" : "college-predictor")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    setActiveTab("predictor");
    fetchPrediction(1);
  });

  form?.querySelector('[name="per_page"]')?.addEventListener("change", () => {
    if (form.checkValidity()) fetchPrediction(1);
  });

  top20Form?.addEventListener("submit", (event) => {
    event.preventDefault();
    setActiveTab("top20");
    fetchTop20();
  });

  top20Form?.querySelectorAll("select").forEach((select) => {
    select.addEventListener("change", () => fetchTop20());
  });

  unlockButton?.addEventListener("click", startRazorpayUnlock);
});
