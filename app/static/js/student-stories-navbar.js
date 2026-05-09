/**
 * Vidyarthi Mitra - Expanded Professional Student Stories
 * Features: Centralized State, Dynamic Rendering, Event Delegation, Modal View
 */

// 1. EXPANDED STATE MANAGEMENT
const storiesData = [
    { 
        id: 1, 
        category: 'engineering', 
        tag: 'IIT Bombay', 
        title: 'Village to IIT Bombay', 
        text: 'A student from a rural background shares how discipline, self-study, and mentorship helped crack JEE Advanced.', 
        fullStory: `Ravi grew up in a small village in Maharashtra with no access to coaching institutes or internet. Armed with only NCERT textbooks and sheer determination, he built a rigorous 12-hour daily study schedule. A local schoolteacher mentored him on problem-solving techniques. After two years of consistent effort, he cracked JEE Advanced and secured a seat at IIT Bombay in Computer Science. His key advice: "Understand concepts deeply — never rote-learn formulas."`,
        link: '/story/1' 
    },
    { 
        id: 2, 
        category: 'medical', 
        tag: 'NEET', 
        title: 'NEET Topper with First Attempt', 
        text: 'Learn daily routine, revision strategy, and mindset of a NEET UG topper who secured a government medical seat.', 
        fullStory: `Priya cracked NEET UG in her very first attempt, securing an All India Rank under 500. Her secret? A strict 5 AM wake-up, subject rotation every 2 hours, and weekly full-syllabus mock tests. She revised Biology flashcards every night before sleeping. "NEET is a marathon, not a sprint. Consistency over intensity," she says. She now studies at AIIMS Delhi and mentors aspirants on her YouTube channel.`,
        link: '/story/2' 
    },
    { 
        id: 3, 
        category: 'engineering', 
        tag: 'CET', 
        title: 'MHT-CET to COEP Pune', 
        text: 'From average mock scores to a top Maharashtra engineering college. Smart planning made the difference.', 
        fullStory: `Sameer was scoring 60–65% in MHT-CET mocks during December. Instead of panicking, he analyzed his weak chapters and created a targeted 90-day plan focusing on Physics and Maths. He attempted 40+ previous year papers and tracked every mistake in an error journal. By exam day, his mock scores had jumped to 88%. He secured a seat in Computer Engineering at COEP Pune. "Work smarter, not just harder," is his advice to future aspirants.`,
        link: '/story/3' 
    },
    { 
        id: 4, 
        category: 'upsc', 
        tag: 'UPSC', 
        title: 'UPSC Success After 3 Failures', 
        text: 'A powerful story of persistence, self-belief, and strategy that finally led to IAS selection.', 
        fullStory: `After failing UPSC Prelims twice and clearing Mains but failing the interview once, Ananya did not give up. She completely overhauled her strategy — dropping expensive coaching, joining a peer study group, and focusing on answer writing every single day. She also worked on her interview personality with mock panels. On her fourth attempt, she cracked UPSC with an All India Rank of 47 and is now an IAS officer in Rajasthan. "Failure is just data. Use it," she says.`,
        link: '/story/4' 
    },
    { 
        id: 5, 
        category: 'career', 
        tag: 'Career', 
        title: 'From Tier-3 College to Google', 
        text: 'How strong fundamentals, projects, and internships helped land a global tech job.', 
        fullStory: `Kiran graduated from a lesser-known college in Nagpur but refused to let that define his future. He spent two years mastering Data Structures, Algorithms, and System Design through free resources like Leetcode and MIT OpenCourseWare. He built three impactful open-source projects and contributed to GitHub. After 200+ applications and 12 interview rounds across companies, Google extended him an offer as a Software Engineer. "Your college name opens doors, but your skills keep you in the room," he shares.`,
        link: '/story/5' 
    },
    { 
        id: 6, 
        category: 'mba', 
        tag: 'MBA', 
        title: 'CAT 99+ Percentile Journey', 
        text: 'Time management, mock analysis, and consistency that led to admission in a top IIM.', 
        fullStory: `Meera was a working professional preparing for CAT while managing a full-time job at an IT firm. She studied 2 hours every morning before office and gave full mocks every Sunday. Instead of attempting all questions, she perfected her selection strategy — attempting only high-accuracy questions first. Her CAT percentile jumped from 85 to 99.2 in one year. She converted IIM Ahmedabad and is now pursuing her MBA with a scholarship. "Mock analysis matters more than mock attempts," she advises.`,
        link: '/story/6' 
    },
    { 
        id: 7, 
        category: 'defense', 
        tag: 'NDA', 
        title: 'The NDA Spirit: Small Town to Khadakwasla', 
        text: 'Balancing rigorous physical training with academic excellence to clear the SSB interview.', 
        fullStory: `Arjun from Latur always dreamed of serving the nation. He trained physically — running 5 km daily, swimming, and doing obstacle courses — while simultaneously preparing for NDA Mathematics and General Ability Tests. His SSB preparation focused on group tasks, lecturette practice, and self-awareness exercises. After clearing NDA on his second attempt, he joined the National Defence Academy in Khadakwasla. "The uniform is earned, not given. It demands everything you have," he reflects with pride.`,
        link: '/story/7' 
    },
    { 
        id: 8, 
        category: 'law', 
        tag: 'CLAT', 
        title: 'Mastering the Law Marathon', 
        text: 'How intensive reading and logical reasoning practice secured a seat at NLSIU Bangalore.', 
        fullStory: `Shreya prepared for CLAT while in Class 12 without any formal coaching. She read two newspapers daily, solved 50 legal reasoning questions every evening, and built a vocabulary journal of 10 new words per day. She also studied landmark Supreme Court judgments to strengthen her legal aptitude. Her disciplined reading habit gave her an edge in the comprehension-heavy CLAT pattern. She secured Rank 8 All India and is now a first-year student at NLSIU Bangalore. "CLAT rewards readers. So read everything," she says.`,
        link: '/story/8' 
    }
];

// ── Modal HTML injected once into DOM ──────────────────────────────────────
const modalHTML = `
<div id="storyModal" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
    <div class="modal-box">
        <button class="modal-close" id="modalClose" aria-label="Close">&times;</button>
        <span class="modal-tag" id="modalTag"></span>
        <h2 id="modalTitle"></h2>
        <p id="modalBody"></p>
        <a id="modalLink" href="#" class="modal-cta">Explore More Stories &rarr;</a>
    </div>
</div>`;
document.body.insertAdjacentHTML('beforeend', modalHTML);

// ── Modal CSS injected once (keeps everything self-contained) ──────────────
const modalStyles = `
<style>
.modal-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.65);
    backdrop-filter: blur(4px);
    z-index: 1000;
    align-items: center;
    justify-content: center;
    padding: 1rem;
}
.modal-overlay.active {
    display: flex;
}
.modal-box {
    background: #fff;
    border-radius: 16px;
    padding: 2.5rem 2rem;
    max-width: 560px;
    width: 100%;
    position: relative;
    box-shadow: 0 20px 60px rgba(0,0,0,0.25);
    animation: modalSlideIn 0.3s ease;
}
@keyframes modalSlideIn {
    from { opacity: 0; transform: translateY(30px) scale(0.97); }
    to   { opacity: 1; transform: translateY(0)   scale(1);    }
}
.modal-close {
    position: absolute;
    top: 1rem;
    right: 1.2rem;
    background: none;
    border: none;
    font-size: 1.8rem;
    cursor: pointer;
    color: #666;
    line-height: 1;
    transition: color 0.2s;
}
.modal-close:hover { color: #ff7a00; }
.modal-tag {
    display: inline-block;
    background: #fff3e0;
    color: #ff7a00;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    margin-bottom: 0.9rem;
}
#modalTitle {
    font-size: 1.4rem;
    font-weight: 700;
    color: #1a1a2e;
    margin-bottom: 1rem;
    line-height: 1.35;
}
#modalBody {
    font-size: 0.97rem;
    color: #444;
    line-height: 1.75;
    margin-bottom: 1.5rem;
}
.modal-cta {
    display: inline-block;
    background: #ff7a00;
    color: #fff;
    text-decoration: none;
    padding: 0.6rem 1.4rem;
    border-radius: 8px;
    font-weight: 600;
    font-size: 0.9rem;
    transition: background 0.2s, transform 0.15s;
}
.modal-cta:hover { background: #e06500; transform: translateY(-1px); }
</style>`;
document.head.insertAdjacentHTML('beforeend', modalStyles);

// ── DOM References ─────────────────────────────────────────────────────────
const container  = document.getElementById("storiesContainer");
const modal      = document.getElementById("storyModal");
const modalClose = document.getElementById("modalClose");

// ── Open / Close helpers ───────────────────────────────────────────────────
const openModal = (story) => {
    document.getElementById("modalTag").textContent   = story.tag;
    document.getElementById("modalTitle").textContent = story.title;
    document.getElementById("modalBody").textContent  = story.fullStory;
    document.getElementById("modalLink").href         = story.link;
    modal.classList.add("active");
    document.body.style.overflow = "hidden";       // prevent background scroll

    console.log(
        `%c Vidyarthi Mitra %c Opened: ${story.title}`,
        "background:#ff7a00;color:#fff;padding:2px 6px;border-radius:3px;",
        "color:inherit;"
    );
};

const closeModal = () => {
    modal.classList.remove("active");
    document.body.style.overflow = "";
};

// ── Intersection Observer (scroll reveal) ─────────────────────────────────
const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add("reveal-active");
            observer.unobserve(entry.target);
        }
    });
}, { threshold: 0.15 });

// ── Render cards ───────────────────────────────────────────────────────────
const renderStories = (filter = 'all') => {
    if (!container) return;
    container.innerHTML = "";

    const filtered = filter === 'all'
        ? storiesData
        : storiesData.filter(s => s.category === filter);

    filtered.forEach((story, index) => {
        const card = document.createElement("div");
        card.className = `story-card ${story.category}`;
        card.style.transitionDelay = `${index * 0.1}s`;

        card.innerHTML = `
            <span class="tag">${story.tag}</span>
            <h3>${story.title}</h3>
            <p>${story.text}</p>
            <button data-id="${story.id}">Read Full Story</button>
        `;

        container.appendChild(card);
        observer.observe(card);
    });
};

// ── Event Delegation: card buttons ────────────────────────────────────────
container.addEventListener("click", (e) => {
    if (e.target.tagName === "BUTTON") {
        const story = storiesData.find(s => s.id == e.target.dataset.id);
        if (story) openModal(story);
    }
});

// ── Close modal: button, overlay click, or Escape key ─────────────────────
modalClose.addEventListener("click", closeModal);

modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();   // click outside the box
});

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("active")) closeModal();
});

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => renderStories());