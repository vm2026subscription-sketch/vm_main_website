const searchInput = document.getElementById("searchInput");
const examFilter  = document.getElementById("examFilter");
const container   = document.getElementById("examContainer");

function getCards() {
    return document.querySelectorAll(".exam-card");
}

function debounce(func, timeout = 300) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => { func.apply(this, args); }, timeout);
    };
}

const performFilter = () => {
    const query    = searchInput.value.toLowerCase().trim();
    const category = examFilter.value;
    let visible    = 0;

    getCards().forEach(card => {
        const title = card.querySelector("h3").textContent.toLowerCase();
        const matchSearch   = !query || title.includes(query);
        const matchCategory = category === "all" || card.classList.contains(category);

        if (matchSearch && matchCategory) {
            card.style.display  = "block";
            card.style.opacity  = "1";
            card.style.transform = "translateY(0)";
            visible++;
        } else {
            card.style.display = "none";
        }
    });

    let noResult = document.getElementById("no-results");
    if (visible === 0) {
        if (!noResult) {
            const msg = document.createElement("div");
            msg.id = "no-results";
            msg.innerHTML = `<div style="text-align:center;padding:50px;color:#ff7a00;"><p>No exams found matching your criteria.</p></div>`;
            container.appendChild(msg);
        }
    } else if (noResult) {
        noResult.remove();
    }
};

const revealOnScroll = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity  = "1";
            entry.target.style.transform = "translateY(0)";
            revealOnScroll.unobserve(entry.target);
        }
    });
}, { threshold: 0.1 });

getCards().forEach(card => {
    card.style.opacity   = "0";
    card.style.transform = "translateY(20px)";
    card.style.transition = "all 0.5s ease-out";
    revealOnScroll.observe(card);
});

searchInput.addEventListener("input", debounce(() => performFilter()));
examFilter.addEventListener("change", performFilter);
