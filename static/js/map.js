// Who is logged in (from the page), and the colours used for hazard and lane types
const config = JSON.parse(document.getElementById('map-config').textContent);

const DUBLIN_CENTRE = [53.3498, -6.2603];

const HAZARD_COLORS = {
    pothole: '#e67e22',
    poor_visibility: '#8e44ad',
    dangerous_junction: '#e74c3c',
    obstruction: '#d4ac0d',
    other: '#7f8c8d'
};

const LANE_COLORS = {
    segregated: '#1e8449',
    painted: '#2e86c1',
    shared: '#7d3c98',
    greenway: '#17a589',
    other: '#95a5a6'
};

const map = L.map('map').setView(DUBLIN_CENTRE, 13);

const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19
});

const cartoLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '© OpenStreetMap contributors © CARTO',
    subdomains: 'abcd',
    maxZoom: 19
});

cartoLayer.addTo(map);

// Map layers. Areas sit under lanes, and lanes under the markers.
// Each layer can be switched on or off from the control in the top right.
map.createPane('areasPane').style.zIndex = 350;
map.createPane('lanesPane').style.zIndex = 380;

const layers = {
    areas: L.layerGroup().addTo(map),
    lanes: L.layerGroup().addTo(map),
    stations: L.layerGroup().addTo(map),
    hazards: L.layerGroup().addTo(map)
};

L.control.layers(
    {
        'CartoDB Light': cartoLayer,
        'OpenStreetMap': osmLayer
    },
    {
        'Bike stations': layers.stations,
        'Hazard reports': layers.hazards,
        'Cycle lanes': layers.lanes,
        'Hazards per area': layers.areas
    }
).addTo(map);

const proximityLayer = L.featureGroup().addTo(map);
let pendingMarker = null;

const current = { stations: [], hazards: [], lanes: [], areas: [] };
let areasGeoJson = null;

// What a click on the map does: nothing, nearest bikes, hazards nearby, or report a hazard
let clickMode = null;
let pendingLocation = null;
let editingHazardId = null;

function showLoading(show) {
    document.getElementById('loading').style.display = show ? 'block' : 'none';
}

// Helpers: make user text safe to show, format distances, and pick colours for stations and areas
function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value ?? '';
    return div.innerHTML;
}

function formatDistance(metres) {
    return metres < 1000 ? `${Math.round(metres)} m` : `${(metres / 1000).toFixed(1)} km`;
}

function getStationColor(availableBikes) {
    if (availableBikes === 0) return '#e74c3c';
    if (availableBikes < 3) return '#f39c12';
    return '#27ae60';
}

const AREA_GRADES = [0, 1, 5, 10, 20];

function getAreaColor(hazardCount) {
    return hazardCount >= 20 ? '#bd0026' :
           hazardCount >= 10 ? '#f03b20' :
           hazardCount >= 5  ? '#fd8d3c' :
           hazardCount >= 1  ? '#fecc5c' :
                               '#ffffb2';
}

function downloadJson(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Sending changes to the API. Every change needs the CSRF token from the cookie,
// and if the API rejects it, its error message is shown to the user.
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

async function fetchFeatures(path, filters = {}) {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
        if (Array.isArray(value)) {
            value.forEach(item => params.append(key, item));
        } else if (value !== '' && value !== null && value !== undefined) {
            params.append(key, value);
        }
    });

    const response = await fetch(`${path}?${params}`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || `Request failed (${response.status})`);
    }
    return data.features || [];
}

async function sendJson(method, url, body) {
    const response = await fetch(url, {
        method,
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: body ? JSON.stringify(body) : undefined
    });
    if (!response.ok) {
        let message = `Request failed (${response.status})`;
        try {
            const data = await response.json();
            message = Object.entries(data)
                .map(([field, errors]) => `${field}: ${[].concat(errors).join(' ')}`)
                .join('\n');
        } catch (e) {
        }
        throw new Error(message);
    }
    return response.status === 204 ? null : response.json();
}

async function loadStations(filters = {}) {
    current.stations = await fetchFeatures('/api/stations/', filters);
    displayStations(current.stations);
}

async function loadHazards(filters = {}) {
    const { nearLanes, distance, ...params } = filters;

    if (params.hazard_type && params.hazard_type.length === 0) {
        current.hazards = [];
    } else if (nearLanes) {
        current.hazards = await fetchFeatures('/api/hazards/near_lanes/', { ...params, distance });
    } else {
        current.hazards = await fetchFeatures('/api/hazards/', params);
    }
    displayHazards(current.hazards);
}

async function loadLanes(filters = {}) {
    current.lanes = await fetchFeatures('/api/lanes/', filters);
    displayLanes(current.lanes);
}

async function loadAreas() {
    current.areas = await fetchFeatures('/api/areas/hazard_counts/');
    displayAreas(current.areas);
}

// Drawing the layers: stations as coloured dots, hazards as pins, lanes as coloured lines
function stationPopup(props) {
    return `
        <div>
            <h6>🚲 ${escapeHtml(props.name)}</h6>
            <p class="mb-1"><strong>Bikes:</strong> ${props.available_bikes} / ${props.capacity}</p>
            <p class="mb-1"><strong>Free stands:</strong> ${props.available_stands}</p>
            ${props.distance_m != null ? `<p class="mb-1"><strong>Distance:</strong> ${formatDistance(props.distance_m)}</p>` : ''}
            ${props.last_updated ? `<p class="mb-0 small text-muted">Updated ${new Date(props.last_updated).toLocaleString()}</p>` : ''}
        </div>
    `;
}

function displayStations(stations) {
    layers.stations.clearLayers();

    L.geoJSON(stations, {
        pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
            radius: 7,
            fillColor: getStationColor(feature.properties.available_bikes),
            color: '#ffffff',
            weight: 2,
            opacity: 1,
            fillOpacity: 0.9
        }),
        onEachFeature: (feature, layer) => layer.bindPopup(stationPopup(feature.properties))
    }).addTo(layers.stations);
}

// Hazard popups show the details, plus Edit and Delete buttons for the person who reported it
function canEditHazard(props) {
    return config.isAuthenticated && (config.isStaff || props.reported_by === config.username);
}

function hazardPopup(hazard) {
    const props = hazard.properties;
    const el = document.createElement('div');
    el.innerHTML = `
        <h6>⚠️ ${escapeHtml(props.hazard_type_display)}</h6>
        ${props.description ? `<p class="mb-1">${escapeHtml(props.description)}</p>` : ''}
        <p class="mb-0 small text-muted">
            Reported ${new Date(props.created_at).toLocaleDateString()}
            ${props.reported_by ? `by ${escapeHtml(props.reported_by)}` : ''}
        </p>
    `;

    if (canEditHazard(props)) {
        const buttons = document.createElement('div');
        buttons.className = 'd-flex gap-2 mt-2';
        buttons.innerHTML = `
            <button type="button" class="btn btn-sm btn-outline-primary">Edit</button>
            <button type="button" class="btn btn-sm btn-outline-danger">Delete</button>
        `;
        const [editButton, deleteButton] = buttons.querySelectorAll('button');
        editButton.addEventListener('click', () => openHazardForm(hazard));
        deleteButton.addEventListener('click', () => deleteHazard(hazard.id));
        el.appendChild(buttons);
    }
    return el;
}

function hazardIcon(hazardType) {
    const color = HAZARD_COLORS[hazardType] || HAZARD_COLORS.other;
    return L.divIcon({
        className: '',
        html: `<div class="hazard-icon" style="background:${color}"><span>!</span></div>`,
        iconSize: [24, 24],
        iconAnchor: [12, 24],
        popupAnchor: [0, -24]
    });
}

function displayHazards(hazards) {
    layers.hazards.clearLayers();

    L.geoJSON(hazards, {
        pointToLayer: (feature, latlng) => L.marker(latlng, { icon: hazardIcon(feature.properties.hazard_type) }),
        onEachFeature: (feature, layer) => layer.bindPopup(() => hazardPopup(feature))
    }).addTo(layers.hazards);
}

function displayLanes(lanes) {
    layers.lanes.clearLayers();

    L.geoJSON(lanes, {
        pane: 'lanesPane',
        style: feature => ({
            color: LANE_COLORS[feature.properties.lane_type] || LANE_COLORS.other,
            weight: 4,
            opacity: 0.85
        }),
        onEachFeature: (feature, layer) => {
            const props = feature.properties;
            layer.bindPopup(`
                <div>
                    <h6>${escapeHtml(props.name || 'Cycle lane')}</h6>
                    <p class="mb-0"><strong>Type:</strong> ${escapeHtml(props.lane_type_display)}</p>
                </div>
            `);
        }
    }).addTo(layers.lanes);
}

// Areas are coloured by how many hazards they contain. Hovering highlights an area and
// shows its count in the info box (top right); clicking zooms in. The legend explains the colours.
function areaStyle(feature) {
    return {
        fillColor: getAreaColor(feature.properties.hazard_count),
        weight: 2,
        opacity: 1,
        color: 'white',
        dashArray: '3',
        fillOpacity: 0.5
    };
}

function highlightFeature(e) {
    const layer = e.target;
    layer.setStyle({
        weight: 4,
        color: '#666',
        dashArray: '',
        fillOpacity: 0.7
    });
    layer.bringToFront();
    info.update(layer.feature.properties);
}

function resetHighlight(e) {
    areasGeoJson.resetStyle(e.target);
    info.update();
}

function zoomToFeature(e) {
    if (clickMode) return;
    map.fitBounds(e.target.getBounds());
}

function displayAreas(areas) {
    layers.areas.clearLayers();

    areasGeoJson = L.geoJSON(areas, {
        pane: 'areasPane',
        style: areaStyle,
        onEachFeature: (feature, layer) => {
            layer.on({
                mouseover: highlightFeature,
                mouseout: resetHighlight,
                click: zoomToFeature
            });
        }
    }).addTo(layers.areas);
}

const info = L.control();

info.onAdd = function () {
    this._div = L.DomUtil.create('div', 'info');
    this.update();
    return this._div;
};

info.update = function (props) {
    this._div.innerHTML = '<h4>Hazards per area</h4>' + (props
        ? `<b>${escapeHtml(props.name)}</b><br>${props.hazard_count} hazard${props.hazard_count === 1 ? '' : 's'} reported` +
          `<br>${props.lane_length_km} km of cycle lane`
        : 'Hover over an area');
};

info.addTo(map);

map.on('overlayadd', e => { if (e.layer === layers.areas) info.addTo(map); });
map.on('overlayremove', e => { if (e.layer === layers.areas) info.remove(); });

const legend = L.control({ position: 'bottomright' });

legend.onAdd = function () {
    const div = L.DomUtil.create('div', 'info legend');

    let html = '<h4>Hazards per area</h4>';
    for (let i = 0; i < AREA_GRADES.length; i++) {
        const from = AREA_GRADES[i];
        const to = AREA_GRADES[i + 1] - 1;
        const label = AREA_GRADES[i + 1] === undefined ? `${from}+` : from === to ? `${from}` : `${from}&ndash;${to}`;
        html += `<i style="background:${getAreaColor(from)}"></i> ${label}<br>`;
    }

    html += '<h4>Bike stations</h4>';
    html += `<i style="background:${getStationColor(5)}"></i> 3+ bikes<br>`;
    html += `<i style="background:${getStationColor(1)}"></i> 1&ndash;2 bikes<br>`;
    html += `<i style="background:${getStationColor(0)}"></i> Empty<br>`;

    html += '<h4>Cycle lanes</h4>';
    [['segregated', 'Segregated'], ['painted', 'Painted'], ['shared', 'Shared / bus'], ['greenway', 'Greenway']]
        .forEach(([type, label]) => {
            html += `<i class="line" style="background:${LANE_COLORS[type]}"></i> ${label}<br>`;
        });

    div.innerHTML = html;
    return div;
};

legend.addTo(map);

function updateResultsSummary() {
    const bikes = current.stations.reduce((sum, s) => sum + (s.properties.available_bikes || 0), 0);
    document.getElementById('stations-count').textContent = current.stations.length;
    document.getElementById('bikes-count').textContent = bikes.toLocaleString();
    document.getElementById('hazards-count').textContent = current.hazards.length;
    document.getElementById('lanes-count').textContent = current.lanes.length;
}

function getCurrentFilters() {
    const hazardTypes = [...document.querySelectorAll('.hazard-type-filter:checked')].map(el => el.value);

    return {
        stations: {
            has_bikes: document.getElementById('stations-has-bikes').checked ? 'true' : ''
        },
        hazards: {
            hazard_type: hazardTypes,
            nearLanes: document.getElementById('hazards-near-lanes').checked,
            distance: document.getElementById('near-lanes-distance').value || 50
        },
        lanes: {
            lane_type: document.getElementById('lane-type-filter').value
        }
    };
}

async function applyFilters() {
    showLoading(true);

    try {
        const filters = getCurrentFilters();
        await Promise.all([
            loadStations(filters.stations),
            loadHazards(filters.hazards),
            loadLanes(filters.lanes),
            loadAreas()
        ]);
        updateResultsSummary();
    } catch (error) {
        console.error('Error loading map data:', error);
        alert(`Error loading map data: ${error.message}`);
    } finally {
        showLoading(false);
    }
}

function clearFilters() {
    document.querySelectorAll('.hazard-type-filter').forEach(el => { el.checked = true; });
    document.getElementById('hazards-near-lanes').checked = false;
    document.getElementById('near-lanes-distance').value = 50;
    document.getElementById('lane-type-filter').value = '';
    document.getElementById('stations-has-bikes').checked = false;
    applyFilters();
}

// The search and report buttons choose what a map click does.
// A banner at the top of the map shows the current mode, and Esc cancels it.
function setClickMode(mode) {
    clickMode = mode;
    document.getElementById('radius-control').classList.toggle('d-none', mode !== 'radius');
    document.getElementById('nearest-search-btn').classList.toggle('active', mode === 'nearest');
    document.getElementById('radius-search-btn').classList.toggle('active', mode === 'radius');
    map.getContainer().classList.toggle('picking', mode !== null);

    const hint = document.getElementById('map-hint');
    const messages = {
        nearest: 'Click the map to find the nearest bikes (Esc to stop)',
        radius: 'Click the map to find hazards nearby (Esc to stop)',
        report: 'Click the map where the hazard is (Esc to cancel)'
    };
    hint.textContent = messages[mode] || '';
    hint.style.display = mode ? 'block' : 'none';
}

function toggleClickMode(mode) {
    setClickMode(clickMode === mode ? null : mode);
}

map.on('click', e => {
    if (!clickMode) return;
    map.closePopup();

    if (clickMode === 'report') {
        setClickMode(null);
        openHazardForm(null, e.latlng);
    } else {
        runProximitySearch(e.latlng, clickMode);
    }
});

async function runProximitySearch(latlng, mode) {
    const isRadiusSearch = mode === 'radius';
    const radius = Number(document.getElementById('radius-input').value);
    const status = document.getElementById('proximity-status');

    if (isRadiusSearch && (!Number.isFinite(radius) || radius <= 0 || radius > 5000)) {
        status.textContent = 'Enter a radius greater than 0 and no more than 5000 m.';
        return;
    }

    status.textContent = 'Searching…';
    clearProximityResults();
    L.marker(latlng).bindTooltip('Search point').addTo(proximityLayer);

    try {
        const params = { lat: latlng.lat.toFixed(6), lng: latlng.lng.toFixed(6) };
        let features;
        let heading;

        if (isRadiusSearch) {
            features = await fetchFeatures('/api/hazards/nearby/', {
                ...params,
                distance: radius,
                hazard_type: getCurrentFilters().hazards.hazard_type
            });
            heading = `${features.length} hazard${features.length === 1 ? '' : 's'} within ${radius} m`;
            L.circle(latlng, { radius, color: '#198754', fillOpacity: 0.08 }).addTo(proximityLayer);
        } else {
            features = await fetchFeatures('/api/stations/nearest/', { ...params, has_bikes: 'true', limit: 5 });
            heading = features.length ? `${features.length} nearest stations with bikes` : 'No stations with bikes found';
        }

        showProximityResults(latlng, features, heading, isRadiusSearch);
        map.fitBounds(proximityLayer.getBounds(), { padding: [30, 30], maxZoom: 16 });
        status.textContent = 'Search complete.';
    } catch (error) {
        status.textContent = error.message;
    }
}

function showProximityResults(searchLatLng, features, heading, isRadiusSearch) {
    const results = document.getElementById('proximity-results');
    const title = document.createElement('strong');
    title.className = 'small mb-1';
    title.textContent = heading;
    results.append(title);

    features.forEach((feature, i) => {
        const [lng, lat] = feature.geometry.coordinates;
        const props = feature.properties;

        L.polyline([searchLatLng, [lat, lng]], { color: '#2c3e50', weight: 2, dashArray: '6 6' }).addTo(proximityLayer);
        const ring = L.circleMarker([lat, lng], { radius: 12, color: '#2c3e50', weight: 3, fill: false })
            .bindPopup(isRadiusSearch ? () => hazardPopup(feature) : stationPopup(props))
            .addTo(proximityLayer);

        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'list-group-item list-group-item-action small';
        item.textContent = isRadiusSearch
            ? `${i + 1}. ${props.hazard_type_display} — ${formatDistance(props.distance_m)}`
            : `${i + 1}. ${props.name} — ${formatDistance(props.distance_m)}, ${props.available_bikes} bikes`;
        item.addEventListener('click', () => {
            map.setView([lat, lng], 17);
            ring.openPopup();
        });
        results.append(item);
    });
}

function clearProximityResults() {
    proximityLayer.clearLayers();
    document.getElementById('proximity-results').replaceChildren();
}

// "Use my location": the browser finds where you are, then the selected search runs from there
function locateUser() {
    document.getElementById('proximity-status').textContent = 'Finding your location…';
    map.locate({ enableHighAccuracy: true });
}

map.on('locationfound', e => {
    runProximitySearch(e.latlng, clickMode === 'radius' ? 'radius' : 'nearest');
});

map.on('locationerror', e => {
    document.getElementById('proximity-status').textContent =
        `Could not get your location (${e.message}). Choose a search and click the map instead.`;
});

// Reporting hazards. The same pop-up form is used for new and edited hazards.
// After saving or deleting, the hazards and area counts are reloaded.
let hazardModal = null;

function openHazardForm(hazard, latlng) {
    editingHazardId = hazard ? hazard.id : null;
    pendingLocation = latlng || null;

    document.getElementById('hazard-modal-title').textContent = hazard ? 'Edit hazard' : 'Report a hazard';
    document.getElementById('hazard-type').value = hazard ? hazard.properties.hazard_type : 'pothole';
    document.getElementById('hazard-description').value = hazard ? hazard.properties.description : '';
    document.getElementById('hazard-form-errors').classList.add('d-none');

    if (pendingLocation) {
        pendingMarker = L.marker(pendingLocation, { icon: hazardIcon('other'), opacity: 0.7 }).addTo(map);
    }
    map.closePopup();
    hazardModal.show();
}

async function saveHazard(event) {
    event.preventDefault();

    const properties = {
        hazard_type: document.getElementById('hazard-type').value,
        description: document.getElementById('hazard-description').value.trim()
    };
    const saveButton = document.getElementById('hazard-save');
    saveButton.disabled = true;

    try {
        if (editingHazardId) {
            await sendJson('PATCH', `/api/hazards/${editingHazardId}/`, { type: 'Feature', properties });
        } else {
            await sendJson('POST', '/api/hazards/', {
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [pendingLocation.lng, pendingLocation.lat] },
                properties
            });
        }
        hazardModal.hide();
        await refreshHazards();
    } catch (error) {
        const errors = document.getElementById('hazard-form-errors');
        errors.textContent = error.message;
        errors.classList.remove('d-none');
    } finally {
        saveButton.disabled = false;
    }
}

async function deleteHazard(id) {
    if (!confirm('Delete this hazard report?')) return;
    try {
        await sendJson('DELETE', `/api/hazards/${id}/`);
        map.closePopup();
        await refreshHazards();
    } catch (error) {
        alert(`Could not delete hazard: ${error.message}`);
    }
}

async function refreshHazards() {
    await Promise.all([loadHazards(getCurrentFilters().hazards), loadAreas()]);
    updateResultsSummary();
}

document.addEventListener('DOMContentLoaded', function() {
    hazardModal = new bootstrap.Modal(document.getElementById('hazard-modal'));
    document.getElementById('hazard-modal').addEventListener('hidden.bs.modal', () => {
        if (pendingMarker) {
            map.removeLayer(pendingMarker);
            pendingMarker = null;
        }
    });
    document.getElementById('hazard-form').addEventListener('submit', saveHazard);

    document.querySelectorAll('[data-hazard-swatch]').forEach(el => {
        el.style.background = HAZARD_COLORS[el.dataset.hazardSwatch] || HAZARD_COLORS.other;
    });

    const clickHandlers = {
        'apply-filters': applyFilters,
        'clear-filters': clearFilters,
        'nearest-search-btn': () => toggleClickMode('nearest'),
        'radius-search-btn': () => toggleClickMode('radius'),
        'locate-btn': locateUser,
        'report-hazard': () => toggleClickMode('report'),
        'export-hazards': () => downloadJson({ type: 'FeatureCollection', features: current.hazards }, 'hazards_export.geojson'),
        'export-stations': () => downloadJson({ type: 'FeatureCollection', features: current.stations }, 'stations_export.geojson')
    };
    Object.entries(clickHandlers).forEach(([id, handler]) => {
        const element = document.getElementById(id);
        if (element) element.addEventListener('click', handler);
    });

    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') setClickMode(null);
    });

    applyFilters();
});

