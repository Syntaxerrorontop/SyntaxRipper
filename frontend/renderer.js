const { ipcRenderer } = require('electron');

const API_URL = 'http://127.0.0.1:12345';
const WS_URL = 'ws://127.0.0.1:12345/ws';

// Global State
let ws = null;
let reconnectInterval = null;
let libraryData = [];
let selectedGameId = null;
let currentSettings = { game_paths: [], download_path: "", download_cache_path: "" };
let currentGalleryImages = [];
let currentGalleryIndex = 0;
let runningGames = []; // List of running game IDs
window.collapsedCategories = new Set(); 

// --- Custom Dialogs ---
function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = 'position: fixed; bottom: 20px; right: 20px; z-index: 9999; display: flex; flex-direction: column; gap: 10px; pointer-events: none;';
        document.body.appendChild(container);
    }
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.style.cssText = `
        background: #252526; 
        color: white; 
        padding: 12px 20px; 
        border-radius: 6px; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.5); 
        border-left: 4px solid ${type === 'error' ? '#ff6b6b' : type === 'success' ? '#28a745' : '#007acc'};
        opacity: 0;
        transform: translateY(20px);
        transition: all 0.3s ease;
        pointer-events: auto;
        min-width: 250px;
        font-size: 14px;
    `;
    toast.innerHTML = `<div style="font-weight:bold; margin-bottom:4px;">${type.toUpperCase()}</div><div>${message}</div>`;
    
    container.appendChild(toast);
    
    // Animate In
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
    });
    
    // Animate Out
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function showAlert(title, message) {
    return new Promise((resolve) => {
        const overlay = document.getElementById('modal-overlay');
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-body').textContent = message;
        const footer = document.getElementById('modal-footer');
        footer.innerHTML = '';
        
        const btn = document.createElement('button');
        btn.className = 'modal-btn modal-btn-primary';
        btn.textContent = 'OK';
        btn.onclick = () => {
            overlay.style.display = 'none';
            resolve();
        };
        footer.appendChild(btn);
        overlay.style.display = 'flex';
    });
}

function showConfirm(title, message, isDanger = false) {
    return new Promise((resolve) => {
        const overlay = document.getElementById('modal-overlay');
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-body').textContent = message;
        const footer = document.getElementById('modal-footer');
        footer.innerHTML = '';
        
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'modal-btn modal-btn-secondary';
        cancelBtn.textContent = 'Cancel';
        cancelBtn.onclick = () => {
            overlay.style.display = 'none';
            resolve(false);
        };
        
        const confirmBtn = document.createElement('button');
        confirmBtn.className = isDanger ? 'modal-btn modal-btn-danger' : 'modal-btn modal-btn-primary';
        confirmBtn.textContent = 'Confirm';
        confirmBtn.onclick = () => {
            overlay.style.display = 'none';
            resolve(true);
        };
        
        footer.appendChild(cancelBtn);
        footer.appendChild(confirmBtn);
        overlay.style.display = 'flex';
        cancelBtn.focus(); // Default focus for safety
    });
}

function showPrompt(title, message, defaultValue = "") {
    return new Promise((resolve) => {
        const overlay = document.getElementById('modal-overlay');
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-body').innerHTML = `
            <p>${message}</p>
            <input type="text" id="modal-input" value="${defaultValue}" 
                   style="width: 100%; padding: 10px; background: #161616; border: 1px solid #333; color: white; border-radius: 6px; box-sizing: border-box; margin-top: 10px;">
        `;
        const footer = document.getElementById('modal-footer');
        footer.innerHTML = '';
        
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'modal-btn modal-btn-secondary';
        cancelBtn.textContent = 'Cancel';
        cancelBtn.onclick = () => {
            overlay.style.display = 'none';
            resolve(null);
        };
        
        const okBtn = document.createElement('button');
        okBtn.className = 'modal-btn modal-btn-primary';
        okBtn.textContent = 'OK';
        okBtn.onclick = () => {
            const val = document.getElementById('modal-input').value;
            overlay.style.display = 'none';
            resolve(val);
        };
        
        footer.appendChild(cancelBtn);
        footer.appendChild(okBtn);
        overlay.style.display = 'flex';
        document.getElementById('modal-input').focus();
    });
}

// --- Connection ---
function connectWebSocket() {
    console.log("Attempting WebSocket connection...");
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => { 
        console.log("WebSocket connected.");
        if (reconnectInterval) clearInterval(reconnectInterval); 
    };
    
    ws.onmessage = (event) => { 
        try { 
            const msg = JSON.parse(event.data);
            console.log("WS Message:", msg);
            handleWsMessage(msg); 
        } catch(e) {
            console.error("WS Parse Error:", e, event.data);
        } 
    }; 
    
    ws.onclose = () => {
        console.warn("WebSocket closed. Reconnecting in 2s...");
        updateFooterStatus('error');
        if (!reconnectInterval) reconnectInterval = setInterval(connectWebSocket, 2000);
    };

    ws.onerror = (err) => {
        console.error("WebSocket Error:", err);
    };
}

function handleWsMessage(msg) {
    if (msg.type === 'status') {
        const statusEl = document.getElementById('dl-status-text');
        if (statusEl) statusEl.textContent = msg.data;
        if (msg.data.includes("Finished") || msg.data.includes("Complete")) refreshLibrary();
    } else if (msg.type === 'progress') {
        const progressFill = document.getElementById('dl-progress-fill');
        const dlStatus = document.getElementById('dl-status');
        let val = typeof msg.data === 'number' ? msg.data : parseFloat(msg.data);
        if (isNaN(val)) val = 0;
        if (progressFill) progressFill.style.width = `${val}%`;
        if (dlStatus) dlStatus.textContent = `${val.toFixed(1)}%`;
    } else if (msg.type === 'meta') {
        const titleEl = document.getElementById('dl-title');
        if (titleEl && msg.data.filename) titleEl.textContent = msg.data.filename;
    } else if (msg.type === 'complete') {
        showToast(msg.data.message || "Operation Complete", "success");
        refreshLibrary();
    } else if (msg.type === 'scraper_status') {
        updateFooterStatus(msg.data);
    } else if (msg.type === 'update_available') {
        showToast(`Update Available: ${msg.data.name} (${msg.data.latest})`, "info");
        refreshLibrary();
    } else if (msg.type === 'hltb_update') {
        // If currently viewing this game, update the display
        if (selectedGameId === msg.data.id) {
            updateHLTBDisplay(msg.data.data);
        }
    }
}

function updateHLTBDisplay(stats) {
    const hltbEl = document.getElementById('detail-hltb');
    if (!hltbEl) return;
    
    if (stats && stats.main !== "N/A") {
        hltbEl.innerHTML = `
            <span title="Main Story: Time to complete the main campaign">🕒 ${stats.main}</span>
            <span title="Main + Extra: Time for main story plus side quests">✅ ${stats.main_extra}</span>
            <span title="Completionist: Time to achieve 100% completion">🏆 ${stats.completionist}</span>
        `;
    } else {
        hltbEl.innerHTML = '';
    }
}

function updateFooterStatus(status) {
    const el = document.getElementById('footerStatus');
    if (!el) return;
    if (status === 'initializing') {
        el.innerHTML = '<span class="spin">↻</span> Starting Engine...';
        el.style.color = '#e0e0e0'; 
    } else if (status === 'ready') {
        el.textContent = '🟢 Online';
        el.style.color = 'lightgreen';
        fetchVersion();
    } else if (status === 'error') {
        el.textContent = '🔴 Offline';
        el.style.color = 'red';
    }
}

async function fetchVersion() {
    try {
        const res = await fetch(`${API_URL}/api/version`);
        const data = await res.json();
        // Assume footer has a span for version
        const vEl = document.querySelector('#footer span:nth-child(2)'); 
        if (vEl) vEl.textContent = `V${data.version}`;
    } catch(e) {}
}

// --- Navigation ---
function switchTab(tabName) {
    if (!tabName || typeof tabName !== 'string') return;
    
    document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    
    const targetView = document.getElementById(`view-${tabName}`);
    if (targetView) targetView.classList.add('active');
    
    const mapping = { 'library': 0, 'search': 1, 'downloads': 2, 'scripts': 3, 'settings': 4, 'profile': 1 }; 
    // Wait, profile icon index? Profile is new item.
    // Let's re-map based on DOM order or just use querySelector.
    // Mapping was for .nav-item active class.
    
    // Reset all nav items active state
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(n => n.classList.remove('active'));
    
    // Find the nav item that calls this function with this tabName
    // Simple lookup based on title or manual index.
    const indexMap = {
        'library': 0, 'search': 1, 'downloads': 2, 'scripts': 3, 'settings': 4, 'profile': 5
    };
    if (indexMap[tabName] !== undefined && navItems[indexMap[tabName]]) {
        navItems[indexMap[tabName]].classList.add('active');
    }

    if (tabName === 'library') refreshLibrary();
    if (tabName === 'settings') loadSettings();
    if (tabName === 'profile') loadProfileStats();
}

// --- Settings ---
async function loadSettings() {
    try {
        const res = await fetch(`${API_URL}/api/settings`);
        currentSettings = await res.json();
        if (currentSettings.collapsed_categories) {
            window.collapsedCategories = new Set(currentSettings.collapsed_categories);
        }
        renderSettings();
        const nameEl = document.getElementById('sidebar-username');
        if (nameEl) nameEl.textContent = currentSettings.username || "Guest";
        
        // Re-apply tree state if library is loaded (now handles auto-select)
        if (libraryData.length > 0) renderTree();
    } catch(e) { console.error("Load settings failed", e); }
}

function renderSettings() {
    const list = document.getElementById('gamePathsList');
    if (list) {
        list.innerHTML = '';
        currentSettings.game_paths.forEach((path, index) => {
            const li = document.createElement('li');
            li.style.cssText = 'padding:10px; border-bottom:1px solid #333; display:flex; justify-content:space-between; align-items:center;';
            li.innerHTML = `<span>${path}</span><button class="btn btn-secondary" style="color: #ff6b6b; padding: 2px 8px;" onclick="removeGamePath(${index})">✕</button>`;
            list.appendChild(li);
        });
    }
    const userIn = document.getElementById('usernameInput'); if (userIn) userIn.value = currentSettings.username || "";
    const langIn = document.getElementById('languageInput'); if (langIn) langIn.value = currentSettings.language || "";
    const rawgIn = document.getElementById('rawgKeyInput'); if (rawgIn) rawgIn.value = currentSettings.rawg_api_key || "";
    const debridIn = document.getElementById('debridKeyInput'); if (debridIn) debridIn.value = currentSettings.real_debrid_key || "";
    const dpathIn = document.getElementById('downloadPathInput'); if (dpathIn) dpathIn.value = currentSettings.download_path || "";
    const dcacheIn = document.getElementById('downloadCachePathInput'); if (dcacheIn) dcacheIn.value = currentSettings.download_cache_path || "";
    const gpathIn = document.getElementById('installedGamesPathInput'); if (gpathIn) gpathIn.value = currentSettings.installed_games_path || "";
    const mpathIn = document.getElementById('mediaOutputPathInput'); if (mpathIn) mpathIn.value = currentSettings.media_output_path || "";
    const speedIn = document.getElementById('speedLimitInput'); if (speedIn) speedIn.value = currentSettings.speed || 0;
    const speedEnabledIn = document.getElementById('speedLimitEnabledInput'); if (speedEnabledIn) speedEnabledIn.checked = currentSettings.speed_enabled || false;
    const autoUpdateIn = document.getElementById('autoUpdateInput'); if (autoUpdateIn) autoUpdateIn.checked = currentSettings.auto_update_games || false;
    const resumeIn = document.getElementById('resumeStartupInput'); if (resumeIn) resumeIn.checked = currentSettings.resume_on_startup || false;
    const dryIn = document.getElementById('dryLaunchInput'); if (dryIn) dryIn.checked = currentSettings.dry_launch || false;
    const verboseIn = document.getElementById('verboseLoggingInput'); if (verboseIn) verboseIn.checked = currentSettings.verbose_logging || false;
    const rpcIn = document.getElementById('discordRpcInput'); if (rpcIn) rpcIn.checked = currentSettings.discord_rpc_enabled !== false; // Default true
    const gameModeIn = document.getElementById('gamingModeInput'); if (gameModeIn) gameModeIn.checked = currentSettings.gaming_mode_enabled !== false; // Default true
    
    loadToolsStatus();
}

async function loadToolsStatus() {
    const list = document.getElementById('tools-status-list');
    if (!list) return;
    try {
        const res = await fetch(`${API_URL}/api/tools/status`);
        const tools = await res.json();
        list.innerHTML = '';
        
        for (const [key, info] of Object.entries(tools)) {
            const li = document.createElement('li');
            li.style.cssText = 'padding:10px; display:flex; justify-content:space-between; align-items:center;';
            
            let actionBtn = '';
            if (info.installed) {
                if (key === 'vc_redist') {
                    actionBtn = `<button class="btn btn-secondary" onclick="runVcRedist()" style="padding:4px 10px; font-size:12px;">Run Installer</button>`;
                } else {
                    actionBtn = `<span style="color:#28a745;">✔ Installed</span>`;
                }
            } else {
                actionBtn = `<button class="btn btn-primary" onclick="installTool('${key}')" style="padding:4px 10px; font-size:12px;">Install</button>`;
            }
            
            li.innerHTML = `
                <div>
                    <div style="font-weight:bold; color:white;">${info.name}</div>
                    <div style="font-size:12px; color:#888;">${info.path || "Not found"}</div>
                </div>
                ${actionBtn}
            `;
            list.appendChild(li);
        }
    } catch(e) { list.innerHTML = '<li style="color:red">Failed to load tools status</li>'; }
}

async function installTool(key) {
    if (!await showConfirm("Install Tool", `Download and install ${key}? This might take a moment.`, false)) return;
    try {
        await fetch(`${API_URL}/api/tools/install/${key}`, { method: 'POST' });
        await showAlert("Success", "Tool installed successfully!");
        loadToolsStatus();
    } catch(e) { await showAlert("Error", "Install failed: " + e.message); }
}

async function runVcRedist() {
    try {
        await fetch(`${API_URL}/api/tools/run/vc_redist`, { method: 'POST' });
        await showAlert("Started", "Check for UAC prompt.");
    } catch(e) { await showAlert("Error", e.message); }
}

async function addGamePath() {
    const path = await ipcRenderer.invoke('select-folder');
    if (path && !currentSettings.game_paths.includes(path)) {
        currentSettings.game_paths.push(path);
        await saveSettings();
    }
}

async function removeGamePath(index) {
    currentSettings.game_paths.splice(index, 1);
    await saveSettings();
}

async function changeDownloadPath() {
    const path = await ipcRenderer.invoke('select-folder');
    if (path) { 
        currentSettings.download_path = path; 
        const el = document.getElementById('downloadPathInput');
        if (el) el.value = path;
        await saveSettings(); 
    }
}

async function changeDownloadCachePath() {
    const path = await ipcRenderer.invoke('select-folder');
    if (path) { 
        currentSettings.download_cache_path = path; 
        const el = document.getElementById('downloadCachePathInput');
        if (el) el.value = path;
        await saveSettings(); 
    }
}

async function changeInstalledGamesPath() {
    const path = await ipcRenderer.invoke('select-folder');
    if (path) { 
        currentSettings.installed_games_path = path; 
        const el = document.getElementById('installedGamesPathInput');
        if (el) el.value = path;
        await saveSettings(); 
    }
}

async function changeMediaOutputPath() {
    const path = await ipcRenderer.invoke('select-folder');
    if (path) { 
        currentSettings.media_output_path = path; 
        const el = document.getElementById('mediaOutputPathInput');
        if (el) el.value = path;
        await saveSettings(); 
    }
}

async function openPath(path) {
    if (!path) return;
    try {
        await fetch(`${API_URL}/api/system/open-path`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ path: path })
        });
    } catch(e) { console.error(e); }
}

function togglePasswordVisibility(id) {
    const el = document.getElementById(id);
    if (el) el.type = el.type === "password" ? "text" : "password";
}

async function cleanCache() {
    if (!await showConfirm("Clean Cache", "Are you sure? This will delete all downloaded images and game data.")) return;
    try {
        const res = await fetch(`${API_URL}/api/settings/clean-cache`, { method: 'POST' });
        if (res.ok) { await showAlert("Success", "Metadata cache cleaned!"); refreshLibrary(); }
    } catch(e) { await showAlert("Error", e.message); }
}

async function cleanDownloadCache() {
    if (!await showConfirm("Clean Cache", "Are you sure? This will delete all temporary download data. This cannot be undone.")) return;
    try {
        const res = await fetch(`${API_URL}/api/download/cache/clean`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) { await showAlert("Success", `Download cache cleaned! Removed ${data.count} items.`); pollDownloadStatus(); }
    } catch(e) { await showAlert("Error", e.message); }
}

async function openLogDir() {
    try {
        const res = await fetch(`${API_URL}/api/system/open-logs`, { method: 'POST' });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Unknown error");
        }
    } catch(e) { await showAlert("Error", "Failed to open logs: " + e.message); }
}

async function forceUpdateConfig() {
    if (!await showConfirm("Force Update", "This will re-scan all game folders for executables and metadata. Continue?", false)) return;
    try {
        await fetch(`${API_URL}/api/library/force-update`, { method: 'POST' });
        await showAlert("Started", "Force update started in background.");
        setTimeout(refreshLibrary, 2000);
    } catch(e) { await showAlert("Error", e.message); }
}

// --- Clean Saves Dialog ---
let orphanedSavesList = [];

async function openCleanSavesDialog() {
    try {
        const res = await fetch(`${API_URL}/api/settings/orphaned-saves`);
        orphanedSavesList = await res.json();
        
        if (!orphanedSavesList || orphanedSavesList.length === 0) {
            await showAlert("Clean Save Data", "No unused save data found.");
            return;
        }
        
        renderCleanSavesList();
        document.getElementById('clean-saves-modal').style.display = 'flex';
    } catch(e) { await showAlert("Error", "Failed to load orphaned saves: " + e.message); }
}

function closeCleanSavesDialog() {
    document.getElementById('clean-saves-modal').style.display = 'none';
}

function renderCleanSavesList() {
    const list = document.getElementById('orphaned-saves-list');
    list.innerHTML = '';
    orphanedSavesList.forEach((item, idx) => {
        const div = document.createElement('div');
        div.style.cssText = 'padding: 10px; border-bottom: 1px solid #333; display: flex; align-items: center; gap: 10px;';
        div.innerHTML = `
            <input type="checkbox" class="save-check" data-index="${idx}" checked style="width: 18px; height: 18px;">
            <div style="flex: 1; overflow: hidden;">
                <div style="font-weight: bold; color: white;">${item.name}</div>
                <div style="font-size: 12px; color: #888; text-overflow: ellipsis; white-space: nowrap; overflow: hidden;">${item.path}</div>
            </div>
        `;
        list.appendChild(div);
    });
}

function toggleSaveSelection(selectAll) {
    document.querySelectorAll('.save-check').forEach(cb => cb.checked = selectAll);
}

async function deleteSelectedSaves() {
    const selectedIndices = Array.from(document.querySelectorAll('.save-check:checked')).map(cb => parseInt(cb.dataset.index));
    
    if (selectedIndices.length === 0) {
        closeCleanSavesDialog();
        return;
    }
    
    if (!await showConfirm("Confirm Delete", `Permanently delete ${selectedIndices.length} save folders?`, true)) return;
    
    try {
        const res = await fetch(`${API_URL}/api/settings/clean-saves`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ indices: selectedIndices })
        });
        const data = await res.json();
        await showAlert("Success", `Deleted ${data.deleted_count} save folders.`);
        closeCleanSavesDialog();
    } catch(e) { await showAlert("Error", "Deletion failed: " + e.message); }
}

async function saveSettings() {
    try {
        const userIn = document.getElementById('usernameInput'); if (userIn) currentSettings.username = userIn.value;
        const langIn = document.getElementById('languageInput'); if (langIn) currentSettings.language = langIn.value;
        const rawgIn = document.getElementById('rawgKeyInput'); if (rawgIn) currentSettings.rawg_api_key = rawgIn.value.trim();
        const debridIn = document.getElementById('debridKeyInput'); if (debridIn) currentSettings.real_debrid_key = debridIn.value.trim();
        const speedIn = document.getElementById('speedLimitInput'); if (speedIn) currentSettings.speed = parseInt(speedIn.value) || 0;
        const speedEnabledIn = document.getElementById('speedLimitEnabledInput'); if (speedEnabledIn) currentSettings.speed_enabled = speedEnabledIn.checked;
        const autoUpdateIn = document.getElementById('autoUpdateInput'); if (autoUpdateIn) currentSettings.auto_update_games = autoUpdateIn.checked;
        const resumeIn = document.getElementById('resumeStartupInput'); if (resumeIn) currentSettings.resume_on_startup = resumeIn.checked;
        const dryIn = document.getElementById('dryLaunchInput'); if (dryIn) currentSettings.dry_launch = dryIn.checked;
        const verboseIn = document.getElementById('verboseLoggingInput'); if (verboseIn) currentSettings.verbose_logging = verboseIn.checked;
        const controllerIn = document.getElementById('controllerSupportInput'); if (controllerIn) currentSettings.controller_support = controllerIn.checked;
        const showHiddenIn = document.getElementById('showHiddenInput'); if (showHiddenIn) currentSettings.show_hidden_games = showHiddenIn.checked;
        const rpcIn = document.getElementById('discordRpcInput'); if (rpcIn) currentSettings.discord_rpc_enabled = rpcIn.checked;
        const gameModeIn = document.getElementById('gamingModeInput'); if (gameModeIn) currentSettings.gaming_mode_enabled = gameModeIn.checked;
        // Mappings are updated in-place in currentSettings during remap, just need to send them
        
        // Media Output Path is updated in-place by changeMediaOutputPath, but just in case:
        const dcacheIn = document.getElementById('downloadCachePathInput'); if (dcacheIn) currentSettings.download_cache_path = dcacheIn.value;
        const gpathIn = document.getElementById('installedGamesPathInput'); if (gpathIn) currentSettings.installed_games_path = gpathIn.value;
        const mpathIn = document.getElementById('mediaOutputPathInput'); if (mpathIn) currentSettings.media_output_path = mpathIn.value;

        await fetch(`${API_URL}/api/settings`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(currentSettings)
        });
        await loadSettings();
        refreshLibrary();
        await showAlert("Success", "Settings saved!");
    } catch(e) { await showAlert("Error", "Save failed: " + e); }
}

// --- Library ---
async function refreshLibrary() {
    try {
        const res = await fetch(`${API_URL}/api/library`);
        const data = await res.json();
        libraryData = data.library;
        renderTree();
        
        // Refresh details if a game is selected, to update buttons (e.g. after uninstall)
        if (selectedGameId) {
            // Validate if game still exists (might be removed)
            const stillExists = libraryData.find(g => g.id === selectedGameId);
            if (stillExists) showDetails(selectedGameId);
            else closeDetails();
        }
    } catch (e) { console.error("Lib load fail", e); }
}

function renderTree(filterText = "") {
    const container = document.getElementById('library-tree');
    if (!container) return;
    container.innerHTML = '';
    const cleanTree = {};
    const categoriesSet = new Set();
    
    // Sorting
    const sortMode = document.getElementById('librarySort') ? document.getElementById('librarySort').value : 'name';
    const showHidden = currentSettings.show_hidden_games;

    let updateCount = 0;

    libraryData.forEach(game => {
        if (!showHidden && game.hidden) return;
        if (filterText && !game.name.toLowerCase().includes(filterText.toLowerCase())) return;
        
        if (game.update_available) updateCount++;

        let cats = (game.categories || []).filter(c => c !== "Installed" && c !== "Not Installed");
        cats.forEach(c => categoriesSet.add(c));
        if (cats.length === 0) cats = [game.installed ? "Installed" : "Not installed"];
        cats.forEach(cat => {
            const parts = cat.split(':');
            let currentLevel = cleanTree;
            parts.forEach((part, idx) => {
                if (!currentLevel[part]) currentLevel[part] = { games: [], children: {} };
                if (idx === parts.length - 1) currentLevel[part].games.push(game);
                currentLevel = currentLevel[part].children;
            });
        });
    });
    
    // Badge Update
    const libBadge = document.getElementById('badge-library');
    if (libBadge) {
        libBadge.textContent = updateCount > 0 ? `${updateCount} Update${updateCount > 1 ? 's' : ''}` : '';
        libBadge.style.display = updateCount > 0 ? 'inline-block' : 'none';
    }

    window.allCategories = Array.from(categoriesSet).sort();
    window.visibleCategories = Object.keys(cleanTree);

    function renderNode(node, parent) {
        const keys = Object.keys(node).sort((a, b) => {
             const order = currentSettings.category_order || [];
             const idxA = order.indexOf(a), idxB = order.indexOf(b);
             if (idxA === -1 && idxB === -1) return a.localeCompare(b);
             if (idxA === -1) return 1; if (idxB === -1) return -1;
             return idxA - idxB;
        });

        keys.forEach(key => {
            const item = node[key];
            const details = document.createElement('details');
            details.open = !window.collapsedCategories.has(key);
            details.ontoggle = () => { 
                if (!details.open) window.collapsedCategories.add(key); 
                else window.collapsedCategories.delete(key);
                
                // Save state
                fetch(`${API_URL}/api/library/collapsed_categories`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ collapsed: Array.from(window.collapsedCategories) })
                });
            };
            details.draggable = true;
            details.ondragstart = (e) => { e.stopPropagation(); e.dataTransfer.setData("category-name", key); };
            details.ondragover = (e) => e.preventDefault();
            details.ondrop = (e) => {
                e.preventDefault(); e.stopPropagation();
                const draggedCat = e.dataTransfer.getData("category-name");
                if (draggedCat) { if (draggedCat !== key) handleCategoryReorder(draggedCat, key); } 
                else handleDrop(e, key);
            };

            const summary = document.createElement('summary'); summary.textContent = key;
            if (key !== "Installed" && key !== "Not installed" && !key.startsWith("External:")) {
                summary.ondragover = (e) => e.preventDefault();
                summary.ondrop = (e) => handleDrop(e, key);
                summary.oncontextmenu = (e) => showCategoryContextMenu(e, key);
            }
            details.appendChild(summary);
            renderNode(item.children, details);
            
            // Sort Games inside category
            item.games.sort((a, b) => {
                if (sortMode === 'time') return b.playtime - a.playtime;
                if (sortMode === 'added') return 0; // Assuming list is chronological or added date needed
                return a.name.localeCompare(b.name);
            });

            item.games.forEach(game => {
                const div = document.createElement('div');
                div.className = `tree-item ${game.installed ? 'installed' : 'uninstalled'}`;
                div.textContent = game.name;
                div.onclick = (e) => { e.stopPropagation(); showDetails(game.id); };
                if (selectedGameId === game.id) div.classList.add('selected');
                div.draggable = true;
                div.ondragstart = (e) => { e.stopPropagation(); e.dataTransfer.setData("text/plain", game.id); };
                div.oncontextmenu = (e) => showContextMenu(e, game);
                details.appendChild(div);
            });
            parent.appendChild(details);
        });
    }
    renderNode(cleanTree, container);
    
    // Auto-select last game if not already selected
    if (!selectedGameId && currentSettings.last_selected_game_id) {
        const game = libraryData.find(g => g.id === currentSettings.last_selected_game_id);
        if (game) showDetails(game.id);
    }
}

let currentSettingsGameId = null;

async function openGameSettings(game) {
    currentSettingsGameId = game.id;
    document.getElementById('gs-title').textContent = `Settings: ${game.name}`;
    document.getElementById('gs-alias').value = game.name;
    document.getElementById('gs-exe').value = game.exe || "";
    
    // We might need to fetch the full game data to get arguments if not in libraryData
    try {
        const res = await fetch(`${API_URL}/api/library/game/${game.id}`);
        if (res.ok) {
            const fullData = await res.json();
            document.getElementById('gs-args').value = (fullData.args || []).join('\n');
            document.getElementById('gs-exe').value = fullData.exe || "";
            document.getElementById('gs-pre-script').value = fullData.pre_launch_script || "";
            document.getElementById('gs-post-script').value = fullData.post_exit_script || "";
            document.getElementById('gs-save-path').value = fullData.save_path || "";
            document.getElementById('gs-tags').value = (fullData.tags || []).join(', ');
            
            const candidateSelect = document.getElementById('gs-save-candidates');
            const candidates = fullData.save_candidates || [];
            if (candidates.length > 0) {
                candidateSelect.style.display = 'block';
                candidateSelect.innerHTML = '<option value="">Select Path...</option>';
                candidates.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = c;
                    opt.textContent = c;
                    candidateSelect.appendChild(opt);
                });
            } else {
                candidateSelect.style.display = 'none';
            }

            loadGameBackups(game.id);
        }
    } catch (e) {
        console.error("Failed to fetch full game data", e);
        document.getElementById('gs-args').value = "";
    }
    
    document.getElementById('game-settings-modal').style.display = 'flex';
}

async function loadGameBackups(gameId) {
    const list = document.getElementById('gs-backup-list');
    list.innerHTML = '<li>Loading...</li>';
    try {
        const res = await fetch(`${API_URL}/api/game/${gameId}/backups`);
        const backups = await res.json();
        list.innerHTML = '';
        if (backups.length === 0) {
            list.innerHTML = '<li style="color:#666; font-style:italic;">No backups found.</li>';
            return;
        }
        backups.forEach(b => {
            const li = document.createElement('li');
            li.style.cssText = 'padding:5px 10px; font-size:12px; display:flex; justify-content:space-between;';
            li.innerHTML = `<span>${b.date}</span> <button class="btn btn-secondary" style="padding:2px 8px; font-size:10px;" onclick="restoreBackup('${gameId}', '${b.filename}')">Restore</button>`;
            list.appendChild(li);
        });
    } catch(e) { list.innerHTML = '<li>Error loading backups</li>'; }
}

async function triggerManualBackup() {
    if (!currentSettingsGameId) return;
    try {
        await fetch(`${API_URL}/api/game/${currentSettingsGameId}/backup`, { method: 'POST' });
        loadGameBackups(currentSettingsGameId);
    } catch(e) { showAlert("Error", "Backup failed: " + e.message); }
}

async function restoreBackup(gameId, filename) {
    if (!await showConfirm("Restore Backup", "This will overwrite current saves. Continue?", true)) return;
    try {
        const res = await fetch(`${API_URL}/api/game/${gameId}/restore`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({filename})
        });
        if (res.ok) showAlert("Success", "Backup restored.");
        else showAlert("Error", "Restore failed.");
    } catch(e) {}
}

function closeGameSettings() {
    document.getElementById('game-settings-modal').style.display = 'none';
    currentSettingsGameId = null;
}

async function runCompression() {
    if (!currentSettingsGameId) return;
    if (!await showConfirm("Compress Game", "This uses Windows CompactOS (LZX). It may take a while but saves space. Continue?", false)) return;
    
    try {
        await showAlert("Started", "Compression started. Please wait...");
        const res = await fetch(`${API_URL}/api/game/${currentSettingsGameId}/compress`, { method: 'POST' });
        const data = await res.json();
        console.log("Compression Data:", data); // Debug
        
        if (data.error) throw new Error(data.error);
        
        const savedMB = ((data.saved || 0) / 1024 / 1024).toFixed(2);
        const ratio = Number(data.ratio || 0);
        await showAlert("Finished", `Compression complete!\nSaved: ${savedMB} MB\nRatio: ${ratio.toFixed(1)}%`);
    } catch(e) { await showAlert("Error", e.message); }
}

async function runIntegrityCheck() {
    if (!currentSettingsGameId) return;
    // For now simple verify, could support generate too if we assume current state is valid
    // We'll try verify first, if missing, ask to generate
    
    try {
        const res = await fetch(`${API_URL}/api/game/${currentSettingsGameId}/integrity/verify`, { method: 'POST' });
        const data = await res.json();
        
        if (data.error && data.error.includes("No checksum")) {
            if (await showConfirm("Generate Integrity", "No checksums found. Generate baseline checksums now?", false)) {
                await fetch(`${API_URL}/api/game/${currentSettingsGameId}/integrity/generate`, { method: 'POST' });
                await showAlert("Success", "Checksums generated.");
            }
            return;
        }
        
        if (data.ok) {
            await showAlert("Integrity OK", `Verified ${data.total} files. No issues.`);
        } else {
            await showAlert("Integrity Issues", `Found issues!\nMismatches: ${data.mismatches.length}\nMissing: ${data.missing.length}`);
        }
    } catch(e) { await showAlert("Error", e.message); }
}

async function runJunkClean() {
    if (!currentSettingsGameId) return;
    try {
        const res = await fetch(`${API_URL}/api/game/${currentSettingsGameId}/junk/scan`, { method: 'POST' });
        const items = await res.json();
        
        if (items.length === 0) {
            await showAlert("Clean Junk", "No junk files found.");
            return;
        }
        
        const count = items.length;
        if (await showConfirm("Clean Junk", `Found ${count} items (Redist, DirectX, temps). Delete them?`, true)) {
            const cleanRes = await fetch(`${API_URL}/api/game/${currentSettingsGameId}/junk/clean`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ items })
            });
            const resData = await cleanRes.json();
            await showAlert("Finished", `Deleted ${resData.deleted} items.`);
        }
    } catch(e) { await showAlert("Error", e.message); }
}

async function saveGameSettings() {
    if (!currentSettingsGameId) return;
    
    const alias = document.getElementById('gs-alias').value;
    const exe = document.getElementById('gs-exe').value;
    const args = document.getElementById('gs-args').value.split('\n').map(a => a.trim()).filter(a => a.length > 0);
    const savePath = document.getElementById('gs-save-path').value;
    const tags = document.getElementById('gs-tags').value.split(',').map(t => t.trim()).filter(t => t.length > 0);
    const pre = document.getElementById('gs-pre-script').value;
    const post = document.getElementById('gs-post-script').value;
    
    try {
        // Save Settings
        await fetch(`${API_URL}/api/library/update_settings`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ id: currentSettingsGameId, alias, exe, args, save_path: savePath, tags: tags })
        });
        
        // Save Scripts
        await fetch(`${API_URL}/api/game/${currentSettingsGameId}/scripts`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ pre_launch: pre, post_exit: post })
        });

        closeGameSettings();
        refreshLibrary();
        if (selectedGameId === currentSettingsGameId) showDetails(selectedGameId);
    } catch (e) {
        showAlert("Error", "Failed to save settings: " + e.message);
    }
}

async function selectGameExe() {
    const path = await ipcRenderer.invoke('select-file', {
        title: 'Select Game Executable',
        filters: [{ name: 'Executables', extensions: ['exe', 'bat', 'cmd', 'sh'] }]
    });
    if (path) {
        document.getElementById('gs-exe').value = path;
    }
}

async function openFolder(id) { try { await fetch(`${API_URL}/api/open-folder/${id}`, { method: 'POST' }); } catch (e) {} }

// --- Drag & Drop ---
async function handleDrop(e, category) {
    e.preventDefault(); const gameId = e.dataTransfer.getData("text/plain");
    if (gameId && category !== "Installed" && category !== "Not installed" && !category.startsWith("External:")) {
        await updateGameCategories(gameId, category, "add");
    }
}

async function handleCategoryReorder(srcCat, targetCat) {
    let order = [...(currentSettings.category_order || [])];
    const currentCats = window.visibleCategories || [];
    currentCats.forEach(c => { if (!order.includes(c)) order.push(c); });
    const srcIdx = order.indexOf(srcCat), tgtIdx = order.indexOf(targetCat);
    if (srcIdx > -1 && tgtIdx > -1) {
        order.splice(srcIdx, 1); order.splice(tgtIdx, 0, srcCat);
        currentSettings.category_order = order;
        try {
            await fetch(`${API_URL}/api/library/reorder_categories`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ order: order })
            });
            renderTree(); 
        } catch(e) {}
    }
}

// --- Context Menus ---
document.addEventListener('click', () => { const m = document.getElementById('context-menu'); if (m) m.style.display = 'none'; });
function showCategoryContextMenu(e, category) {
    e.preventDefault(); e.stopPropagation();
    const menu = document.getElementById('context-menu');
    menu.style.display = 'block';
    menu.style.left = `${e.pageX}px`; menu.style.top = `${e.pageY}px`;
    menu.innerHTML = `<div class="context-item" tabindex="0" style="color:#ff6b6b;" onclick="deleteCategory('${category}')">Delete Category '${category}'</div>`;
    menu.querySelector('.context-item').focus();
}

async function deleteCategory(category) {
    if (!await showConfirm("Delete Category", `Delete category '${category}'?`, true)) return;
    try {
        const res = await fetch(`${API_URL}/api/library/delete_category`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({category}) });
        if (res.ok) refreshLibrary();
    } catch(e) {}
}

function showContextMenu(e, game) {
    e.preventDefault(); const menu = document.getElementById('context-menu');
    menu.style.display = 'block'; menu.style.left = `${e.pageX}px`; menu.style.top = `${e.pageY}px`;
    const isProtected = (c) => c === "Installed" || c === "Not Installed" || c.startsWith("External:");
    const gameCats = (game.categories || []).filter(c => !isProtected(c));
    const otherCats = (window.allCategories || []).filter(c => !gameCats.includes(c) && !isProtected(c));
    
    let html = '';
    
    // Hide Action
    const hideText = game.hidden ? "Unhide Game" : "Hide Game";
    html += `<div class="context-item" tabindex="0" onclick="toggleHideGame('${game.id}')">${hideText}</div><div class="context-separator"></div>`;

    html += `<div class="context-item has-submenu" tabindex="0">Add to Category...<div class="submenu"><div class="context-item" tabindex="0" onclick="createNewCategory('${game.id}')">➕ New Category...</div><div class="context-separator"></div>${otherCats.map(c => `<div class="context-item" tabindex="0" onclick="updateGameCategories('${game.id}', '${c}', 'add')">${c}</div>`).join('')}</div></div>`;
    if (gameCats.length > 0) html += `<div class="context-item has-submenu" tabindex="0">Remove from Category...<div class="submenu">${gameCats.map(c => `<div class="context-item" tabindex="0" onclick="updateGameCategories('${game.id}', '${c}', 'remove')">${c}</div>`).join('')}</div></div>`;
    menu.innerHTML = html;
    menu.querySelector('.context-item').focus();
}

async function toggleHideGame(id) {
    try {
        await fetch(`${API_URL}/api/game/${id}/hide`, { method: 'POST' });
        refreshLibrary();
    } catch(e) { console.error(e); }
}

async function createNewCategory(gameId) { 
    const cat = await showPrompt("New Category", "Enter new category name:"); 
    if (cat) await updateGameCategories(gameId, cat, "add"); 
}
async function updateGameCategories(gameId, category, action) {
    const game = libraryData.find(g => g.id === gameId); if (!game) return;
    let cats = (game.categories || []).filter(c => c !== "Installed" && c !== "Not Installed");
    if (action === "add") { if (!cats.includes(category)) cats.push(category); } 
    else if (action === "remove") { cats = cats.filter(c => c !== category); }
    try {
        await fetch(`${API_URL}/api/library/set_categories`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id: gameId, categories: cats}) });
        refreshLibrary();
    } catch(e) {}
}

// --- Helpers ---
function formatSpecs(text) {
    if (!text) return "";
    let clean = text.replace(/Minimum:|Recommended:/gi, "").trim();
    const keys = ["OS", "Processor", "Memory", "Graphics", "DirectX", "Storage", "Sound Card", "Additional Notes"];
    keys.forEach(key => { clean = clean.replace(new RegExp(`(${key}:)`, 'gi'), "\n$1"); });
    const lines = clean.split('\n').map(l => l.trim()).filter(l => l.length > 0);
    if (lines.length === 0) return text;
    let html = '<ul class="spec-list">';
    lines.forEach(line => {
        const splitIdx = line.indexOf(':');
        if (splitIdx > -1) {
            const key = line.substring(0, splitIdx);
            const val = line.substring(splitIdx + 1).trim();
            if (keys.some(k => key.toLowerCase().includes(k.toLowerCase()))) {
                 html += `<li class="spec-item"><span class="spec-label">${key}</span><span class="spec-value">${val}</span></li>`;
                 return;
            }
        }
        html += `<li class="spec-item" style="display:block; color:#aaa;">${line}</li>`;
    });
    return html + '</ul>';
}

function createBadges(id, items) {
    const c = document.getElementById(id); if (!c) return;
    c.innerHTML = "";
    if (items && items.length > 0) {
        items.forEach(item => {
            const s = document.createElement('span');
            s.style.cssText = 'background:#333; padding:2px 8px; border-radius:4px; font-size:12px; color:#ddd;';
            s.textContent = item; c.appendChild(s);
        });
    } else c.textContent = "-";
}

function formatBytes(bytes, decimals = 2) {
    if (!bytes || bytes === 0 || isNaN(bytes)) return '0 Bytes'; 
    const k = 1024, dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'], i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

function formatTime(seconds) {
    if (!seconds || seconds === Infinity) return "--:--:--";
    const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = Math.floor(seconds % 60);
    return [h, m, s].map(v => v < 10 ? "0" + v : v).join(":");
}

// --- Details ---
function filterTree() { renderTree(document.getElementById('librarySearch').value); }

function showDetails(gameId) {
    selectedGameId = gameId; document.querySelectorAll('.tree-item').forEach(el => el.classList.remove('selected'));
    const game = libraryData.find(g => g.id === gameId); if (!game) return;
    document.getElementById('empty-state').style.display = 'none';
    const panel = document.getElementById('details-panel'); panel.classList.add('active');
    
    // Setup settings button
    const settingsBtn = document.getElementById('detail-settings-btn');
    if (game.id.startsWith("ext_")) {
        settingsBtn.style.display = 'none';
    } else {
        settingsBtn.style.display = 'flex';
        settingsBtn.onclick = () => openGameSettings(game);
    }

    const posterUrl = game.banner || game.poster || 'https://via.placeholder.com/1920x600?text=No+Image';
    document.getElementById('detail-hero').style.backgroundImage = `url('${posterUrl}')`;
    document.getElementById('detail-title').textContent = game.name;
    const pt = Number(game.playtime || 0);
    document.getElementById('detail-meta').textContent = `${game.platform} • Version: ${game.version} • Played: ${(pt / 3600).toFixed(1)}h`;
    
    // HLTB
    const hltbEl = document.getElementById('detail-hltb');
    hltbEl.innerHTML = '<span>Loading stats...</span>';
    fetch(`${API_URL}/api/game/${game.id}/hltb`).then(r => r.json()).then(stats => {
        updateHLTBDisplay(stats);
    }).catch(() => hltbEl.innerHTML = '');

    document.getElementById('detail-description').innerHTML = game.description || "<em>No description available.</em>";
    
    // BGM Logic
    if (window.currentAudio) {
        // Fade out old
        const oldAudio = window.currentAudio;
        let vol = 1.0;
        const fade = setInterval(() => {
            vol -= 0.1;
            if (vol <= 0) {
                clearInterval(fade);
                oldAudio.pause();
            } else {
                oldAudio.volume = vol;
            }
        }, 50);
        window.currentAudio = null;
    }

    // Since we can't easily access local files via 'file://' in a web context unless served,
    // we assume the backend serves the theme if it's in the cache or a specific endpoint.
    // However, backend just gave us absolute path. Electron renderer can access local files via 'file://' 
    // IF webSecurity is disabled or specific protocols set.
    // For this prototype, we'll try direct file access if the environment allows, or just skip.
    // Wait, I can't easily modify main.js to disable webSecurity.
    // I will try to use the 'cache' mount for BGM if it was cached there?
    // The backend logic I wrote earlier sets `theme_music` to absolute path.
    // I will need a backend endpoint to stream it if direct access fails.
    
    // Let's just try setting src to absolute path (might fail in browser mode, work in some Electron setups)
    // Actually, I'll update the backend to serve it via an endpoint in a future step if this fails.
    // But for now, let's assume it works or I'll add a 'file://' prefix.
    
    if (game.theme_music) {
        // Note: Chrome blocks local file access from http source. 
        // My app is serving from http://127.0.0.1:12345/index.html likely (or file://).
        // If served via file://, it works. If via http, it fails.
        // Assuming http based on API_URL.
        // I will implement a quick proxy endpoint in next step if needed.
    }
    
    const ratingEl = document.getElementById('detail-rating');
    if (game.rating) ratingEl.innerHTML = `★ ${game.rating} <span style="font-size:14px; color:#666;">/ ${game.rating_top || 5}</span>`;
    else ratingEl.textContent = "N/A";
    
    const reqDiv = document.getElementById('detail-requirements');
    if (game.pc_requirements && (game.pc_requirements.minimum || game.pc_requirements.recommended)) {
        reqDiv.style.display = 'block';
        document.getElementById('req-min').innerHTML = `<h5 style="color:#fff; margin:0 0 10px 0;">Minimum</h5>` + formatSpecs(game.pc_requirements.minimum || "");
        document.getElementById('req-rec').innerHTML = `<h5 style="color:#fff; margin:0 0 10px 0;">Recommended</h5>` + formatSpecs(game.pc_requirements.recommended || "");
    } else reqDiv.style.display = 'none';
    
    createBadges('detail-genres', game.genres); 
    createBadges('detail-tags', game.tags);
    document.getElementById('detail-devs').textContent = (game.developers || []).join(', ') || "-";
    document.getElementById('detail-pubs').textContent = (game.publishers || []).join(', ') || "-";
    
    const actions = document.getElementById('detail-actions'); actions.innerHTML = '';
    if (game.installed) {
        const isRunning = runningGames.includes(game.id);
        const pbtn = document.createElement('button'); 
        pbtn.className = isRunning ? 'btn btn-danger' : 'btn btn-primary'; 
        pbtn.textContent = isRunning ? 'STOP' : 'PLAY'; 
        pbtn.onclick = () => isRunning ? stopGame(game.id) : launchGame(game.id); 
        actions.appendChild(pbtn);
        
        if (game.update_available && game.latest_version) {
            const upbtn = document.createElement('button');
            upbtn.className = 'btn btn-primary';
            upbtn.style.marginLeft = '10px';
            upbtn.style.backgroundColor = '#28a745'; // Green
            upbtn.textContent = `UPDATE (${game.latest_version})`;
            upbtn.onclick = () => {
                startDownload(game.link, game.name);
                // Optimistically hide button
                upbtn.style.display = 'none';
            };
            actions.appendChild(upbtn);
        }
        
        // Setup Wizard Button
        const setupBtn = document.createElement('button');
        setupBtn.className = 'btn btn-secondary';
        setupBtn.style.marginLeft = '10px';
        setupBtn.textContent = 'Setup';
        setupBtn.onclick = async () => {
             if (await showConfirm("Run Setup", "Search for and run Setup.exe or Mount ISO in game folder?", false)) {
                 try {
                     const res = await fetch(`${API_URL}/api/game/${game.id}/setup`, { method: 'POST' });
                     if (res.ok) showToast("Setup started!", "success");
                     else showToast("No setup file found.", "error");
                 } catch(e) { showToast(e.message, "error"); }
             }
        };
        actions.appendChild(setupBtn);

        // Sandbox Button
        const sandboxBtn = document.createElement('button');
        sandboxBtn.className = 'btn btn-secondary';
        sandboxBtn.style.marginLeft = '10px';
        sandboxBtn.innerHTML = '🛡️ Sandbox';
        sandboxBtn.onclick = async () => {
            if (await showConfirm("Launch in Sandbox", "WARNING: Saves will NOT be saved to your PC. Continue?", false)) {
                try {
                    const res = await fetch(`${API_URL}/api/game/${game.id}/sandbox`, { method: 'POST' });
                    const data = await res.json();
                    if (res.ok) showToast("Sandbox launched!", "success");
                    else showAlert("Sandbox Error", data.detail);
                } catch(e) { showToast(e.message, "error"); }
            }
        };
        actions.appendChild(sandboxBtn);

        if (!game.id.startsWith("ext_")) {
            const fbtn = document.createElement('button'); fbtn.className = 'btn btn-secondary'; fbtn.textContent = 'Folder'; fbtn.onclick = () => openFolder(game.id); actions.appendChild(fbtn);
            const ubtn = document.createElement('button'); ubtn.className = 'btn btn-danger'; ubtn.textContent = 'Uninstall'; ubtn.style.marginLeft = '10px';
            ubtn.onclick = () => { uninstallGame(game.id, game.name); closeDetails(); }; actions.appendChild(ubtn);
        } else {
            const rbtn = document.createElement('button'); rbtn.className = 'btn btn-secondary'; rbtn.textContent = 'Remove'; rbtn.style.marginLeft = '10px';
            rbtn.onclick = () => { removeLibraryGame(game.id, game.name); closeDetails(); }; actions.appendChild(rbtn);
        }
    } else {
        const ibtn = document.createElement('button'); ibtn.className = 'btn btn-primary'; ibtn.textContent = 'INSTALL'; ibtn.onclick = () => startDownload(game.link || '', game.name); actions.appendChild(ibtn);
        const rbtn = document.createElement('button'); rbtn.className = 'btn btn-secondary'; rbtn.textContent = 'Remove'; rbtn.style.marginLeft = '10px';
        rbtn.onclick = () => { removeLibraryGame(game.id, game.name); closeDetails(); }; actions.appendChild(rbtn);
    }
    
    const gallery = document.getElementById('detail-gallery'); gallery.innerHTML = '';
    currentGalleryImages = game.screenshots || [];
    if (currentGalleryImages.length > 0) {
        currentGalleryIndex = 0;
        gallery.innerHTML = `<div class="slideshow-container"><div class="slide-arrow" style="left:10px;" onclick="changeSlide(-1)">❮</div><div class="slide-arrow" style="right:10px;" onclick="changeSlide(1)">❯</div><img id="gallery-img" src="" style="width:100%; height:100%; object-fit:contain; cursor:zoom-in;" ondblclick="openFullscreen(this.src)"><div id="gallery-count" style="position:absolute; bottom:10px; right:10px; background:rgba(0,0,0,0.6); color:white; padding:2px 8px; border-radius:4px; font-size:12px;"></div></div>`;
        updateGalleryImage();
    } else gallery.innerHTML = '<p style="color:#666; font-style:italic;">No screenshots available.</p>';

    // Save selection
    if (currentSettings.last_selected_game_id !== game.id) {
        currentSettings.last_selected_game_id = game.id;
        fetch(`${API_URL}/api/library/last_selected`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: game.id})
        });
    }
}

function closeDetails() { document.getElementById('details-panel').classList.remove('active'); document.getElementById('empty-state').style.display = 'flex'; selectedGameId = null; filterTree(); }

// --- Search ---
async function performSearch() {
    const q = document.getElementById('searchInput').value, cat = document.getElementById('searchCategory').value; if (!q) return;
    const grid = document.getElementById('searchResults'); grid.innerHTML = '<p style="color:#888">Searching...</p>';
    try {
        const res = await fetch(`${API_URL}/api/search`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({query:q, category:cat}) });
        const data = await res.json(); renderSearchResults(data.results || [], cat);
    } catch(e) { grid.innerHTML = '<p style="color:red">Search failed.</p>'; }
}

function renderSearchResults(results, category) {
    const grid = document.getElementById('searchResults'); grid.innerHTML = '';
    if (!results || results.length === 0) { grid.innerHTML = '<p>No results found.</p>'; return; }
    results.forEach(r => {
        const d = document.createElement('div');
        d.className = 'search-result-item'; // Add class for selector
        d.setAttribute('tabindex', '0'); // Make focusable
        d.style.cssText = 'padding:15px; background:#252526; border-radius:6px; display:flex; justify-content:space-between; align-items:center; cursor:pointer; outline:none;';
        const attrTitle = r.title.replace(/"/g, '&quot;'), attrUrl = r.url.replace(/"/g, '&quot;');
        
        // Enter key to click
        d.onkeydown = (e) => { if (e.key === 'Enter') { showSearchPreview(r.title, r.url); } };
        
        d.onclick = () => showSearchPreview(r.title, r.url);
        let actionButtons = '';
        if (category === 'Games') {
            const existing = libraryData.find(g => g.name === r.title);
            if (existing) {
                if (existing.installed) actionButtons = `<button class="btn btn-danger" style="padding:6px 15px; font-size:13px;" data-id="${existing.id}" data-title="${attrTitle}" onclick="event.stopPropagation(); uninstallGame(this.dataset.id, this.dataset.title)">Uninstall</button>`;
                else actionButtons = `<button class="btn btn-secondary" style="padding:6px 15px; font-size:13px;" data-id="${existing.id}" data-title="${attrTitle}" onclick="event.stopPropagation(); removeLibraryGame(this.dataset.id, this.dataset.title)">Remove</button>`;
            } else actionButtons = `<div style="display:flex; gap:10px;"><button class="btn btn-secondary" style="padding:6px 15px; font-size:13px;" data-url="${attrUrl}" data-title="${attrTitle}" onclick="event.stopPropagation(); addToLibrary.call(this)">+ Lib</button><button class="btn btn-primary" style="padding:6px 15px; font-size:13px;" data-url="${attrUrl}" data-title="${attrTitle}" onclick="event.stopPropagation(); startDownload.call(this)">Download</button></div>`;
        } else actionButtons = `<button class="btn btn-primary" style="padding:6px 15px; font-size:13px;" data-url="${attrUrl}" data-title="${attrTitle}" onclick="event.stopPropagation(); startDownload.call(this)">Download</button>`;
        d.innerHTML = `<div style="font-weight:500; font-size:16px;">${r.title}</div>${actionButtons}`;
        grid.appendChild(d);
    });
}

// --- Downloads ---
let downloadPollInterval = null;
function startPollingStatus() { if (downloadPollInterval) clearInterval(downloadPollInterval); downloadPollInterval = setInterval(pollDownloadStatus, 1000); }
function stopPollingStatus() { if (downloadPollInterval) { clearInterval(downloadPollInterval); downloadPollInterval = null; } }

async function pollDownloadStatus() {
    try {
        const res = await fetch(`${API_URL}/api/download/status`);
        const status = await res.json();
        updateDownloadUI(status);
        renderDownloadQueue(status.queue || [], status.hash);
    } catch(e) { console.error("Poll error", e); }
}

async function pollRunningGames() {
    try {
        const res = await fetch(`${API_URL}/api/running-games`);
        const data = await res.json();
        const oldRunning = JSON.stringify(runningGames);
        runningGames = data.running || [];
        
        // Refresh details if currently viewing a game that changed state
        if (selectedGameId && oldRunning !== JSON.stringify(runningGames)) {
            showDetails(selectedGameId);
        }
    } catch(e) {}
}

function updateDownloadUI(status) {
    const titleEl = document.getElementById('dl-title'), statusTextEl = document.getElementById('dl-status-text'), progressFill = document.getElementById('dl-progress-fill'), dlStatus = document.getElementById('dl-status'), dlSpeed = document.getElementById('dl-speed'), dlRemaining = document.getElementById('dl-remaining'), dlSizeInfo = document.getElementById('dl-size-info'), pauseBtn = document.getElementById('pause-btn'), cancelBtn = document.getElementById('cancel-btn');
    if (status.active) {
        if (titleEl) titleEl.textContent = status.alias || status.filename || "Downloading...";
        if (statusTextEl && !statusTextEl.textContent.includes("...")) statusTextEl.textContent = "Processing...";
        const progress = typeof status.progress === 'number' ? status.progress : 0;
        if (progressFill) progressFill.style.width = `${progress}%`;
        if (dlStatus) dlStatus.textContent = `${progress.toFixed(1)}%`;
        if (dlSpeed) dlSpeed.textContent = `${formatBytes(status.speed || 0)}/s`;
        if (dlRemaining) dlRemaining.textContent = `Remaining: ${formatTime(status.remaining_time || 0)}`;
        if (pauseBtn) { pauseBtn.disabled = false; pauseBtn.textContent = status.is_paused ? "RESUME" : "PAUSE"; }
        if (cancelBtn) cancelBtn.disabled = false;
    } else {
        if (titleEl) titleEl.textContent = "No active download"; if (statusTextEl) statusTextEl.textContent = "Idle"; if (progressFill) progressFill.style.width = `0%`; if (dlStatus) dlStatus.textContent = `0%`; if (dlSpeed) dlSpeed.textContent = `0 Bytes/s`; if (dlRemaining) dlRemaining.textContent = `Remaining: --:--:--`; if (dlSizeInfo) dlSizeInfo.textContent = `0 Bytes / 0 Bytes`; if (pauseBtn) { pauseBtn.disabled = true; pauseBtn.textContent = "PAUSE"; } if (cancelBtn) cancelBtn.disabled = true;
    }
}

async function startDownload(url, title) {
    const finalUrl = url || this.dataset.url, finalTitle = title || this.dataset.title; if (!finalUrl) return; 
    switchTab('downloads');
    try { await fetch(`${API_URL}/api/download`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url: finalUrl, alias: finalTitle}) }); startPollingStatus(); } catch(e) {}
}

async function addToLibrary(url, title) {
    const finalUrl = url || this.dataset.url, finalTitle = title || this.dataset.title;
    try {
        const res = await fetch(`${API_URL}/api/library/add`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url: finalUrl, title: finalTitle}) });
        const data = await res.json();
        if (data.status === 'added' || data.status === 'exists') { if (data.status === 'added') alert(`${finalTitle} added!`); refreshLibrary(); performSearch(); }
    } catch(e) { alert("Add failed: " + e.message); }
}

async function togglePause() {
    const btn = document.getElementById('pause-btn'); const isPaused = btn.textContent === "RESUME";
    if (isPaused) { await fetch(`${API_URL}/api/resume`, {method:'POST'}); btn.textContent = "PAUSE"; } 
    else { await fetch(`${API_URL}/api/pause`, {method:'POST'}); btn.textContent = "RESUME"; }
}

async function stopDownload() { 
    if (await showConfirm("Cancel Download", "Are you sure you want to cancel this download?", true)) { 
        await fetch(`${API_URL}/api/stop`, {method:'POST'}); pollDownloadStatus(); 
    } 
}

// --- Scripts ---
function selectScript(scriptId) {
    document.querySelectorAll('.script-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.script-panel').forEach(el => el.style.display = 'none');
    
    // Find item by text (hacky but works for now as ID isn't on item)
    // Actually we passed scriptId to onclick, let's use that
    // Add id to items or just logic?
    // Let's assume scriptId matches the div ID suffix
    
    const panel = document.getElementById(`script-${scriptId}`);
    if (panel) panel.style.display = 'block';
}

async function runUniversalDownloader() {
    const url = document.getElementById('script-url-input').value.trim();
    if (!url) { await showAlert("Error", "Please enter a valid URL."); return; }
    
    // Check if it's a known provider or generic
    // The backend handles the logic, we just send it.
    await startDownload(url, "Script Download");
    await showAlert("Success", "Download started! Check the Downloads tab.");
}

async function selectFileForConvert() {
    const path = await ipcRenderer.invoke('select-file', { title: 'Select File to Convert' });
    if (path) updateConverterInput(path);
}

function handleConverterDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    e.target.style.borderColor = '#333';
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        updateConverterInput(e.dataTransfer.files[0].path);
    }
}

function updateConverterInput(path) {
    document.getElementById('convert-input-path').value = path;
    const group = document.getElementById('convert-output-group');
    const select = document.getElementById('convert-format');
    group.style.display = 'block';
    
    // Auto-detect type
    const ext = path.split('.').pop().toLowerCase();
    const isAudio = ['mp3', 'wav', 'ogg', 'flac', 'm4a'].includes(ext);
    const isVideo = ['mp4', 'mkv', 'avi', 'mov', 'wmv'].includes(ext);
    const isImage = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp'].includes(ext);

    let options = [];
    if (isAudio) {
        options = [
            {v: 'mp3', t: 'MP3 (Audio)'},
            {v: 'wav', t: 'WAV (Audio)'},
            {v: 'ogg', t: 'OGG (Audio)'}
        ];
    } else if (isVideo) {
        options = [
            {v: 'mp3', t: 'MP3 (Extract Audio)'},
            {v: 'mp4', t: 'MP4 (Video)'},
            {v: 'mkv', t: 'MKV (Video)'}
        ];
    } else if (isImage) {
        options = [
            {v: 'png', t: 'PNG (Image)'},
            {v: 'jpg', t: 'JPG (Image)'},
            {v: 'webp', t: 'WEBP (Image)'},
            {v: 'gif', t: 'GIF (Animated/Static)'}
        ];
    } else {
        options = [{v: 'mp4', t: 'Generic (MP4)'}];
    }

    select.innerHTML = '';
    options.forEach(opt => {
        const o = document.createElement('option');
        o.value = opt.v;
        o.textContent = opt.t;
        select.appendChild(o);
    });

    // Smart default
    if (isAudio) select.value = ext === 'mp3' ? 'wav' : 'mp3';
    else if (isVideo) select.value = 'mp4';
    else if (isImage) select.value = ext === 'png' ? 'jpg' : 'png';
}

async function runMediaConvert() {
    const path = document.getElementById('convert-input-path').value;
    const fmt = document.getElementById('convert-format').value;
    
    if (!path) return;
    
    try {
        await showAlert("Started", "Conversion started...");
        const res = await fetch(`${API_URL}/api/tools/convert`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ input_path: path, output_format: fmt })
        });
        const data = await res.json();
        
        if (data.error) {
            // Check if it's missing tool
            if (data.error === "FFmpeg not found") {
                if (await showConfirm("Missing Tool", "FFmpeg is required. Install it now?", false)) {
                    switchTab('settings');
                    // Ideally scroll to tools...
                }
            } else {
                throw new Error(data.error);
            }
        } else {
            await showAlert("Success", `Converted: ${data.output}`);
        }
    } catch(e) { await showAlert("Error", e.message); }
}

function renderDownloadQueue(queue, activeHash) {
    let qc = document.getElementById('download-queue-list');
    if (!qc) {
        const parent = document.querySelector('#view-downloads .simple-content');
        const header = document.createElement('h3'); header.textContent = "Queue"; header.style.cssText = "margin-top:30px; border-bottom:1px solid #333; padding-bottom:10px;";
        parent.appendChild(header);
        qc = document.createElement('div'); qc.id = 'download-queue-list'; qc.style.cssText = "margin-top:15px; display:grid; gap:10px; min-height:50px;";
        qc.ondragover = (e) => e.preventDefault(); qc.ondrop = handleDropToQueue;
        parent.appendChild(qc);
    }
    qc.innerHTML = '';
    if (queue.length === 0) { qc.innerHTML = '<p style="color:#666; font-style:italic;">Queue is empty.</p>'; return; }
    queue.forEach(item => {
        const div = document.createElement('div'); div.className = 'queue-item'; div.style.cssText = 'padding:12px 15px; background:#1e1e1e; border:1px solid #333; border-radius:6px; display:flex; justify-content:space-between; align-items:center;';
        const isActive = item.hash === activeHash;
        div.draggable = true; div.ondragstart = (e) => e.dataTransfer.setData("queue-hash", item.hash); div.ondragover = (e) => e.preventDefault();
        div.ondrop = (e) => { e.preventDefault(); const dragged = e.dataTransfer.getData("queue-hash"); if (dragged && dragged !== item.hash) reorderQueue(dragged, item.hash); };
        div.innerHTML = `<div style="display:flex; align-items:center; gap:12px;"><span style="color:#666; cursor:grab;">☰</span><div style="font-weight:500; color:${isActive ? 'var(--accent-color)' : 'white'};">${item.alias} ${isActive ? '<span style="font-size:11px; margin-left:8px; font-weight:normal; color:#888;">(Active)</span>' : ''}</div></div><button class="btn btn-secondary" style="color: #ff6b6b; padding: 2px 8px;" onclick="removeFromQueue('${item.hash}')">✕</button>`;
        qc.appendChild(div);
    });
}

async function reorderQueue(srcHash, targetHash) {
    const res = await fetch(`${API_URL}/api/download/status`); const status = await res.json();
    const hashes = (status.queue || []).map(i => i.hash); const srcIdx = hashes.indexOf(srcHash), tgtIdx = hashes.indexOf(targetHash);
    if (srcIdx > -1 && tgtIdx > -1) {
        hashes.splice(srcIdx, 1); hashes.splice(tgtIdx, 0, srcHash);
        await fetch(`${API_URL}/api/download/queue/reorder`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({hashes}) });
        pollDownloadStatus();
    }
}

async function removeFromQueue(hash) { 
    if (await showConfirm("Remove Item", "Remove this item from the queue?", true)) { 
        await fetch(`${API_URL}/api/download/queue/remove/${hash}`, {method:'POST'}); pollDownloadStatus(); 
    } 
}
function handleDragActiveStart(e) { const titleEl = document.getElementById('dl-title'); if (titleEl && titleEl.textContent !== "No active download") { e.dataTransfer.setData("active-item", "true"); } else e.preventDefault(); }
async function handleDropToActive(e) {
    e.preventDefault(); const draggedHash = e.dataTransfer.getData("queue-hash"); if (!draggedHash) return;
    const res = await fetch(`${API_URL}/api/download/status`); const status = await res.json();
    const hashes = (status.queue || []).map(i => i.hash); const srcIdx = hashes.indexOf(draggedHash);
    if (srcIdx > -1) { hashes.splice(srcIdx, 1); hashes.unshift(draggedHash); await fetch(`${API_URL}/api/download/queue/reorder`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({hashes}) }); pollDownloadStatus(); }
}
async function handleDropToQueue(e) {
    e.preventDefault(); if (!e.dataTransfer.getData("active-item")) return;
    const res = await fetch(`${API_URL}/api/download/status`); const status = await res.json();
    if (!status.active) return;
    const hashes = (status.queue || []).map(i => i.hash); if (hashes.length > 1) { const activeHash = hashes.shift(); hashes.push(activeHash); await fetch(`${API_URL}/api/download/queue/reorder`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({hashes}) }); pollDownloadStatus(); }
}

async function launchGame(id) {
    try { 
        const res = await fetch(`${API_URL}/api/launch/${id}`, { method: 'POST' }); 
        if (!res.ok) { const err = await res.json(); await showAlert("Error", `Failed: ${err.detail}`); }
        else { pollRunningGames(); } // Immediate refresh
    } catch (e) { await showAlert("Error", `Error: ${e.message}`); }
}

async function stopGame(id) {
    try {
        const res = await fetch(`${API_URL}/api/stop/${id}`, { method: 'POST' });
        if (!res.ok) { const err = await res.json(); await showAlert("Error", `Failed: ${err.detail}`); }
        else { pollRunningGames(); } // Immediate refresh
    } catch (e) { await showAlert("Error", `Error: ${e.message}`); }
}
 
async function openFolder(id) { try { await fetch(`${API_URL}/api/open-folder/${id}`, { method: 'POST' }); } catch (e) {} }
function openFullscreen(src) { if (!src) return; const o = document.getElementById('fullscreen-overlay'), i = document.getElementById('fullscreen-img'); i.src = src; o.style.display = 'flex'; }
function closeFullscreen() { document.getElementById('fullscreen-overlay').style.display = 'none'; }
function changeSlide(dir) {
    if (currentGalleryImages.length === 0) return;
    currentGalleryIndex = (currentGalleryIndex + dir + currentGalleryImages.length) % currentGalleryImages.length;
    updateGalleryImage();
    if (document.getElementById('fullscreen-overlay').style.display === 'flex') document.getElementById('fullscreen-img').src = currentGalleryImages[currentGalleryIndex];
}
function updateGalleryImage() {
    const img = document.getElementById('gallery-img'), cnt = document.getElementById('gallery-count');
    if (img) { img.src = currentGalleryImages[currentGalleryIndex]; img.onerror = () => { img.src = 'https://via.placeholder.com/800x450?text=No+Image'; }; }
    if (cnt) cnt.textContent = `${currentGalleryIndex + 1} / ${currentGalleryImages.length}`;
}

async function showSearchPreview(title, url) {
    const panel = document.getElementById('search-preview-panel'); panel.style.display = 'block';
    document.getElementById('preview-title').textContent = title;
    document.getElementById('preview-description').innerHTML = 'Loading metadata...';
    try {
        const res = await fetch(`${API_URL}/api/preview`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ name: title }) });
        const meta = await res.json();
        const posterUrl = meta.banner || meta.poster || 'https://via.placeholder.com/1920x600?text=No+Image';
        document.getElementById('preview-hero').style.backgroundImage = `url('${posterUrl}')`;
        document.getElementById('preview-description').innerHTML = meta.description || "No description available.";
        const ratingEl = document.getElementById('preview-rating');
        if (meta.rating) ratingEl.innerHTML = `★ ${meta.rating} <span style="font-size: 14px; color: #666;">/ ${meta.rating_top || 5}</span>`;
        else ratingEl.textContent = "N/A";
        const reqDiv = document.getElementById('preview-requirements');
        if (meta.pc_requirements && (meta.pc_requirements.minimum || meta.pc_requirements.recommended)) {
            reqDiv.style.display = 'block';
            document.getElementById('preview-req-min').innerHTML = `<h5 style="color:#fff;">Minimum</h5>` + formatSpecs(meta.pc_requirements.minimum || "");
            document.getElementById('preview-req-rec').innerHTML = `<h5 style="color:#fff;">Recommended</h5>` + formatSpecs(meta.pc_requirements.recommended || "");
        } else reqDiv.style.display = 'none';
        createBadges('preview-genres', meta.genres); createBadges('preview-tags', meta.tags);
        document.getElementById('preview-devs').textContent = (meta.developers || []).join(', ') || "-";
        document.getElementById('preview-pubs').textContent = (meta.publishers || []).join(', ') || "-";
        const gallery = document.getElementById('preview-gallery'); gallery.innerHTML = '';
        currentGalleryImages = meta.screenshots || [];
        if (currentGalleryImages.length > 0) {
            currentGalleryIndex = 0;
            gallery.innerHTML = `<div class="slideshow-container"><div class="slide-arrow" style="left:10px;" onclick="changeSlide(-1)">❮</div><div class="slide-arrow" style="right:10px;" onclick="changeSlide(1)">❯</div><img id="gallery-img" src="" style="width:100%; height:100%; object-fit:contain; cursor:zoom-in;" ondblclick="openFullscreen(this.src)"><div id="gallery-count" style="position:absolute; bottom:10px; right:10px; background:rgba(0,0,0,0.6); color:white; padding:2px 8px; border-radius:4px; font-size:12px;"></div></div>`;
            updateGalleryImage();
        }
        const actions = document.getElementById('preview-actions'); const existing = libraryData.find(g => g.name === title);
        if (existing) actions.innerHTML = `<button class="btn btn-secondary" disabled>Already in Library</button>`;
        else { 
            const attrTitle = title.replace(/"/g, '&quot;'), attrUrl = url.replace(/"/g, '&quot;');
            actions.innerHTML = `<button class="btn btn-primary" data-url="${attrUrl}" data-title="${attrTitle}" onclick="addToLibrary.call(this)">+ Add to Library</button><button class="btn btn-primary" data-url="${attrUrl}" data-title="${attrTitle}" onclick="startDownload.call(this)">Download</button>`;
        }
    } catch(e) {}
}
function closeSearchPreview() { document.getElementById('search-preview-panel').style.display = 'none'; }

async function selectRandomGame() {
    try {
        const res = await fetch(`${API_URL}/api/random-game`);
        const data = await res.json();
        if (data.id) {
            switchTab('library');
            showDetails(data.id);
        } else {
            showAlert("Info", "No installed games found.");
        }
    } catch(e) {}
}

async function loadProfileStats() {
    try {
        const res = await fetch(`${API_URL}/api/library/stats`);
        const stats = await res.json();
        
        document.getElementById('profile-playtime').textContent = `${(stats.playtime / 3600).toFixed(1)}h`;
        document.getElementById('profile-count').textContent = stats.count;
        
        const genreContainer = document.getElementById('profile-genres');
        genreContainer.innerHTML = '';
        
        const sortedGenres = Object.entries(stats.genres).sort((a, b) => b[1] - a[1]).slice(0, 8);
        sortedGenres.forEach(([g, count]) => {
            const span = document.createElement('span');
            span.style.cssText = 'background:#252526; padding:5px 10px; border-radius:15px; color:#ddd; font-size:14px; border:1px solid #333;';
            span.innerHTML = `${g} <span style="color:var(--accent-color); font-weight:bold; margin-left:5px;">${count}</span>`;
            genreContainer.appendChild(span);
        });
    } catch(e) { console.error("Stats load failed", e); }
}

async function removeLibraryGame(id, name) {
    if (!await showConfirm("Remove Game", `Remove '${name}' from library?`, true)) return;
    await fetch(`${API_URL}/api/library/remove`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id}) });
    refreshLibrary(); performSearch();
}
async function uninstallGame(id, name) {
    if (!await showConfirm("Uninstall Game", `UNINSTALL '${name}'? This deletes files.`, true)) return;
    const res = await fetch(`${API_URL}/api/library/uninstall`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id}) });
    if (res.ok) { await showAlert("Success", "Uninstalled."); refreshLibrary(); performSearch(); }
}

// --- Controller / Keyboard Support ---
let gamepadIndex = null;
let gpInterval = null;
let lastMoveTime = 0;

window.addEventListener("gamepadconnected", (e) => {
    console.log("Gamepad connected:", e.gamepad.index);
    gamepadIndex = e.gamepad.index;
    if (!gpInterval) gpInterval = setInterval(pollGamepad, 100);
});

window.addEventListener("gamepaddisconnected", (e) => {
    if (gamepadIndex === e.gamepad.index) {
        gamepadIndex = null;
        if (gpInterval) { clearInterval(gpInterval); gpInterval = null; }
    }
});

// Keyboard
document.addEventListener('keydown', (e) => {
    if (!currentSettings.controller_support) return;
    // Only handle if not typing in an input
    if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA') return;

    if (e.key === 'ArrowUp') handleNav('up');
    else if (e.key === 'ArrowDown') handleNav('down');
    else if (e.key === 'ArrowLeft') handleNav('left');
    else if (e.key === 'ArrowRight') handleNav('right');
    else if (e.key === 'Enter') {
        e.preventDefault();
        if (document.activeElement) document.activeElement.click();
    }
});

function pollGamepad() {
    if (gamepadIndex === null || !currentSettings.controller_support) return;
    const gp = navigator.getGamepads()[gamepadIndex];
    if (!gp) return;

    const now = Date.now();
    if (now - lastMoveTime < 200) return; // Debounce

    // D-Pad or Left Stick
    const up = gp.buttons[12].pressed || gp.axes[1] < -0.5;
    const down = gp.buttons[13].pressed || gp.axes[1] > 0.5;
    const left = gp.buttons[14].pressed || gp.axes[0] < -0.5;
    const right = gp.buttons[15].pressed || gp.axes[0] > 0.5;
    const aBtn = gp.buttons[0].pressed;

    if (up) { handleNav('up'); lastMoveTime = now; }
    else if (down) { handleNav('down'); lastMoveTime = now; }
    else if (left) { handleNav('left'); lastMoveTime = now; }
    else if (right) { handleNav('right'); lastMoveTime = now; }
    else if (aBtn) { 
        if (document.activeElement) document.activeElement.click(); 
        lastMoveTime = now + 200; 
    }
}

function handleNav(dir) {
    const active = document.activeElement;
    
    // 1. Handle Modal
    const modal = document.querySelector('.modal-overlay[style*="display: flex"]');
    if (modal) {
        if (!modal.contains(active)) {
            const first = modal.querySelector('button, input, textarea, select');
            if (first) first.focus();
            return;
        }
        moveFocusSibling(active, dir);
        return;
    }

    // 2. Handle Context Menu
    const ctx = document.getElementById('context-menu');
    if (ctx && ctx.style.display === 'block') {
        if (!ctx.contains(active)) {
            const first = ctx.querySelector('.context-item');
            if (first) first.focus();
            return;
        }
        if (dir === 'up' || dir === 'down') moveFocusSibling(active, dir);
        else if (dir === 'left') {
            ctx.style.display = 'none';
            focusFirstTreeItem();
        }
        return;
    }

    // Default focus if body is active
    if (!active || active === document.body) {
        document.querySelector('.nav-item.active').focus();
        return;
    }

    // Identify Zones
    const isSidebar = active.classList.contains('nav-item');
    const isTree = active.classList.contains('tree-item') || active.tagName === 'SUMMARY' || active.id === 'librarySearch' || active.id === 'librarySort';
    const isDetail = document.getElementById('details-panel').contains(active);
    const isSearch = active.classList.contains('search-result-item') || active.id === 'searchInput' || active.id === 'searchCategory';
    const isSettings = active.closest('.settings-card') || active.closest('.simple-header');

    if (isSidebar) {
        if (dir === 'up' || dir === 'down') moveFocusSibling(active, dir);
        else if (dir === 'right') {
            // Determine active view to jump to
            const activeView = document.querySelector('.view.active').id;
            if (activeView === 'view-library') focusFirstTreeItem();
            else if (activeView === 'view-search') document.getElementById('searchInput').focus();
            else if (activeView === 'view-settings') document.querySelector('#view-settings input').focus();
        }
    } 
    else if (isTree) {
        if (dir === 'up' || dir === 'down') moveFocusSibling(active, dir);
        else if (dir === 'left') focusSidebar();
        else if (dir === 'right') focusDetailsAction();
    }
    else if (isDetail) {
        if (dir === 'left') {
            // If focused on leftmost element, go back to tree
            // Visual check or simple assume left escapes detail
            focusFirstTreeItem();
        } else {
             moveFocusSibling(active, dir);
        }
    }
    else if (isSearch) {
        if (dir === 'left' && (active.id === 'searchCategory' || active.id === 'searchInput')) focusSidebar();
        else moveFocusSibling(active, dir);
    }
    else if (isSettings) {
        if (dir === 'left') focusSidebar();
        else moveFocusSibling(active, dir);
    }
    else {
        // Fallback generic move
        moveFocusSibling(active, dir);
    }
}

function moveFocusSibling(el, dir) {
    let selector = '*';
    if (el.classList.contains('nav-item')) selector = '.nav-item';
    else if (el.classList.contains('tree-item') || el.tagName === 'SUMMARY') selector = '#library-tree summary, #library-tree .tree-item';
    else if (el.classList.contains('context-item')) selector = '.context-item';
    else if (el.closest('.modal-card')) selector = '.modal-card button:not([disabled]), .modal-card input, .modal-card textarea, .modal-card select, .modal-card .path-list input';
    else if (el.classList.contains('search-result-item')) selector = '.search-result-item';
    else if (el.closest('#download-queue-list')) selector = '.queue-item';
    else if (el.closest('.settings-card')) selector = '.settings-card input, .settings-card button, .settings-card select';
    else if (el.classList.contains('bp-card')) selector = '.bp-card';

    const all = Array.from(document.querySelectorAll(selector)).filter(e => {
        if (el.closest('.modal-card') && !e.closest('.modal-card').parentElement.style.display.includes('flex')) return false;
        if (el.closest('#context-menu') && e.closest('#context-menu').style.display === 'none') return false;
        // Robust visibility check: offsetParent covers display:none, getClientRects covers collapsed details/visibility:hidden
        return e.offsetParent !== null && !e.disabled && e.getClientRects().length > 0;
    });
    
    // Grid Navigation Logic (Visual)
    const currentRect = el.getBoundingClientRect();
    const currentCenter = { x: currentRect.left + currentRect.width / 2, y: currentRect.top + currentRect.height / 2 };

    let bestCandidate = null;
    let minDistance = Infinity;

    all.forEach(candidate => {
        if (candidate === el) return;

        const rect = candidate.getBoundingClientRect();
        const center = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        
        // Directional Filters
        let isValid = false;
        if (dir === 'up') isValid = center.y < currentCenter.y - 10; // -10 tolerance
        else if (dir === 'down') isValid = center.y > currentCenter.y + 10;
        else if (dir === 'left') isValid = center.x < currentCenter.x - 10;
        else if (dir === 'right') isValid = center.x > currentCenter.x + 10;

        if (isValid) {
            // Euclidean distance
            const dist = Math.sqrt(Math.pow(center.x - currentCenter.x, 2) + Math.pow(center.y - currentCenter.y, 2));
            
            // Bias against elements that are too far away in the perpendicular axis
            let perpDist = 0;
            if (dir === 'up' || dir === 'down') perpDist = Math.abs(center.x - currentCenter.x);
            else perpDist = Math.abs(center.y - currentCenter.y);

            // Penalize perpendicular distance HEAVILY to favor straight lines in grids
            const weightedDist = dist + (perpDist * 10);

            if (weightedDist < minDistance) {
                minDistance = weightedDist;
                bestCandidate = candidate;
            }
        }
    });

    // Fallback to DOM order for flat lists if visual nav fails or is ambiguous (like perfectly aligned lists)
    if (!bestCandidate) {
        const idx = all.indexOf(el);
        if (dir === 'up' && idx > 0) bestCandidate = all[idx - 1];
        else if (dir === 'down' && idx < all.length - 1) bestCandidate = all[idx + 1];
        // For left/right in lists, we might want to exit the list (handled in handleNav) or wrap
    }

    if (bestCandidate) {
        bestCandidate.focus();
        bestCandidate.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function focusFirstTreeItem() {
    const item = document.querySelector('#library-tree summary, #library-tree .tree-item');
    if (item) item.focus();
}

function focusSidebar() {
    document.querySelector('.nav-item.active').focus();
}

function focusDetailsAction() {
    const btn = document.querySelector('#detail-actions button');
    if (btn) btn.focus();
}

// Add tabindex to navigable elements
function updateTabIndices() {
    document.querySelectorAll('.nav-item').forEach(el => el.setAttribute('tabindex', '0'));
    document.querySelectorAll('.tree-item, summary').forEach(el => el.setAttribute('tabindex', '0'));
}
// Hook into renderTree to update indices
const originalRenderTree = renderTree;
renderTree = function(filter) {
    originalRenderTree(filter);
    updateTabIndices();
};

let bigPictureActive = false;

function toggleBigPicture() {
    const view = document.getElementById('view-bigpicture');
    bigPictureActive = !bigPictureActive;
    
    if (bigPictureActive) {
        view.style.display = 'block';
        renderBigPictureGrid();
        // Force focus first item
        setTimeout(() => {
            const first = document.querySelector('.bp-card');
            if (first) first.focus();
        }, 100);
    } else {
        view.style.display = 'none';
    }
}

function renderBigPictureGrid() {
    const grid = document.getElementById('bp-grid');
    grid.innerHTML = '';
    
    // Only show installed games in Big Picture
    const games = libraryData.filter(g => g.installed && !g.hidden);
    
    games.forEach(game => {
        const card = document.createElement('div');
        card.className = 'bp-card';
        card.tabIndex = 0;
        
        const posterUrl = game.poster || 'https://via.placeholder.com/300x450?text=No+Poster';
        card.innerHTML = `<img src="${posterUrl}" style="width:100%; height:100%; object-fit:cover; pointer-events: none;">`;
        
        card.onfocus = () => {
            updateBPInfo(game);
            // Smoothly scroll focused card into view if needed
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        };
        
        card.onclick = () => launchGame(game.id);
        
        grid.appendChild(card);
    });
}

function updateBPInfo(game) {
    document.getElementById('bp-info-title').textContent = game.name;
    const pt = Number(game.playtime || 0);
    document.getElementById('bp-info-meta').textContent = `${game.platform} • Played: ${(pt / 3600).toFixed(1)}h`;
    document.getElementById('bp-info-img').src = game.poster || '';
    document.getElementById('bp-info-rating').textContent = `★ ${game.rating || '0.0'}`;
    
    // Strip HTML from description for short preview
    const tempDiv = document.createElement("div");
    tempDiv.innerHTML = game.description || "No description available.";
    document.getElementById('bp-info-desc').textContent = tempDiv.textContent || tempDiv.innerText || "";

    document.getElementById('bp-launch-btn').onclick = () => openBPModal(game);
}

function openBPModal(game) {
    const modal = document.getElementById('bp-confirm-modal');
    document.getElementById('bp-confirm-title').textContent = game.name;
    document.getElementById('bp-modal-start').onclick = () => {
        launchGame(game.id);
        closeBPModal();
    };
    modal.style.display = 'flex';
    // Focus start button
    setTimeout(() => document.getElementById('bp-modal-start').focus(), 50);
}

function closeBPModal() {
    document.getElementById('bp-confirm-modal').style.display = 'none';
    // Return focus to grid
    const focused = document.querySelector('.bp-card:focus');
    if (!focused) {
        const first = document.querySelector('.bp-card');
        if (first) first.focus();
    }
}

// Init
connectWebSocket();
// Load settings first, then library to ensure state is ready
loadSettings().then(() => {
    switchTab('library');
});
startPollingStatus();
setInterval(pollRunningGames, 2000); // Check for running games every 2s
