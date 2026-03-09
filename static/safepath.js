let map;
let incidentLayer = L.layerGroup();
let infraLayer = L.layerGroup();
let heatLayer = L.layerGroup();
let lightingLayer = L.layerGroup();
let routeLayers = L.layerGroup();
let lastRoutes = [];

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    setupLayerToggles();
    startHUDTelemetry();
    showHUD();
});

function showHUD() {
    const hud = document.getElementById('main-hud');
    if (hud) hud.style.display = 'block';
}

function initMap() {
    map = L.map('map', {
        attributionControl: false,
        zoomControl: false
    }).setView([20.5937, 78.9629], 16);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; SafeNest Tactical'
    }).addTo(map);

    incidentLayer.addTo(map);
    infraLayer.addTo(map);
    heatLayer.addTo(map);
    lightingLayer.addTo(map);
    routeLayers.addTo(map);

    loadMapData();
}

async function loadMapData() {
    // Load Incidents
    fetch('/api/incidents')
        .then(res => res.json())
        .then(data => {
            data.forEach(i => {
                L.circleMarker([i.latitude, i.longitude], {
                    radius: 6,
                    fillColor: '#ef4444',
                    color: '#fff',
                    weight: 1,
                    opacity: 1,
                    fillOpacity: 0.8
                }).addTo(incidentLayer)
                    .bindPopup(`<strong>${i.type}</strong><br>${i.description}`);
            });
        });

    // Load Infrastructure
    fetch('/api/map/infrastructure')
        .then(res => res.json())
        .then(data => {
            data.forEach(i => {
                const iconHtml = i.type === 'cctv_camera' ? '📷' :
                    i.type === 'blue_light_phone' ? '📞' :
                        i.type === 'security_booth' ? '👮' : '📍';

                const customIcon = L.divIcon({
                    html: `<div style="font-size: 20px; filter: drop-shadow(0 0 5px var(--primary));">${iconHtml}</div>`,
                    className: 'tactical-marker',
                    iconSize: [24, 24]
                });

                L.marker([i.latitude, i.longitude], { icon: customIcon })
                    .addTo(infraLayer)
                    .bindPopup(`
                        <div class="tactical-popup">
                            <strong style="color: var(--primary);">${i.type.toUpperCase().replace(/_/g, ' ')}</strong><br>
                            Station: ${i.station_id}<br>
                            Area: ${i.name}<br>
                            Hours: ${i.operating_hours}<br>
                            <button class="btn btn-primary btn-block mt-1" style="font-size: 0.7rem; padding: 4px;">LOCK ON</button>
                        </div>
                    `);
            });
        });

    // Load Heatmap
    fetch('/api/heatmap/grid')
        .then(res => res.json())
        .then(data => {
            data.forEach(g => {
                L.circle([g.grid_lat, g.grid_lng], {
                    radius: 30,
                    fillColor: g.color_hex,
                    fillOpacity: g.heat_intensity * 0.5,
                    stroke: false
                }).addTo(heatLayer);
            });
        });

    // Load Lighting Data
    fetch('/api/map/lighting')
        .then(res => res.json())
        .then(data => {
            data.forEach(l => {
                const color = l.status === 'operational' ? '#FFEE00' : '#444444';
                L.circle([l.latitude, l.longitude], {
                    radius: 25,
                    fillColor: color,
                    fillOpacity: 0.3,
                    stroke: false
                }).addTo(lightingLayer);

                // Add a small point for the actual lamp
                L.circleMarker([l.latitude, l.longitude], {
                    radius: 3,
                    fillColor: color,
                    color: '#fff',
                    weight: 1,
                    fillOpacity: 1
                }).addTo(lightingLayer);
            });
        });
}

function setupLayerToggles() {
    document.getElementById('layer-incidents').addEventListener('change', (e) => {
        if (e.target.checked) map.addLayer(incidentLayer);
        else map.removeLayer(incidentLayer);
    });

    document.getElementById('layer-cctv').addEventListener('change', (e) => {
        if (e.target.checked) map.addLayer(infraLayer);
        else map.removeLayer(infraLayer);
    });

    document.getElementById('layer-3d-heat').addEventListener('change', (e) => {
        if (e.target.checked) map.addLayer(heatLayer);
        else map.removeLayer(heatLayer);
    });

    document.getElementById('layer-lighting').addEventListener('change', (e) => {
        if (e.target.checked) map.addLayer(lightingLayer);
        else map.removeLayer(lightingLayer);
    });
}

async function calculateRoutes() {
    const dest = document.getElementById('dest-input').value;
    const origin = { lat: 20.5937, lng: 78.9629 };
    const destination = { lat: 20.5950, lng: 78.9650 };

    const res = await fetch('/api/safepath/routes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ origin, destination })
    });
    const routes = await res.json();
    renderRouteOptions(routes);
}

function renderRouteOptions(routes) {
    lastRoutes = routes;
    const list = document.getElementById('route-options-list');
    list.innerHTML = routes.map(r => `
        <div class="route-option" id="opt-${r.id}" onclick="displayRoute('${r.id}')">
            <div class="flex justify-between align-center">
                <span style="font-weight: bold; text-transform: uppercase; color: var(--primary);">${r.type}</span>
                <span class="safety-score" style="color: ${r.safety_score > 90 ? '#00FF88' : '#FFFF00'}">${r.safety_score}%</span>
            </div>
            <div class="text-muted" style="font-size: 0.85rem;">
                ${r.duration_mins} mins • ${r.distance_m}m
            </div>
            <div class="mt-1 flex gap-1 flex-wrap">
                ${r.annotations.map(a => `<span class="annotation">${a}</span>`).join('')}
            </div>
            <div class="mt-1 p-1" style="background: rgba(0,255,136,0.1); border-radius: 8px; font-size: 0.75rem; border: 1px solid rgba(0,255,136,0.2);">
                <div class="flex justify-between">
                    <span style="opacity: 0.7;">CCTV Coverage:</span>
                    <strong style="color: var(--squad-neon);">${r.analytics.cctv_count} Units</strong>
                </div>
                <div class="flex justify-between">
                    <span style="opacity: 0.7;">Avg Illumination:</span>
                    <strong style="color: var(--squad-neon);">${r.analytics.avg_lighting_lux} lx</strong>
                </div>
            </div>
        </div>
    `).join('');

    if (routes.length > 0) displayRoute(routes[0].id);
}

function displayRoute(routeId) {
    document.querySelectorAll('.route-option').forEach(el => el.classList.remove('active'));
    document.getElementById(`opt-${routeId}`).classList.add('active');

    routeLayers.clearLayers();

    const route = lastRoutes.find(r => r.id === routeId);
    if (!route) return;

    const color = route.type === 'safest' ? '#00FF88' : route.type === 'balanced' ? '#00d2ff' : '#ef4444';
    L.polyline(route.path, {
        color: color,
        weight: 8,
        opacity: 0.8,
        dashArray: '10, 10'
    }).addTo(routeLayers);

    map.fitBounds(route.path, { padding: [50, 50] });
}

function startHUDTelemetry() {
    setInterval(() => {
        const signal = 95 + Math.floor(Math.random() * 5);
        const signalEl = document.getElementById('hud-signal');
        if (signalEl) signalEl.innerText = `${signal}%`;

        const sats = 6 + Math.floor(Math.random() * 4);
        const gpsEl = document.getElementById('hud-gps');
        if (gpsEl) gpsEl.innerText = `${sats}_SV`;

        const lat = (20.5937 + (Math.random() - 0.5) * 0.0001).toFixed(4);
        const lng = (78.9629 + (Math.random() - 0.5) * 0.0001).toFixed(4);
        const coordsEl = document.getElementById('hud-coords');
        if (coordsEl) coordsEl.innerText = `${lng}, ${lat}`;

        const lux = 200 + Math.floor(Math.random() * 100);
        const lightEl = document.getElementById('hud-lighting');
        if (lightEl) lightEl.innerText = `${lux}lx`;
    }, 3000);
}
