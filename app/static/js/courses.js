const animatedItems = document.querySelectorAll(
  ".course-card, .category-card, .support-card"
);

function animateOnScroll() {
  animatedItems.forEach(item => {
    const rect = item.getBoundingClientRect();
    if (rect.top < window.innerHeight - 80) {
      item.style.opacity = 1;
      item.style.transform = "translateY(0)";
    }
  });
}

animatedItems.forEach(item => {
  item.style.opacity = 0;
  item.style.transform = "translateY(40px)";
  item.style.transition = "0.6s ease";
});

window.addEventListener("scroll", animateOnScroll);
animateOnScroll();
