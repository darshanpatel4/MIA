/**
 * MIA WebSocket Manager
 * Handles all WebSocket connections with auto-reconnect.
 */

class MIAWebSocket {
    constructor(path, options = {}) {
        this.path = path;
        this.options = {
            reconnect: true,
            reconnectDelay: 2000,
            maxReconnectDelay: 30000,
            binaryType: 'blob',
            ...options,
        };
        this.ws = null;
        this.reconnectAttempts = 0;
        this.handlers = {};
        this.isConnected = false;
        this.intentionallyClosed = false;
    }

    connect() {
        const token = localStorage.getItem('mia_token');
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${location.host}${this.path}?token=${token}`;

        try {
            this.ws = new WebSocket(url);
            this.ws.binaryType = this.options.binaryType;

            this.ws.onopen = () => {
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this._emit('open');
            };

            this.ws.onmessage = (event) => {
                this._emit('message', event);
            };

            this.ws.onclose = (event) => {
                this.isConnected = false;
                this._emit('close', event);

                if (!this.intentionallyClosed && this.options.reconnect) {
                    this._reconnect();
                }
            };

            this.ws.onerror = (error) => {
                this._emit('error', error);
            };
        } catch (e) {
            console.error(`WebSocket connection error (${this.path}):`, e);
            if (this.options.reconnect) {
                this._reconnect();
            }
        }
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            if (typeof data === 'object' && !(data instanceof Blob) && !(data instanceof ArrayBuffer)) {
                this.ws.send(JSON.stringify(data));
            } else {
                this.ws.send(data);
            }
        }
    }

    sendJSON(data) {
        this.send(data);
    }

    close() {
        this.intentionallyClosed = true;
        if (this.ws) {
            this.ws.close();
        }
    }

    on(event, handler) {
        if (!this.handlers[event]) {
            this.handlers[event] = [];
        }
        this.handlers[event].push(handler);
        return this;
    }

    off(event, handler) {
        if (this.handlers[event]) {
            this.handlers[event] = this.handlers[event].filter(h => h !== handler);
        }
        return this;
    }

    _emit(event, data) {
        if (this.handlers[event]) {
            this.handlers[event].forEach(handler => {
                try {
                    handler(data);
                } catch (e) {
                    console.error(`WebSocket handler error (${event}):`, e);
                }
            });
        }
    }

    _reconnect() {
        this.reconnectAttempts++;
        const delay = Math.min(
            this.options.reconnectDelay * Math.pow(1.5, this.reconnectAttempts),
            this.options.maxReconnectDelay
        );

        console.log(`Reconnecting ${this.path} in ${delay}ms (attempt ${this.reconnectAttempts})`);
        setTimeout(() => {
            if (!this.intentionallyClosed) {
                this.connect();
            }
        }, delay);
    }
}

// Global WebSocket instances
const wsConnections = {};

function createWS(name, path, options = {}) {
    if (wsConnections[name]) {
        wsConnections[name].close();
    }
    const ws = new MIAWebSocket(path, options);
    wsConnections[name] = ws;
    return ws;
}

function getWS(name) {
    return wsConnections[name];
}
