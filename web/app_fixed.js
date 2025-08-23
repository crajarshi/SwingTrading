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

// Connect WebSocket for real-time updates
function connectWebSocket(runId) {
    const wsUrl = `ws://localhost:8000/ws/scan/${runId}`;
    console.log('Connecting WebSocket:', wsUrl);
    
    state.ws = new WebSocket(wsUrl);
    
    state.ws.onopen = () => {
        console.log('WebSocket connected');
    };
    
    state.ws.onmessage = (event) => {
        const update = JSON.parse(event.data);
        console.log('Progress update:', update);
        
        // Update progress display
        if (update.progress) {
            updateProgressBar(update.progress.done, update.progress.total);
        }
        
        // Handle completion
        if (update.state === 'done') {
            console.log('Scan complete!');
            loadResults(runId);
            updateStatus('done');
            showToast(`Scan complete • ${update.progress.partial_results} results`, 'success');
        } else if (update.state === 'error') {
            updateStatus('error');
            showToast('Scan failed', 'error');
        }
    };
    
    state.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    state.ws.onclose = () => {
        console.log('WebSocket closed');
    };
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
    
    // Add rows
    state.results.forEach(result => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="cell-symbol">${result.symbol}</td>
            <td>$${result.close.toFixed(2)}</td>
            <td>${result.score.toFixed(2)}</td>
            <td>${result.rsi14.toFixed(1)}</td>
            <td>${result.gap_percent.toFixed(1)}%</td>
            <td>${(result.volume / 1e6).toFixed(1)}M</td>
            <td>-</td>
            <td>-</td>
        `;
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
        pill.className = `status-pill ${status}`;
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
    
    // Update status pill with progress
    const pill = document.getElementById('status-pill') || document.getElementById('status-badge');
    if (pill && pill.classList.contains('running')) {
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