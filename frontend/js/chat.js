/**
 * MIA Chat Module
 * WhatsApp-style chat interface with the AI agent.
 */

let chatWS = null;
let isThinking = false;
let currentSessionId = Date.now().toString();
let streamState = null; // { msgDiv, bubbleEl, statusEl, rawText } — the in-progress streaming assistant message

function initChat() {
    chatWS = createWS('chat', '/ws/chat');

    chatWS.on('open', () => {
        updateConnectionStatus(true);
        loadPendingApprovals();
    });

    chatWS.on('close', () => {
        updateConnectionStatus(false);
    });

    chatWS.on('message', (event) => {
        try {
            const data = JSON.parse(event.data);

            if (data.type === 'status' && data.status === 'thinking') {
                showThinking(true);
            } else if (data.type === 'chunk') {
                showThinking(false);
                appendStreamChunk(data.content);
            } else if (data.type === 'tool_call') {
                showThinking(false);
                setStreamStatus(`🔧 Using ${data.tool_name}...`);
            } else if (data.type === 'tool_result') {
                // Handled implicitly — next chunk/tool_call/done will update the UI.
            } else if (data.type === 'done') {
                finalizeStreamingMessage(data.message);
            } else if (data.type === 'response') {
                // Non-streaming fallback (e.g. legacy callers).
                showThinking(false);
                addMessage('assistant', data.message);
            } else if (data.type === 'error') {
                showThinking(false);
                discardStreamingMessage();
                addMessage('assistant', `❌ ${data.message}`);
            } else if (data.type === 'approval_request') {
                renderApprovalCard(data.request);
            } else if (data.type === 'approval_resolved') {
                markApprovalResolved(data.request_id, data.request, data.result);
            } else if (data.type === 'notification') {
                showNotification(data.title, data.message, data.level);
            }
        } catch (e) {
            console.error('Chat message parse error:', e);
        }
    });

    chatWS.connect();
}

// ── Streaming Message Rendering ─────────────────────────────

function createStreamingMessageEl() {
    const container = document.getElementById('chatMessages');
    const welcome = document.getElementById('chatWelcome');
    if (welcome) welcome.style.display = 'none';

    const msgDiv = document.createElement('div');
    msgDiv.className = 'message assistant';

    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const timeStr = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });

    msgDiv.innerHTML = `
        <div class="message-avatar">${ICON.bot}</div>
        <div class="message-body">
            <div class="message-bubble"></div>
            <div class="message-footer">
                <span>Assistant ${dateStr}, ${timeStr}</span>
            </div>
        </div>
    `;

    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;

    return { msgDiv, bubbleEl: msgDiv.querySelector('.message-bubble'), statusEl: null, rawText: '' };
}

function appendStreamChunk(text) {
    if (!streamState) {
        streamState = createStreamingMessageEl();
    }
    streamState.rawText += text;
    // Plain-text live update while streaming; full markdown formatting is applied on 'done'.
    streamState.bubbleEl.textContent = streamState.rawText;

    const container = document.getElementById('chatMessages');
    container.scrollTop = container.scrollHeight;
}

function setStreamStatus(text) {
    if (!streamState) {
        streamState = createStreamingMessageEl();
    }
    if (!streamState.statusEl) {
        streamState.statusEl = document.createElement('div');
        streamState.statusEl.className = 'stream-tool-status';
        streamState.statusEl.style.cssText = 'font-size:12px;color:var(--text-dim);margin-bottom:6px;';
        streamState.bubbleEl.parentNode.insertBefore(streamState.statusEl, streamState.bubbleEl);
    }
    streamState.statusEl.textContent = text;

    const container = document.getElementById('chatMessages');
    container.scrollTop = container.scrollHeight;
}

function finalizeStreamingMessage(finalText) {
    if (!streamState) {
        if (finalText) addMessage('assistant', finalText);
        return;
    }
    const text = (finalText !== null && finalText !== undefined && finalText !== '') ? finalText : streamState.rawText;
    if (streamState.statusEl) streamState.statusEl.remove();
    streamState.bubbleEl.innerHTML = formatMessage(text);
    streamState = null;

    const container = document.getElementById('chatMessages');
    container.scrollTop = container.scrollHeight;
}

function discardStreamingMessage() {
    if (streamState) {
        streamState.msgDiv.remove();
        streamState = null;
    }
}

function sendMessage() {
    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    if (!message || isThinking) return;

    // Hide welcome screen
    const welcome = document.getElementById('chatWelcome');
    if (welcome) welcome.style.display = 'none';

    addMessage('user', message);
    chatWS.sendJSON({ message, session_id: currentSessionId });

    input.value = '';
    input.style.height = 'auto';
}

function sendQuickAction(text) {
    const input = document.getElementById('chatInput');
    input.value = text;
    sendMessage();
}

function addMessage(role, content) {
    const container = document.getElementById('chatMessages');
    const welcome = document.getElementById('chatWelcome');
    if (welcome) welcome.style.display = 'none';

    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;

    const avatar = role === 'assistant' ? ICON.bot : ICON.user;
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const timeStr = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });

    // Parse markdown-like content
    const formatted = formatMessage(content);

    if (role === 'user') {
        msgDiv.innerHTML = `
            <div class="message-body">
                <div class="message-bubble">${formatted}</div>
                <div class="message-footer">
                    <button class="delete-icon" onclick="this.closest('.message').remove()" title="Delete">${ICON.trash}</button>
                    <span>You ${dateStr}, ${timeStr}</span>
                </div>
            </div>
            <div class="message-avatar">${avatar}</div>
        `;
    } else {
        msgDiv.innerHTML = `
            <div class="message-avatar">${avatar}</div>
            <div class="message-body">
                <div class="message-bubble">${formatted}</div>
                <div class="message-footer">
                    <span>Assistant ${dateStr}, ${timeStr}</span>
                </div>
            </div>
        `;
    }

    // ALWAYS append new messages
    container.appendChild(msgDiv);

    // Ensure thinking indicator remains at the very bottom if it exists
    const dynamicThinking = document.getElementById('dynamicThinking');
    if (dynamicThinking) {
        container.appendChild(dynamicThinking);
    }

    container.scrollTop = container.scrollHeight;
}

function formatMessage(text) {
    // Code blocks
    text = text.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    // Inline code
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic
    text = text.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
    // Line breaks
    text = text.replace(/\n/g, '<br>');
    return text;
}

function showThinking(show) {
    isThinking = show;
    
    const sendBtn = document.getElementById('sendBtn');
    if (sendBtn) sendBtn.disabled = show;

    const container = document.getElementById('chatMessages');

    if (show) {
        if (!document.getElementById('dynamicThinking')) {
            const msgDiv = document.createElement('div');
            msgDiv.className = 'message assistant';
            msgDiv.id = 'dynamicThinking';
            msgDiv.innerHTML = `
                <div class="message-avatar">${ICON.bot}</div>
                <div class="message-body">
                    <div class="message-bubble" style="min-width: 50px;">
                        <div class="thinking-dots"><span></span><span></span><span></span></div>
                    </div>
                </div>
            `;
            container.appendChild(msgDiv);
            container.scrollTop = container.scrollHeight;
        }
    } else {
        const thinking = document.getElementById('dynamicThinking');
        if (thinking) thinking.remove();
    }
}

function clearChat() {
    const container = document.getElementById('chatMessages');
    const welcome = document.getElementById('chatWelcome');
    
    // Remove all message divs
    const messages = container.querySelectorAll('.message');
    messages.forEach(msg => msg.remove());
    
    if (welcome) {
        welcome.style.display = 'flex';
    }
}

function handleChatKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

function updateConnectionStatus(connected) {
    const badge = document.getElementById('statusBadge');
    const btn = document.getElementById('connectionStatus');

    if (badge) {
        badge.textContent = connected ? 'Connected' : 'Disconnected';
        badge.style.background = connected ? 'rgba(79, 196, 154, 0.15)' : 'rgba(226, 96, 79, 0.15)';
        badge.style.color = connected ? 'var(--success)' : 'var(--danger)';
    }
    if (btn) {
        btn.classList.toggle('offline', !connected);
        btn.title = connected ? 'Connected' : 'Disconnected';
    }
}

// ── Approvals ───────────────────────────────────────────────────────────
// MIA pauses before removing lines, deleting, overwriting, or sending/posting.
// Cards are built with textContent only — diffs and reasons are untrusted text.

const APPROVAL_KIND_LABELS = {
    edit: 'Removes code or text',
    delete: 'Deletes',
    overwrite: 'Overwrites',
    command: 'Destructive command',
    send: 'Cannot be undone',
};

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
}

async function loadPendingApprovals() {
    try {
        const res = await fetch('/api/approvals', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('mia_token')}` }
        });
        if (!res.ok) return;
        const pending = await res.json();
        pending.forEach(renderApprovalCard);
    } catch (e) {
        console.error('Failed to load pending approvals', e);
    }
}

function renderApprovalCard(request) {
    if (!request || document.getElementById(`approval-${request.id}`)) return;

    const container = document.getElementById('chatMessages');
    const welcome = document.getElementById('chatWelcome');
    if (welcome) welcome.style.display = 'none';

    const msgDiv = el('div', 'message assistant approval-message');
    msgDiv.id = `approval-${request.id}`;
    const avatar = el('div', 'message-avatar');
    avatar.innerHTML = ICON.lock;
    const body = el('div', 'message-body');
    const card = el('div', `approval-card kind-${request.kind || 'edit'}`);

    const head = el('div', 'approval-head');
    head.append(
        el('span', 'approval-tag', 'Needs your approval'),
        el('span', 'approval-kind', APPROVAL_KIND_LABELS[request.kind] || request.kind),
        el('span', 'approval-id', `#${request.id}`),
    );
    card.append(head, el('div', 'approval-title', request.title));

    if (request.reason) {
        const reason = el('div', 'approval-reason');
        reason.append(el('span', 'approval-label', 'Why'), el('span', null, request.reason));
        card.append(reason);
    }

    const details = request.details || {};
    const facts = el('dl', 'approval-facts');
    Object.entries(details).forEach(([key, value]) => {
        if (key === 'diff') return;
        facts.append(el('dt', null, key.replace(/_/g, ' ')), el('dd', null, String(value)));
    });
    if (facts.children.length) card.append(facts);

    if (details.diff) {
        const diff = el('pre', 'approval-diff');
        details.diff.split('\n').forEach(line => {
            let cls = 'ctx';
            if (line.startsWith('+++') || line.startsWith('---')) cls = 'file';
            else if (line.startsWith('@@')) cls = 'hunk';
            else if (line.startsWith('+')) cls = 'add';
            else if (line.startsWith('-')) cls = 'del';
            diff.append(el('span', `diff-line ${cls}`, line || ' '));
        });
        card.append(diff);
    }

    const actions = el('div', 'approval-actions');
    const approveBtn = el('button', 'approval-btn approve', 'Approve');
    const rejectBtn = el('button', 'approval-btn reject', 'Reject');
    approveBtn.onclick = () => decideApproval(request.id, true);
    rejectBtn.onclick = () => decideApproval(request.id, false);
    actions.append(approveBtn, rejectBtn);

    const status = el('div', 'approval-status');
    status.hidden = true;
    card.append(actions, status);

    body.append(card);
    msgDiv.append(avatar, body);
    container.appendChild(msgDiv);

    const dynamicThinking = document.getElementById('dynamicThinking');
    if (dynamicThinking) container.appendChild(dynamicThinking);
    container.scrollTop = container.scrollHeight;
}

function decideApproval(requestId, approved) {
    const msg = document.getElementById(`approval-${requestId}`);
    if (!msg) return;
    msg.querySelectorAll('.approval-btn').forEach(btn => btn.disabled = true);
    const status = msg.querySelector('.approval-status');
    status.hidden = false;
    status.textContent = approved ? 'Approving…' : 'Rejecting…';
    chatWS.sendJSON({ type: 'approval_decision', request_id: requestId, approved });
}

function markApprovalResolved(requestId, request, result) {
    const msg = document.getElementById(`approval-${requestId}`);
    if (!msg) return;
    const state = request ? request.status : 'failed';
    const labels = { done: 'Approved', failed: 'Approved, but it failed', rejected: 'Rejected', expired: 'Expired' };

    const actions = msg.querySelector('.approval-actions');
    if (actions) actions.remove();
    msg.querySelector('.approval-card').classList.add(`resolved-${state}`);
    const status = msg.querySelector('.approval-status');
    status.hidden = false;
    status.textContent = '';
    status.append(el('strong', null, labels[state] || state), el('span', null, result ? ` · ${result}` : ''));
}

// ── Session Management ──────────────────────────────────────────────────

async function loadSessions() {
    try {
        const res = await fetch('/api/chat/sessions', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('mia_token')}` }
        });
        const sessions = await res.json();
        
        const listDiv = document.getElementById('sessionsListContainer');
        if (!listDiv) return;
        
        listDiv.innerHTML = `
            <div class="section-title">
                <span>SESSIONS</span>
                <button class="icon-btn small" onclick="loadSessions()">${ICON.refresh}</button>
            </div>
        `;
        
        if (sessions.length === 0) {
            listDiv.innerHTML += '<div style="padding: 0 16px; font-size: 12px; color: var(--text-dim);">No sessions yet</div>';
            return;
        }

        sessions.forEach(s => {
            const item = document.createElement('div');
            item.className = 'session-item' + (s.id === currentSessionId ? ' active' : '');
            
            // Make session-item flex if not already, to layout correctly
            item.style.display = 'flex';
            item.style.alignItems = 'center';
            item.style.justifyContent = 'space-between';
            
            // Format time nicely
            const d = new Date(s.updated_at * 1000);
            const timeStr = d.toLocaleDateString();
            
            item.innerHTML = `
                <div style="flex:1; overflow:hidden; cursor:pointer;" onclick="loadSession('${s.id}')">
                    <div class="session-title">${s.name}</div>
                    <div class="session-time" style="font-size:10px;">${timeStr}</div>
                </div>
                <div class="session-actions dropdown-container" style="position:relative; z-index:100; margin-left: 8px;">
                    <button class="icon-btn small" onclick="toggleSessionMenu('${s.id}', event)" style="opacity:0.7; padding: 4px;">${ICON.dots}</button>
                    <div id="menu-${s.id}" class="session-menu" style="display:none; position:absolute; right:0; top:100%; background:var(--bg-card); border:1px solid var(--border-strong); border-radius:8px; padding:4px; box-shadow:var(--shadow-lg); min-width: 130px; z-index: 9999;">
                        <button onclick="renameSession('${s.id}', '${s.name.replace(/'/g, "\\'")}', event)" style="display:flex; align-items:center; gap:8px; width:100%; text-align:left; background:transparent; border:none; color:var(--text); padding:8px 12px; cursor:pointer; font-size: 13px; font-family:inherit; border-radius:6px; transition: background 0.2s;" onmouseover="this.style.background='var(--bg-hover)'" onmouseout="this.style.background='transparent'">${ICON.pencil} Rename</button>
                        <button onclick="deleteSession('${s.id}', event)" style="display:flex; align-items:center; gap:8px; width:100%; text-align:left; background:transparent; border:none; color:var(--danger); padding:8px 12px; cursor:pointer; font-size: 13px; font-family:inherit; border-radius:6px; margin-top:2px; transition: background 0.2s;" onmouseover="this.style.background='var(--bg-hover)'" onmouseout="this.style.background='transparent'">${ICON.trash} Delete</button>
                    </div>
                </div>
            `;
            listDiv.appendChild(item);
        });
        
    } catch(e) {
        console.error("Failed to load sessions", e);
    }
}

async function loadSession(id) {
    currentSessionId = id;
    
    // update UI active state
    loadSessions();
    
    // clear chat messages
    const container = document.getElementById('chatMessages');
    const msgs = container.querySelectorAll('.message');
    msgs.forEach(m => m.remove());
    
    const welcome = document.getElementById('chatWelcome');
    if (welcome) welcome.style.display = 'none';
    
    // fetch history
    try {
        const res = await fetch('/api/chat/sessions/' + id, {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('mia_token')}` }
        });
        const history = await res.json();
        
        history.forEach(msg => {
            if(msg.role === 'user') {
                addMessage('user', msg.content);
            } else if (msg.role === 'assistant') {
                addMessage('assistant', msg.content);
            }
        });
    } catch(e) {
        console.error("Failed to load session history", e);
    }
}

function createNewSession() {
    currentSessionId = Date.now().toString();
    clearChat(); 
    loadSessions(); 
}

// ── Session Menu Actions ────────────────────────────────────────────────

function toggleSessionMenu(id, event) {
    event.stopPropagation();
    const menu = document.getElementById('menu-' + id);
    const isVisible = menu.style.display === 'block';
    
    // Close all other menus
    document.querySelectorAll('.session-menu').forEach(m => m.style.display = 'none');
    
    if (!isVisible) {
        menu.style.display = 'block';
    }
}

// Close menus when clicking outside
document.addEventListener('click', () => {
    document.querySelectorAll('.session-menu').forEach(m => m.style.display = 'none');
});

async function renameSession(id, oldName, event) {
    event.stopPropagation();
    document.querySelectorAll('.session-menu').forEach(m => m.style.display = 'none');
    
    const newName = prompt("Enter new name for this session:", oldName);
    if (!newName || newName.trim() === '' || newName === oldName) return;
    
    try {
        await fetch('/api/chat/sessions/' + id + '/rename', {
            method: 'POST',
            headers: { 
                'Authorization': `Bearer ${localStorage.getItem('mia_token')}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ new_name: newName.trim() })
        });
        loadSessions();
    } catch(e) {
        console.error("Failed to rename session", e);
    }
}

async function deleteSession(id, event) {
    event.stopPropagation();
    document.querySelectorAll('.session-menu').forEach(m => m.style.display = 'none');
    
    if (!confirm("Are you sure you want to delete this session?")) return;
    
    try {
        await fetch('/api/chat/sessions/' + id, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('mia_token')}` }
        });
        if (currentSessionId === id) {
            createNewSession();
        } else {
            loadSessions();
        }
    } catch(e) {
        console.error("Failed to delete session", e);
    }
}
