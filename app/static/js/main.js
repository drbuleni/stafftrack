// StaffTrack Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert:not(.alert-info):not(.alert-warning)');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 5000);
    });

    // Confirm delete actions
    const deleteButtons = document.querySelectorAll('[data-confirm]');
    deleteButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            const message = this.getAttribute('data-confirm') || 'Are you sure you want to proceed?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });

    // Form validation styling
    const forms = document.querySelectorAll('.needs-validation');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });

    // Date input defaults
    const dateInputs = document.querySelectorAll('input[type="date"]:not([value])');
    const today = new Date().toISOString().split('T')[0];
    dateInputs.forEach(function(input) {
        if (!input.value && input.hasAttribute('data-default-today')) {
            input.value = today;
        }
    });

    // Tooltip initialization
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipTriggerList.forEach(function(tooltipTriggerEl) {
        new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Active nav item highlighting
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
    navLinks.forEach(function(link) {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });

    // Print button functionality
    const printButtons = document.querySelectorAll('[data-print]');
    printButtons.forEach(function(button) {
        button.addEventListener('click', function() {
            window.print();
        });
    });
});

// Format currency helper
function formatCurrency(amount) {
    return 'R ' + parseFloat(amount).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,');
}

// Format date helper
function formatDate(dateString) {
    const options = { day: '2-digit', month: 'short', year: 'numeric' };
    return new Date(dateString).toLocaleDateString('en-ZA', options);
}

// ============================================
// dd/mm/yyyy date pickers (flatpickr)
// Native date inputs display year-first on many
// locales; staff read dates as day/month/year.
// The real input keeps submitting yyyy-mm-dd.
// ============================================
(function () {
    function initDateInput(input) {
        if (input._flatpickr || input.dataset.noFlatpickr !== undefined) return;
        const isReadonly = input.hasAttribute('readonly');
        const config = {
            altInput: true,
            altFormat: 'd/m/Y',
            dateFormat: 'Y-m-d',
            allowInput: false,
            clickOpens: !isReadonly,
        };
        if (input.min) config.minDate = input.min;
        if (input.max) config.maxDate = input.max;
        flatpickr(input, config);
    }

    function initAllDateInputs(root) {
        (root || document).querySelectorAll('input[type="date"]').forEach(initDateInput);
    }

    function start() {
        initAllDateInputs();
        // Cover date inputs added later (e.g. dynamic table rows)
        new MutationObserver(function (mutations) {
            mutations.forEach(function (m) {
                m.addedNodes.forEach(function (node) {
                    if (node.nodeType !== 1) return;
                    if (node.matches && node.matches('input[type="date"]')) {
                        initDateInput(node);
                    } else if (node.querySelectorAll) {
                        initAllDateInputs(node);
                    }
                });
            });
        }).observe(document.body, { childList: true, subtree: true });
    }

    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = 'https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.css';
    document.head.appendChild(css);

    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.js';
    script.onload = function () {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', start);
        } else {
            start();
        }
    };
    document.head.appendChild(script);
    // If the CDN is unreachable, inputs stay native - still usable.
})();
