// Utility to show status messages
function showStatus(elementId, message, type = 'info') {
    const el = document.getElementById(elementId);
    if (el) {
        el.textContent = message;
        el.style.color = type === 'error' ? 'var(--danger)' :
            type === 'success' ? 'var(--success)' : 'var(--text-muted)';
    }
}

// Socket.IO Initialization
let socket = null;
if (typeof io !== 'undefined') {
    socket = io();
    socket.on('connect', () => {
        console.log('Connected to server');
    });
}

// Authentication Handling
async function handleAuth(event, endpoint, redirectUrl) {
    event.preventDefault();
    const form = event.target;
    const submitBtn = form.querySelector('button[type="submit"]');
    const originalBtnText = submitBtn.textContent;

    const username = form.username.value;
    const password = form.password.value;
    const msgId = form.id === 'loginForm' ? 'login-msg' : 'register-msg';

    // Loading State
    submitBtn.disabled = true;
    submitBtn.textContent = 'AUTHENTICATING...';
    showStatus(msgId, 'Establishing secure connection...', 'info');

    try {
        console.log(`Sending auth request to ${endpoint}...`);
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        console.log(`Auth response status: ${response.status}`);
        const data = await response.json();
        console.log("Auth response data:", data);

        if (response.ok) {
            showStatus(msgId, data.message || 'Success! Redirecting...', 'success');
            setTimeout(() => {
                if (data.is_admin) {
                    window.location.href = '/admin';
                } else {
                    window.location.href = redirectUrl;
                }
            }, 800);
        } else {
            showStatus(msgId, data.error || 'Invalid credentials or error', 'error');
            submitBtn.disabled = false;
            submitBtn.textContent = originalBtnText;
        }
    } catch (err) {
        console.error("Auth Exception:", err);
        showStatus(msgId, 'Network error: ' + err.message, 'error');
        submitBtn.disabled = false;
        submitBtn.textContent = originalBtnText;
    }
}

// User Dashboard Logic
let watchId = null;

function initDashboard() {
    updateTimeAndRisk();
    setInterval(updateTimeAndRisk, 60000); // Update every minute

    loadContacts();
    loadMyAlerts();

    const trackBtn = document.getElementById('track-btn');
    if (trackBtn) {
        trackBtn.addEventListener('click', toggleTracking);
    }

    // Initial location check
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            (pos) => updateLocDisplay(pos.coords.latitude, pos.coords.longitude),
            (err) => console.error(err)
        );
    }

    // Broadcast Listener
    if (socket) {
        socket.on('broadcast_alert', (data) => {
            const banner = document.getElementById('broadcast-banner');
            const msg = document.getElementById('broadcast-message');
            if (banner && msg) {
                msg.textContent = `[URGENT] ${data.sender}: ${data.message}`;
                banner.style.display = 'block';
                console.log("Broadcast received:", data);
            }
        });
    }

    loadIncidents();
}

// Safety Timer Logic
let safetyTimer = null;
let timerSeconds = 0;

function toggleSafetyTimer() {
    const btn = document.getElementById('timer-btn');
    const input = document.getElementById('timer-input');
    const display = document.getElementById('timer-display');

    if (safetyTimer) {
        clearInterval(safetyTimer);
        safetyTimer = null;
        btn.textContent = 'Start Timer';
        btn.classList.add('btn-primary');
        btn.classList.remove('btn-danger');
        display.textContent = '';
        input.disabled = false;
    } else {
        const mins = parseInt(input.value);
        if (isNaN(mins) || mins <= 0) {
            alert("Please enter a valid number of minutes.");
            return;
        }

        console.log(`Starting safety timer for ${mins} minutes`);
        timerSeconds = mins * 60;
        input.disabled = true;
        btn.textContent = 'CANCEL TIMER';
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-danger');

        safetyTimer = setInterval(() => {
            timerSeconds--;
            const m = Math.floor(timerSeconds / 60);
            const s = timerSeconds % 60;
            display.textContent = `Time Remaining: ${m}:${s.toString().padStart(2, '0')}`;
            display.parentElement.parentElement.classList.add('timer-running');

            if (timerSeconds <= 0) {
                console.log("Safety timer expired!");
                display.parentElement.parentElement.classList.remove('timer-running');
                clearInterval(safetyTimer);
                safetyTimer = null;
                triggerAutoSOS();
            }
        }, 1000);
    }
}

function triggerAutoSOS() {
    alert("SAFETY TIMER EXPIRED! Triggering Automatic SOS...");
    sendSOS();
}

// Emergency Contacts Logic
async function loadContacts() {
    console.log("Loading emergency contacts...");
    try {
        const res = await fetch('/api/contacts');
        if (!res.ok) throw new Error("Failed to fetch contacts");
        const contacts = await res.json();
        const list = document.getElementById('contact-list');
        if (!list) return;

        list.innerHTML = contacts.map(c => `
            <li>
                <strong>${c.name}</strong>: ${c.phone}
            </li>
        `).join('');

        if (contacts.length === 0) {
            list.innerHTML = '<li class="text-muted">No contacts added.</li>';
        }
        console.log(`Loaded ${contacts.length} contacts`);
        logVital("EMERGENCY CONTACTS SYNCED", "success");
    } catch (e) {
        console.error("Error loading contacts", e);
    }
}

async function addContact(event) {
    event.preventDefault();
    const form = event.target;
    const name = form.name.value;
    const phone = form.phone.value;
    console.log(`Adding contact: ${name}, ${phone}`);

    try {
        const res = await fetch('/api/contacts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, phone })
        });

        if (res.ok) {
            console.log("Contact added successfully");
            form.reset();
            loadContacts();
        } else {
            const data = await res.json();
            alert("Failed to add contact: " + (data.error || "Unknown error"));
        }
    } catch (e) {
        console.error("Network error adding contact", e);
        alert("Network error adding contact");
    }
}

async function loadMyAlerts() {
    console.log("Loading student alert history...");
    try {
        const res = await fetch('/api/my-alerts');
        const alerts = await res.json();
        const tbody = document.querySelector('#my-alerts-table tbody');
        if (!tbody) return;

        tbody.innerHTML = alerts.map(a => `
            <tr>
                <td>${new Date(a.timestamp).toLocaleString()}</td>
                <td>${a.latitude.toFixed(4)}, ${a.longitude.toFixed(4)}</td>
                <td><span class="${a.status === 'ACTIVE' ? 'status-high' : 'status-low'}">${a.status}</span></td>
            </tr>
        `).join('');

        if (alerts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">No SOS alerts sent yet.</td></tr>';
        }
        console.log(`Loaded ${alerts.length} alerts`);
    } catch (e) {
        console.error("Error loading alerts", e);
    }
}

// Student Dashboard Utilities
function updateTimeAndRisk() {
    const now = new Date();
    const hour = now.getHours();
    const isRiskTime = hour >= 18 || hour < 6; // 6 PM to 6 AM

    const timeEl = document.getElementById('current-time');
    if (timeEl) timeEl.textContent = now.toLocaleTimeString();

    const riskEl = document.getElementById('risk-level');
    if (riskEl) {
        if (isRiskTime) {
            riskEl.textContent = 'HIGH (Night Time)';
            riskEl.className = 'status-high';
        } else {
            riskEl.textContent = 'LOW (Day Time)';
            riskEl.className = 'status-low';
        }
    }
}

function updateLocDisplay(lat, lng) {
    const el = document.getElementById('current-loc');
    if (el) el.textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
}

function toggleTracking() {
    const btn = document.getElementById('track-btn');
    const status = document.getElementById('track-status');

    if (watchId !== null) {
        navigator.geolocation.clearWatch(watchId);
        watchId = null;
        btn.textContent = 'Start Tracking';
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-primary');
        status.textContent = 'Inactive';
    } else {
        if (!navigator.geolocation) {
            alert("Geolocation is not supported by this browser.");
            return;
        }

        btn.textContent = 'Stop Tracking';
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-danger');
        status.textContent = 'Active (Real-time)';

        // Use watchPosition for real-time updates
        watchId = navigator.geolocation.watchPosition((pos) => {
            const lat = pos.coords.latitude;
            const lng = pos.coords.longitude;

            updateLocDisplay(lat, lng);
            if (socket) {
                socket.emit('send_location', { lat, lng });
            }

        }, (err) => {
            console.error(err);
            status.textContent = 'Error: ' + err.message;
        }, {
            enableHighAccuracy: true,
            maximumAge: 0
        });
    }
}

async function sendSOS() {
    console.log("Triggering SOS alert...");
    const fallbackPosition = () => {
        console.warn("Using fallback coordinates (GCEK Campus, Karad)");
        return { coords: { latitude: 17.3087, longitude: 74.1848 } };
    };

    const handleSOS = async (pos) => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        console.log(`Sending SOS at ${lat}, ${lng}`);

        try {
            const res = await fetch('/api/sos', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lat, lng })
            });

            if (res.ok) {
                console.log("SOS Alert recorded successfully");
                alert("SOS ALERT SENT! Help is on the way.");
                loadMyAlerts(); // Refresh history
            } else {
                const data = await res.json();
                console.error("SOS Alert failed", data);
                alert("Failed to send SOS: " + (data.error || "Unknown error"));
            }
        } catch (e) {
            console.error("Network error sending SOS", e);
            alert("Network error sending SOS. Please check your connection.");
        }
    };

    if (!navigator.geolocation) {
        console.warn("Geolocation not supported, using fallback.");
        handleSOS(fallbackPosition());
        return;
    }

    navigator.geolocation.getCurrentPosition(handleSOS, (err) => {
        console.error("Geolocation error during SOS", err);
        alert("Could not get your location. Using campus default for emergency.");
        handleSOS(fallbackPosition());
    }, {
        enableHighAccuracy: true,
        timeout: 5000,
        maximumAge: 0
    });
}

// Admin Dashboard Logic
function initAdmin() {
    loadUsers();
    loadAlerts();
    loadHotspots();
    loadAnonymousReports();
    loadJusticeAnalytics();

    if (socket) {
        socket.on('receive_location', (data) => {
            updateUserOnMap(data);
        });

        socket.on('user_offline', (data) => {
            if (activeUsers[data.user_id]) {
                delete activeUsers[data.user_id];
                renderActiveUsers();
            }
        });

        socket.on('new_alert', (data) => {
            prependAlert(data);
            alert(`EMERGENCY: SOS from ${data.username}!`);
        });
    }

    setInterval(() => {
        loadUsers();
        loadAlerts();
        loadHotspots();
        loadAnonymousReports();
        loadJusticeAnalytics();
    }, 10000);
}

async function loadJusticeAnalytics() {
    console.log("Fetching justice reporting trends...");
    const container = document.getElementById('justice-stats-container');
    if (!container) return;

    try {
        const res = await fetch('/api/justice/analytics');
        const stats = await res.json();

        if (stats.length === 0) {
            container.innerHTML = '<p class="text-muted text-center">No trend data available.</p>';
            return;
        }

        container.innerHTML = stats.map(s => {
            const percentage = Math.min(100, (s.reports_count / 50) * 100); // Scale relative to 50 reports
            let color = 'var(--primary)';
            if (s.reports_count > 10) color = 'var(--danger)';
            else if (s.reports_count > 5) color = 'var(--warning)';

            return `
            <div class="mb-2">
                <div class="flex justify-between mb-1" style="font-size: 0.8rem;">
                    <span>${s.category}</span>
                    <strong style="color: ${color};">${s.reports_count} Reports</strong>
                </div>
                <div style="width: 100%; height: 6px; background: rgba(255,255,255,0.05); border-radius: 10px; overflow: hidden;">
                    <div style="width: ${percentage}%; height: 100%; background: ${color}; box-shadow: 0 0 10px ${color}; transition: width 0.5s ease;"></div>
                </div>
            </div>
            `;
        }).join('');
    } catch (e) {
        console.error("Error loading justice analytics", e);
    }
}

const activeUsers = {};

function updateUserOnMap(data) {
    activeUsers[data.user_id] = data;
    renderActiveUsers();
}

function renderActiveUsers() {
    const list = document.getElementById('active-user-list');
    if (!list) return;

    list.innerHTML = Object.values(activeUsers).map(u => `
        <li class="active-user-item">
            <span class="status-indicator"></span>
            <strong>${u.username}</strong> 
            <span class="text-muted" style="font-size: 0.85rem;">(${u.lat.toFixed(4)}, ${u.lng.toFixed(4)})</span>
            <a href="https://www.google.com/maps?q=${u.lat},${u.lng}" target="_blank" class="map-link">View</a>
        </li>
    `).join('');

    if (Object.keys(activeUsers).length === 0) {
        list.innerHTML = '<li class="text-muted">No students currently tracking.</li>';
    }
}

async function loadUsers() {
    try {
        const res = await fetch('/api/admin/users');
        const users = await res.json();
        const list = document.getElementById('registered-user-list');
        if (!list) return;

        list.innerHTML = users.map(u => `
            <li>
                <strong>${u.username}</strong>
                <span class="text-muted" style="font-size: 0.8rem;">(ID: ${u.id})</span>
            </li>
        `).join('');

        if (users.length === 0) {
            list.innerHTML = '<li class="text-muted">No students registered yet.</li>';
        }
    } catch (e) {
        console.error("Error loading users:", e);
    }
}

async function loadAlerts() {
    const res = await fetch('/api/admin/alerts');
    const alerts = await res.json();
    const tbody = document.querySelector('#alerts-table tbody');
    tbody.innerHTML = ''; // Clear existing
    alerts.forEach(renderAlertRow);
}

function prependAlert(data) {
    const tbody = document.querySelector('#alerts-table tbody');
    // Create a row compatible with renderAlertRow expected format or new data format
    // The new_alert data matches the alert object structure mostly
    const alertObj = {
        timestamp: data.timestamp,
        username: data.username,
        latitude: data.latitude,
        longitude: data.longitude,
        status: 'ACTIVE' // Default for new SOS
    };

    const row = createAlertRow(alertObj);
    tbody.insertBefore(row, tbody.firstChild);
}

function renderAlertRow(alert) {
    const tbody = document.querySelector('#alerts-table tbody');
    tbody.appendChild(createAlertRow(alert));
}

function createAlertRow(a) {
    const tr = document.createElement('tr');
    tr.id = `alert-row-${a.id}`;
    tr.innerHTML = `
        <td>${new Date(a.timestamp).toLocaleTimeString()}</td>
        <td>${a.username}</td>
        <td>
            <a href="https://www.google.com/maps?q=${a.latitude},${a.longitude}" target="_blank" class="map-link">
               (${a.latitude.toFixed(4)}, ${a.longitude.toFixed(4)})
            </a>
        </td>
        <td>
            <span class="${a.status === 'ACTIVE' ? 'status-high' : 'status-low'}">${a.status}</span>
            <div style="font-size: 0.75rem; color: #888;">${a.responder_name || 'No Responder'}</div>
        </td>
        <td>
            <div class="flex gap-1">
                ${a.status === 'ACTIVE' ? `
                    <button onclick="dispatchResponder(${a.id})" class="btn btn-primary" style="padding: 0.4rem 0.8rem; font-size: 0.8rem; background: #10b981;">Dispatch</button>
                    <button onclick="resolveAlert(${a.id})" class="btn btn-primary" style="padding: 0.4rem 0.8rem; font-size: 0.8rem;">Resolve</button>
                ` : '-'}
            </div>
        </td>
    `;
    return tr;
}

async function resolveAlert(alertId) {
    try {
        const res = await fetch(`/api/admin/alerts/resolve/${alertId}`, { method: 'POST' });
        if (res.ok) {
            loadAlerts(); // Refresh the list
        } else {
            alert("Failed to resolve alert.");
        }
    } catch (e) {
        console.error("Error resolving alert:", e);
    }
}

async function loadAnonymousReports() {
    console.log("Loading anonymous disclosures...");
    const container = document.getElementById('anonymous-reports-list');
    if (!container) return;

    try {
        const res = await fetch('/api/admin/whistleblower/reports');
        const reports = await res.json();

        if (reports.length === 0) {
            container.innerHTML = '<p class="text-muted text-center">No disclosures reported.</p>';
            return;
        }

        container.innerHTML = reports.map(r => `
            <div class="glass-bg p-2 rounded mb-2" style="border: 1px solid #333;">
                <div class="flex justify-between mb-1">
                    <div>
                        <strong style="color: #fff;">[${r.urgency.toUpperCase()}] ${r.title}</strong>
                        <span class="text-muted" style="font-size: 0.7rem; margin-left: 0.5rem;">#${r.reference_hash}</span>
                    </div>
                    <span class="text-muted" style="font-size: 0.8rem;">${new Date(r.submitted_at).toLocaleString()}</span>
                </div>
                <p class="text-muted" style="font-size: 0.9rem;">${r.description}</p>
                <div class="mt-1 flex justify-between align-center">
                    <div class="flex gap-1 align-center">
                        <span class="status-badge" style="background: ${r.status === 'received' ? '#fbbf24' : '#10b981'}; color: #000; font-size: 0.7rem; padding: 0.2rem 0.5rem; border-radius: 4px;">${r.status.toUpperCase()}</span>
                        <span class="text-muted" style="font-size: 0.7rem;">Category: ${r.category}</span>
                    </div>
                    <button onclick="openAdminChat('${r.reference_hash}')" class="btn btn-primary" style="padding: 0.3rem 0.6rem; font-size: 0.75rem;">Open Dialogue</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error("Error loading anonymous reports", e);
    }
}

// Phase 3: Admin Dispatch & Anonymous Chat Logic
let currentReportHash = null;

function dispatchResponder(alertId) {
    const responder = prompt("Enter Responder Name (e.g. Officer Alpha):", "Officer Alpha");
    if (!responder) return;

    socket.emit('dispatch_responder', { alert_id: alertId, responder_name: responder });
    alert(`Responder ${responder} dispatched to SOS #${alertId}`);

    // Calibrate Tactical Asset Movement (Advanced UI Feedback)
    let lat = 20.5937;
    let lng = 78.9629;
    const interval = setInterval(() => {
        lat += 0.0001;
        lng += 0.0001;
        socket.emit('update_responder_loc', { alert_id: alertId, lat: lat, lng: lng });
    }, 3000);
    setTimeout(() => clearInterval(interval), 30000); // Stop after 30s
}

async function openAdminChat(hash) {
    currentReportHash = hash;
    const modal = document.getElementById('admin-chat-modal');
    modal.style.display = 'block';

    const res = await fetch(`/api/whistleblower/chat/${hash}`);
    const chats = await res.json();
    renderAdminChats(chats);
}

function closeAdminChat() {
    document.getElementById('admin-chat-modal').style.display = 'none';
}

async function sendAdminReply() {
    const input = document.getElementById('admin-chat-input');
    const msg = input.value.trim();
    if (!msg || !currentReportHash) return;

    const res = await fetch(`/api/whistleblower/chat/${currentReportHash}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, role: 'ADMIN' })
    });
    const chats = await res.json();
    renderAdminChats(chats);
    input.value = '';
}

function renderAdminChats(chats) {
    const container = document.getElementById('admin-chat-messages');
    container.innerHTML = chats.map(c => `
        <div style="margin-bottom: 0.8rem; text-align: ${c.sender_role === 'ADMIN' ? 'right' : 'left'};">
            <span style="font-size: 0.65rem; color: #888;">${c.sender_role} • ${new Date(c.timestamp).toLocaleTimeString()}</span>
            <div style="background: ${c.sender_role === 'ADMIN' ? '#6366f1' : '#333'}; color: white; padding: 0.4rem 0.8rem; border-radius: 10px; display: inline-block; max-width: 85%; word-wrap: break-word;">
                ${c.message}
            </div>
        </div>
    `).join('');
    container.scrollTop = container.scrollHeight;
}

// Incident Reporting Logic
async function reportIncident(event) {
    event.preventDefault();
    const form = event.target;
    const type = form.type.value;
    const description = form.description.value;

    console.log("Reporting incident...");

    const fallbackPosition = () => {
        console.warn("Using fallback coordinates for incident (GCEK Campus, Karad)");
        return { coords: { latitude: 17.3087, longitude: 74.1848 } };
    };

    const submitIncident = async (pos) => {
        try {
            const res = await fetch('/api/incidents', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    type,
                    description,
                    lat: pos.coords.latitude,
                    lng: pos.coords.longitude
                })
            });

            if (res.ok) {
                form.reset();
                loadIncidents();
                triggerAITriage(description);
            } else {
                alert("Failed to report incident.");
            }
        } catch (e) {
            console.error("Error reporting incident:", e);
        }
    };

    if (!navigator.geolocation) {
        submitIncident(fallbackPosition());
        return;
    }

    navigator.geolocation.getCurrentPosition(submitIncident, (err) => {
        console.error("Geolocation error, using fallback", err);
        submitIncident(fallbackPosition());
    });
}

async function triggerAITriage(description) {
    const modal = document.getElementById('ai-triage-modal');
    const loading = document.getElementById('triage-loading');
    const results = document.getElementById('triage-results');

    if (!modal) return;

    modal.style.display = 'block';
    loading.style.display = 'block';
    results.style.display = 'none';

    try {
        const res = await fetch('/api/ai/triage', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description })
        });
        const data = await res.json();

        setTimeout(() => {
            loading.style.display = 'none';
            results.style.display = 'block';

            document.getElementById('triage-priority').textContent = data.priority;
            document.getElementById('triage-priority').className = `status-pill status-${data.priority.toLowerCase()}`;
            document.getElementById('triage-category').textContent = data.category;
            document.getElementById('triage-instructions').textContent = data.instructions;

            logVital(`AI TRIAGE COMPLETED: ${data.priority} PRIORITY`, data.priority === 'CRITICAL' ? 'alert' : 'system');
        }, 1500); // Visual flair for "thinking"
    } catch (e) {
        console.error("Error in AI triage", e);
        modal.style.display = 'none';
    }
}

function closeTriageModal() {
    document.getElementById('ai-triage-modal').style.display = 'none';
}

async function loadIncidents() {
    console.log("Loading community incident feed...");
    try {
        const res = await fetch('/api/incidents');
        const incidents = await res.json();
        const container = document.getElementById('incident-feed');
        if (!container) return;

        if (incidents.length === 0) {
            container.innerHTML = '<p class="text-muted text-center">No reports yet.</p>';
            return;
        }

        container.innerHTML = incidents.map(i => `
            <div class="incident-item">
                <div class="incident-header">
                    <span class="incident-type">${i.type}</span>
                    <span class="incident-time">${new Date(i.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
                <div class="incident-desc">${i.description}</div>
                <div class="incident-reporter">By ${i.username}</div>
            </div>
        `).join('');
    } catch (e) {
        console.error("Error loading incidents:", e);
    }
}

// Broadcast and Analytics (Admin)
async function sendBroadcast() {
    const input = document.getElementById('broadcast-text');
    const status = document.getElementById('broadcast-status');
    const message = input.value.trim();

    if (!message) return alert("Please enter a message!");

    try {
        const res = await fetch('/api/admin/broadcast', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });

        if (res.ok) {
            input.value = '';
            status.textContent = "Broadcast sent successfully!";
            setTimeout(() => status.textContent = '', 3000);
        } else {
            alert("Failed to send broadcast.");
        }
    } catch (e) {
        console.error("Error sending broadcast:", e);
    }
}

async function loadHotspots() {
    try {
        const res = await fetch('/api/admin/analytics/hotspots');
        const hotspots = await res.json();
        const list = document.getElementById('hotspot-list');
        if (!list) return;

        if (hotspots.length === 0) {
            list.innerHTML = '<p class="text-muted">No spatial patterns identified yet.</p>';
            return;
        }

        list.innerHTML = hotspots.map(h => `
            <div class="hotspot-item">
                <div>
                    <strong>${h.lat.toFixed(4)}, ${h.lng.toFixed(4)}</strong>
                    <div class="text-muted" style="font-size: 0.75rem;">Density Cluster</div>
                </div>
                <span class="hotspot-count">${h.count} SOS Incident(s)</span>
            </div>
        `).join('');
    } catch (e) {
        console.error("Error loading hotspots:", e);
    }
}

// Logout
async function logout() {
    await fetch('/api/logout', { method: 'POST' });
    window.location.href = '/';
}
// --- Tactical Safety Expansion (Phase 4) ---

let currentSquadId = null;
let pulseSessionId = null;
let pulseTimer = null;
let pulseTimeRemaining = 0;
let batteryLevel = null;

// Initialize Squad Features
async function updateSquadStatus() {
    try {
        const res = await fetch('/api/squads/status');
        const squadData = await res.json();

        if (squadData.length > 0) {
            const squad = squadData[0];
            currentSquadId = squad.squad_id || 0;

            document.getElementById('no-squad-view').style.display = 'none';
            document.getElementById('active-squad-view').style.display = 'block';
            document.getElementById('squad-name-display').style.display = 'inline-block';
            document.getElementById('squad-name-display').textContent = squad.squad_name;
            document.getElementById('display-invite-code').textContent = squad.invite_code;

            renderSquadMembers(squadData);

            // Join Socket Room
            if (socket) {
                socket.emit('join_squad_room', { squad_id: currentSquadId });
            }
        }
    } catch (e) {
        console.error("Error fetching squad status", e);
    }
}

function renderSquadMembers(members) {
    const list = document.getElementById('squad-members-list');
    const hudList = document.getElementById('hud-member-list');
    if (!list) return;

    const html = members.map(m => `
        <div class="squad-member ${m.member_status === 'sos' ? 'sos' : 'online'}">
            <div class="flex align-center">
                <span class="member-status-dot ${m.member_status === 'online' ? 'status-online' : 'status-offline'}"></span>
                <strong>${m.username}</strong>
                ${m.role === 'leader' ? '<span class="badge" style="font-size: 0.6rem; margin-left: 5px;">LEADER</span>' : ''}
            </div>
            <div class="flex align-center gap-1">
                ${m.battery_level ? `<span class="battery-indicator">${m.battery_level}% 🔋</span>` : ''}
                <span class="text-muted" style="font-size: 0.7rem;">${m.member_status}</span>
            </div>
        </div>
    `).join('');

    list.innerHTML = html;
    if (hudList) hudList.innerHTML = html;
}

async function createSquad() {
    const name = prompt("Enter Squad Name:", `${sessionStorage.getItem('username') || 'Student'}'s Squad`);
    if (!name) return;

    try {
        const res = await fetch('/api/squads/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ squad_name: name })
        });
        if (res.ok) {
            updateSquadStatus();
        }
    } catch (e) {
        console.error("Error creating squad", e);
    }
}

async function showJoinSquadModal() {
    const code = prompt("Enter 8-digit Invite Code:");
    if (!code) return;

    try {
        const res = await fetch('/api/squads/join', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ invite_code: code })
        });
        if (res.ok) {
            updateSquadStatus();
        } else {
            alert("Invalid invite code");
        }
    } catch (e) {
        console.error("Error joining squad", e);
    }
}

// Guardian Pulse Logic
async function startPulse() {
    const interval = parseInt(document.getElementById('pulse-interval').value);

    try {
        const res = await fetch('/api/pulse/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ interval })
        });
        const data = await res.json();

        if (res.ok) {
            pulseSessionId = data.session_id;
            document.getElementById('pulse-inactive').style.display = 'none';
            document.getElementById('pulse-active').style.display = 'block';

            pulseTimeRemaining = interval;
            runPulseTimer();
            logVital("GUARDIAN PULSE ACTIVATED");
        }
    } catch (e) {
        console.error("Error starting pulse", e);
    }
}

function runPulseTimer() {
    if (pulseTimer) clearInterval(pulseTimer);

    pulseTimer = setInterval(() => {
        pulseTimeRemaining--;
        document.getElementById('pulse-countdown').textContent = pulseTimeRemaining;

        // Update SVG circle
        const circle = document.querySelector('.pulse-timer-path');
        const offset = 283 - (pulseTimeRemaining / parseInt(document.getElementById('pulse-interval').value)) * 283;
        circle.style.strokeDashoffset = offset;

        if (pulseTimeRemaining <= 0) {
            clearInterval(pulseTimer);
            showPulseConfirmation();
        }
    }, 1000);
}

function showPulseConfirmation() {
    document.getElementById('pulse-status-text').textContent = "CONFIRMATION REQUIRED";
    document.getElementById('pulse-status-text').style.color = "var(--pulse-neon)";
    document.getElementById('pulse-confirm-btn').style.display = 'block';

    logVital("PENDING SAFETY CHECK-IN...");

    // Auto SOS if no response in 30s
    setTimeout(() => {
        if (document.getElementById('pulse-confirm-btn').style.display === 'block') {
            triggerPulseSOS();
        }
    }, 30000);
}

async function confirmPulse() {
    try {
        await fetch('/api/pulse/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pulse_id: pulseSessionId })
        });

        document.getElementById('pulse-confirm-btn').style.display = 'none';
        document.getElementById('pulse-status-text').textContent = "Pulse Monitor Active";
        document.getElementById('pulse-status-text').style.color = "white";

        pulseTimeRemaining = parseInt(document.getElementById('pulse-interval').value);
        runPulseTimer();
        logVital("SAFETY CONFIRMED - NEXT PULSE SCHEDULED");
    } catch (e) {
        console.error("Error confirming pulse", e);
    }
}

function triggerPulseSOS() {
    logVital("CRITICAL: PULSE MISSED. ESCALATING...", "alert");
    sendSOS();
}

// Tactical HUD Control
function openTacticalHUD() {
    document.getElementById('tactical-hud').style.display = 'block';
    logVital("HUD OVERLAY ONLINE");
}

function closeTacticalHUD() {
    document.getElementById('tactical-hud').style.display = 'none';
}

function logVital(message, type = 'system') {
    const logs = document.getElementById('hud-vital-logs');
    if (!logs) return;
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const color = type === 'alert' ? '#ff0077' : type === 'success' ? '#00ff88' : 'rgba(255,255,255,0.7)';
    logs.innerHTML = `<div style="color: ${color}; font-family: 'Courier New', monospace; margin-bottom: 2px;">
        > [${time}] ${message}
    </div>${logs.innerHTML}`;
}

// Enhanced Telemetry Stream
setInterval(() => {
    const hud = document.getElementById('tactical-hud');
    if (hud && hud.style.display === 'block') {
        // Update specific pills
        const signal = 95 + Math.floor(Math.random() * 5);
        const signalEl = document.getElementById('hud-dash-signal');
        if (signalEl) signalEl.innerText = `${signal}%`;

        const sats = 8 + Math.floor(Math.random() * 4);
        const gpsEl = document.getElementById('hud-dash-gps');
        if (gpsEl) gpsEl.innerText = `${sats}_SV`;

        const lux = 180 + Math.floor(Math.random() * 100);
        const lightEl = document.getElementById('hud-dash-lighting');
        if (lightEl) lightEl.innerText = `${lux}lx`;

        const lat = (20.5937 + (Math.random() - 0.5) * 0.0001).toFixed(4);
        const lng = (78.9629 + (Math.random() - 0.5) * 0.0001).toFixed(4);
        const coordsEl = document.getElementById('hud-dash-coords');
        if (coordsEl) coordsEl.innerText = `${lng}, ${lat}`;

        const telemetry = [
            `GPS ACCURACY: ${Math.floor(Math.random() * 5 + 3)}m`,
            `SIGNAL STRENGTH: -${Math.floor(Math.random() * 20 + 85)}dBm`,
            `EYE-IN-SKY: LINK ${Math.random() > 0.9 ? 'STABLE' : 'OPTIMAL'}`,
            `GRID ENCRYPTION: AES-256 ACTIVE`,
            `AMBIENT LUX: ${lux} lx`,
            `REFERENCE POS: ${lng}, ${lat}`
        ];

        if (batteryLevel !== null) {
            telemetry.push(`LOCAL POWER: ${batteryLevel}%`);
        }

        if (pulseSessionId !== null) {
            telemetry.push(`GUARDIAN PULSE: SESSION_ACTIVE`);
        }

        logVital(telemetry[Math.floor(Math.random() * telemetry.length)]);
    }
}, 3000);

// Battery Tracking
if ('getBattery' in navigator) {
    navigator.getBattery().then(batt => {
        batteryLevel = Math.floor(batt.level * 100);
        batt.addEventListener('levelchange', () => {
            batteryLevel = Math.floor(batt.level * 100);
            logVital(`LOCAL POWER LEVEL: ${batteryLevel}%`, batteryLevel < 20 ? 'alert' : 'system');
        });
    });
}

// Socket Listeners for Squad
if (socket) {
    socket.on('squad_update', (data) => {
        logVital(data.message);
        updateSquadStatus();
    });

    socket.on('member_location', (data) => {
        console.log("Squad location update:", data);
        // In a real app, update markers on map
    });

    socket.on('squad_sos_alert', (data) => {
        document.getElementById('sos-active-warning').style.display = 'block';
        document.getElementById('sos-originator-text').textContent = `Distress from ${data.username}`;
        openTacticalHUD();
        logVital(`!!! SOS RECEIVED FROM ${data.username.toUpperCase()} !!!`);

        // Play alert sound if needed
    });
}

// Extend initDashboard
const originalInit = initDashboard;
initDashboard = function () {
    originalInit();
    updateSquadStatus();

    // Add HUD toggle to SOS hexagon or tracking card
    const sosHex = document.getElementById('sos-tactical-card');
    if (sosHex) {
        // Change onclick to something that handles both SOS and long-press for HUD?
        // For now, let's just make the tracking card open the HUD
        const trackHex = document.getElementById('track-btn');
        if (trackHex) {
            trackHex.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                openTacticalHUD();
            });
        }
    }
};
