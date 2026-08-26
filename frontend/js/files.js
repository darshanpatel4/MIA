/**
 * MIA File Browser Module
 * Visual file manager with upload/download.
 */

let currentPath = 'C:\\Users';

async function initFiles() {
    await loadDrives();
    await navigateTo(currentPath);
}

async function loadDrives() {
    // Drives are loaded as part of the file listing
}

async function navigateTo(path) {
    currentPath = path;
    try {
        const data = await apiFetch(`/api/files/list?path=${encodeURIComponent(path)}`);
        if (data.error) {
            showNotification('File Browser', data.error, 'error');
            return;
        }
        renderBreadcrumb(data.path);
        renderFileList(data.items || []);
    } catch (e) {
        showNotification('File Browser', 'Failed to load directory', 'error');
    }
}

function navigateUp() {
    const parent = currentPath.split('\\').slice(0, -1).join('\\');
    if (parent) {
        navigateTo(parent);
    } else {
        navigateTo('C:\\');
    }
}

function renderBreadcrumb(path) {
    const container = document.getElementById('pathBreadcrumb');
    const parts = path.split('\\').filter(Boolean);
    let accumulated = '';

    container.innerHTML = parts.map((part, i) => {
        accumulated += (i === 0 ? '' : '\\') + part;
        if (i === 0) accumulated = part; // Drive letter
        const fullPath = accumulated + (i === 0 ? '\\' : '');
        return `
            <button class="path-segment" onclick="navigateTo('${fullPath.replace(/\\/g, '\\\\')}')">${part}</button>
            ${i < parts.length - 1 ? '<span class="path-separator">›</span>' : ''}
        `;
    }).join('');
}

function renderFileList(items) {
    const container = document.getElementById('filesList');

    if (items.length === 0) {
        container.innerHTML = `
            <div class="empty-state-icon-wrap" style="text-align:center;padding:60px;color:var(--text-dim)">
                <div class="empty-state-icon">${ICON.folder}</div>
                <p>Empty directory</p>
            </div>
        `;
        return;
    }

    container.innerHTML = items.map(item => {
        const icon = item.is_dir ? ICON.folder : getFileIcon(item.extension);
        const size = item.size != null ? formatFileSize(item.size) : `${item.children_count >= 0 ? item.children_count : '?'} items`;
        const date = item.modified ? new Date(item.modified).toLocaleString() : '';
        const escapedPath = item.path.replace(/\\/g, '\\\\').replace(/'/g, "\\'");

        if (item.error) {
            return `
                <div class="file-item" style="opacity:0.5">
                    <span class="file-icon">${ICON.lock}</span>
                    <span class="file-name">${item.name}</span>
                    <span class="file-size" style="color:var(--danger)">Access denied</span>
                </div>
            `;
        }

        return `
            <button class="file-item" onclick="${item.is_dir ? `navigateTo('${escapedPath}')` : `previewFile('${escapedPath}')`}" oncontextmenu="showFileMenu(event, '${escapedPath}', ${item.is_dir})">
                <span class="file-icon">${icon}</span>
                <span class="file-name">${item.name}</span>
                <span class="file-size">${size}</span>
                <span class="file-date">${date}</span>
            </button>
        `;
    }).join('');
}

function getFileIcon(ext) {
    const imageExts = ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp'];
    const archiveExts = ['.zip', '.rar', '.7z', '.tar', '.gz'];
    const codeExts = ['.py', '.js', '.html', '.css', '.json', '.java', '.cpp', '.c', '.rs', '.go'];

    if (imageExts.includes(ext)) return ICON.fileImage;
    if (archiveExts.includes(ext)) return ICON.fileArchive;
    if (codeExts.includes(ext)) return ICON.fileCode;
    return ICON.file;
}

function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

async function previewFile(path) {
    // Download the file
    downloadFile(path);
}

function downloadFile(path) {
    const token = getToken();
    const url = `/api/files/download?path=${encodeURIComponent(path)}`;
    const link = document.createElement('a');
    link.href = url;
    link.download = path.split('\\').pop();
    // Add auth header via fetch and blob
    fetch(url, { headers: { 'Authorization': `Bearer ${token}` } })
        .then(res => res.blob())
        .then(blob => {
            const blobUrl = URL.createObjectURL(blob);
            link.href = blobUrl;
            link.click();
            URL.revokeObjectURL(blobUrl);
        });
}

async function uploadFile(input) {
    const files = input.files;
    if (!files.length) return;

    for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);

        try {
            const token = getToken();
            const res = await fetch(`/api/files/upload?directory=${encodeURIComponent(currentPath)}`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData,
            });
            const data = await res.json();

            if (data.success) {
                showNotification('Upload', `Uploaded: ${file.name}`, 'success');
            } else {
                showNotification('Upload', data.error || 'Failed', 'error');
            }
        } catch (e) {
            showNotification('Upload', `Error: ${e.message}`, 'error');
        }
    }

    input.value = '';
    refreshFiles();
}

function refreshFiles() {
    navigateTo(currentPath);
}

function showFileMenu(event, path, isDir) {
    event.preventDefault();
    // Simple context menu via prompt for now
    const action = prompt(
        `File: ${path.split('\\').pop()}\n\n` +
        `Actions:\n1. Delete\n2. Rename\n3. Download\n\nEnter number:`
    );

    if (action === '1') {
        if (confirm(`Delete "${path.split('\\').pop()}"?`)) {
            apiFetch(`/api/files/delete?path=${encodeURIComponent(path)}`, { method: 'DELETE' })
                .then(r => {
                    showNotification('Files', r.message || r.error, r.success ? 'success' : 'error');
                    refreshFiles();
                });
        }
    } else if (action === '2') {
        const newName = prompt('New name:', path.split('\\').pop());
        if (newName) {
            apiFetch(`/api/files/rename?path=${encodeURIComponent(path)}`, {
                method: 'POST',
                body: JSON.stringify({ new_name: newName }),
            }).then(r => {
                showNotification('Files', r.new_path ? `Renamed to ${newName}` : r.error, r.success ? 'success' : 'error');
                refreshFiles();
            });
        }
    } else if (action === '3') {
        downloadFile(path);
    }
}
