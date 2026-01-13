// Dashboard JavaScript
let lastUpdate = null;

// Fetch status from backend
async function fetchStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        updateDashboard(data);
        lastUpdate = new Date();
    } catch (error) {
        console.error('Failed to fetch status:', error);
    }
}

function updateDashboard(status) {
    // Update status bar
    document.getElementById('currentPhase').textContent = status.currentPhase || 'Waiting';
    document.getElementById('currentPhase').className = `phase-badge ${status.currentPhase || 'Waiting'}`;
    document.getElementById('processedCount').textContent = status.processedCount || 0;
    
    // Update next scan time
    if (status.nextScanTime) {
        const nextScan = new Date(status.nextScanTime);
        const now = new Date();
        const diff = Math.max(0, Math.floor((nextScan - now) / 1000));
        document.getElementById('nextScan').textContent = `${diff}s`;
    } else {
        document.getElementById('nextScan').textContent = 'Soon';
    }
    
    // Update active queue
    updateActiveQueue(status.activeTickets || []);
    
    // Update current ticket
    updateCurrentTicket(status);
    
    // Update monitored tickets
    updateMonitoredTickets(status.monitoredTickets || []);
    
    // Update history
    updateHistory(status.scanHistory || []);
}

function updateActiveQueue(tickets) {
    const container = document.getElementById('activeQueue');
    
    if (tickets.length === 0) {
        container.innerHTML = '<div class="empty-state">No tickets in queue</div>';
        return;
    }
    
    container.innerHTML = tickets.map(ticket => `
        <div class="queue-item">
            <div>
                <span class="key">${escapeHtml(ticket.key)}</span>
                <span class="priority ${escapeHtml(ticket.priority)}">${escapeHtml(ticket.priority)}</span>
            </div>
            <div class="status">${escapeHtml(ticket.status)}</div>
        </div>
    `).join('');
}

function updateCurrentTicket(status) {
    const container = document.getElementById('currentTicket');
    
    if (!status.currentTicketKey) {
        container.innerHTML = '<div class="empty-state">No active ticket</div>';
        return;
    }
    
    let html = `
        <div class="info-row">
            <span class="info-label">Ticket:</span>
            <span class="info-value">
                ${status.currentJiraUrl ? 
                    `<a href="${escapeHtml(status.currentJiraUrl)}" target="_blank">${escapeHtml(status.currentTicketKey)}</a>` : 
                    escapeHtml(status.currentTicketKey)}
            </span>
        </div>
    `;
    
    if (status.currentPrUrl) {
        html += `
            <div class="info-row">
                <span class="info-label">PR:</span>
                <span class="info-value">
                    <a href="${escapeHtml(status.currentPrUrl)}" target="_blank">View Pull Request</a>
                </span>
            </div>
        `;
    }
    
    if (status.currentTicketLogs && status.currentTicketLogs.length > 0) {
        html += `
            <div class="logs">
                ${status.currentTicketLogs.map(log => 
                    `<div class="log-line">${escapeHtml(log)}</div>`
                ).join('')}
            </div>
        `;
    }
    
    container.innerHTML = html;
}

function updateMonitoredTickets(tickets) {
    const container = document.getElementById('monitoredTickets');
    
    if (tickets.length === 0) {
        container.innerHTML = '<div class="empty-state">No PRs being monitored</div>';
        return;
    }
    
    container.innerHTML = tickets.map(ticket => {
        let checksHtml = '';
        if (ticket.checks && ticket.checks.length > 0) {
            checksHtml = `
                <div class="checks">
                    <strong>CI Checks:</strong>
                    ${ticket.checks.map(check => `
                        <div class="check-item">
                            <span>${escapeHtml(check.name)}</span>
                            <span class="check-status ${getCheckStatusClass(check)}">${getCheckStatusText(check)}</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }
        
        return `
            <div class="monitored-item">
                <div>
                    <span class="key">${escapeHtml(ticket.key)}</span>
                    ${ticket.priority ? `<span class="priority ${escapeHtml(ticket.priority)}">${escapeHtml(ticket.priority)}</span>` : ''}
                </div>
                ${ticket.prUrl ? `<div class="time"><a href="${escapeHtml(ticket.prUrl)}" target="_blank">View PR</a></div>` : ''}
                ${ticket.repoName ? `<div class="time">Repo: ${escapeHtml(ticket.repoName)}</div>` : ''}
                ${checksHtml}
            </div>
        `;
    }).join('');
}

function updateHistory(history) {
    const container = document.getElementById('scanHistory');
    
    if (history.length === 0) {
        container.innerHTML = '<div class="empty-state">No history yet</div>';
        return;
    }
    
    const recentHistory = history.slice(0, 10); // Show last 10
    
    container.innerHTML = recentHistory.map(item => `
        <div class="history-item">
            <div>
                <span class="key">${escapeHtml(item.key)}</span>
                <span class="result ${escapeHtml(item.result)}">${escapeHtml(item.result)}</span>
            </div>
            <div class="time">${escapeHtml(item.time)}</div>
            ${item.prUrl ? `<div><a href="${escapeHtml(item.prUrl)}" target="_blank">View PR</a></div>` : ''}
            ${item.jiraUrl ? `<div><a href="${escapeHtml(item.jiraUrl)}" target="_blank">View in Jira</a></div>` : ''}
        </div>
    `).join('');
}

function getCheckStatusClass(check) {
    if (check.conclusion === 'success') return 'success';
    if (check.conclusion === 'failure') return 'failure';
    if (check.status === 'in_progress') return 'in_progress';
    if (check.status === 'queued') return 'queued';
    return 'queued';
}

function getCheckStatusText(check) {
    if (check.conclusion) return check.conclusion;
    if (check.status) return check.status;
    return 'pending';
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// Auto-refresh every 3 seconds
setInterval(fetchStatus, 3000);

// Initial fetch
fetchStatus();
