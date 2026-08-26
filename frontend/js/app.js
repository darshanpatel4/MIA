/**
 * MIA App Core
 * Main application initialization, panel switching, and notifications.
 */

// ── Panel Titles ────────────────────────────────────────────
const PANEL_TITLES = {
    chat: 'Chat with MIA',
    screen: 'Remote Screen',
    files: 'File Browser',
    monitor: 'System Monitor',
    processes: 'Process Manager',
    tasks: 'Scheduled Tasks',
    terminal: 'Terminal',
};

let currentPanel = 'chat';

// ── Panel Switching ─────────────────────────────────────────

function switchPanel(panel) {
    // Deactivate current
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item[data-panel]').forEach(n => n.classList.remove('active'));

    // Activate new
    const panelEl = document.getElementById(`panel-${panel}`);
    const navEl = document.querySelector(`.nav-item[data-panel="${panel}"]`);

    if (panelEl) panelEl.classList.add('active');
    if (navEl) navEl.classList.add('active');

    document.getElementById('panelTitle').textContent = PANEL_TITLES[panel] || panel;
    currentPanel = panel;

    // Panel-specific initialization
    onPanelActivate(panel);
}

function onPanelActivate(panel) {
    switch (panel) {
        case 'monitor':
            startMonitoring();
            if (typeof loadProcesses === 'function') loadProcesses();
            break;
        case 'files':
            if (!document.getElementById('filesList').innerHTML) {
                navigateTo(currentPath);
            }
            break;
        case 'tasks':
            loadTasks();
            break;
        case 'terminal':
            document.getElementById('terminalInput').focus();
            break;
    }
}

// ── Notifications ───────────────────────────────────────────

function showNotification(title, message, level = 'info') {
    const container = document.getElementById('notificationContainer');
    const id = 'notif_' + Date.now();

    const toast = document.createElement('div');
    toast.className = `notification-toast ${level}`;
    toast.id = id;
    toast.innerHTML = `
        <div style="flex:1">
            <div class="notification-title">${title}</div>
            <div class="notification-message">${message}</div>
        </div>
        <button class="notification-close" onclick="dismissNotification('${id}')">✕</button>
    `;

    container.appendChild(toast);

    // Auto-dismiss after 5 seconds
    setTimeout(() => dismissNotification(id), 5000);
}

function dismissNotification(id) {
    const toast = document.getElementById(id);
    if (toast) {
        toast.style.animation = 'fadeOut 0.3s ease';
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }
}

// ── Keyboard Shortcuts ──────────────────────────────────────

document.addEventListener('keydown', (e) => {
    // Don't trigger shortcuts when typing
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    // Ctrl+1-7: Switch panels
    if (e.ctrlKey && e.key >= '1' && e.key <= '7') {
        e.preventDefault();
        const panels = ['chat', 'screen', 'files', 'monitor', 'processes', 'tasks', 'terminal'];
        const idx = parseInt(e.key) - 1;
        if (panels[idx]) switchPanel(panels[idx]);
    }

    // Ctrl+K: Focus chat input
    if (e.ctrlKey && e.key === 'k') {
        e.preventDefault();
        switchPanel('chat');
        document.getElementById('chatInput').focus();
    }
});

// ── App Initialization ──────────────────────────────────────

async function initApp() {
    // Check authentication
    const authed = await checkAuth();
    if (!authed) return;

    // Initialize all modules
    initChat();
    initScreen();
    initMonitor();
    initTerminal();

    // Show welcome notification
    setTimeout(() => {
        showNotification('Welcome', 'MIA is ready. Use Ctrl+K to focus chat.', 'success');
    }, 1000);

    console.log('🤖 MIA initialized');
}

// Start the app
initApp();
