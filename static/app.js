let currentTV = null;
let dashboardInterval = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadConfig();

    document.getElementById('tv-select').addEventListener('change', (e) => {
        setTV(e.target.value);
    });
});

async function loadConfig() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();

        const select = document.getElementById('tv-select');
        const removeBtn = document.getElementById('remove-tv-btn');
        select.innerHTML = '';

        const tvNames = Object.keys(data.tvs);

        if (tvNames.length === 0) {
            select.classList.add('hidden');
            if (removeBtn) removeBtn.classList.add('hidden');
            document.getElementById('controls-container').classList.add('hidden');
            document.getElementById('dashboard').classList.add('hidden');
            document.getElementById('no-tv-container').classList.remove('hidden');
            return;
        }

        select.classList.remove('hidden');
        if (removeBtn) removeBtn.classList.remove('hidden');
        document.getElementById('controls-container').classList.remove('hidden');
        document.getElementById('dashboard').classList.remove('hidden');
        document.getElementById('no-tv-container').classList.add('hidden');

        tvNames.forEach(name => {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            select.appendChild(opt);
        });

        if (data.default && tvNames.includes(data.default)) {
            select.value = data.default;
            setTV(data.default);
        } else {
            select.value = tvNames[0];
            setTV(tvNames[0]);
        }
    } catch (e) {
        showToast('Failed to load configuration', 'error');
    }
}

function setTV(name) {
    currentTV = name;
    if (dashboardInterval) clearInterval(dashboardInterval);
    updateDashboard();
    dashboardInterval = setInterval(updateDashboard, 5000);
}

// Commands
async function sendCommand(command, args = null) {
    if (!currentTV) return;
    try {
        const res = await fetch('/api/command', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                tv_name: currentTV,
                command: command,
                args: args || {}
            })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Command sent: ' + command, 'success');
            // Optimistically update dashboard
            setTimeout(updateDashboard, 500);
        } else {
            showToast('Error: ' + data.detail, 'error');
        }
    } catch (e) {
        showToast('Failed to send command', 'error');
    }
}

function sendButton(buttonName) {
    sendCommand('sendButton', {buttons: [buttonName]});
}

function sendNotif() {
    const text = document.getElementById('notif-text').value;
    if (text) {
        sendCommand('notification', {message: text});
        document.getElementById('notif-text').value = '';
    }
}

function openUrl() {
    let url = document.getElementById('url-text').value;
    if (url) {
        if (!url.startsWith('http')) url = 'https://' + url;
        sendCommand('openBrowserAt', {url: url});
        document.getElementById('url-text').value = '';
    }
}

// Dashboard
async function updateDashboard() {
    if (!currentTV) return;
    try {
        const res = await fetch(`/api/dashboard?tv_name=${encodeURIComponent(currentTV)}`);
        const data = await res.json();

        if (data.status === 'success' && data.data) {
            const d = data.data;

            // Assume TV is on if we get a response, if we timeout or fail, it might be off.
            // A more robust way is getting power state, but often API fails to connect if off.
            document.getElementById('status-power').textContent = 'ON';
            document.getElementById('status-power').classList.replace('text-red-600', 'text-green-600') || document.getElementById('status-power').classList.add('text-green-600');

            if (d.audio) {
                document.getElementById('status-volume').textContent = d.audio.volume || 0;
                document.getElementById('vol-slider').value = d.audio.volume || 0;
                document.getElementById('status-muted').textContent = d.audio.mute ? 'Yes' : 'No';
            }
            if (d.app && d.app.appId) {
                // Remove prefix like com.webos.app. to make it readable
                let appName = d.app.appId.split('.').pop() || 'Unknown';
                // capitalize
                appName = appName.charAt(0).toUpperCase() + appName.slice(1);
                document.getElementById('status-app').textContent = appName;
                document.getElementById('status-app').title = d.app.appId;
            }
        }
    } catch (e) {
        // If it fails, TV is likely off
        document.getElementById('status-power').textContent = 'OFF / UNREACHABLE';
        document.getElementById('status-power').classList.replace('text-green-600', 'text-red-600') || document.getElementById('status-power').classList.add('text-red-600');
        document.getElementById('status-volume').textContent = '-';
        document.getElementById('status-muted').textContent = '-';
        document.getElementById('status-app').textContent = '-';
    }
}

// Scanning and Auth
function showScanModal() {
    document.getElementById('scan-modal').classList.remove('hidden');
    document.getElementById('scan-initial').classList.remove('hidden');
    document.getElementById('scan-loading').classList.add('hidden');
    document.getElementById('scan-results').classList.add('hidden');
    document.getElementById('auth-loading').classList.add('hidden');
    
    updateAddedTVsInModal();
}

function hideScanModal() {
    document.getElementById('scan-modal').classList.add('hidden');
}

async function startScan() {
    document.getElementById('scan-initial').classList.add('hidden');
    document.getElementById('scan-loading').classList.remove('hidden');
    document.getElementById('scan-results').innerHTML = '';

    try {
        const res = await fetch('/api/scan', {method: 'POST'});
        const data = await res.json();

        document.getElementById('scan-loading').classList.add('hidden');
        document.getElementById('scan-results').classList.remove('hidden');

        if (data.count === 0) {
            document.getElementById('scan-results').innerHTML = '<p class="text-center text-gray-500">No TVs found. Make sure TV is on and connected to the same network.</p>';
            return;
        }

        data.list.forEach(tv => {
            const div = document.createElement('div');
            div.className = 'border p-3 rounded flex justify-between items-center';

            const infoDiv = document.createElement('div');
            const modelDiv = document.createElement('div');
            modelDiv.className = 'font-bold';
            modelDiv.textContent = tv.model || 'Unknown TV';
            const addressDiv = document.createElement('div');
            addressDiv.className = 'text-sm text-gray-500';
            addressDiv.textContent = tv.address;
            infoDiv.appendChild(modelDiv);
            infoDiv.appendChild(addressDiv);

            const btn = document.createElement('button');
            btn.className = 'bg-primary text-white px-3 py-1 rounded text-sm hover:bg-pink-700';
            btn.textContent = 'Pair';
            btn.onclick = () => authTV(tv.address, tv.model || 'MyTV');

            div.appendChild(infoDiv);
            div.appendChild(btn);

            document.getElementById('scan-results').appendChild(div);
        });

    } catch (e) {
        document.getElementById('scan-loading').classList.add('hidden');
        showToast('Scan failed', 'error');
    }
}

async function removeCurrentTV() {
    if (!currentTV) return;
    await handleRemoveTVByName(currentTV);
}

async function handleRemoveTVByName(name) {
    if (!confirm(`Are you sure you want to remove ${name}?`)) return;

    try {
        const res = await fetch('/api/remove_tv', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({tv_name: name})
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('TV removed', 'success');
            loadConfig();
            if (document.getElementById('scan-modal').classList.contains('hidden') === false) {
                updateAddedTVsInModal();
            }
        } else {
            showToast('Error: ' + (data.detail || 'Unknown error'), 'error');
        }
    } catch (e) {
        showToast('Failed to remove TV', 'error');
    }
}

async function updateAddedTVsInModal() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();
        const tvNames = Object.keys(data.tvs);
        const container = document.getElementById('added-tvs-container');
        const list = document.getElementById('added-tvs-list');
        
        list.innerHTML = '';
        if (tvNames.length > 0) {
            container.classList.remove('hidden');
            tvNames.forEach(name => {
                const div = document.createElement('div');
                div.className = 'flex justify-between items-center bg-gray-50 p-2 rounded border border-gray-100';
                div.innerHTML = `
                    <span class="font-semibold text-sm">${name}</span>
                    <button onclick="handleRemoveTVByName('${name}')" class="text-red-600 hover:text-red-800 p-1" title="Remove TV">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                    </button>
                `;
                list.appendChild(div);
            });
        } else {
            container.classList.add('hidden');
        }
    } catch (e) {
        console.error('Failed to update added TVs in modal', e);
    }
}

async function authTV(host, defaultName) {
    const tvName = prompt("Enter a name for this TV to save:", defaultName.replace(/[^a-zA-Z0-9]/g, ''));
    if (!tvName) return;

    document.getElementById('scan-results').classList.add('hidden');
    document.getElementById('auth-loading').classList.remove('hidden');

    try {
        const res = await fetch('/api/auth', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({tv_name: tvName, host: host})
        });
        const data = await res.json();

        if (data.status === 'success') {
            showToast('Successfully paired with TV!', 'success');
            hideScanModal();
            loadConfig(); // Reload UI
        } else {
            showToast('Pairing failed: ' + (data.detail || 'Unknown error'), 'error');
            hideScanModal();
        }
    } catch (e) {
        showToast('Pairing request failed', 'error');
        hideScanModal();
    }
}

// Toast logic
let toastTimeout;
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    const msg = document.getElementById('toast-message');
    const icon = document.getElementById('toast-icon');

    msg.textContent = message;

    if (type === 'success') {
        toast.classList.replace('bg-red-600', 'bg-gray-800');
        icon.innerHTML = '<svg class="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>';
    } else {
        toast.classList.replace('bg-gray-800', 'bg-red-600');
        icon.innerHTML = '<svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>';
    }

    toast.classList.add('show');

    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Make functions available globally explicitly
window.removeCurrentTV = removeCurrentTV;
window.handleRemoveTVByName = handleRemoveTVByName;
window.showScanModal = showScanModal;
window.hideScanModal = hideScanModal;
window.startScan = startScan;
window.sendCommand = sendCommand;
window.sendButton = sendButton;
window.sendNotif = sendNotif;
window.openUrl = openUrl;
window.authTV = authTV;
