function animateCount(element, target) {
  const duration = 1200;
  const start = 0;
  const startTime = performance.now();

  function tick(now) {
    const progress = Math.min((now - startTime) / duration, 1);
    const value = Math.floor(start + (target - start) * progress);
    element.textContent = value.toLocaleString('en-IN');
    if (progress < 1) requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
}

function handleSubscribe() {
  const emailEl = document.getElementById('subEmail');
  const mobileEl = document.getElementById('subMobile');
  const statusEl = document.getElementById('subStatus');

  const email = emailEl.value.trim();
  const mobile = mobileEl.value.trim();
  const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  const mobileOk = /^\d{10}$/.test(mobile);

  if (!emailOk) {
    statusEl.textContent = 'Please enter a valid email address.';
    statusEl.style.color = '#dc2626';
    return;
  }

  if (!mobileOk) {
    statusEl.textContent = 'Please enter a valid 10-digit WhatsApp number.';
    statusEl.style.color = '#dc2626';
    return;
  }

  statusEl.textContent = 'Thanks! You are subscribed for early access.';
  statusEl.style.color = '#16a34a';
  emailEl.value = '';
  mobileEl.value = '';
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.count').forEach((element) => {
    const target = Number(element.getAttribute('data-target') || '0');
    animateCount(element, target);
  });
});
