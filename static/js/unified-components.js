/**
 * KillShill Unified Components JavaScript
 * Version: 1.0
 * Description: Enhanced functionality for all UI components
 */

(function() {
    'use strict';

    // Initialize all components when DOM is loaded
    document.addEventListener('DOMContentLoaded', function() {
        initializeThemeSystem();
        initializeSidebar();
        initializeNavigation();
        initializeForms();
        initializeButtons();
        initializeTables();
        initializeAlerts();
        initializeTooltips();
        initializeModals();
        initializeSearch();
        
        console.log('KillShill Unified Components initialized successfully');
    });

    /**
     * Theme System
     */
    function initializeThemeSystem() {
        const themeToggle = document.getElementById('themeToggle') || document.getElementById('authThemeToggle');
        const themeIcon = document.getElementById('themeIcon') || document.getElementById('authThemeIcon');
        const body = document.body;
        
        if (!themeToggle) return;
        
        // Load saved theme or default to light
        const savedTheme = localStorage.getItem('theme') || 'light';
        setTheme(savedTheme);
        
        function setTheme(theme) {
            if (theme === 'dark') {
                body.classList.add('dark-theme');
                if (themeIcon) {
                    themeIcon.className = 'fas fa-sun';
                    themeToggle.title = 'Switch to light mode';
                }
            } else {
                body.classList.remove('dark-theme');
                if (themeIcon) {
                    themeIcon.className = 'fas fa-moon';
                    themeToggle.title = 'Switch to dark mode';
                }
            }
            localStorage.setItem('theme', theme);
            
            // Dispatch theme change event
            window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme } }));
        }
        
        themeToggle.addEventListener('click', function() {
            const currentTheme = body.classList.contains('dark-theme') ? 'dark' : 'light';
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            setTheme(newTheme);
            
            // Add click animation
            this.style.transform = 'scale(0.9)';
            setTimeout(() => {
                this.style.transform = 'scale(1)';
            }, 150);
        });
    }

    /**
     * Sidebar Navigation
     */
    function initializeSidebar() {
        const mobileToggle = document.getElementById('mobileToggle');
        const sidebar = document.getElementById('sidebar');
        const mainContent = document.getElementById('mainContent');
        
        if (!mobileToggle || !sidebar || !mainContent) return;
        
        // Mobile menu toggle
        mobileToggle.addEventListener('click', function() {
            sidebar.classList.toggle('show');
            mainContent.classList.toggle('expanded');
            
            // Update aria attributes
            const isExpanded = sidebar.classList.contains('show');
            this.setAttribute('aria-expanded', isExpanded);
        });
        
        // Close sidebar when clicking outside on mobile
        document.addEventListener('click', function(e) {
            if (window.innerWidth <= 768 && 
                !sidebar.contains(e.target) && 
                !mobileToggle.contains(e.target) && 
                sidebar.classList.contains('show')) {
                sidebar.classList.remove('show');
                mainContent.classList.remove('expanded');
                mobileToggle.setAttribute('aria-expanded', 'false');
            }
        });
        
        // Handle keyboard navigation
        sidebar.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && window.innerWidth <= 768) {
                sidebar.classList.remove('show');
                mainContent.classList.remove('expanded');
                mobileToggle.focus();
            }
        });
    }

    /**
     * Navigation Enhancement
     */
    function initializeNavigation() {
        const navLinks = document.querySelectorAll('.nav-link');
        
        navLinks.forEach(link => {
            // Add active state management
            link.addEventListener('click', function() {
                // Remove active class from all nav links
                navLinks.forEach(nl => nl.classList.remove('active'));
                // Add active class to clicked link
                this.classList.add('active');
            });
            
            // Add hover effects
            link.addEventListener('mouseenter', function() {
                if (!this.classList.contains('active')) {
                    this.style.transform = 'translateX(4px)';
                }
            });
            
            link.addEventListener('mouseleave', function() {
                if (!this.classList.contains('active')) {
                    this.style.transform = 'translateX(0)';
                }
            });
        });
    }

    /**
     * Enhanced Form Functionality
     */
    function initializeForms() {
        // Form field enhancements
        document.querySelectorAll('.form-control').forEach(input => {
            // Focus effects
            input.addEventListener('focus', function() {
                this.parentElement.classList.add('focused');
            });
            
            input.addEventListener('blur', function() {
                this.parentElement.classList.remove('focused');
                if (this.value) {
                    this.parentElement.classList.add('has-value');
                } else {
                    this.parentElement.classList.remove('has-value');
                }
            });
            
            // Initial state check
            if (input.value) {
                input.parentElement.classList.add('has-value');
            }
        });
        
        // Form submission handling
        document.querySelectorAll('form').forEach(form => {
            form.addEventListener('submit', function(e) {
                const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
                if (submitButton && !submitButton.disabled) {
                    setButtonLoading(submitButton, true);
                    
                    // Reset loading state if form validation fails
                    setTimeout(() => {
                        if (!form.checkValidity()) {
                            setButtonLoading(submitButton, false);
                        }
                    }, 100);
                }
            });
        });
        
        // Real-time validation
        document.querySelectorAll('input[type="email"]').forEach(input => {
            input.addEventListener('input', function() {
                const isValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.value);
                const formGroup = this.closest('.form-floating') || this.closest('.form-group');
                
                if (this.value.length > 0) {
                    if (isValid) {
                        formGroup.classList.remove('is-invalid');
                        formGroup.classList.add('is-valid');
                    } else {
                        formGroup.classList.remove('is-valid');
                        formGroup.classList.add('is-invalid');
                    }
                } else {
                    formGroup.classList.remove('is-valid', 'is-invalid');
                }
            });
        });
        
        // Password confirmation validation
        const passwordInputs = document.querySelectorAll('input[type="password"]');
        passwordInputs.forEach(input => {
            if (input.name === 'confirm_password' || input.name === 'password_confirmation') {
                input.addEventListener('input', function() {
                    const passwordField = document.querySelector('input[name="password"]');
                    if (passwordField) {
                        const formGroup = this.closest('.form-floating') || this.closest('.form-group');
                        
                        if (this.value.length > 0) {
                            if (this.value === passwordField.value) {
                                formGroup.classList.remove('is-invalid');
                                formGroup.classList.add('is-valid');
                            } else {
                                formGroup.classList.remove('is-valid');
                                formGroup.classList.add('is-invalid');
                            }
                        } else {
                            formGroup.classList.remove('is-valid', 'is-invalid');
                        }
                    }
                });
            }
        });
    }

    /**
     * Button Enhancements
     */
    function initializeButtons() {
        document.querySelectorAll('.btn').forEach(button => {
            // Click animation
            button.addEventListener('click', function(e) {
                // Add ripple effect
                const ripple = document.createElement('span');
                const rect = this.getBoundingClientRect();
                const size = Math.max(rect.width, rect.height);
                const x = e.clientX - rect.left - size / 2;
                const y = e.clientY - rect.top - size / 2;
                
                ripple.style.width = ripple.style.height = size + 'px';
                ripple.style.left = x + 'px';
                ripple.style.top = y + 'px';
                ripple.classList.add('ripple');
                
                this.appendChild(ripple);
                
                setTimeout(() => {
                    ripple.remove();
                }, 600);
                
                // Scale animation
                this.style.transform = 'scale(0.98)';
                setTimeout(() => {
                    this.style.transform = 'scale(1)';
                }, 150);
            });
        });
    }

    /**
     * Table Enhancements
     */
    function initializeTables() {
        document.querySelectorAll('.table tbody tr').forEach(row => {
            row.addEventListener('click', function() {
                // Row selection
                this.classList.toggle('selected');
                
                // Dispatch row click event
                const event = new CustomEvent('rowClicked', {
                    detail: { row: this }
                });
                this.dispatchEvent(event);
            });
        });
        
        // Add sortable functionality to tables
        document.querySelectorAll('.table th').forEach(header => {
            if (header.dataset.sortable !== 'false') {
                header.style.cursor = 'pointer';
                header.addEventListener('click', function() {
                    sortTable(this);
                });
            }
        });
    }

    /**
     * Alert Auto-dismiss
     */
    function initializeAlerts() {
        // Auto-dismiss alerts after 5 seconds
        setTimeout(function() {
            const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
            alerts.forEach(alert => {
                if (window.bootstrap && window.bootstrap.Alert) {
                    const bsAlert = new bootstrap.Alert(alert);
                    bsAlert.close();
                }
            });
        }, 5000);
    }

    /**
     * Tooltip and Popover Initialization
     */
    function initializeTooltips() {
        if (window.bootstrap) {
            // Initialize tooltips
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
            
            // Initialize popovers
            const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
            popoverTriggerList.map(function (popoverTriggerEl) {
                return new bootstrap.Popover(popoverTriggerEl);
            });
        }
    }

    /**
     * Modal Enhancements
     */
    function initializeModals() {
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('show.bs.modal', function() {
                // Add show animation
                this.style.opacity = '0';
                setTimeout(() => {
                    this.style.opacity = '1';
                }, 100);
            });
        });
    }

    /**
     * Global Search
     */
    function initializeSearch() {
        const globalSearch = document.getElementById('globalSearch');
        if (globalSearch) {
            let searchTimeout;
            
            globalSearch.addEventListener('input', function(e) {
                const query = e.target.value;
                
                // Clear previous timeout
                clearTimeout(searchTimeout);
                
                // Debounce search
                searchTimeout = setTimeout(() => {
                    if (query.length > 2) {
                        performSearch(query);
                    }
                }, 300);
            });
            
            globalSearch.addEventListener('keypress', function(e) {
                if (e.key === 'Enter' && this.value.trim()) {
                    e.preventDefault();
                    window.location.href = `/dashboard/search/?q=${encodeURIComponent(this.value)}`;
                }
            });
        }
    }

    /**
     * Utility Functions
     */
    
    // Button loading state
    function setButtonLoading(button, loading = true) {
        if (loading) {
            button.disabled = true;
            const originalContent = button.innerHTML;
            button.dataset.originalContent = originalContent;
            button.innerHTML = '<span class="spinner me-2"></span>Loading...';
        } else {
            button.disabled = false;
            button.innerHTML = button.dataset.originalContent || button.innerHTML;
        }
    }
    
    // Table sorting
    function sortTable(header) {
        const table = header.closest('table');
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const columnIndex = Array.from(header.parentElement.children).indexOf(header);
        const isAscending = header.classList.contains('sort-desc');
        
        // Clear all sort classes
        header.parentElement.querySelectorAll('th').forEach(th => {
            th.classList.remove('sort-asc', 'sort-desc');
        });
        
        // Add appropriate sort class
        header.classList.add(isAscending ? 'sort-asc' : 'sort-desc');
        
        // Sort rows
        rows.sort((a, b) => {
            const aText = a.children[columnIndex].textContent.trim();
            const bText = b.children[columnIndex].textContent.trim();
            
            let aValue = aText;
            let bValue = bText;
            
            // Try to parse as numbers
            if (!isNaN(aText) && !isNaN(bText)) {
                aValue = parseFloat(aText);
                bValue = parseFloat(bText);
            }
            
            if (aValue < bValue) return isAscending ? -1 : 1;
            if (aValue > bValue) return isAscending ? 1 : -1;
            return 0;
        });
        
        // Reorder rows in DOM
        rows.forEach(row => tbody.appendChild(row));
    }
    
    // Search functionality
    function performSearch(query) {
        console.log('Searching for:', query);
        
        // Show search suggestions (implement as needed)
        const suggestions = document.getElementById('searchSuggestions');
        if (suggestions) {
            // Populate suggestions
            suggestions.innerHTML = `
                <div class="search-suggestion">
                    <i class="fas fa-search me-2"></i>
                    Search for "${query}"
                </div>
            `;
            suggestions.style.display = 'block';
        }
    }
    
    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
    
    // Performance monitoring
    window.addEventListener('load', function() {
        console.log('KillShill Dashboard loaded successfully');
        
        // Track page load time
        const loadTime = performance.timing.loadEventEnd - performance.timing.navigationStart;
        console.log('Page load time:', loadTime + 'ms');
        
        // Dispatch loaded event
        window.dispatchEvent(new CustomEvent('killshillLoaded', {
            detail: { loadTime }
        }));
    });
    
    // Export utilities for global access
    window.KillShill = {
        setButtonLoading,
        performSearch,
        version: '1.0'
    };

})();

// CSS for animations and effects
const style = document.createElement('style');
style.textContent = `
    /* Ripple effect */
    .btn {
        position: relative;
        overflow: hidden;
    }
    
    .ripple {
        position: absolute;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.3);
        transform: scale(0);
        animation: ripple-animation 0.6s linear;
        pointer-events: none;
    }
    
    @keyframes ripple-animation {
        to {
            transform: scale(4);
            opacity: 0;
        }
    }
    
    /* Table row selection */
    .table tbody tr.selected {
        background-color: rgba(37, 99, 235, 0.1) !important;
    }
    
    .dark-theme .table tbody tr.selected {
        background-color: rgba(59, 130, 246, 0.2) !important;
    }
    
    /* Table sorting indicators */
    .table th[data-sortable]:not([data-sortable="false"]) {
        position: relative;
        user-select: none;
    }
    
    .table th.sort-asc::after {
        content: '↑';
        position: absolute;
        right: 8px;
        color: var(--primary);
    }
    
    .table th.sort-desc::after {
        content: '↓';
        position: absolute;
        right: 8px;
        color: var(--primary);
    }
    
    /* Search suggestions */
    #searchSuggestions {
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        background: var(--white);
        border: 1px solid var(--gray-200);
        border-radius: var(--radius-lg);
        box-shadow: var(--shadow-lg);
        max-height: 300px;
        overflow-y: auto;
        z-index: var(--z-dropdown);
        display: none;
    }
    
    .dark-theme #searchSuggestions {
        background: var(--dark-bg-card);
        border-color: var(--dark-border);
    }
    
    .search-suggestion {
        padding: var(--space-3) var(--space-4);
        cursor: pointer;
        transition: background-color var(--transition-fast);
    }
    
    .search-suggestion:hover {
        background-color: var(--gray-50);
    }
    
    .dark-theme .search-suggestion:hover {
        background-color: var(--dark-bg-hover);
    }
    
    /* Spinner animation */
    .spinner {
        width: 1rem;
        height: 1rem;
        border: 2px solid currentColor;
        border-right-color: transparent;
        border-radius: 50%;
        animation: spin 0.75s linear infinite;
        display: inline-block;
    }
    
    @keyframes spin {
        to {
            transform: rotate(360deg);
        }
    }
    
    /* Enhanced form focus */
    .form-group.focused .form-label,
    .form-floating.focused label {
        color: var(--primary) !important;
    }
    
    .form-group.has-value .form-label,
    .form-floating.has-value label {
        font-weight: var(--font-medium);
    }
    
    /* Smooth transitions */
    .nav-link,
    .btn,
    .form-control,
    .card {
        transition: all var(--transition-normal);
    }
    
    /* Accessibility improvements */
    .btn:focus,
    .form-control:focus,
    .nav-link:focus {
        outline: 2px solid var(--primary);
        outline-offset: 2px;
    }
    
    /* Reduced motion support */
    @media (prefers-reduced-motion: reduce) {
        *,
        *::before,
        *::after {
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.01ms !important;
        }
    }
`;
document.head.appendChild(style);