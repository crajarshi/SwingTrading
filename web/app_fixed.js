/**
 * SwingTrading Scanner - Fixed Working Version
 */

// Global state
const state = {
    activeRun: null,
    results: [],
    ws: null
};

// API base URL
const API_URL = 'http://localhost:8000';

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('SwingTrading Scanner UI initialized');
    
    // Set today's date
    const dateEl = document.getElementById('session-date');
    if (dateEl) {
        dateEl.textContent = new Date().toLocaleDateString();
    }
    
    // Wire up the main Run button
    const runBtn = document.getElementById('run-btn');
    if (runBtn) {
        runBtn.addEventListener('click', startScan);
        console.log('Run button wired up');
    } else {
        console.error('Run button not found!');
    }
    
    // Wire up Cancel button
    const cancelBtn = document.getElementById('cancel-btn');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', cancelScan);
    }
    
    // Test that API is working
    testAPI();
});

// Test API connection
async function testAPI() {
    try {
        const response = await fetch(`${API_URL}/api/config`);
        if (response.ok) {
            console.log('✅ API connection successful');
        } else {
            console.error('❌ API connection failed');
        }
    } catch (error) {
        console.error('❌ Cannot connect to API:', error);
        showToast('Cannot connect to server. Make sure it\'s running.', 'error');
    }
}

// Start a scan
async function startScan() {
    console.log('Starting scan...');
    
    try {
        // Get control values
        const controls = {
            feed: document.getElementById('feed-select')?.value || 'iex',
            bypass_regime: document.getElementById('regime-bypass')?.checked || false
        };
        
        // Start scan via API
        const response = await fetch(`${API_URL}/api/scan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(controls)
        });
        
        if (!response.ok) {
            throw new Error('Failed to start scan');
        }
        
        const data = await response.json();
        console.log('Scan started:', data);
        
        state.activeRun = data;
        
        // Update UI
        updateStatus('running');
        showProgress(true);
        
        // Connect WebSocket for progress
        connectWebSocket(data.run_id);
        
        showToast('Scan started', 'success');
        
    } catch (error) {
        console.error('Failed to start scan:', error);
        showToast('Failed to start scan', 'error');
    }
}

// Cancel scan
async function cancelScan() {
    if (!state.activeRun) return;
    
    if (confirm('Cancel scan in progress?')) {
        try {
            await fetch(`${API_URL}/api/scan/${state.activeRun.run_id}`, {
                method: 'DELETE'
            });
            
            updateStatus('canceled');
            showToast('Scan canceled', 'warning');
        } catch (error) {
            console.error('Failed to cancel:', error);
        }
    }
}

// Use polling instead of WebSocket (simpler, more reliable)
function connectWebSocket(runId) {
    console.log('Starting progress polling for:', runId);
    
    let attempts = 0;
    const maxAttempts = 30;
    
    const pollInterval = setInterval(async () => {
        attempts++;
        
        try {
            const response = await fetch(`http://localhost:8000/api/scan/${runId}/status`);
            const status = await response.json();
            
            console.log('Status update:', status);
            
            // Update progress display
            if (status.progress) {
                updateProgressBar(status.progress.done, status.progress.total);
            }
            
            // Handle completion
            if (status.state === 'done' || status.state === 'error' || attempts >= maxAttempts) {
                clearInterval(pollInterval);
                
                if (status.state === 'done') {
                    console.log('Scan complete!');
                    loadResults(runId);
                    updateStatus('done');
                    showToast(`Scan complete • ${status.progress.partial_results} results`, 'success');
                } else if (status.state === 'error') {
                    updateStatus('error');
                    showToast('Scan failed', 'error');
                } else if (attempts >= maxAttempts) {
                    updateStatus('error');
                    showToast('Scan timeout', 'error');
                }
            }
        } catch (error) {
            console.error('Poll error:', error);
            clearInterval(pollInterval);
            updateStatus('error');
            showToast('Lost connection to scan', 'error');
        }
    }, 500); // Poll every 500ms
}

// Load and display results
async function loadResults(runId) {
    try {
        const response = await fetch(`${API_URL}/api/scan/${runId}/results`);
        const data = await response.json();
        
        console.log('Results loaded:', data);
        state.results = data.results || [];
        
        displayResults();
        showProgress(false);
        
    } catch (error) {
        console.error('Failed to load results:', error);
    }
}

// Display results in table
function displayResults() {
    const tbody = document.getElementById('results-tbody');
    if (!tbody) {
        console.error('Results table body not found');
        return;
    }
    
    // Clear existing
    tbody.innerHTML = '';
    
    // Hide empty state
    const emptyState = document.getElementById('empty-never-run');
    if (emptyState) {
        emptyState.style.display = 'none';
    }
    
    // Show table
    const tableWrapper = document.getElementById('results-table-wrapper');
    if (tableWrapper) {
        tableWrapper.style.display = 'block';
    }
    
    // Add rows with actionable signals
    state.results.forEach(result => {
        const row = document.createElement('tr');
        
        // Determine action style
        let actionClass = '';
        let actionIcon = '';
        if (result.action === 'BUY') {
            actionClass = 'action-buy';
            actionIcon = '🟢';
        } else if (result.action === 'WATCH') {
            actionClass = 'action-watch';
            actionIcon = '👁️';
        } else if (result.action === 'AVOID') {
            actionClass = 'action-avoid';
            actionIcon = '⚠️';
        }
        
        // Build the row with actionable data
        row.innerHTML = `
            <td class="cell-symbol">
                <strong>${result.symbol}</strong>
                <span class="${actionClass}" style="margin-left: 8px;">
                    ${actionIcon} ${result.action}
                </span>
            </td>
            <td>
                $${result.close ? result.close.toFixed(2) : 'N/A'}
                ${result.day_change_pct ? `<span style="color: ${result.day_change_pct > 0 ? 'green' : 'red'}; font-size: 0.9em;">
                    (${result.day_change_pct > 0 ? '+' : ''}${result.day_change_pct.toFixed(2)}%)
                </span>` : ''}
            </td>
            <td>
                <strong>${result.score.toFixed(1)}</strong>
                ${result.signal_strength ? `<br><small>${result.signal_strength}</small>` : ''}
            </td>
            <td>${result.rsi14.toFixed(1)}</td>
            <td>${result.gap_percent.toFixed(1)}%</td>
            <td>
                ${result.entry_price ? `
                    Entry: $${result.entry_price}<br>
                    Stop: $${result.stop_loss}
                ` : '-'}
            </td>
            <td>
                ${result.target_1 ? `
                    T1: $${result.target_1}<br>
                    T2: $${result.target_2}
                ` : '-'}
            </td>
            <td>
                ${result.risk_reward || '-'}<br>
                ${result.position_size ? `<small>${result.position_size}</small>` : ''}
            </td>
        `;
        
        // Add click handler for more details
        row.style.cursor = 'pointer';
        row.onclick = () => {
            alert(`${result.symbol} Trading Plan:\n\n` +
                  `Action: ${result.action}\n` +
                  `Current Price: $${result.close}\n` +
                  `Entry: $${result.entry_price}\n` +
                  `Stop Loss: $${result.stop_loss} (${((result.stop_loss - result.close) / result.close * 100).toFixed(1)}%)\n` +
                  `Target 1: $${result.target_1} (+${((result.target_1 - result.close) / result.close * 100).toFixed(1)}%)\n` +
                  `Target 2: $${result.target_2} (+${((result.target_2 - result.close) / result.close * 100).toFixed(1)}%)\n` +
                  `Risk/Reward: ${result.risk_reward}\n` +
                  `Position Size: ${result.position_size}\n\n` +
                  `Reasoning: ${result.reasoning}`);
        };
        
        tbody.appendChild(row);
    });
    
    console.log(`Displayed ${state.results.length} results`);
}

// Update status display
function updateStatus(status) {
    const pill = document.getElementById('status-pill') || document.getElementById('status-badge');
    if (pill) {
        const statusText = {
            'idle': 'Ready to scan',
            'running': 'Scanning...',
            'done': 'Scan complete',
            'canceled': 'Scan canceled',
            'error': 'Scan failed'
        }[status] || status;
        
        pill.textContent = statusText;
        pill.className = `status-badge ${status}`;
    }
    
    // Toggle buttons
    const runBtn = document.getElementById('run-btn');
    const cancelBtn = document.getElementById('cancel-btn');
    
    if (status === 'running') {
        if (runBtn) runBtn.style.display = 'none';
        if (cancelBtn) cancelBtn.style.display = 'inline-flex';
    } else {
        if (runBtn) runBtn.style.display = 'inline-flex';
        if (cancelBtn) cancelBtn.style.display = 'none';
    }
}

// Show/hide progress
function showProgress(show) {
    const container = document.getElementById('progress-bar-container') || 
                     document.getElementById('progress-container');
    if (container) {
        container.style.display = show ? 'block' : 'none';
    }
}

// Update progress bar
function updateProgressBar(done, total) {
    const fill = document.getElementById('progress-bar-fill') || 
                 document.getElementById('progress-fill');
    if (fill) {
        const percent = total > 0 ? (done / total) * 100 : 0;
        fill.style.width = `${percent}%`;
    }
    
    // Update progress text
    const progressText = document.getElementById('progress-text');
    if (progressText) {
        progressText.textContent = `${done} / ${total}`;
    }
    
    // Update status pill with progress
    const pill = document.getElementById('status-pill') || document.getElementById('status-badge');
    if (pill) {
        pill.textContent = `Scanning ${done}/${total}`;
    }
}

// Show toast notification
function showToast(message, type = 'info') {
    console.log(`Toast [${type}]: ${message}`);
    
    const container = document.getElementById('toast-container');
    if (!container) {
        console.warn('Toast container not found');
        return;
    }
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Make functions available globally for debugging
window.startScan = startScan;
window.cancelScan = cancelScan;
window.showToast = showToast;