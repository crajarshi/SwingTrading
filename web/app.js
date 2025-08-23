/**
 * SwingTrading Scanner - Main Application
 */

// ============================================================================
// State Management
// ============================================================================

const state = {
    controls: {},
    activeRun: null,
    results: [],
    metadata: null,
    isDirty: false,
    history: [],
    ws: null,
    reconnectAttempts: 0
};

// ============================================================================
// API Client
// ============================================================================

const api = {
    baseURL: 'http://localhost:8000',
    
    async post(endpoint, data) {
        const response = await fetch(`${this.baseURL}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`API error: ${response.statusText}`);
        return response.json();
    },
    
    async get(endpoint) {
        const response = await fetch(`${this.baseURL}${endpoint}`);
        if (!response.ok) throw new Error(`API error: ${response.statusText}`);
        return response.json();
    },
    
    async delete(endpoint) {
        const response = await fetch(`${this.baseURL}${endpoint}`, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error(`API error: ${response.statusText}`);
        return response.json();
    }
};

// ============================================================================
// Formatting Utilities
// ============================================================================

const format = {
    price(value) {
        return value ? `$${value.toFixed(2)}` : '--';
    },
    
    score(value) {
        return value ? value.toFixed(2) : '--';
    },
    
    percent(value) {
        return value != null ? `${value.toFixed(1)}%` : '--';
    },
    
    ratio(value) {
        return value ? `${value.toFixed(1)}x` : '--';
    },
    
    number(value, decimals = 0) {
        return value ? value.toFixed(decimals) : '--';
    },
    
    largeNumber(value) {
        if (!value) return '--';
        if (value >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
        if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
        if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
        return value.toFixed(0);
    }
};

// ============================================================================
// Toast Notifications
// ============================================================================

function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ============================================================================
// Controls Management
// ============================================================================

function initializeControls() {
    // Load saved controls from localStorage
    const saved = localStorage.getItem('swingtrading_controls');
    if (saved) {
        try {
            const savedControls = JSON.parse(saved);
            restoreControls(savedControls);
        } catch (e) {
            console.error('Failed to load saved controls:', e);
        }
    }
    
    // Add event listeners to all controls
    document.querySelectorAll('input, select, textarea').forEach(control => {
        control.addEventListener('change', handleControlChange);
    });
    
    // Weight sliders special handling
    document.querySelectorAll('.weight-slider').forEach(slider => {
        slider.addEventListener('input', handleWeightChange);
    });
    
    // Accordion toggle
    document.querySelector('.accordion-toggle').addEventListener('click', function() {
        const content = this.parentElement.nextElementSibling;
        const expanded = this.getAttribute('aria-expanded') === 'true';
        this.setAttribute('aria-expanded', !expanded);
        this.textContent = expanded ? '▶ Advanced Settings' : '▼ Advanced Settings';
        content.style.display = expanded ? 'none' : 'block';
    });
    
    // Preset buttons
    document.querySelectorAll('.chip').forEach(chip => {
        chip.addEventListener('click', () => applyPreset(chip.dataset.preset));
    });
    
    // Reset and Save buttons
    document.getElementById('reset-btn').addEventListener('click', resetToDefaults);
    document.getElementById('save-defaults-btn').addEventListener('click', saveAsDefaults);
}

function handleControlChange() {
    markDirty();
    saveControlsToLocalStorage();
}

function handleWeightChange() {
    // Update displayed values
    document.getElementById('pullback-val').textContent = document.getElementById('weight-pullback').value;
    document.getElementById('trend-val').textContent = document.getElementById('weight-trend').value;
    document.getElementById('rsi-val').textContent = document.getElementById('weight-rsi').value;
    document.getElementById('volume-val').textContent = document.getElementById('weight-volume').value;
    
    // Check sum and auto-normalize
    const weights = [
        parseFloat(document.getElementById('weight-pullback').value),
        parseFloat(document.getElementById('weight-trend').value),
        parseFloat(document.getElementById('weight-rsi').value),
        parseFloat(document.getElementById('weight-volume').value)
    ];
    
    const sum = weights.reduce((a, b) => a + b, 0);
    document.getElementById('weight-sum').textContent = `${sum.toFixed(0)}%`;
    
    if (Math.abs(sum - 100) > 0.1) {
        document.getElementById('weight-normalized').style.display = 'inline-block';
    } else {
        document.getElementById('weight-normalized').style.display = 'none';
    }
    
    markDirty();
    saveControlsToLocalStorage();
}

function markDirty() {
    if (state.activeRun && state.activeRun.state === 'running') return;
    
    state.isDirty = true;
    const btn = document.getElementById('run-btn');
    btn.textContent = 'Apply & Re-Run';
    btn.classList.add('edited');
    
    // Show edited overlay if results exist
    if (state.results.length > 0) {
        document.getElementById('edited-overlay').style.display = 'block';
        document.getElementById('results-container').classList.add('dimmed');
    }
}

function clearDirty() {
    state.isDirty = false;
    const btn = document.getElementById('run-btn');
    btn.textContent = 'Run Scan';
    btn.classList.remove('edited');
    
    document.getElementById('edited-overlay').style.display = 'none';
    document.getElementById('results-container').classList.remove('dimmed');
}

function getControls() {
    const controls = {};
    
    // Quick controls
    const tickers = document.getElementById('ticker-input').value;
    if (tickers) controls.tickers = tickers.split(',').map(t => t.trim());
    
    controls.feed = document.getElementById('feed-select').value;
    controls.bypass_regime = document.getElementById('regime-bypass').checked;
    controls.sort_by = document.getElementById('sort-select').value;
    
    // Filters
    controls.min_price = parseFloat(document.getElementById('min-price').value);
    controls.max_gap_percent = parseFloat(document.getElementById('max-gap').value);
    controls.min_atr_ratio = parseFloat(document.getElementById('min-atr').value);
    controls.min_dollar_volume = parseFloat(document.getElementById('min-volume').value) * 1e6;
    
    // Indicators
    controls.atr_period = parseInt(document.getElementById('atr-period').value);
    controls.rsi_period = parseInt(document.getElementById('rsi-period').value);
    controls.sma_short = parseInt(document.getElementById('sma-short').value);
    controls.sma_long = parseInt(document.getElementById('sma-long').value);
    
    // Weights (auto-normalized)
    const weights = {
        pullback_proximity: parseFloat(document.getElementById('weight-pullback').value),
        trend_strength: parseFloat(document.getElementById('weight-trend').value),
        rsi_headroom: parseFloat(document.getElementById('weight-rsi').value),
        volume_ratio: parseFloat(document.getElementById('weight-volume').value)
    };
    const sum = Object.values(weights).reduce((a, b) => a + b, 0);
    if (Math.abs(sum - 100) > 0.1) {
        // Auto-normalize
        Object.keys(weights).forEach(key => {
            weights[key] = (weights[key] / sum) * 100;
        });
    }
    controls.weights = weights;
    
    // Performance
    controls.max_workers = parseInt(document.getElementById('max-workers').value);
    controls.rate_limit_per_minute = parseInt(document.getElementById('rate-limit').value);
    controls.task_timeout = parseInt(document.getElementById('timeout').value);
    controls.rate_limit_start_full = document.getElementById('start-full').checked;
    
    return controls;
}

function restoreControls(controls) {
    if (controls.tickers) document.getElementById('ticker-input').value = controls.tickers.join(', ');
    if (controls.feed) document.getElementById('feed-select').value = controls.feed;
    if (controls.bypass_regime != null) document.getElementById('regime-bypass').checked = controls.bypass_regime;
    if (controls.sort_by) document.getElementById('sort-select').value = controls.sort_by;
    
    if (controls.min_price != null) document.getElementById('min-price').value = controls.min_price;
    if (controls.max_gap_percent != null) document.getElementById('max-gap').value = controls.max_gap_percent;
    if (controls.min_atr_ratio != null) document.getElementById('min-atr').value = controls.min_atr_ratio;
    if (controls.min_dollar_volume != null) document.getElementById('min-volume').value = controls.min_dollar_volume / 1e6;
    
    if (controls.atr_period) document.getElementById('atr-period').value = controls.atr_period;
    if (controls.rsi_period) document.getElementById('rsi-period').value = controls.rsi_period;
    if (controls.sma_short) document.getElementById('sma-short').value = controls.sma_short;
    if (controls.sma_long) document.getElementById('sma-long').value = controls.sma_long;
    
    if (controls.weights) {
        document.getElementById('weight-pullback').value = controls.weights.pullback_proximity || 30;
        document.getElementById('weight-trend').value = controls.weights.trend_strength || 25;
        document.getElementById('weight-rsi').value = controls.weights.rsi_headroom || 25;
        document.getElementById('weight-volume').value = controls.weights.volume_ratio || 20;
        handleWeightChange();
    }
    
    if (controls.max_workers) document.getElementById('max-workers').value = controls.max_workers;
    if (controls.rate_limit_per_minute) document.getElementById('rate-limit').value = controls.rate_limit_per_minute;
    if (controls.task_timeout) document.getElementById('timeout').value = controls.task_timeout;
    if (controls.rate_limit_start_full != null) document.getElementById('start-full').checked = controls.rate_limit_start_full;
}

function saveControlsToLocalStorage() {
    const controls = getControls();
    localStorage.setItem('swingtrading_controls', JSON.stringify(controls));
}

function applyPreset(preset) {
    const presets = {
        conservative: {
            min_price: 10,
            max_gap_percent: 10,
            min_atr_ratio: 0.015,
            min_dollar_volume: 10,
            bypass_regime: false
        },
        balanced: {
            min_price: 5,
            max_gap_percent: 15,
            min_atr_ratio: 0.01,
            min_dollar_volume: 5,
            bypass_regime: false
        },
        aggressive: {
            min_price: 2,
            max_gap_percent: 25,
            min_atr_ratio: 0.005,
            min_dollar_volume: 2,
            bypass_regime: true
        }
    };
    
    const settings = presets[preset];
    if (settings) {
        restoreControls(settings);
        markDirty();
        
        // Update active preset chip
        document.querySelectorAll('.chip').forEach(chip => {
            chip.classList.toggle('chip-active', chip.dataset.preset === preset);
        });
    }
}

function resetToDefaults() {
    applyPreset('balanced');
    showToast('Reset to default settings');
}

async function saveAsDefaults() {
    try {
        const controls = getControls();
        await api.post('/api/config/save', controls);
        showToast('Settings saved as default', 'success');
    } catch (error) {
        showToast('Failed to save settings', 'error');
    }
}

// ============================================================================
// Scan Management
// ============================================================================

async function startScan() {
    if (state.activeRun && state.activeRun.state === 'running') {
        return;
    }
    
    try {
        // Get current controls
        const controls = getControls();
        
        // Start scan
        const response = await api.post('/api/scan', controls);
        const runId = response.run_id;
        
        // Store run ID for reconnection
        sessionStorage.setItem('active_run_id', runId);
        
        // Update state
        state.activeRun = {
            run_id: runId,
            state: 'running',
            started_at: new Date()
        };
        
        // Clear dirty state
        clearDirty();
        
        // Update UI
        updateRunStatus('running');
        showProgressBar(true);
        clearResults();
        
        // Connect WebSocket
        connectWebSocket(runId);
        
    } catch (error) {
        console.error('Failed to start scan:', error);
        showToast('Failed to start scan', 'error');
    }
}

async function cancelScan() {
    if (!state.activeRun || state.activeRun.state !== 'running') return;
    
    if (confirm('Cancel scan in progress?')) {
        try {
            await api.delete(`/api/scan/${state.activeRun.run_id}`);
            updateRunStatus('canceled');
            showToast('Scan canceled. No changes saved.', 'warning');
        } catch (error) {
            console.error('Failed to cancel scan:', error);
        }
    }
}

function connectWebSocket(runId) {
    // Close existing connection
    if (state.ws) {
        state.ws.close();
    }
    
    // Create new WebSocket connection
    const wsUrl = `ws://localhost:8000/ws/scan/${runId}`;
    state.ws = new WebSocket(wsUrl);
    
    state.ws.onopen = () => {
        console.log('WebSocket connected');
        state.reconnectAttempts = 0;
    };
    
    state.ws.onmessage = (event) => {
        const update = JSON.parse(event.data);
        handleProgressUpdate(update);
    };
    
    state.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    state.ws.onclose = () => {
        console.log('WebSocket closed');
        
        // Attempt reconnection if run is still active
        if (state.activeRun && state.activeRun.state === 'running') {
            if (state.reconnectAttempts < 3) {
                state.reconnectAttempts++;
                setTimeout(() => connectWebSocket(runId), 1000);
            } else {
                // Fall back to polling
                startPolling(runId);
            }
        }
    };
}

function startPolling(runId) {
    const pollInterval = setInterval(async () => {
        try {
            const status = await api.get(`/api/scan/${runId}/status`);
            
            if (status.state !== 'running') {
                clearInterval(pollInterval);
                await loadResults(runId);
            }
        } catch (error) {
            clearInterval(pollInterval);
        }
    }, 1000);
}

function handleProgressUpdate(update) {
    // Update progress bar
    const progress = update.progress;
    updateProgress(progress.done, progress.total, progress.partial_results);
    
    // Handle state changes
    if (update.state === 'done') {
        updateRunStatus('done');
        loadResults(update.run_id);
        showToast(`Scan complete • ${progress.partial_results} results`, 'success');
    } else if (update.state === 'error') {
        updateRunStatus('error');
        handleScanError(update.error);
    } else if (update.state === 'canceled') {
        updateRunStatus('canceled');
    }
}

async function loadResults(runId) {
    try {
        const response = await api.get(`/api/scan/${runId}/results`);
        state.results = response.results;
        state.metadata = response.metadata;
        
        displayResults();
        showProgressBar(false);
        
        // Update run header
        updateRunHeader();
        
    } catch (error) {
        console.error('Failed to load results:', error);
        showToast('Failed to load results', 'error');
    }
}

function handleScanError(error) {
    showProgressBar(false);
    
    // Map error codes to user-friendly messages
    const errorMessages = {
        2: 'Configuration Invalid. Check Settings.',
        3: 'Rate limited. Reduce workers or increase timeout.',
        4: 'Insufficient data. Increase history or lower min bars.'
    };
    
    const message = errorMessages[error.code] || error.title;
    showToast(message, 'error', 5000);
    
    // Show error details in console
    if (error.logs && error.logs.length > 0) {
        console.error('Error details:', error.logs.join('\n'));
    }
}

// ============================================================================
// Results Display
// ============================================================================

function displayResults() {
    const container = document.getElementById('results-container');
    const tableWrapper = document.getElementById('results-table-wrapper');
    const tbody = document.getElementById('results-tbody');
    
    // Hide empty states
    document.getElementById('empty-never-run').style.display = 'none';
    document.getElementById('empty-regime').style.display = 'none';
    document.getElementById('empty-no-results').style.display = 'none';
    
    if (state.results.length === 0) {
        // Show appropriate empty state
        document.getElementById('empty-no-results').style.display = 'block';
        document.getElementById('universe-count').textContent = state.metadata?.universe_size || 0;
        tableWrapper.style.display = 'none';
    } else {
        // Sort results
        const sortBy = document.getElementById('sort-select').value;
        const sorted = [...state.results].sort((a, b) => {
            if (sortBy === 'score') return b.score - a.score;
            if (sortBy === 'rsi14') return a.rsi14 - b.rsi14;
            if (sortBy === 'gap_percent') return b.gap_percent - a.gap_percent;
            return 0;
        });
        
        // Build table rows
        tbody.innerHTML = '';
        sorted.forEach(result => {
            const row = createResultRow(result);
            tbody.appendChild(row);
        });
        
        tableWrapper.style.display = 'block';
    }
}

function createResultRow(result) {
    const row = document.createElement('tr');
    row.dataset.symbol = result.symbol;
    
    // Calculate derived fields
    const volumeRatio = result.volume_avg_10d > 0 ? result.volume / result.volume_avg_10d : 0;
    const trendVsSMA50 = result.sma50 ? ((result.close - result.sma50) / result.sma50) * 100 : null;
    const pullbackFromHigh20 = result.high20 ? ((result.high20 - result.close) / result.high20) * 100 : null;
    
    row.innerHTML = `
        <td class="cell-symbol">${result.symbol}</td>
        <td>${format.price(result.close)}</td>
        <td class="cell-score">
            ${format.score(result.score)}
            <div class="score-bar-bg">
                <div class="score-bar-fill" style="width: ${result.score}%"></div>
            </div>
        </td>
        <td>
            ${format.number(result.rsi14, 1)}
            ${result.rsi14 < 30 ? '<span class="rsi-indicator rsi-oversold" title="Oversold"></span>' : ''}
            ${result.rsi14 > 70 ? '<span class="rsi-indicator rsi-overbought" title="Overbought"></span>' : ''}
        </td>
        <td>${format.percent(result.gap_percent)}</td>
        <td>${format.ratio(volumeRatio)}</td>
        <td>${trendVsSMA50 != null ? format.percent(trendVsSMA50) : '--'}</td>
        <td>${pullbackFromHigh20 != null ? format.percent(pullbackFromHigh20) : '--'}</td>
    `;
    
    row.addEventListener('click', () => openDetailDrawer(result));
    
    return row;
}

function clearResults() {
    document.getElementById('results-tbody').innerHTML = '';
    document.getElementById('results-table-wrapper').style.display = 'none';
    document.getElementById('empty-never-run').style.display = 'block';
}

// ============================================================================
// Detail Drawer
// ============================================================================

function openDetailDrawer(result) {
    // Update drawer content
    document.getElementById('drawer-symbol').textContent = result.symbol;
    document.getElementById('drawer-price').textContent = format.price(result.close);
    document.getElementById('drawer-date').textContent = state.metadata?.last_session || '--';
    
    // Indicators
    document.getElementById('drawer-atr').textContent = format.number(result.atr20, 2);
    document.getElementById('drawer-rsi').textContent = format.number(result.rsi14, 1);
    document.getElementById('drawer-sma20').textContent = format.price(result.sma20);
    document.getElementById('drawer-sma50').textContent = format.price(result.sma50);
    
    // Score breakdown (simplified calculation)
    const totalScore = result.score;
    document.getElementById('drawer-total-score').textContent = format.score(totalScore);
    
    // Estimate component scores
    const components = {
        pullback: totalScore * 0.3,
        trend: totalScore * 0.25,
        rsi: totalScore * 0.25,
        volume: totalScore * 0.2
    };
    
    Object.keys(components).forEach(key => {
        const value = components[key];
        const percentage = (value / 25) * 100; // Max 25 points per component
        document.getElementById(`score-${key}`).style.width = `${Math.min(percentage, 100)}%`;
        document.getElementById(`score-${key}-val`).textContent = value.toFixed(1);
    });
    
    // Liquidity
    document.getElementById('drawer-dollar-volume').textContent = format.largeNumber(result.dollar_volume_10d_avg);
    
    // Show drawer
    document.getElementById('detail-drawer').style.display = 'block';
    document.querySelector('.main-layout').classList.add('drawer-open');
}

function closeDetailDrawer() {
    document.getElementById('detail-drawer').style.display = 'none';
    document.querySelector('.main-layout').classList.remove('drawer-open');
}

// ============================================================================
// UI Updates
// ============================================================================

function updateRunStatus(status) {
    const badge = document.getElementById('status-badge');
    const runBtn = document.getElementById('run-btn');
    const cancelBtn = document.getElementById('cancel-btn');
    
    badge.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    badge.className = `status-badge ${status}`;
    
    if (status === 'running') {
        runBtn.style.display = 'none';
        cancelBtn.style.display = 'inline-flex';
    } else {
        runBtn.style.display = 'inline-flex';
        cancelBtn.style.display = 'none';
    }
}

function showProgressBar(show) {
    document.getElementById('progress-container').style.display = show ? 'block' : 'none';
}

function updateProgress(done, total, partialResults) {
    const fill = document.getElementById('progress-fill');
    const text = document.getElementById('progress-text');
    
    const percentage = total > 0 ? (done / total) * 100 : 0;
    fill.style.width = `${percentage}%`;
    text.textContent = `${done} / ${total}${partialResults ? ` (${partialResults} results)` : ''}`;
}

function updateRunHeader() {
    if (!state.metadata) return;
    
    const header = document.getElementById('run-header');
    const info = document.getElementById('run-info');
    
    const tickerCount = state.metadata.universe_size;
    const feed = state.metadata.feed?.toUpperCase() || 'IEX';
    const spyRsi = state.metadata.regime_status?.spy_rsi?.toFixed(1) || '--';
    const runtime = state.metadata.run_time_seconds?.toFixed(1) || '--';
    
    info.textContent = `${tickerCount} tickers scanned • Feed: ${feed} • SPY RSI: ${spyRsi} • Run time: ${runtime}s`;
    header.style.display = 'block';
}

// ============================================================================
// Session Persistence & Reconnection
// ============================================================================

async function checkForActiveRun() {
    const runId = sessionStorage.getItem('active_run_id');
    if (!runId) return;
    
    try {
        const status = await api.get(`/api/scan/${runId}/status`);
        
        // Check if run is still active and within TTL
        const startedAt = new Date(status.started_at);
        const elapsed = Date.now() - startedAt.getTime();
        
        if (elapsed < 10 * 60 * 1000) { // 10 minute TTL
            if (status.state === 'running') {
                // Resume the run
                state.activeRun = {
                    run_id: runId,
                    state: status.state,
                    started_at: startedAt
                };
                
                showToast('Resuming scan...', 'info');
                updateRunStatus('running');
                showProgressBar(true);
                updateProgress(status.progress.done, status.progress.total, status.progress.partial_results);
                
                // Reconnect WebSocket
                connectWebSocket(runId);
            } else if (status.state === 'done') {
                // Load completed results
                await loadResults(runId);
            }
        } else {
            // Run expired
            sessionStorage.removeItem('active_run_id');
            showToast('Previous run expired', 'warning');
        }
    } catch (error) {
        console.error('Failed to check for active run:', error);
        sessionStorage.removeItem('active_run_id');
    }
}

// ============================================================================
// Event Listeners
// ============================================================================

document.addEventListener('DOMContentLoaded', async () => {
    // Initialize controls
    initializeControls();
    
    // Set session date
    document.getElementById('session-date').textContent = new Date().toLocaleDateString();
    
    // Check for active run
    await checkForActiveRun();
    
    // Load initial config
    try {
        const config = await api.get('/api/config');
        // Can use this to set defaults if needed
    } catch (error) {
        console.error('Failed to load config:', error);
    }
    
    // Run button
    document.getElementById('run-btn').addEventListener('click', startScan);
    document.getElementById('cancel-btn').addEventListener('click', cancelScan);
    
    // Export button
    document.getElementById('export-btn').addEventListener('click', async () => {
        if (state.activeRun) {
            window.open(`${api.baseURL}/api/export/${state.activeRun.run_id}/csv`);
        }
    });
    
    // CLI button
    document.getElementById('cli-btn').addEventListener('click', async () => {
        if (state.activeRun) {
            const controls = getControls();
            const response = await api.get(`/api/cli/${state.activeRun.run_id}?overrides=${encodeURIComponent(JSON.stringify(controls))}`);
            navigator.clipboard.writeText(response.command);
            showToast('CLI command copied to clipboard', 'success');
        }
    });
    
    // Help button
    document.getElementById('help-btn').addEventListener('click', () => {
        document.getElementById('help-overlay').style.display = 'flex';
    });
    
    // Detail drawer close
    document.getElementById('drawer-close').addEventListener('click', closeDetailDrawer);
    
    // Copy symbol button
    document.getElementById('copy-symbol-btn').addEventListener('click', () => {
        const symbol = document.getElementById('drawer-symbol').textContent;
        navigator.clipboard.writeText(symbol);
        showToast(`${symbol} copied to clipboard`, 'success');
    });
    
    // Apply suggestion button
    document.getElementById('apply-suggestion-btn').addEventListener('click', () => {
        document.getElementById('min-volume').value = 3;
        document.getElementById('min-atr').value = 0.005;
        markDirty();
        startScan();
    });
    
    // Table sorting
    document.querySelectorAll('th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
            const sortBy = th.dataset.sort;
            document.getElementById('sort-select').value = sortBy;
            displayResults();
            
            // Update sort arrows
            document.querySelectorAll('.sort-arrow').forEach(arrow => {
                arrow.classList.remove('asc', 'desc');
            });
            th.querySelector('.sort-arrow').classList.add('desc');
        });
    });
    
    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            const activeElement = document.activeElement;
            if (activeElement.tagName !== 'TEXTAREA') {
                e.preventDefault();
                document.getElementById('run-btn').click();
            }
        } else if (e.key === '?') {
            document.getElementById('help-btn').click();
        } else if (e.key === 'Escape') {
            closeDetailDrawer();
            document.getElementById('help-overlay').style.display = 'none';
        }
    });
});