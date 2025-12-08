/**
 * Modern SPA Navigation System
 * Provides smooth, fast navigation without full page reloads
 */

class SPANavigation {
    constructor() {
        this.currentPage = null;
        this.isLoading = false;
        this.cache = new Map();
        this.loadingTimeout = null;
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.createLoadingOverlay();
        this.preloadCriticalPages();
        this.setupPageTransitions();
        
        // Store initial page state
        this.currentPage = window.location.pathname;
        history.replaceState({ path: this.currentPage }, '', this.currentPage);
    }
    
    setupEventListeners() {
        // Handle navigation clicks
        document.addEventListener('click', (e) => {
            const link = e.target.closest('a[href]');
            if (this.shouldInterceptLink(link)) {
                e.preventDefault();
                this.addLinkLoadingState(link);
                this.navigateTo(link.href);
            }
        });
        
        // Handle browser back/forward
        window.addEventListener('popstate', (e) => {
            if (e.state && e.state.path) {
                this.navigateTo(e.state.path, false);
            }
        });
        
        // Preload on hover
        document.addEventListener('mouseover', (e) => {
            const link = e.target.closest('a[href]');
            if (this.shouldInterceptLink(link)) {
                this.preloadPage(link.href);
            }
        });
    }
    
    shouldInterceptLink(link) {
        if (!link) return false;
        
        const href = link.getAttribute('href');
        if (!href) return false;
        
        // Skip external links
        if (href.startsWith('http') && !href.includes(window.location.hostname)) {
            return false;
        }
        
        // Skip non-dashboard links
        if (!href.includes('/dashboard/') && !href.startsWith('/dashboard/')) {
            return false;
        }
        
        // Skip logout and auth links
        if (href.includes('/auth/') || href.includes('/logout/')) {
            return false;
        }
        
        // Skip if link has target="_blank"
        if (link.getAttribute('target') === '_blank') {
            return false;
        }
        
        return true;
    }
    
    async navigateTo(url, addToHistory = true) {
        if (this.isLoading || url === this.currentPage) return;
        
        this.isLoading = true;
        this.showLoadingState();
        
        try {
            const content = await this.fetchPage(url);
            await this.updatePage(content, url);
            
            if (addToHistory) {
                history.pushState({ path: url }, '', url);
            }
            
            this.currentPage = url;
            this.updateActiveNavigation(url);
            
        } catch (error) {
            console.error('Navigation error:', error);
            this.showError('Failed to load page. Please try again.');
            
            // Fallback to normal navigation
            if (addToHistory) {
                window.location.href = url;
            }
        } finally {
            this.isLoading = false;
            this.hideLoadingState();
            this.removeLinkLoadingStates();
        }
    }
    
    async fetchPage(url) {
        // Check cache first
        if (this.cache.has(url)) {
            return this.cache.get(url);
        }
        
        const response = await fetch(url, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'text/html,application/xhtml+xml'
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const html = await response.text();
        
        // Cache the result
        this.cache.set(url, html);
        
        // Limit cache size
        if (this.cache.size > 10) {
            const firstKey = this.cache.keys().next().value;
            this.cache.delete(firstKey);
        }
        
        return html;
    }
    
    async updatePage(html, url) {
        const parser = new DOMParser();
        const newDoc = parser.parseFromString(html, 'text/html');
        
        // Extract the main content
        const newContent = newDoc.querySelector('.page-content');
        const newTitle = newDoc.querySelector('title');
        const newPageTitle = newDoc.querySelector('.page-title');
        
        if (!newContent) {
            throw new Error('Invalid page structure');
        }
        
        // Update page title
        if (newTitle) {
            document.title = newTitle.textContent;
        }
        
        // Update page header title
        if (newPageTitle) {
            const currentPageTitle = document.querySelector('.page-title');
            if (currentPageTitle) {
                currentPageTitle.textContent = newPageTitle.textContent;
            }
        }
        
        // Smooth transition
        await this.transitionContent(newContent);
        
        // Re-initialize any JavaScript components
        this.reinitializeComponents();
        
        // Scroll to top smoothly
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    
    async transitionContent(newContent) {
        const currentContent = document.querySelector('.page-content');
        
        // Add page transition classes for smooth animation
        this.addPageTransitionClasses();
        
        // Add exit animation
        currentContent.classList.add('spa-page-exit');
        
        // Wait for fade out animation
        await new Promise(resolve => setTimeout(resolve, 300));
        
        // Replace content
        currentContent.innerHTML = newContent.innerHTML;
        
        // Remove exit classes and add enter animation
        currentContent.classList.remove('spa-page-exit');
        currentContent.classList.add('spa-page-enter');
        
        // Remove transition classes after animation completes
        setTimeout(() => {
            currentContent.classList.remove('spa-page-enter');
            this.removePageTransitionClasses();
        }, 400);
    }
    
    updateActiveNavigation(url) {
        // Remove all active states
        document.querySelectorAll('.nav-link.active').forEach(link => {
            link.classList.remove('active');
        });
        
        // Add active state to current page
        const currentLink = document.querySelector(`a[href="${url}"]`);
        if (currentLink && currentLink.classList.contains('nav-link')) {
            currentLink.classList.add('active');
        }
        
        // Handle URL patterns for dynamic matching
        const urlPatterns = {
            '/dashboard/': 'home',
            '/dashboard/analytics/': 'analytics',
            '/dashboard/leaderboard/': 'leaderboard',
            '/dashboard/trending-kols/': 'trending_kols',
            '/dashboard/submit-influencer/': 'submit_influencer',
            '/dashboard/watchlist/': 'watchlist',
            '/dashboard/alerts/': 'alerts',
            '/dashboard/submissions-tracking/': 'submissions_tracking',
            '/dashboard/settings/': 'settings',
            '/dashboard/admin-management/': 'admin_management'
        };
        
        for (const [pattern, name] of Object.entries(urlPatterns)) {
            if (url.includes(pattern)) {
                const link = document.querySelector(`.nav-link[href*="${pattern}"]`);
                if (link) {
                    link.classList.add('active');
                }
                break;
            }
        }
    }
    
    createLoadingOverlay() {
        const overlay = document.createElement('div');
        overlay.id = 'spa-loading-overlay';
        overlay.innerHTML = `
            <div class="loading-content">
                <div class="loading-spinner">
                    <div class="spinner-ring"></div>
                    <div class="spinner-ring"></div>
                    <div class="spinner-ring"></div>
                </div>
                <div class="loading-text">Loading...</div>
            </div>
        `;
        
        // Add styles
        const style = document.createElement('style');
        style.textContent = `
            #spa-loading-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(var(--bs-body-bg-rgb), 0.9);
                backdrop-filter: blur(10px);
                z-index: 9999;
                display: none;
                align-items: center;
                justify-content: center;
                transition: all 0.3s ease;
            }
            
            .loading-content {
                text-align: center;
                color: var(--bs-primary);
            }
            
            .loading-spinner {
                position: relative;
                width: 60px;
                height: 60px;
                margin: 0 auto 20px;
            }
            
            .spinner-ring {
                position: absolute;
                width: 100%;
                height: 100%;
                border: 3px solid transparent;
                border-top: 3px solid var(--bs-primary);
                border-radius: 50%;
                animation: spin 1.2s cubic-bezier(0.5, 0, 0.5, 1) infinite;
            }
            
            .spinner-ring:nth-child(1) { animation-delay: -0.45s; }
            .spinner-ring:nth-child(2) { animation-delay: -0.3s; }
            .spinner-ring:nth-child(3) { animation-delay: -0.15s; }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .loading-text {
                font-weight: 500;
                font-size: 1.1rem;
            }
            
            .dark-theme #spa-loading-overlay {
                background: rgba(var(--dark-bg-primary-rgb), 0.9);
            }
        `;
        
        document.head.appendChild(style);
        document.body.appendChild(overlay);
    }
    
    showLoadingState() {
        // Clear any existing timeout
        if (this.loadingTimeout) {
            clearTimeout(this.loadingTimeout);
        }
        
        // Show loading overlay after a short delay
        this.loadingTimeout = setTimeout(() => {
            const overlay = document.getElementById('spa-loading-overlay');
            if (overlay && this.isLoading) {
                overlay.style.display = 'flex';
                requestAnimationFrame(() => {
                    overlay.style.opacity = '1';
                });
            }
        }, 100); // Only show if loading takes more than 100ms
    }
    
    hideLoadingState() {
        if (this.loadingTimeout) {
            clearTimeout(this.loadingTimeout);
            this.loadingTimeout = null;
        }
        
        const overlay = document.getElementById('spa-loading-overlay');
        if (overlay) {
            overlay.style.opacity = '0';
            setTimeout(() => {
                overlay.style.display = 'none';
            }, 300);
        }
    }
    
    showError(message) {
        // Create and show error notification
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger alert-dismissible fade show position-fixed';
        errorDiv.style.cssText = `
            top: 20px;
            right: 20px;
            z-index: 10000;
            min-width: 300px;
        `;
        errorDiv.innerHTML = `
            <i class="fas fa-exclamation-triangle me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(errorDiv);
        
        // Auto remove after 5 seconds
        setTimeout(() => {
            if (errorDiv.parentNode) {
                errorDiv.remove();
            }
        }, 5000);
    }
    
    async preloadPage(url) {
        if (this.cache.has(url) || this.isLoading) return;
        
        try {
            await this.fetchPage(url);
        } catch (error) {
            // Silently fail preloading
            console.debug('Preload failed for:', url);
        }
    }
    
    preloadCriticalPages() {
        // Preload commonly visited pages
        const criticalPages = [
            '/dashboard/',
            '/dashboard/analytics/',
            '/dashboard/submit-influencer/',
            '/dashboard/settings/'
        ];
        
        criticalPages.forEach(page => {
            setTimeout(() => this.preloadPage(page), Math.random() * 2000);
        });
    }
    
    setupPageTransitions() {
        // Add CSS for smooth page transitions
        const style = document.createElement('style');
        style.textContent = `
            .page-content {
                transition: opacity 0.3s ease, transform 0.3s ease;
            }
            
            .page-transition-enter {
                opacity: 0;
                transform: translateY(20px);
            }
            
            .page-transition-enter-active {
                opacity: 1;
                transform: translateY(0);
            }
        `;
        document.head.appendChild(style);
    }
    
    reinitializeComponents() {
        // Re-initialize Bootstrap components
        if (window.bootstrap) {
            // Tooltips
            document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
                new bootstrap.Tooltip(el);
            });
            
            // Popovers
            document.querySelectorAll('[data-bs-toggle="popover"]').forEach(el => {
                new bootstrap.Popover(el);
            });
        }
        
        // Re-initialize any chart libraries if present
        if (window.Chart && typeof window.initializeCharts === 'function') {
            window.initializeCharts();
        }
        
        // Trigger custom event for other components
        document.dispatchEvent(new CustomEvent('spa:pageLoaded', {
            detail: { url: this.currentPage }
        }));
    }
    
    // Public methods
    clearCache() {
        this.cache.clear();
    }
    
    preloadUrl(url) {
        return this.preloadPage(url);
    }
    
    isPageCached(url) {
        return this.cache.has(url);
    }
    
    addLinkLoadingState(link) {
        if (link && link.classList.contains('nav-link')) {
            link.classList.add('spa-loading');
            // Add subtle pulse effect to sidebar during navigation
            const sidebar = document.getElementById('sidebar');
            if (sidebar) {
                sidebar.classList.add('spa-updating');
            }
        }
    }
    
    removeLinkLoadingStates() {
        // Remove loading states from all navigation links
        document.querySelectorAll('.nav-link.spa-loading').forEach(link => {
            link.classList.remove('spa-loading');
        });
        
        // Remove sidebar updating state
        const sidebar = document.getElementById('sidebar');
        if (sidebar) {
            sidebar.classList.remove('spa-updating');
        }
    }
    
    addPageTransitionClasses() {
        const pageContent = document.querySelector('.page-content');
        if (pageContent) {
            pageContent.classList.add('spa-transitioning');
        }
    }
    
    removePageTransitionClasses() {
        const pageContent = document.querySelector('.page-content');
        if (pageContent) {
            pageContent.classList.remove('spa-transitioning');
        }
    }
}

// Initialize SPA Navigation when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.spaNav = new SPANavigation();
    
    // Add smooth hover effects to navigation
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('mouseenter', function() {
            if (!this.classList.contains('active')) {
                this.style.transform = 'translateX(8px)';
            }
        });
        
        link.addEventListener('mouseleave', function() {
            this.style.transform = '';
        });
    });
});

// Enhanced navigation indicators
document.addEventListener('DOMContentLoaded', () => {
    // Add loading states to navigation links
    const style = document.createElement('style');
    style.textContent = `
        .nav-link {
            position: relative;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            overflow: hidden;
        }
        
        .nav-link::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
            transition: left 0.5s;
        }
        
        .nav-link:hover::before {
            left: 100%;
        }
        
        .nav-link.loading {
            opacity: 0.7;
            pointer-events: none;
        }
        
        .nav-link.loading::after {
            content: '';
            position: absolute;
            right: 10px;
            top: 50%;
            transform: translateY(-50%);
            width: 12px;
            height: 12px;
            border: 2px solid transparent;
            border-top: 2px solid currentColor;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            0% { transform: translateY(-50%) rotate(0deg); }
            100% { transform: translateY(-50%) rotate(360deg); }
        }
    `;
    document.head.appendChild(style);
});
