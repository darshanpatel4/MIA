/**
 * MIA Screen Module
 * Real-time screen viewer with remote mouse/keyboard control.
 */

let screenWS = null;
let controlWS = null;
let isStreaming = false;
let isControlActive = false;
let frameCount = 0;
let fpsInterval = null;

function initScreen() {
    // FPS counter
    fpsInterval = setInterval(() => {
        document.getElementById('fpsCounter').textContent = `${frameCount} FPS`;
        frameCount = 0;
    }, 1000);

    loadMonitors();
}

// ── Multi-Monitor Selection ─────────────────────────────────

async function loadMonitors() {
    const select = document.getElementById('monitorSelect');
    if (!select) return;

    try {
        const monitors = await apiFetch('/api/screen/monitors');
        if (!Array.isArray(monitors) || monitors.length === 0) return;

        const previousValue = select.value;
        select.innerHTML = monitors.map(m =>
            `<option value="${m.index}">Monitor ${m.index}${m.is_primary ? ' (Primary)' : ''} — ${m.width}x${m.height}</option>`
        ).join('');

        // Hide the picker entirely when there's only one screen — nothing to pick.
        select.parentElement.style.display = monitors.length > 1 ? '' : 'none';

        // Restore previous selection if it still exists, otherwise default to primary/first.
        if (monitors.some(m => String(m.index) === previousValue)) {
            select.value = previousValue;
        } else {
            const primary = monitors.find(m => m.is_primary) || monitors[0];
            select.value = primary.index;
        }
    } catch (e) {
        console.error('Failed to load monitors:', e);
    }
}

function setStreamMonitor(index) {
    if (screenWS && screenWS.isConnected) {
        screenWS.sendJSON({ action: 'set_monitor', monitor: parseInt(index) });
    }
}

function toggleStream() {
    if (isStreaming) {
        stopStream();
    } else {
        startStream();
    }
}

function startStream() {
    screenWS = createWS('screen', '/ws/screen', { binaryType: 'blob', reconnect: false });

    screenWS.on('open', () => {
        isStreaming = true;
        document.getElementById('streamToggle').innerHTML = `${ICON.stop}Stop Stream`;
        document.getElementById('streamToggle').classList.add('active');
        document.getElementById('streamStatus').textContent = 'Streaming';
        document.getElementById('noStreamMsg').style.display = 'none';
        document.getElementById('screenImage').style.display = 'block';

        // Apply whichever monitor is currently selected in the picker
        const monitorSelect = document.getElementById('monitorSelect');
        if (monitorSelect && monitorSelect.value) {
            setStreamMonitor(monitorSelect.value);
        }
    });

    screenWS.on('message', (event) => {
        if (event.data instanceof Blob) {
            const img = document.getElementById('screenImage');
            const url = URL.createObjectURL(event.data);
            const oldUrl = img.src;
            img.src = url;
            if (oldUrl && oldUrl.startsWith('blob:')) {
                URL.revokeObjectURL(oldUrl);
            }
            frameCount++;
        }
    });

    screenWS.on('close', () => {
        isStreaming = false;
        document.getElementById('streamToggle').innerHTML = `${ICON.play}Start Stream`;
        document.getElementById('streamToggle').classList.remove('active');
        document.getElementById('streamStatus').textContent = 'Stopped';
    });

    screenWS.connect();
}

function stopStream() {
    if (screenWS) {
        screenWS.close();
        screenWS = null;
    }
    isStreaming = false;
    document.getElementById('streamToggle').innerHTML = `${ICON.play}Start Stream`;
    document.getElementById('streamToggle').classList.remove('active');
    document.getElementById('streamStatus').textContent = 'Stopped';
    document.getElementById('screenImage').style.display = 'none';
    document.getElementById('noStreamMsg').style.display = 'flex';
}

function setStreamQuality(quality) {
    if (screenWS && screenWS.isConnected) {
        screenWS.sendJSON({ action: 'set_quality', quality: parseInt(quality) });
    }
}

function setStreamScale(scale) {
    if (screenWS && screenWS.isConnected) {
        screenWS.sendJSON({ action: 'set_scale', scale: parseFloat(scale) });
    }
}

// ── Remote Control ──────────────────────────────────────────

function toggleControl() {
    isControlActive = !isControlActive;
    const btn = document.getElementById('controlToggle');
    const viewer = document.getElementById('screenViewer');

    if (isControlActive) {
        btn.innerHTML = `${ICON.mouse}Control: ON`;
        btn.classList.add('active');
        viewer.classList.add('control-active');
        startControlWS();
        attachControlListeners();
    } else {
        btn.innerHTML = `${ICON.mouse}Control: OFF`;
        btn.classList.remove('active');
        viewer.classList.remove('control-active');
        detachControlListeners();
        if (controlWS) {
            controlWS.close();
            controlWS = null;
        }
    }
}

function startControlWS() {
    controlWS = createWS('control', '/ws/control', { reconnect: true });
    controlWS.connect();
}

function sendControlEvent(data) {
    if (controlWS && controlWS.isConnected) {
        const img = document.getElementById('screenImage');
        data.viewWidth = img.naturalWidth || img.width;
        data.viewHeight = img.naturalHeight || img.height;
        controlWS.sendJSON(data);
    }
}

function attachControlListeners() {
    const viewer = document.getElementById('screenViewer');
    const img = document.getElementById('screenImage');

    img.addEventListener('mousedown', onMouseDown);
    img.addEventListener('mouseup', onMouseUp);
    img.addEventListener('mousemove', onMouseMove);
    img.addEventListener('click', onClick);
    img.addEventListener('dblclick', onDblClick);
    img.addEventListener('wheel', onWheel);
    img.addEventListener('contextmenu', onContextMenu);
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('keyup', onKeyUp);
}

function detachControlListeners() {
    const img = document.getElementById('screenImage');
    img.removeEventListener('mousedown', onMouseDown);
    img.removeEventListener('mouseup', onMouseUp);
    img.removeEventListener('mousemove', onMouseMove);
    img.removeEventListener('click', onClick);
    img.removeEventListener('dblclick', onDblClick);
    img.removeEventListener('wheel', onWheel);
    img.removeEventListener('contextmenu', onContextMenu);
    document.removeEventListener('keydown', onKeyDown);
    document.removeEventListener('keyup', onKeyUp);
}

function getImgCoords(e) {
    const img = document.getElementById('screenImage');
    const rect = img.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * (img.naturalWidth || img.width);
    const y = ((e.clientY - rect.top) / rect.height) * (img.naturalHeight || img.height);
    return { x: Math.round(x), y: Math.round(y) };
}

function getButton(e) {
    return e.button === 2 ? 'right' : e.button === 1 ? 'middle' : 'left';
}

function onMouseDown(e) { e.preventDefault(); const c = getImgCoords(e); sendControlEvent({ type: 'mousedown', ...c, button: getButton(e) }); }
function onMouseUp(e) { e.preventDefault(); const c = getImgCoords(e); sendControlEvent({ type: 'mouseup', ...c, button: getButton(e) }); }
function onMouseMove(e) { if (e.buttons > 0) { const c = getImgCoords(e); sendControlEvent({ type: 'mousemove', ...c }); } }
function onClick(e) { e.preventDefault(); const c = getImgCoords(e); sendControlEvent({ type: 'click', ...c, button: getButton(e) }); }
function onDblClick(e) { e.preventDefault(); const c = getImgCoords(e); sendControlEvent({ type: 'dblclick', ...c }); }
function onWheel(e) { e.preventDefault(); sendControlEvent({ type: 'scroll', delta: Math.sign(-e.deltaY) * 3 }); }
function onContextMenu(e) { e.preventDefault(); }

const KEY_MAP = {
    'Control': 'ctrl', 'Alt': 'alt', 'Shift': 'shift', 'Meta': 'win',
    'Enter': 'enter', 'Backspace': 'backspace', 'Delete': 'delete',
    'Tab': 'tab', 'Escape': 'escape', 'ArrowUp': 'up', 'ArrowDown': 'down',
    'ArrowLeft': 'left', 'ArrowRight': 'right', ' ': 'space',
    'Home': 'home', 'End': 'end', 'PageUp': 'pageup', 'PageDown': 'pagedown',
    'Insert': 'insert', 'CapsLock': 'capslock',
    'F1': 'f1', 'F2': 'f2', 'F3': 'f3', 'F4': 'f4', 'F5': 'f5', 'F6': 'f6',
    'F7': 'f7', 'F8': 'f8', 'F9': 'f9', 'F10': 'f10', 'F11': 'f11', 'F12': 'f12',
};

function onKeyDown(e) {
    if (!isControlActive || document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA') return;
    e.preventDefault();
    const key = KEY_MAP[e.key] || e.key;
    sendControlEvent({ type: 'keydown', key });
}

function onKeyUp(e) {
    if (!isControlActive || document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA') return;
    e.preventDefault();
    const key = KEY_MAP[e.key] || e.key;
    sendControlEvent({ type: 'keyup', key });
}

function toggleFullscreen() {
    const panel = document.getElementById('screenPanel');
    panel.classList.toggle('fullscreen');
}
