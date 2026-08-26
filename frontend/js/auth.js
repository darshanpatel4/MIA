/**
 * MIA Auth Module
 * Token management and API authentication.
 */

function getToken() {
    return localStorage.getItem('mia_token');
}

function setToken(token) {
    localStorage.setItem('mia_token', token);
}

function removeToken() {
    localStorage.removeItem('mia_token');
}

async function checkAuth() {
    const token = getToken();
    if (!token) {
        window.location.href = '/login';
        return false;
    }

    try {
        const res = await apiFetch('/api/auth/session');
        if (!res.authenticated) {
            removeToken();
            window.location.href = '/login';
            return false;
        }
        return true;
    } catch (e) {
        return true; // Assume authenticated if server is down
    }
}

async function logout() {
    try {
        await apiFetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {}
    removeToken();
    window.location.href = '/login';
}

/**
 * Authenticated fetch wrapper.
 */
async function apiFetch(url, options = {}) {
    const token = getToken();
    const headers = {
        ...options.headers,
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    // Don't set Content-Type for FormData (let browser set it)
    if (!(options.body instanceof FormData)) {
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    }

    const res = await fetch(url, { ...options, headers });

    if (res.status === 401) {
        removeToken();
        window.location.href = '/login';
        throw new Error('Unauthorized');
    }

    return res.json();
}
