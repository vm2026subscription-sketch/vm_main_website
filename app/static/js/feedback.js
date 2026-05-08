/* ═══════════════════════════════════════════════════════════
   Vidyarthi Mitra  |  Feedback Form  |  feedback.js
   Handles:
     1. Live avatar preview  (original logic)
     2. Remove image button
     3. Digits-only filter on mobile field
     4. Client-side validation with inline errors
     5. Double-submit prevention
   ═══════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    /* ── DOM References ───────────────────────────────────── */
    var form         = document.getElementById('feedbackForm');
    var avatarInput  = document.getElementById('avatarInput');
    var previewImg   = document.getElementById('previewImg');
    var placeholder  = document.getElementById('imgPlaceholder');
    var removeBtn    = document.getElementById('removeBtn');
    var submitBtn    = document.getElementById('submitBtn');


    /* ════════════════════════════════════════════════════════
       1. AVATAR — Live Preview
          Original FileReader logic preserved exactly.
          Placeholder toggle + Remove button added.
       ════════════════════════════════════════════════════════ */

    function showPreview(src) {
        previewImg.src            = src;
        previewImg.style.display  = 'block';
        placeholder.style.display = 'none';
        removeBtn.style.display   = 'block';
    }

    function clearPreview() {
        previewImg.src            = '';
        previewImg.style.display  = 'none';
        placeholder.style.display = 'flex';
        removeBtn.style.display   = 'none';
        avatarInput.value         = '';     // reset file input
    }

    avatarInput.addEventListener('change', function (event) {
        var file    = event.target.files[0];
        var preview = document.getElementById('previewImg');   // original ref

        if (file) {
            // Client-side checks before FileReader
            if (!file.type.startsWith('image/')) {
                alert('Please select a valid image file (PNG, JPG, GIF, WEBP).');
                clearPreview();
                return;
            }
            if (file.size > 5 * 1024 * 1024) {
                alert('Image size must be less than 5 MB.');
                clearPreview();
                return;
            }

            // Original FileReader logic
            var reader = new FileReader();
            reader.onload = function (e) {
                preview.src = e.target.result;    // original line
                showPreview(e.target.result);     // toggle placeholder
            };
            reader.readAsDataURL(file);

        } else {
            // Original: reset to placeholder — clearPreview() handles this
            clearPreview();
        }
    });

    removeBtn.addEventListener('click', clearPreview);


    /* ════════════════════════════════════════════════════════
       2. MOBILE — Accept digits only
       ════════════════════════════════════════════════════════ */
    var mobileInput = document.getElementById('u_mobile');
    mobileInput.addEventListener('input', function () {
        this.value = this.value.replace(/\D/g, '');
    });


    /* ════════════════════════════════════════════════════════
       3. VALIDATION RULES
       ════════════════════════════════════════════════════════ */
    var validators = {
        u_name:        function (v) { return v.length > 0; },
        u_mobile:      function (v) { return /^\d{10}$/.test(v); },
        u_email:       function (v) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v); },
        u_designation: function (v) { return v.length > 0; },
        u_feedback:    function (v) { return v.length > 0; }
    };

    /* Apply or remove invalid/valid CSS class + show/hide error span */
    function setFieldState(input, errEl, isValid) {
        if (isValid) {
            input.classList.remove('invalid');
            input.classList.add('valid');
            errEl.classList.remove('show');
        } else {
            input.classList.add('invalid');
            input.classList.remove('valid');
            errEl.classList.add('show');
        }
    }

    /* Validate a single field by its id; returns true if valid */
    function validateOne(id) {
        var input = document.getElementById(id);
        var errEl = document.getElementById('err_' + id.replace('u_', ''));
        if (!input || !errEl) return true;
        var ok = validators[id](input.value.trim());
        setFieldState(input, errEl, ok);
        return ok;
    }


    /* ════════════════════════════════════════════════════════
       4. REAL-TIME ERROR CLEARING
          Clear error as soon as the user starts correcting.
       ════════════════════════════════════════════════════════ */
    Object.keys(validators).forEach(function (id) {
        var input = document.getElementById(id);
        if (!input) return;

        // Live re-check while typing (only if field was already invalid)
        input.addEventListener('input', function () {
            if (input.classList.contains('invalid')) {
                validateOne(id);
            }
        });

        // Full check when focus leaves the field
        input.addEventListener('blur', function () {
            if (input.value.trim().length > 0) {
                validateOne(id);
            }
        });
    });


    /* ════════════════════════════════════════════════════════
       5. FORM SUBMIT
          Validate all fields → stop if any fail →
          disable button to prevent double-submit →
          let the browser POST to Flask /submit.
       ════════════════════════════════════════════════════════ */
    form.addEventListener('submit', function (e) {

        var allValid     = true;
        var firstInvalid = null;

        Object.keys(validators).forEach(function (id) {
            var ok = validateOne(id);
            if (!ok) {
                allValid = false;
                if (!firstInvalid) firstInvalid = document.getElementById(id);
            }
        });

        if (!allValid) {
            e.preventDefault();          // stop POST to Flask
            firstInvalid.focus();
            firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }

        // All valid — disable button so user can't submit twice
        submitBtn.disabled    = true;
        submitBtn.textContent = 'Submitting…';
        // Form now POSTs to Flask /submit route
    });

})();
