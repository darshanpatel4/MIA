/**
 * MIA AI Models
 * Choose which model MIA thinks with, save API keys, and sign in to Claude with a browser.
 * Built with textContent only — provider output (CLI text, errors) is untrusted.
 */

let providersState = null;
let claudeTab = null;          // 'login' | 'key' — which Claude auth tab is showing
let claudeLoginTimer = null;

const PROVIDER_SHORT = { openrouter: 'openrouter', anthropic: 'claude', openai: 'gpt', gemini: 'gemini', deepseek: 'deepseek', ollama: 'ollama' };
let openRouterModels = null;   // cached model catalogue: [{id, name, context, input_per_m, output_per_m}]

function h(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
}

async function aiApi(method, path, body) {
    const res = await fetch('/api/ai' + path, {
        method,
        headers: {
            'Authorization': `Bearer ${localStorage.getItem('mia_token')}`,
            ...(body ? { 'Content-Type': 'application/json' } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
    return data;
}

async function loadProviders() {
    const container = document.getElementById('providersContent');
    if (!container) return;
    try {
        providersState = await aiApi('GET', '/providers');
        renderProviders();
    } catch (e) {
        container.textContent = `Couldn't load AI models: ${e.message}`;
    }
}

async function refreshModelSelector() {
    // Coming back from the OpenRouter sign-in page: open Settings so the user can pick a model.
    let justConnected = false;
    try {
        justConnected = localStorage.getItem('mia_openrouter_connected') === '1';
        localStorage.removeItem('mia_openrouter_connected');
    } catch (e) { /* storage unavailable */ }
    if (justConnected) {
        switchMainView('settings');
        showNotification('OpenRouter', 'Connected. Pick a model and click "Use this model".', 'success');
    }
    try {
        const state = providersState || await aiApi('GET', '/providers');
        updateModelSelector(state);
    } catch (e) { /* not logged in yet */ }
}

function updateModelSelector(state) {
    const selector = document.getElementById('modelSelector');
    if (!selector || !state) return;
    selector.firstChild.textContent = `${PROVIDER_SHORT[state.active] || state.active} · ${state.active_model || '?'} `;
    selector.classList.toggle('not-ready', !state.agent_ready);
    selector.title = state.agent_ready ? 'Change model' : `Model not ready: ${state.agent_error || 'set it up in Settings'}`;
}

// ── Rendering ───────────────────────────────────────────────

function renderProviders() {
    const container = document.getElementById('providersContent');
    const state = providersState;
    container.textContent = '';
    updateModelSelector(state);

    const activeProvider = state.providers.find(p => p.active);
    const banner = h('div', 'providers-banner' + (state.agent_ready ? '' : ' error'));
    banner.append(
        h('span', 'providers-banner-label', 'MIA is using'),
        h('strong', null, activeProvider ? activeProvider.label : state.active),
        h('code', null, state.active_model || '—'),
    );
    if (!state.agent_ready) {
        banner.append(h('span', 'providers-banner-error', state.agent_error || 'Not set up yet — add a key or sign in below.'));
    }
    container.append(banner);

    const grid = h('div', 'providers-grid');
    state.providers.forEach(provider => grid.append(renderProviderCard(provider)));
    container.append(grid);
}

function renderProviderCard(p) {
    const card = h('div', 'provider-card' + (p.active ? ' active' : ''));
    card.dataset.provider = p.id;

    const head = h('div', 'provider-head');
    head.append(h('span', 'provider-name', p.label));
    if (p.recommended && !p.active) head.append(h('span', 'provider-pill recommended', 'Recommended'));
    if (p.active) head.append(h('span', 'provider-pill in-use', 'In use'));
    else if (p.ready) head.append(h('span', 'provider-pill ready', 'Ready'));
    else head.append(h('span', 'provider-pill', 'Not set up'));
    card.append(head);

    // Model
    const modelRow = h('label', 'provider-field');
    modelRow.append(h('span', 'provider-label', 'Model'));
    const listId = `models-${p.id}`;
    const modelInput = h('input', 'provider-input provider-model');
    modelInput.value = p.model;
    modelInput.setAttribute('list', listId);
    modelInput.spellcheck = false;
    const datalist = h('datalist');
    datalist.id = listId;
    p.models.forEach(m => { const o = h('option'); o.value = m; datalist.append(o); });
    modelRow.append(modelInput, datalist);
    card.append(modelRow);
    if (p.id === 'openrouter') {
        const price = h('div', 'provider-note provider-price');
        modelRow.append(price);
        attachOpenRouterCatalogue(modelInput, datalist, price);
    }

    // Authentication
    if (p.id === 'anthropic') card.append(renderClaudeAuth(p));
    else if (p.id === 'openrouter') card.append(renderOpenRouterAuth(p));
    else if (p.needs_key) card.append(renderKeyForm(p));
    else card.append(h('p', 'provider-note', `Runs locally at ${p.base_url} — no key needed. Pull the model with \`ollama pull ${p.model}\`.`));

    if (p.id === 'openai') {
        card.append(h('p', 'provider-note', "OpenAI doesn't offer browser sign-in for apps like MIA, so this uses an API key."));
    }

    // Actions
    const actions = h('div', 'provider-actions');
    const testBtn = h('button', 'provider-btn', 'Test connection');
    testBtn.onclick = () => testProvider(p.id, card);
    const useBtn = h('button', 'provider-btn primary', p.active ? 'Save model' : 'Use this model');
    useBtn.onclick = () => useProvider(p.id, card);
    actions.append(testBtn, useBtn);
    card.append(actions, h('div', 'provider-result'));
    return card;
}

function renderKeyForm(p, onlyForm) {
    const wrap = h('div', 'provider-auth');
    if (p.key_saved) {
        const saved = h('div', 'provider-saved');
        saved.append(h('span', null, `API key saved ${p.key_hint}`));
        const remove = h('button', 'provider-link-btn danger', 'Remove');
        remove.onclick = () => providerAction(`/providers/${p.id}/key`, 'DELETE', null, `${p.label} key removed`);
        saved.append(remove);
        wrap.append(saved);
    }
    const row = h('div', 'provider-key-row');
    const input = h('input', 'provider-input');
    input.type = 'password';
    input.autocomplete = 'off';
    input.placeholder = p.key_saved ? 'Paste a new key to replace it' : 'Paste API key';
    const save = h('button', 'provider-btn', 'Save key');
    save.onclick = () => {
        if (!input.value.trim()) return;
        providerAction(`/providers/${p.id}/key`, 'POST', { api_key: input.value }, `${p.label} key saved`);
    };
    input.addEventListener('keydown', e => { if (e.key === 'Enter') save.click(); });
    row.append(input, save);
    wrap.append(row);
    if (p.key_url && !onlyForm) {
        const link = h('a', 'provider-link', 'Get an API key ↗');
        link.href = p.key_url;
        link.target = '_blank';
        link.rel = 'noopener';
        wrap.append(link);
    }
    return wrap;
}

// ── OpenRouter ──────────────────────────────────────────────

async function attachOpenRouterCatalogue(input, datalist, priceEl) {
    const showPrice = () => {
        const m = (openRouterModels || []).find(x => x.id === input.value.trim());
        priceEl.textContent = m
            ? `${m.name} · $${m.input_per_m} in / $${m.output_per_m} out per 1M tokens · ${Math.round((m.context || 0) / 1000)}K context`
            : (openRouterModels ? 'Type to search all tool-capable models (e.g. "claude", "gemini", "free").' : '');
    };
    input.addEventListener('input', showPrice);
    try {
        if (!openRouterModels) openRouterModels = await aiApi('GET', '/providers/openrouter/models');
        datalist.textContent = '';
        openRouterModels.forEach(m => {
            const o = h('option');
            o.value = m.id;
            o.label = `${m.name} — $${m.input_per_m}/$${m.output_per_m} per 1M`;
            datalist.append(o);
        });
        showPrice();
    } catch (e) {
        priceEl.textContent = `Couldn't load the model list: ${e.message}`;
    }
}

function renderOpenRouterAuth(p) {
    const wrap = h('div', 'provider-auth');
    wrap.append(h('p', 'provider-note', 'One account and key for hundreds of models — Claude, GPT, Gemini, Llama, DeepSeek and more. Pay-as-you-go credits on openrouter.ai.'));
    if (p.key_saved) {
        const saved = h('div', 'provider-saved');
        saved.append(h('span', null, `Connected (key ${p.key_hint})`));
        const remove = h('button', 'provider-link-btn danger', 'Disconnect');
        remove.onclick = () => providerAction('/providers/openrouter/key', 'DELETE', null, 'OpenRouter disconnected');
        saved.append(remove);
        wrap.append(saved);
    }

    const buttons = h('div', 'provider-key-row');
    const connect = h('button', 'provider-btn', p.key_saved ? 'Reconnect with OpenRouter' : 'Connect with OpenRouter');
    connect.title = 'Sign in on openrouter.ai and come straight back here — no key to copy.';
    connect.onclick = async () => {
        try {
            const { url } = await aiApi('POST', '/providers/openrouter/oauth/start', { callback_url: `${location.origin}/openrouter-callback` });
            location.href = url;
        } catch (e) { showNotification('OpenRouter', e.message, 'error'); }
    };
    const withCode = h('button', 'provider-btn', 'Use a code instead');
    withCode.title = 'For another device, or if the redirect back to MIA fails: sign in, then paste the code OpenRouter shows.';
    buttons.append(connect, withCode);
    wrap.append(buttons);

    const codePanel = h('div', 'claude-login');
    codePanel.hidden = true;
    withCode.onclick = async () => {
        try {
            const { url } = await aiApi('POST', '/providers/openrouter/oauth/start', {});
            codePanel.hidden = false;
            codePanel.textContent = '';
            const link = h('a', 'provider-link', 'Open the OpenRouter sign-in ↗');
            link.href = url; link.target = '_blank'; link.rel = 'noopener';
            const row = h('div', 'provider-key-row');
            const code = h('input', 'provider-input');
            code.placeholder = 'Paste the code OpenRouter shows';
            code.autocomplete = 'off';
            const send = h('button', 'provider-btn', 'Connect');
            send.onclick = () => code.value.trim() && providerAction('/providers/openrouter/oauth/finish', 'POST', { code: code.value.trim() }, 'OpenRouter connected');
            code.addEventListener('keydown', e => { if (e.key === 'Enter') send.click(); });
            row.append(code, send);
            codePanel.append(h('div', 'claude-login-state', 'Open the link on any device, approve, then paste the code here.'), link, row);
            window.open(url, '_blank', 'noopener');
        } catch (e) { showNotification('OpenRouter', e.message, 'error'); }
    };
    wrap.append(codePanel);

    const keyToggle = h('details', 'provider-key-details');
    keyToggle.append(h('summary', 'provider-link-btn', 'Or paste an API key'), renderKeyForm(p, true));
    wrap.append(keyToggle);
    return wrap;
}

function renderClaudeAuth(p) {
    const wrap = h('div', 'provider-auth');
    if (!claudeTab) claudeTab = p.auth_mode === 'api_key' && p.key_saved ? 'key' : 'login';

    const tabs = h('div', 'provider-tabs');
    [['login', 'Sign in with browser'], ['key', 'API key']].forEach(([id, label]) => {
        const tab = h('button', 'provider-tab' + (claudeTab === id ? ' active' : ''), label);
        tab.onclick = () => { claudeTab = id; renderProviders(); };
        tabs.append(tab);
    });
    wrap.append(tabs);

    if (claudeTab === 'key') {
        wrap.append(renderKeyForm(p));
        if (p.key_saved && p.auth_mode === 'login') {
            const switchBtn = h('button', 'provider-link-btn', 'Use this saved key instead of the browser sign-in');
            switchBtn.onclick = () => providerAction('/providers/anthropic/auth-mode', 'POST', { mode: 'api_key' }, 'Claude now uses the API key');
            wrap.append(switchBtn);
        }
        return wrap;
    }

    if (p.auth_mode === 'login') {
        wrap.append(h('div', 'provider-saved', 'Signed in with your Claude Console account'));
    }
    if (!p.ant_installed) {
        wrap.append(h('p', 'provider-note', p.ant_install_hint));
        const install = h('button', 'provider-btn', 'Install sign-in helper');
        install.onclick = async () => {
            install.disabled = true;
            install.textContent = 'Downloading…';
            await providerAction('/providers/anthropic/install-cli', 'POST', null, 'Sign-in helper installed');
            install.disabled = false;
            install.textContent = 'Install sign-in helper';
        };
        wrap.append(install);
        return wrap;
    }
    wrap.append(h('p', 'provider-note', 'Uses your Claude Console account (API billing) through the official Anthropic CLI — no key to copy.'));

    const buttons = h('div', 'provider-key-row');
    const here = h('button', 'provider-btn', p.auth_mode === 'login' ? 'Sign in again' : 'Sign in on this PC');
    here.onclick = () => startClaudeLogin(false);
    const remote = h('button', 'provider-btn', 'Sign in from another device');
    remote.title = "Opens no browser on the PC — open the link on any device, approve, and paste the code it shows back here.";
    remote.onclick = () => startClaudeLogin(true);
    buttons.append(here, remote);
    wrap.append(buttons);

    if (p.auth_mode !== 'login') {
        const useExisting = h('button', 'provider-link-btn', 'Already ran `ant auth login` in a terminal? Use that sign-in');
        useExisting.onclick = () => providerAction('/providers/anthropic/auth-mode', 'POST', { mode: 'login' }, 'Claude now uses your browser sign-in');
        wrap.append(useExisting);
    }

    const panel = h('div', 'claude-login');
    panel.id = 'claudeLoginPanel';
    panel.hidden = true;
    wrap.append(panel);
    return wrap;
}

// ── Actions ─────────────────────────────────────────────────

async function providerAction(path, method, body, successMessage) {
    try {
        providersState = await aiApi(method, path, body);
        renderProviders();
        showNotification('AI Models', successMessage, 'success');
    } catch (e) {
        showNotification('AI Models', e.message, 'error');
    }
}

function setCardResult(card, text, ok) {
    const result = card.querySelector('.provider-result');
    result.textContent = text;
    result.className = 'provider-result' + (ok === true ? ' ok' : ok === false ? ' fail' : '');
}

async function testProvider(providerId, card) {
    const model = card.querySelector('.provider-model').value;
    setCardResult(card, 'Testing…');
    try {
        const res = await aiApi('POST', `/providers/${providerId}/test`, { model });
        setCardResult(card, res.message, res.ok);
    } catch (e) {
        setCardResult(card, e.message, false);
    }
}

async function useProvider(providerId, card) {
    const model = card.querySelector('.provider-model').value;
    try {
        providersState = await aiApi('POST', '/active', { provider: providerId, model });
        renderProviders();
        const active = providersState.providers.find(p => p.active);
        if (providersState.agent_ready) {
            showNotification('AI Models', `MIA now uses ${active.label} · ${providersState.active_model}`, 'success');
        } else {
            showNotification('AI Models', `Switched, but it isn't ready: ${providersState.agent_error}`, 'warning');
        }
    } catch (e) {
        setCardResult(card, e.message, false);
    }
}

// ── Claude browser sign-in ──────────────────────────────────

let claudeLoginNoBrowser = false;

async function startClaudeLogin(noBrowser) {
    claudeLoginNoBrowser = noBrowser;
    try {
        renderClaudeLogin(await aiApi('POST', '/providers/anthropic/login', { no_browser: noBrowser }));
        clearInterval(claudeLoginTimer);
        claudeLoginTimer = setInterval(pollClaudeLogin, 1500);
    } catch (e) {
        showNotification('Claude sign-in', e.message, 'error');
    }
}

async function pollClaudeLogin() {
    try {
        const status = await aiApi('GET', '/providers/anthropic/login');
        renderClaudeLogin(status);
        if (status.state !== 'running') {
            clearInterval(claudeLoginTimer);
            if (status.state === 'success') {
                showNotification('Claude sign-in', 'Signed in — Claude is ready to use.', 'success');
                claudeTab = 'login';
                loadProviders();
            }
        }
    } catch (e) {
        clearInterval(claudeLoginTimer);
    }
}

function buildClaudeLoginPanel(panel) {
    const stateEl = h('div', 'claude-login-state');
    const links = h('div', 'claude-login-links');
    const output = h('pre', 'claude-login-output');
    const row = h('div', 'provider-key-row');
    const code = h('input', 'provider-input');
    code.placeholder = 'Paste the code from the browser (if asked)';
    code.autocomplete = 'off';
    const send = h('button', 'provider-btn', 'Send code');
    send.onclick = async () => {
        if (!code.value.trim()) return;
        try {
            renderClaudeLogin(await aiApi('POST', '/providers/anthropic/login/input', { text: code.value }));
            code.value = '';
        } catch (e) {
            showNotification('Claude sign-in', e.message, 'error');
        }
    };
    code.addEventListener('keydown', e => { if (e.key === 'Enter') send.click(); });
    const cancel = h('button', 'provider-link-btn danger', 'Cancel');
    cancel.onclick = async () => {
        clearInterval(claudeLoginTimer);
        renderClaudeLogin(await aiApi('DELETE', '/providers/anthropic/login'));
    };
    row.append(code, send, cancel);
    panel.append(stateEl, links, output, row);
    panel.dataset.built = '1';
}

// Updates the panel in place so a half-typed code survives each poll.
function renderClaudeLogin(status) {
    const panel = document.getElementById('claudeLoginPanel');
    if (!panel) return;
    if (!panel.dataset.built) buildClaudeLoginPanel(panel);
    panel.hidden = false;

    const titles = {
        running: claudeLoginNoBrowser
            ? 'Open the sign-in link on any device, approve, then paste the code that page shows below.'
            : 'Finish signing in in the browser window that opened on the PC running MIA…',
        success: 'Signed in.',
        failed: 'Sign-in failed — see the output below.',
        idle: '',
    };
    const [stateEl, links, output, row] = panel.children;
    stateEl.textContent = titles[status.state] ?? status.state;
    stateEl.className = `claude-login-state ${status.state}`;

    links.textContent = '';
    (status.urls || []).forEach(url => {
        const a = h('a', 'provider-link', 'Open sign-in link ↗');
        a.href = url;
        a.target = '_blank';
        a.rel = 'noopener';
        links.append(a);
    });
    output.textContent = (status.output || '').trim();
    output.hidden = !output.textContent;
    row.hidden = status.state !== 'running';
}
