document.addEventListener('DOMContentLoaded', () => {
    const reqSelect = document.getElementById('requirementSelect');
    const sections = {
        career: document.getElementById('careerSection'),
        admission: document.getElementById('admissionSection'),
        other: document.getElementById('otherSection')
    };

    function showFormMsg(msg, type) {
        let el = document.getElementById('_guideme_msg');
        if (!el) {
            el = document.createElement('div');
            el.id = '_guideme_msg';
            el.style.cssText = 'margin:12px 0;padding:10px 14px;border-radius:8px;font-size:14px;font-weight:500;';
            const btn = document.querySelector('.submit-btn');
            if (btn) btn.parentNode.insertBefore(el, btn);
            else document.body.appendChild(el);
        }
        el.textContent = msg;
        el.style.display = 'block';
        if (type === 'error') {
            el.style.background = '#fef2f2';
            el.style.color = '#dc2626';
            el.style.border = '1px solid #fca5a5';
        } else {
            el.style.background = '#f0fdf4';
            el.style.color = '#16a34a';
            el.style.border = '1px solid #86efac';
            setTimeout(() => { el.style.display = 'none'; }, 5000);
        }
    }

    // Toggle Section logic
    reqSelect.addEventListener('change', function() {
        Object.values(sections).forEach(s => s.style.display = 'none');
        if (this.value) sections[this.value].style.display = 'block';
    });

    // Validation Logic
    document.querySelectorAll('.submit-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();

            const whatsapp = document.getElementById('form_whatsapp').value.trim();
            const email = document.getElementById('form_email').value.trim();
            const name = document.getElementById('form_name').value.trim();
            const address = document.getElementById('form_address').value.trim();

            if (!name || !whatsapp || !email || !address) {
                showFormMsg("Please fill in all required fields.", 'error');
                return;
            }

            // 10-Digit Validation
            if (!/^\d{10}$/.test(whatsapp)) {
                showFormMsg("WhatsApp number must be exactly 10 digits.", 'error');
                return;
            }

            // Email Validation
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(email)) {
                showFormMsg("Please enter a valid email address.", 'error');
                return;
            }

            // Get requirement type
            const reqType = reqSelect.value;
            let message = `Hello! I am interested in ${reqType}. My details:\n`;
            message += `Name: ${name}\n`;
            message += `Email: ${email}\n`;
            message += `WhatsApp: ${whatsapp}\n`;
            message += `Address: ${address}\n`;

            // Add specific section details
            if (reqType === 'career') {
                const level = document.getElementById('career_level').value;
                const careerMsg = document.getElementById('career_msg').value;
                message += `Current Level: ${level}\n`;
                message += `Message: ${careerMsg}\n`;
            } else if (reqType === 'admission') {
                const course = document.getElementById('adm_course').value;
                const percentage = document.getElementById('adm_12th').value;
                message += `Desired Course: ${course}\n`;
                message += `12th Percentage: ${percentage}%\n`;
            } else if (reqType === 'other') {
                const otherMsg = document.getElementById('other_msg').value;
                message += `Message: ${otherMsg}\n`;
            }

            // Send via WhatsApp
            const whatsappUrl = `https://wa.me/917720025900?text=${encodeURIComponent(message)}`;
            window.open(whatsappUrl, '_blank');

            showFormMsg("✅ Your request has been sent! Our team will contact you soon via WhatsApp.", 'success');
            
            // Reset form
            document.querySelectorAll('input, textarea, select').forEach(field => {
                field.value = '';
            });
            Object.values(sections).forEach(s => s.style.display = 'none');
        });
    });
});