/* =================================
   CUT-OFFS PAGE JAVASCRIPT
================================= */

/* 1️⃣ Smooth fade-in on scroll */
const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("show");
      }
    });
  },
  { threshold: 0.15 }
);

const animatedElements = document.querySelectorAll(
  ".cutoff-hero, .cutoff-info, .dashboard-card, .cutoff-factors, .cutoff-cta"
);

animatedElements.forEach((el) => {
  el.classList.add("hidden");
  observer.observe(el);
});

/* 2️⃣ Dashboard card click interaction */
document.querySelectorAll(".dashboard-card").forEach((card) => {
  card.addEventListener("click", () => {
    alert(
      "This feature will open detailed cut-off data.\n\nComing soon!"
    );
  });
});

/* 3️⃣ CTA button click (Predict Rank placeholder) */
const ctaButton = document.querySelector(".cutoff-cta a");

if (ctaButton) {
  ctaButton.addEventListener("click", (e) => {
    e.preventDefault();
    alert(
      "Rank Predictor will be available soon.\n\nYou will be able to enter your rank and get college predictions."
    );
  });
}

/* 4️⃣ Page loaded confirmation */
document.addEventListener("DOMContentLoaded", () => {
  console.log("✅ Cut-Offs page JavaScript loaded successfully");
});
