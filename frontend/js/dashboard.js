/**
 * MIA Dashboard Module
 * Real-time system monitoring with live charts.
 */

let monitorWS = null;

function initMonitor() {
    // Will connect when panel is activated
}

function startMonitoring() {
    if (monitorWS && monitorWS.isConnected) return;

    monitorWS = createWS('monitor', '/ws/monitor');

    monitorWS.on('message', (event) => {
        try {
            const data = JSON.parse(event.data);
            updateDashboard(data);
        } catch (e) {
            console.error('Monitor parse error:', e);
        }
    });

    monitorWS.connect();
}

function stopMonitoring() {
    if (monitorWS) {
        monitorWS.close();
        monitorWS = null;
    }
}

function updateDashboard(data) {
    // ── CPU ──
    if (data.cpu) {
        const cpuPct = Math.round(data.cpu.percent_total);
        document.getElementById('cpuValue').textContent = `${cpuPct}%`;
        document.getElementById('cpuSub').textContent =
            `${data.cpu.cores} cores • ${Math.round(data.cpu.freq_current)} MHz`;

        const cpuBar = document.getElementById('cpuBar');
        cpuBar.style.width = `${cpuPct}%`;
        cpuBar.className = 'progress-bar-fill' +
            (cpuPct > 90 ? ' danger' : cpuPct > 70 ? ' warning' : '');

        const cpuCard = document.getElementById('cpuCard');
        cpuCard.classList.remove('state-ok', 'state-warn', 'state-danger');
        cpuCard.classList.add(cpuPct > 90 ? 'state-danger' : cpuPct > 70 ? 'state-warn' : 'state-ok');

        // Per-core bars
        const coresGrid = document.getElementById('coresGrid');
        if (data.cpu.percent_per_core && data.cpu.percent_per_core.length > 0) {
            if (coresGrid.children.length !== data.cpu.percent_per_core.length) {
                coresGrid.innerHTML = data.cpu.percent_per_core.map(() =>
                    '<div class="core-bar"><div class="core-bar-fill"></div></div>'
                ).join('');
            }
            data.cpu.percent_per_core.forEach((pct, i) => {
                const fill = coresGrid.children[i]?.querySelector('.core-bar-fill');
                if (fill) {
                    fill.style.height = `${pct}%`;
                    fill.style.background = pct > 90 ? 'var(--danger)' :
                        pct > 70 ? 'var(--warning)' : 'var(--accent)';
                }
            });
        }
    }

    // ── RAM ──
    if (data.memory) {
        const ramPct = Math.round(data.memory.percent);
        const used = formatBytes(data.memory.used);
        const total = formatBytes(data.memory.total);
        document.getElementById('ramValue').textContent = `${ramPct}%`;
        document.getElementById('ramSub').textContent = `${used} / ${total}`;

        const ramBar = document.getElementById('ramBar');
        ramBar.style.width = `${ramPct}%`;
        ramBar.className = 'progress-bar-fill' +
            (ramPct > 90 ? ' danger' : ramPct > 75 ? ' warning' : '');

        const ramCard = document.getElementById('ramCard');
        ramCard.classList.remove('state-ok', 'state-warn', 'state-danger');
        ramCard.classList.add(ramPct > 90 ? 'state-danger' : ramPct > 75 ? 'state-warn' : 'state-ok');
    }

    // ── Network ──
    if (data.network) {
        const up = formatSpeed(data.network.upload_speed || 0);
        const down = formatSpeed(data.network.download_speed || 0);
        document.getElementById('netValue').textContent = `↓${down}`;
        document.getElementById('netSub').textContent = `↑ ${up} • Total: ↓${formatBytes(data.network.bytes_recv)} ↑${formatBytes(data.network.bytes_sent)}`;
    }

    // ── System ──
    if (data.battery) {
        document.getElementById('sysValue').textContent = `${data.battery.percent}%`;
        document.getElementById('sysSub').textContent =
            `${data.battery.plugged ? 'Charging' : 'On battery'} • Uptime: ${data.uptime || '—'}`;
    } else {
        document.getElementById('sysValue').textContent = data.uptime || '—';
        document.getElementById('sysSub').textContent = data.os || 'Loading...';
    }

    // ── Disks ──
    if (data.disks) {
        const grid = document.getElementById('disksGrid');
        grid.innerHTML = data.disks.map(disk => {
            const pct = disk.percent;
            const barClass = pct > 90 ? 'danger' : pct > 75 ? 'warning' : '';
            const state = pct > 90 ? 'state-danger' : pct > 75 ? 'state-warn' : 'state-ok';
            return `
                <div class="stat-card ${state}">
                    <div class="stat-card-header">
                        <span class="stat-card-title">${disk.device}</span>
                        <span class="stat-card-icon">${ICON.disk}</span>
                    </div>
                    <div class="stat-card-value">${pct}%</div>
                    <div class="stat-card-sub">${formatBytes(disk.used)} / ${formatBytes(disk.total)} (${disk.fstype})</div>
                    <div class="progress-bar"><div class="progress-bar-fill ${barClass}" style="width:${pct}%"></div></div>
                </div>
            `;
        }).join('');
    }
}

// ── Process Manager ─────────────────────────────────────────

let allProcesses = [];

async function loadProcesses() {
    const sortBy = document.getElementById('processSortBy')?.value || 'memory';
    const tbody = document.getElementById('processTableBody');
    try {
        if (tbody && allProcesses.length === 0) tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-dim)">Loading processes...</td></tr>';
        
        const res = await apiFetch(`/api/processes?sort_by=${sortBy}&limit=100&_t=${Date.now()}`); // Added cache buster
        
        if (Array.isArray(res)) {
            allProcesses = res;
            renderProcesses(allProcesses);
        } else {
            console.error('Invalid response:', res);
            showNotification('Error', 'Invalid data format from API', 'error');
            if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--danger)">Error: ${res.detail || 'Invalid format'}</td></tr>`;
        }
    } catch (e) {
        console.error('Failed to load processes:', e);
        showNotification('Error', `Failed to load processes: ${e.message}`, 'error');
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--danger)">Failed to load: ${e.message}</td></tr>`;
    }
}

function searchProcesses(query) {
    const filtered = allProcesses.filter(p =>
        p.name.toLowerCase().includes(query.toLowerCase()) ||
        String(p.pid).includes(query)
    );
    renderProcesses(filtered);
}

function renderProcesses(processes) {
    const tbody = document.getElementById('processTableBody');
    tbody.innerHTML = processes.map(p => `
        <tr>
            <td class="mono" style="color:var(--text-dim)">${p.pid}</td>
            <td>${p.name}</td>
            <td class="mono">${p.cpu.toFixed(1)}</td>
            <td class="mono">${p.memory.toFixed(1)}</td>
            <td><span style="color:${p.status === 'running' ? 'var(--success)' : 'var(--text-dim)'}">${p.status}</span></td>
            <td><button class="kill-btn" onclick="killProcess(${p.pid}, '${p.name.replace(/'/g, "\\'")}')">Kill</button></td>
        </tr>
    `).join('');
}

async function killProcess(pid, name) {
    if (!confirm(`Kill process "${name}" (PID ${pid})?`)) return;
    try {
        const result = await apiFetch(`/api/processes/kill/${pid}`, { method: 'POST' });
        showNotification('Process Manager', result.message || result.error, result.success ? 'success' : 'error');
        loadProcesses();
    } catch (e) {
        showNotification('Error', 'Failed to kill process', 'error');
    }
}

// ── Terminal ────────────────────────────────────────────────

let terminalWS = null;
let terminalHistory = [];
let terminalHistoryIndex = -1;

function initTerminal() {
    terminalWS = createWS('terminal', '/ws/terminal');

    terminalWS.on('message', (event) => {
        try {
            const data = JSON.parse(event.data);
            const output = document.getElementById('terminalOutput');

            if (data.type === 'stdout') {
                output.innerHTML += `<span class="stdout">${escapeHtml(data.data)}</span>`;
            } else if (data.type === 'stderr') {
                output.innerHTML += `<span class="stderr">${escapeHtml(data.data)}</span>`;
            } else if (data.type === 'exit') {
                const color = data.exit_code === 0 ? 'system' : 'stderr';
                output.innerHTML += `<span class="${color}">\n[Exit code: ${data.exit_code}]\n</span>`;
            } else if (data.type === 'error') {
                output.innerHTML += `<span class="stderr">${escapeHtml(data.data)}\n</span>`;
            }

            output.scrollTop = output.scrollHeight;
        } catch (e) {}
    });

    terminalWS.connect();
}

function handleTerminalKeydown(event) {
    if (event.key === 'Enter') {
        const input = document.getElementById('terminalInput');
        const command = input.value.trim();
        if (!command) return;

        const output = document.getElementById('terminalOutput');
        output.innerHTML += `<span class="prompt">\nPS&gt; </span><span class="stdout">${escapeHtml(command)}\n</span>`;

        terminalHistory.push(command);
        terminalHistoryIndex = terminalHistory.length;

        terminalWS.sendJSON({ command });
        input.value = '';
    } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        if (terminalHistoryIndex > 0) {
            terminalHistoryIndex--;
            document.getElementById('terminalInput').value = terminalHistory[terminalHistoryIndex];
        }
    } else if (event.key === 'ArrowDown') {
        event.preventDefault();
        if (terminalHistoryIndex < terminalHistory.length - 1) {
            terminalHistoryIndex++;
            document.getElementById('terminalInput').value = terminalHistory[terminalHistoryIndex];
        } else {
            terminalHistoryIndex = terminalHistory.length;
            document.getElementById('terminalInput').value = '';
        }
    }
}

// ── Tasks ───────────────────────────────────────────────────

async function loadTasks() {
    try {
        const tasks = await apiFetch('/api/tasks');
        renderTasks(tasks);
    } catch (e) {
        console.error('Failed to load tasks:', e);
    }
}

function renderTasks(tasks) {
    const container = document.getElementById('tasksList');
    if (tasks.length === 0) {
        container.innerHTML = `
            <div style="text-align:center;padding:60px 20px;color:var(--text-dim)">
                <div class="empty-state-icon">${ICON.clock}</div>
                <p>No scheduled tasks yet</p>
                <p style="font-size:13px;margin-top:8px">Use the chat to schedule tasks, e.g., "Run disk cleanup at 3am"</p>
            </div>
        `;
        return;
    }

    container.innerHTML = tasks.map(task => {
        const statusClass = task.status === 'active' || task.status === 'pending'
            ? 'badge-success' : task.status === 'completed' ? 'badge-info' : 'badge-warning';
        return `
            <div class="task-card">
                <div class="task-card-header">
                    <span class="task-name">${task.name}</span>
                    <span class="task-status ${statusClass}">${task.status}</span>
                </div>
                <div class="task-command">${escapeHtml(task.command)}</div>
                <div class="task-meta">
                    <span>${task.type === 'recurring' ? 'Cron: ' + task.cron : 'At: ' + task.scheduled_at}</span>
                    ${task.last_run ? `<span>Last: ${new Date(task.last_run).toLocaleString()}</span>` : ''}
                    ${task.run_count ? `<span>Runs: ${task.run_count}</span>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

function showAddTaskDialog() {
    const cmd = prompt('Command to schedule:');
    if (!cmd) return;
    const schedule = prompt('Schedule (ISO datetime like 2024-01-15T14:30:00 or cron like */5 * * * *):');
    if (!schedule) return;
    const name = prompt('Task name (optional):', '');

    const isCron = schedule.includes('*') || schedule.split(' ').length === 5;

    apiFetch('/api/tasks', {
        method: 'POST',
        body: JSON.stringify({
            command: cmd,
            schedule: schedule,
            name: name || undefined,
            type: isCron ? 'recurring' : 'one_time',
        }),
    }).then(result => {
        showNotification('Scheduler', result.message || result.error, result.success ? 'success' : 'error');
        loadTasks();
    });
}

// ── Utilities ───────────────────────────────────────────────

function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
}

function formatSpeed(bytesPerSec) {
    if (bytesPerSec < 1024) return `${Math.round(bytesPerSec)} B/s`;
    if (bytesPerSec < 1024 * 1024) return `${(bytesPerSec / 1024).toFixed(1)} KB/s`;
    return `${(bytesPerSec / (1024 * 1024)).toFixed(1)} MB/s`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
