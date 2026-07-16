/**
 * submit-story.js
 * Client-side validation + submission.
 * MODE: Tries Flask /api/submit-story first.
 *       If server is unavailable, saves locally and shows success anyway.
 *       Flip USE_LOCAL_ONLY = true to always skip the network call.
 */

const USE_LOCAL_ONLY = false; // â† set true to always skip Flask entirely

// â”€â”€ DOM refs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const form       = document.getElementById("storyForm");
const submitBtn  = document.getElementById("submitBtn");
const btnText    = document.getElementById("btnText");
const btnSpinner = document.getElementById("btnSpinner");
const successMsg = document.getElementById("successMsg");
const errorBanner= document.getElementById("errorBanner");
const charCount  = document.getElementById("charCount");
const storyArea  = document.getElementById("story");

const MAX_CHARS = 2000;

// â”€â”€ Character counter â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
storyArea.addEventListener("input", () => {
    const len = storyArea.value.length;
    charCount.textContent = `${len} / ${MAX_CHARS} characters`;
    charCount.style.color = len > MAX_CHARS ? "#e53935" : "#888";
});

// â”€â”€ Field-level validation helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function showFieldError(id, message) {
    const el = document.getElementById(`${id}Error`);
    const input = document.getElementById(id);
    if (el) el.textContent = message;
    if (input) input.classList.add("input-error");
}

function clearFieldError(id) {
    const el = document.getElementById(`${id}Error`);
    const input = document.getElementById(id);
    if (el) el.textContent = "";
    if (input) input.classList.remove("input-error");
}

function clearAllErrors() {
    ["name", "email", "exam", "story"].forEach(clearFieldError);
    errorBanner.textContent = "";
    errorBanner.classList.add("hidden");
}

// Inline error clearing on user input
["name", "email", "exam", "story"].forEach(id => {
    document.getElementById(id)?.addEventListener("input", () => clearFieldError(id));
});

// â”€â”€ Client-side validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function validate(data) {
    let valid = true;

    if (!data.name.trim()) {
        showFieldError("name", "Full name is required.");
        valid = false;
    }

    const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!data.email.trim()) {
        showFieldError("email", "Email address is required.");
        valid = false;
    } else if (!emailRe.test(data.email)) {
        showFieldError("email", "Enter a valid email address.");
        valid = false;
    }

    if (!data.exam.trim()) {
        showFieldError("exam", "Exam / achievement is required.");
        valid = false;
    }

    if (!data.story.trim()) {
        showFieldError("story", "Please write your story.");
        valid = false;
    } else if (data.story.trim().length < 50) {
        showFieldError("story", "Story must be at least 50 characters.");
        valid = false;
    } else if (data.story.length > MAX_CHARS) {
        showFieldError("story", `Story must not exceed ${MAX_CHARS} characters.`);
        valid = false;
    }

    return valid;
}

// â”€â”€ Loading state helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function setLoading(on) {
    submitBtn.disabled = on;
    btnText.textContent = on ? "Submittingâ€¦" : "Submit Story";
    btnSpinner.classList.toggle("hidden", !on);
}

// â”€â”€ Save to localStorage (fallback when Flask is offline) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function saveLocally(payload) {
    const key = "vm_pending_stories";
    const existing = JSON.parse(localStorage.getItem(key) || "[]");
    existing.push({ ...payload, submitted_at: new Date().toISOString(), id: Date.now() });
    localStorage.setItem(key, JSON.stringify(existing));
}

// â”€â”€ Show success UI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function showSuccess(source = "server") {
    form.querySelectorAll(".form-group, button[type='submit']")
        .forEach(el => el.classList.add("hidden"));
    successMsg.classList.remove("hidden");

    console.log(
        `%c Vidyarthi Mitra %c Story saved (${source})`,
        "background:#ff7a00;color:#fff;padding:2px 6px;border-radius:3px;",
        "color:inherit;"
    );
}

// â”€â”€ Form submit â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearAllErrors();

    const payload = {
        name:  document.getElementById("name").value,
        email: document.getElementById("email").value,
        exam:  document.getElementById("exam").value,
        story: document.getElementById("story").value,
    };

    if (!validate(payload)) return;

    setLoading(true);

    // â”€â”€ LOCAL-ONLY MODE: skip network entirely â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if (USE_LOCAL_ONLY) {
        await new Promise(r => setTimeout(r, 800)); // brief fake delay
        saveLocally(payload);
        showSuccess("local");
        setLoading(false);
        return;
    }

    // â”€â”€ TRY FLASK, FALL BACK GRACEFULLY â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000); // 5s timeout

        const res = await fetch("/api/submit-story", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
            signal: controller.signal,
        });
        clearTimeout(timeout);

        const json = await res.json();

        if (res.ok && json.success) {
            showSuccess("server");
        } else {
            // Server returned an error (validation etc.) â€” show it
            errorBanner.textContent = json.error || "Submission failed. Please try again.";
            errorBanner.classList.remove("hidden");
        }

    } catch (err) {
        // Network unavailable or Flask not running â†’ save locally, still show success
        saveLocally(payload);
        showSuccess("local");
        console.info("Flask unavailable â€” story saved locally.", err.message);

    } finally {
        setLoading(false);
    }
});