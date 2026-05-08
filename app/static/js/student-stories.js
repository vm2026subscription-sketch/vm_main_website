/**
 * Student Stories - Advanced Interaction
 */

// 1. SCROLL REVEAL EFFECT
const observerOptions = {
    threshold: 0.1,
    rootMargin: "0px 0px -50px 0px"
};

const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = "1";
            entry.target.style.transform = "translateY(0)";
            revealObserver.unobserve(entry.target); // Animate only once
        }
    });
}, observerOptions);

// Initialize cards for animation
document.querySelectorAll('.story-card').forEach(card => {
    card.style.opacity = "0";
    card.style.transform = "translateY(30px)";
    card.style.transition = "all 0.6s ease-out";
    revealObserver.observe(card);
});

// 2. CLICK FEEDBACK
document.querySelectorAll(".story-card button").forEach(btn => {
  btn.addEventListener("click", (e) => {
    const storyTitle = e.target.parentElement.querySelector('h3').innerText;
    console.log(`Loading full story for: ${storyTitle}`);
    // You can add logic here to redirect to a dynamic Flask route
  });
});