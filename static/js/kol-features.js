/**
 * KOL Analytics Platform - Interactive Features
 * Handles mini-profiles, watchlist, abuse reports, and simulation
 */

// API Base URL
const API_BASE = '/api/v1';
const ENABLE_MINI_PROFILE_TOOLTIPS = false; // Temporarily disabled (hover popups too aggressive)

// Get CSRF token for Django
function getCSRFToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
           document.querySelector('meta[name="csrf-token"]')?.content ||
           getCookie('csrftoken');
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Get auth token (for API authentication)
function getAuthToken() {
    // For Django session auth, we don't need bearer tokens
    // Authentication is handled via session cookies
    return null;
}

// Check if user is authenticated (via Django)
function isAuthenticated() {
    if (typeof window.IS_AUTHENTICATED !== 'undefined') {
        if (typeof window.IS_AUTHENTICATED === 'string') {
            return window.IS_AUTHENTICATED === 'true';
        }
        return Boolean(window.IS_AUTHENTICATED);
    }
    const bodyState = document.body?.dataset?.isAuth;
    if (typeof bodyState !== 'undefined') {
        return bodyState === 'true';
    }
    // Fallback: attempt to detect session cookie
    return document.cookie.includes('sessionid');
}

// ===================
// MINI-PROFILE TOOLTIPS
// ===================

let miniProfileCache = {};
let currentTooltip = null;
let tooltipTimeout = null;

function initMiniProfiles() {
    if (!ENABLE_MINI_PROFILE_TOOLTIPS) {
        return;
    }
    // Add hover listeners to all influencer names
    document.querySelectorAll('[data-influencer-id]').forEach(element => {
        element.style.cursor = 'pointer';
        element.style.position = 'relative';

        element.addEventListener('mouseenter', function(e) {
            const influencerId = this.getAttribute('data-influencer-id');
            tooltipTimeout = setTimeout(() => {
                showMiniProfile(influencerId, this);
            }, 300); // Show after 300ms hover
        });

        element.addEventListener('mouseleave', function() {
            clearTimeout(tooltipTimeout);
            // Delay hiding to allow moving to tooltip
            setTimeout(() => {
                if (currentTooltip && !currentTooltip.matches(':hover')) {
                    hideMiniProfile();
                }
            }, 200);
        });
    });
}

async function showMiniProfile(influencerId, targetElement) {
    // Check cache first
    if (miniProfileCache[influencerId]) {
        displayMiniProfile(miniProfileCache[influencerId], targetElement);
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/influencer/${influencerId}/mini-profile/`);
        if (!response.ok) throw new Error('Failed to fetch profile');

        const data = await response.json();
        miniProfileCache[influencerId] = data;
        displayMiniProfile(data, targetElement);
    } catch (error) {
        console.error('Error loading mini profile:', error);
    }
}

function displayMiniProfile(profile, targetElement) {
    hideMiniProfile(); // Hide any existing tooltip

    const assetFocusArray = Array.isArray(profile.asset_focus)
        ? profile.asset_focus
        : profile.asset_focus
            ? [profile.asset_focus]
            : [];
    const assetFocusText = assetFocusArray.length ? assetFocusArray.join(', ') : 'N/A';

    const tooltip = document.createElement('div');
    tooltip.className = 'mini-profile-tooltip';
    tooltip.innerHTML = `
        <div class="mini-profile-header">
            <div class="d-flex align-items-center gap-2">
                <div class="avatar-circle avatar-circle-sm hero-gradient-primary">
                    ${profile.channel_name.charAt(0).toUpperCase()}
                </div>
                <div>
                    <div class="fw-bold">${profile.channel_name}</div>
                    <div class="text-muted small">${profile.platform}</div>
                </div>
            </div>
            <button class="btn-close-mini" onclick="hideMiniProfile()">&times;</button>
        </div>
        <div class="mini-profile-stats">
            <div class="stat-item">
                <div class="stat-label">Total Calls</div>
                <div class="stat-value">${profile.total_calls}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Accuracy</div>
                <div class="stat-value text-success">${profile.accuracy}%</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Avg Return</div>
                <div class="stat-value">${profile.avg_return > 0 ? '+' : ''}${profile.avg_return}%</div>
            </div>
                </div>
                <div class="mini-profile-details">
                    <div class="mb-2">
                        <strong>Asset Focus:</strong> ${assetFocusText}
                    </div>
            <div class="mb-2">
                <strong>Recent Performance:</strong> <span class="badge badge-info">${profile.recent_performance}</span>
            </div>
        </div>
        <div class="mini-profile-actions">
            <button class="btn btn-sm btn-primary" onclick="addToWatchlist(${profile.id})">
                <i class="fas fa-star"></i> Save
            </button>
            <button class="btn btn-sm btn-secondary" onclick="viewFullProfile(${profile.id})">
                View Profile
            </button>
        </div>
    `;

    // Position the tooltip
    document.body.appendChild(tooltip);
    const rect = targetElement.getBoundingClientRect();
    tooltip.style.position = 'fixed';
    tooltip.style.top = `${rect.bottom + 10}px`;
    tooltip.style.left = `${rect.left}px`;
    tooltip.style.zIndex = '10000';

    // Adjust if going off-screen
    const tooltipRect = tooltip.getBoundingClientRect();
    if (tooltipRect.right > window.innerWidth) {
        tooltip.style.left = `${window.innerWidth - tooltipRect.width - 20}px`;
    }
    if (tooltipRect.bottom > window.innerHeight) {
        tooltip.style.top = `${rect.top - tooltipRect.height - 10}px`;
    }

    currentTooltip = tooltip;

    // Allow hovering on tooltip
    tooltip.addEventListener('mouseleave', () => {
        setTimeout(() => {
            if (!targetElement.matches(':hover')) {
                hideMiniProfile();
            }
        }, 200);
    });
}

function hideMiniProfile() {
    if (currentTooltip) {
        currentTooltip.remove();
        currentTooltip = null;
    }
}

// ===================
// WATCHLIST FUNCTIONALITY
// ===================

let userWatchlist = new Set();
let watchlistMeta = new Map();

async function loadUserWatchlist() {
    if (!isAuthenticated()) return;

    try {
        const response = await fetch(`${API_BASE}/watchlist/`, {
            credentials: 'same-origin',  // Include session cookie
            headers: {
                'X-CSRFToken': getCSRFToken()
            }
        });

        if (response.ok) {
            const data = await response.json();
            userWatchlist = new Set();
            watchlistMeta = new Map();

            data.watchlist.forEach(item => {
                const influencerId = item.influencer.id;
                userWatchlist.add(influencerId);
                watchlistMeta.set(influencerId, item.id);
            });

            updateWatchlistButtons();
        }
    } catch (error) {
        console.error('Error loading watchlist:', error);
    }
}

async function addToWatchlist(influencerId, notes = '') {
    if (!isAuthenticated()) {
        showNotification('Please login to save influencers', 'warning');
        // Redirect to login page
        window.location.href = '/auth/login/?next=' + window.location.pathname;
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/watchlist/`, {
            method: 'POST',
            credentials: 'same-origin',  // Include session cookie
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                influencer_id: influencerId,
                notes: notes
            })
        });

        const data = await response.json();

        if (response.ok) {
            userWatchlist.add(influencerId);
            if (data.watchlist_id) {
                watchlistMeta.set(influencerId, data.watchlist_id);
            }
            updateWatchlistButtons();
            showNotification('Added to watchlist!', 'success');
        } else {
            showNotification(data.error || 'Failed to add to watchlist', 'error');
        }
    } catch (error) {
        console.error('Error adding to watchlist:', error);
        showNotification('Error adding to watchlist', 'error');
    }
}

async function removeFromWatchlist(watchlistId, influencerId) {
    if (!isAuthenticated()) return;

    try {
        const response = await fetch(`${API_BASE}/watchlist/${watchlistId}/`, {
            method: 'DELETE',
            credentials: 'same-origin',  // Include session cookie
            headers: {
                'X-CSRFToken': getCSRFToken()
            }
        });

        if (response.ok) {
            userWatchlist.delete(influencerId);
            watchlistMeta.delete(influencerId);
            updateWatchlistButtons();
            showNotification('Removed from watchlist', 'success');

            // Refresh watchlist page if we're on it
            if (window.location.pathname.includes('watchlist')) {
                location.reload();
            }
        }
    } catch (error) {
        console.error('Error removing from watchlist:', error);
        showNotification('Error removing from watchlist', 'error');
    }
}

function updateWatchlistButtons() {
    document.querySelectorAll('[data-watchlist-btn]').forEach(btn => {
        const influencerId = parseInt(btn.getAttribute('data-influencer-id'));
        const isSaved = userWatchlist.has(influencerId);
        const watchlistId = watchlistMeta.get(influencerId);
        const iconOnly = btn.hasAttribute('data-icon-only');

        if (iconOnly) {
            btn.innerHTML = isSaved ? '<i class="fas fa-star"></i>' : '<i class="far fa-star"></i>';
            btn.classList.toggle('is-saved', isSaved);
            btn.setAttribute('title', isSaved ? 'Remove from watchlist' : 'Save to watchlist');
        } else {
            if (isSaved) {
                btn.innerHTML = '<i class="fas fa-star"></i> Saved';
                btn.classList.remove('btn-outline-primary');
                btn.classList.add('btn-warning');
                btn.setAttribute('title', 'Remove from watchlist');
            } else {
                btn.innerHTML = '<i class="far fa-star"></i> Save';
                btn.classList.remove('btn-warning');
                btn.classList.add('btn-outline-primary');
                btn.setAttribute('title', 'Save to watchlist');
            }
        }

        if (isSaved) {
            btn.dataset.watchlistId = watchlistId || '';
            btn.dataset.watchlistState = 'saved';
        } else {
            delete btn.dataset.watchlistId;
            btn.dataset.watchlistState = 'unsaved';
        }
    });
}

// ===================
// ABUSE REPORTING
// ===================

function showReportModal(type, id, name) {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Report ${type === 'profile' ? 'Influencer' : 'Signal'}</h5>
                    <button class="btn-close" onclick="closeReportModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <p class="text-muted">Reporting: <strong>${name}</strong></p>
                    <div class="mb-3">
                        <label class="form-label">Reason *</label>
                        <select class="form-control" id="report-reason">
                            <option value="">Select a reason...</option>
                            <option value="fake_data">Fake or Manipulated Data</option>
                            <option value="spam">Spam or Promotional Content</option>
                            <option value="manipulation">Market Manipulation</option>
                            <option value="misleading">Misleading Information</option>
                            <option value="duplicate">Duplicate Profile</option>
                            <option value="offensive">Offensive Content</option>
                            <option value="scam">Potential Scam</option>
                            <option value="other">Other</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Description *</label>
                        <textarea class="form-control" id="report-description" rows="4" placeholder="Please provide details about your report..."></textarea>
                    </div>
                    <div id="report-error" class="alert alert-danger d-none"></div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeReportModal()">Cancel</button>
                    <button class="btn btn-danger" onclick="submitReport('${type}', ${id})">Submit Report</button>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
    modal.style.display = 'flex';
}

function closeReportModal() {
    const modal = document.querySelector('.modal-overlay');
    if (modal) modal.remove();
}

async function submitReport(type, id) {
    const reason = document.getElementById('report-reason').value;
    const description = document.getElementById('report-description').value;
    const errorDiv = document.getElementById('report-error');

    // Validation
    if (!reason || !description.trim()) {
        errorDiv.textContent = 'Please fill in all required fields';
        errorDiv.classList.remove('d-none');
        return;
    }

    if (!isAuthenticated()) {
        showNotification('Please login to report', 'warning');
        closeReportModal();
        window.location.href = '/auth/login/?next=' + window.location.pathname;
        return;
    }

    try {
        const payload = {
            report_type: type,
            reason: reason,
            description: description
        };

        if (type === 'profile') {
            payload.influencer_id = id;
        } else {
            payload.trade_call_id = id;
        }

        const response = await fetch(`${API_BASE}/report/`, {
            method: 'POST',
            credentials: 'same-origin',  // Include session cookie
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (response.ok) {
            closeReportModal();
            showNotification('Report submitted successfully. Thank you!', 'success');
        } else {
            errorDiv.textContent = data.error || 'Failed to submit report';
            errorDiv.classList.remove('d-none');
        }
    } catch (error) {
        console.error('Error submitting report:', error);
        errorDiv.textContent = 'Error submitting report. Please try again.';
        errorDiv.classList.remove('d-none');
    }
}

// ===================
// SIMULATION ENGINE
// ===================

function showSimulationModal(influencerId, influencerName) {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Simulate Returns - ${influencerName}</h5>
                    <button class="btn-close" onclick="closeSimulationModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <label class="form-label">Initial Budget ($)</label>
                            <input type="number" class="form-control" id="sim-budget" value="1000" min="100" step="100">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">Time Period (days)</label>
                            <select class="form-control" id="sim-period">
                                <option value="7">Last 7 days</option>
                                <option value="30" selected>Last 30 days</option>
                                <option value="60">Last 60 days</option>
                                <option value="90">Last 90 days</option>
                            </select>
                        </div>
                    </div>
                    <button class="btn btn-primary w-100 mb-3" onclick="runSimulation(${influencerId})">
                        <i class="fas fa-calculator"></i> Calculate Returns
                    </button>
                    <div id="simulation-loading" class="text-center d-none">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p class="mt-2">Calculating...</p>
                    </div>
                    <div id="simulation-results" class="d-none">
                        <!-- Results will be inserted here -->
                    </div>
                    <div id="simulation-error" class="alert alert-danger d-none"></div>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
    modal.style.display = 'flex';
}

function closeSimulationModal() {
    const modal = document.querySelector('.modal-overlay');
    if (modal) modal.remove();
}

async function runSimulation(influencerId) {
    const budget = parseFloat(document.getElementById('sim-budget').value);
    const periodDays = parseInt(document.getElementById('sim-period').value);
    const loading = document.getElementById('simulation-loading');
    const results = document.getElementById('simulation-results');
    const errorDiv = document.getElementById('simulation-error');

    // Show loading
    loading.classList.remove('d-none');
    results.classList.add('d-none');
    errorDiv.classList.add('d-none');

    try {
        const response = await fetch(`${API_BASE}/simulate/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                influencer_id: influencerId,
                budget: budget,
                period_days: periodDays
            })
        });

        const data = await response.json();

        loading.classList.add('d-none');

        if (response.ok) {
            displaySimulationResults(data);
        } else {
            errorDiv.textContent = data.error || 'Failed to run simulation';
            errorDiv.classList.remove('d-none');
        }
    } catch (error) {
        console.error('Error running simulation:', error);
        loading.classList.add('d-none');
        errorDiv.textContent = 'Error running simulation. Please try again.';
        errorDiv.classList.remove('d-none');
    }
}

function displaySimulationResults(data) {
    const results = document.getElementById('simulation-results');
    const res = data.results;

    const returnClass = res.total_return_pct >= 0 ? 'text-success' : 'text-danger';
    const returnIcon = res.total_return_pct >= 0 ? 'fa-arrow-up' : 'fa-arrow-down';

    results.innerHTML = `
        <div class="simulation-summary">
            <h6 class="mb-3">Simulation Results</h6>
            <div class="row text-center mb-4">
                <div class="col-4">
                    <div class="stat-card">
                        <div class="stat-label">Initial Investment</div>
                        <div class="stat-value">$${data.simulation_parameters.initial_budget.toLocaleString()}</div>
                    </div>
                </div>
                <div class="col-4">
                    <div class="stat-card">
                        <div class="stat-label">Final Value</div>
                        <div class="stat-value ${returnClass}">$${res.final_value.toLocaleString()}</div>
                    </div>
                </div>
                <div class="col-4">
                    <div class="stat-card">
                        <div class="stat-label">Total Return</div>
                        <div class="stat-value ${returnClass}">
                            <i class="fas ${returnIcon}"></i> ${res.total_return_pct}%
                        </div>
                    </div>
                </div>
            </div>
            <div class="row text-center">
                <div class="col-3">
                    <div class="stat-label">Total Calls</div>
                    <div class="stat-value-sm">${res.total_calls}</div>
                </div>
                <div class="col-3">
                    <div class="stat-label">Success Rate</div>
                    <div class="stat-value-sm text-success">${res.success_rate}%</div>
                </div>
                <div class="col-3">
                    <div class="stat-label">Avg Win</div>
                    <div class="stat-value-sm text-success">$${res.avg_win.toLocaleString()}</div>
                </div>
                <div class="col-3">
                    <div class="stat-label">Avg Loss</div>
                    <div class="stat-value-sm text-danger">$${Math.abs(res.avg_loss).toLocaleString()}</div>
                </div>
            </div>
            <div class="alert alert-info mt-3">
                <i class="fas fa-info-circle"></i>
                <small>This simulation assumes equal allocation per trade and is based on historical performance. Past performance does not guarantee future results.</small>
            </div>
        </div>
    `;

    results.classList.remove('d-none');
}

// ===================
// NOTIFICATIONS
// ===================

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `toast-notification toast-${type}`;
    notification.innerHTML = `
        <div class="toast-content">
            <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : type === 'warning' ? 'exclamation-triangle' : 'info-circle'}"></i>
            <span>${message}</span>
        </div>
    `;

    document.body.appendChild(notification);

    setTimeout(() => notification.classList.add('show'), 100);
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// ===================
// VIEW FULL PROFILE
// ===================

function viewFullProfile(influencerId) {
    window.location.href = `/dashboard/influencer/${influencerId}/`;
}

// ===================
// INITIALIZATION
// ===================

document.addEventListener('DOMContentLoaded', function() {
    // Initialize mini-profiles (disabled when ENABLE_MINI_PROFILE_TOOLTIPS is false)
    initMiniProfiles();

    // Load user's watchlist
    loadUserWatchlist();

    // Add watchlist button listeners
    document.querySelectorAll('[data-watchlist-btn]').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            const influencerId = parseInt(this.getAttribute('data-influencer-id'));

            if (userWatchlist.has(influencerId)) {
                const watchlistId = parseInt(this.dataset.watchlistId, 10);
                if (watchlistId) {
                    removeFromWatchlist(watchlistId, influencerId);
                } else {
                    showNotification('Already in watchlist', 'info');
                }
            } else {
                addToWatchlist(influencerId);
            }
        });
    });

    // Close modals on overlay click
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('modal-overlay')) {
            closeReportModal();
            closeSimulationModal();
        }
    });
});

// Export for global use
window.KOLFeatures = {
    showMiniProfile,
    hideMiniProfile,
    addToWatchlist,
    removeFromWatchlist,
    showReportModal,
    closeReportModal,
    showSimulationModal,
    closeSimulationModal,
    runSimulation,
    showNotification,
    viewFullProfile
};
