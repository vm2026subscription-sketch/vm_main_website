/**
 * Vidyarthi Mitra - Advanced Portal Logic
 * Implements: Debouncing, Intersection Observers, and Dynamic DOM Injection
 */

const searchInput = document.getElementById("searchInput");
const examFilter = document.getElementById("examFilter");
const container = document.getElementById("examContainer");
const allCards = document.querySelectorAll(".exam-card");

// 1. DEBOUNCE: Prevents excessive calculations during typing
function debounce(func, timeout = 300) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => { func.apply(this, args); }, timeout);
    };
}

// 2. FILTER LOGIC: Enhanced with smooth transitions
const performFilter = () => {
    const query = searchInput.value.toLowerCase().trim();
    const category = examFilter.value;
    let visibleCount = 0;

    allCards.forEach(card => {
        const title = card.querySelector('h3').textContent.toLowerCase();
        const tag = card.querySelector('.tag').textContent.toLowerCase();
        
        const matchesSearch = title.includes(query);
        const matchesCategory = category === "all" || card.classList.contains(category);

        if (matchesSearch && matchesCategory) {
            card.style.display = "block";
            card.style.opacity = "1";
            card.style.transform = "translateY(0)";
            visibleCount++;
        } else {
            card.style.display = "none";
            card.style.opacity = "0";
        }
    });

    updateEmptyState(visibleCount);
};

// 3. EMPTY STATE: Dynamic Orange UI feedback
function updateEmptyState(count) {
    let existingMsg = document.getElementById("no-results");
    if (count === 0) {
        if (!existingMsg) {
            const msg = document.createElement("div");
            msg.id = "no-results";
            msg.innerHTML = `
                <div style="text-align:center; padding: 50px; color: #ff7a00;">
                    <h2 style="font-size: 2rem;">!</h2>
                    <p>No exams found matching your criteria.</p>
                </div>
            `;
            container.appendChild(msg);
        }
    } else if (existingMsg) {
        existingMsg.remove();
    }
}

// 4. INTERSECTION OBSERVER: "Scroll-Reveal" effect
const revealOnScroll = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = "1";
            entry.target.style.transform = "translateY(0)";
            revealOnScroll.unobserve(entry.target);
        }
    });
}, { threshold: 0.1 });

// Initialize Cards
allCards.forEach(card => {
    card.style.opacity = "0";
    card.style.transform = "translateY(20px)";
    card.style.transition = "all 0.5s ease-out";
    revealOnScroll.observe(card);
});

// Event Listeners
searchInput.addEventListener("input", debounce(() => performFilter()));
examFilter.addEventListener("change", performFilter);
// Active Link Highlighting
const navLinks = document.querySelectorAll('.nav-links a');

navLinks.forEach(link => {
    link.addEventListener('click', function() {
        navLinks.forEach(l => l.classList.remove('active'));
        this.classList.add('active');
    });
});

// Scroll Effect: Shrink navbar on scroll
window.addEventListener('scroll', () => {
    const navbar = document.querySelector('.navbar');
    if (window.scrollY > 50) {
        navbar.style.height = '65px';
        navbar.style.boxShadow = '0 5px 20px rgba(0,0,0,0.1)';
    } else {
        navbar.style.height = '80px';
        navbar.style.boxShadow = 'none';
    }
});