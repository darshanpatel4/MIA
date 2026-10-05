/**
 * MIA Automations
 * Scheduled tasks (MIA tasks or commands) and the heartbeat checklist.
 * Built with textContent only — task instructions and results are untrusted text.
 */

let tasksPollTimer = null;

function mk(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
}

function fmtTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

async function autoApi(method, url, body) {
    const data = await apiFetch(url, { method, body: body ? JSON.stringify(body) : undefined });
    if (data && data.detail) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed');
    return data;
}

// Called when the Tasks view opens (app.js) and on a timer while it's visible.
async function loadTasks(tasksOnly = false) {
    try {
        const tasks = await autoApi('GET', '/api/tasks');
        renderTasks(tasks);
        if (!tasksOnly) renderHeartbeat(await autoApi('GET', '/api/heartbeat'));
    } catch (e) {
        console.error('Failed to load tasks:', e);
    }
    clearInterval(tasksPollTimer);
    tasksPollTimer = setInterval(() => {
        const view = document.getElementById('view-tasks');
        if (view && view.classList.contains('active')) loadTasks(true);
        else clearInterval(tasksPollTimer);
    }, 15000);
}

function createTaskWithMia() {
    const box = document.getElementById('newTaskText');
    const text = box.value.trim();
    if (!text) { box.focus(); return; }
    box.value = '';
    switchMainView('chat');
    const input = document.getElementById('chatInput');
    input.value = `Schedule this for me: ${text}`;
    sendMessage();
}

// ── Task list ───────────────────────────────────────────────

function renderTasks(tasks) {
    const container = document.getElementById('tasksList');
    container.textContent = '';
    if (!tasks.length) {
        const empty = mk('div', 'auto-empty');
        empty.append(
            mk('p', null, 'No scheduled tasks yet.'),
            mk('p', 'auto-hint', 'Describe one above, or just tell MIA in chat — e.g. "Every Monday at 9am, summarize my week\'s calendar".'),
        );
        container.append(empty);
        return;
    }
    tasks.slice().reverse().forEach(task => container.append(renderTaskCard(task)));
}

function taskState(task) {
    if (task.running) return ['running', 'Running…'];
    if (!task.enabled && task.status === 'active') return ['paused', 'Paused'];
    return [task.status, { active: 'Active', completed: 'Done', missed: 'Missed' }[task.status] || task.status];
}

function renderTaskCard(task) {
    const card = mk('div', 'task-card auto-card');
    const [stateClass, stateLabel] = taskState(task);

    const header = mk('div', 'task-card-header');
    const title = mk('div', 'auto-title');
    title.append(mk('span', 'task-name', task.name), mk('span', 'auto-kind', task.kind === 'agent' ? 'MIA task' : 'Command'));
    header.append(title, mk('span', `auto-pill ${stateClass}`, stateLabel));
    card.append(header);

    card.append(mk('div', task.kind === 'agent' ? 'auto-instructions' : 'task-command', task.instructions || task.command));

    const meta = mk('div', 'task-meta auto-meta');
    meta.append(
        mk('span', null, task.schedule_text),
        mk('span', null, `Next: ${task.enabled ? fmtTime(task.next_run) : '—'}`),
        mk('span', null, `To: ${task.deliver_to.join(' + ')}`),
    );
    if (task.run_count) meta.append(mk('span', null, `Runs: ${task.run_count}`));
    card.append(meta);

    if (task.last_run) {
        const last = mk('details', 'auto-last');
        const summary = mk('summary', `auto-last-summary ${task.last_status}`,
            `Last run ${fmtTime(task.last_run)} · ${{ done: 'done', failed: 'failed', waiting_approval: 'waiting for your approval' }[task.last_status] || task.last_status}`);
        last.append(summary, mk('pre', 'auto-result', task.last_result || ''));
        if (task.history && task.history.length > 1) {
            const older = mk('div', 'auto-history');
            task.history.slice(1, 6).forEach(run => older.append(mk('div', null, `${fmtTime(run.time)} · ${run.status}${run.manual ? ' (manual)' : ''}`)));
            last.append(older);
        }
        card.append(last);
    }

    const actions = mk('div', 'auto-actions');
    const run = mk('button', 'provider-btn', 'Run now');
    run.disabled = task.running;
    run.onclick = () => taskAction(task, 'run');
    actions.append(run);
    if (task.status === 'active') {
        const toggle = mk('button', 'provider-btn', task.enabled ? 'Pause' : 'Resume');
        toggle.onclick = () => taskAction(task, task.enabled ? 'pause' : 'resume');
        actions.append(toggle);
    }
    const del = mk('button', 'provider-link-btn danger', 'Delete');
    del.onclick = () => taskAction(task, 'delete');
    actions.append(del);
    card.append(actions);
    return card;
}

async function taskAction(task, action) {
    try {
        if (action === 'run') {
            await autoApi('POST', `/api/tasks/${task.id}/run`);
            showNotification('Scheduler', `Running "${task.name}" — you'll get the result when it finishes.`, 'info');
        } else if (action === 'pause' || action === 'resume') {
            await autoApi('POST', `/api/tasks/${task.id}/enabled`, { enabled: action === 'resume' });
        } else if (action === 'delete') {
            if (!confirm(`Delete the scheduled task "${task.name}"?`)) return;
            await autoApi('DELETE', `/api/tasks/${task.id}`);
        }
        loadTasks(true);
    } catch (e) {
        showNotification('Scheduler', e.message, 'error');
    }
}

// ── Heartbeat ───────────────────────────────────────────────

function renderHeartbeat(hb) {
    const container = document.getElementById('heartbeatCard');
    container.textContent = '';
    const card = mk('div', 'task-card auto-heartbeat');

    const header = mk('div', 'task-card-header');
    const title = mk('div', 'auto-title');
    title.append(mk('span', 'task-name', 'Heartbeat'), mk('span', 'auto-kind', 'checks in, alerts only when something matters'));
    header.append(title, mk('span', `auto-pill ${hb.enabled ? 'active' : 'paused'}`, hb.enabled ? 'On' : 'Off'));
    card.append(header);

    const grid = mk('div', 'auto-hb-grid');
    const field = (label, input) => { const l = mk('label', 'auto-field'); l.append(mk('span', 'provider-label', label), input); grid.append(l); return input; };

    const enabled = mk('select', 'provider-input');
    [['true', 'On'], ['false', 'Off']].forEach(([v, t]) => { const o = mk('option', null, t); o.value = v; enabled.append(o); });
    enabled.value = String(hb.enabled);
    field('Status', enabled);

    const every = mk('input', 'provider-input');
    every.type = 'number'; every.min = 5; every.value = hb.every_minutes;
    field('Every (minutes)', every);

    const hours = mk('input', 'provider-input');
    hours.value = hb.active_hours; hours.placeholder = '08:00-22:00 (empty = all day)';
    field('Active hours', hours);

    const deliver = mk('select', 'provider-input');
    [['telegram,web', 'Telegram + web'], ['telegram', 'Telegram'], ['web', 'Web only']].forEach(([v, t]) => { const o = mk('option', null, t); o.value = v; deliver.append(o); });
    deliver.value = hb.deliver_to.join(',');
    field('Alerts to', deliver);
    card.append(grid);

    const checklistLabel = mk('label', 'auto-field');
    const checklist = mk('textarea', 'provider-input auto-textarea auto-checklist');
    checklist.rows = 6;
    checklist.value = hb.checklist;
    checklist.spellcheck = false;
    checklistLabel.append(mk('span', 'provider-label', 'Checklist — one "- item" per line'), checklist);
    card.append(checklistLabel);

    const meta = mk('div', 'task-meta auto-meta');
    meta.append(mk('span', null, `Next: ${hb.enabled ? fmtTime(hb.next_run) : '—'}`), mk('span', null, `Last check: ${fmtTime(hb.last_run)}`));
    if (!hb.has_items) meta.append(mk('span', 'auto-warn', 'Add at least one checklist item'));
    card.append(meta);

    if (hb.last_alert) {
        const last = mk('details', 'auto-last');
        last.append(mk('summary', 'auto-last-summary', `Last alert ${fmtTime(hb.last_alert.time)}`), mk('pre', 'auto-result', hb.last_alert.text));
        card.append(last);
    }

    const result = mk('div', 'provider-result');
    const actions = mk('div', 'auto-actions');
    const save = mk('button', 'provider-btn primary', 'Save');
    save.onclick = async () => {
        try {
            renderHeartbeat(await autoApi('POST', '/api/heartbeat', {
                enabled: enabled.value === 'true',
                every_minutes: parseInt(every.value, 10),
                active_hours: hours.value,
                deliver_to: deliver.value.split(','),
                checklist: checklist.value,
            }));
            showNotification('Heartbeat', 'Saved', 'success');
        } catch (e) {
            result.textContent = e.message; result.className = 'provider-result fail';
        }
    };
    const runNow = mk('button', 'provider-btn', 'Check now');
    runNow.onclick = async () => {
        runNow.disabled = true;
        result.textContent = 'Checking…'; result.className = 'provider-result';
        try {
            const res = await autoApi('POST', '/api/heartbeat/run');
            result.textContent = res.status === 'ok' ? '✓ Nothing needs your attention.' : res.message;
            result.className = 'provider-result' + (res.status === 'ok' ? ' ok' : '');
        } catch (e) {
            result.textContent = e.message; result.className = 'provider-result fail';
        }
        runNow.disabled = false;
    };
    actions.append(runNow, save);
    card.append(actions, result);
    container.append(card);
}
