import json
import os
import sys
import logging
import asyncio
import threading
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from .scan import LGTVScan
from .remote import LGTVRemote
from .auth import LGTVAuth
from .cursor import LGTVCursor
from . import find_config, write_config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="LGTV WebOS Remote UI")

def get_config():
    try:
        filename = find_config()
        if os.path.isfile(filename):
            with open(filename, "r") as f:
                return json.load(f), filename
        return {}, filename
    except Exception as e:
        logger.error(f"Error loading config: {e}")
    return {}, None

class CommandRequest(BaseModel):
    tv_name: str
    command: str
    args: Optional[Dict[str, Any]] = None

class AuthRequest(BaseModel):
    tv_name: str
    host: str

def get_html():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LGTV WebOS Remote</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        primary: '#a61e4d',
                    }
                }
            }
        }
    </script>
    <style>
        .toast {
            transition: opacity 0.3s, transform 0.3s;
            opacity: 0;
            transform: translateY(1rem);
            pointer-events: none;
        }
        .toast.show {
            opacity: 1;
            transform: translateY(0);
        }
    </style>
</head>
<body class="bg-gray-100 min-h-screen text-gray-800 font-sans">

    <!-- Navbar -->
    <nav class="bg-primary text-white shadow-md sticky top-0 z-50">
        <div class="max-w-4xl mx-auto px-4 py-3 flex justify-between items-center">
            <h1 class="text-xl font-bold flex items-center">
                <svg class="w-6 h-6 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
                LGTV Remote
            </h1>
            <div class="flex items-center space-x-2">
                <select id="tv-select" class="bg-white text-gray-800 rounded px-2 py-1 text-sm outline-none border border-transparent focus:border-white w-32 md:w-48 hidden">
                </select>
                <button onclick="showScanModal()" class="bg-white text-primary rounded px-3 py-1 text-sm font-semibold hover:bg-gray-100 transition">
                    Scan / Add
                </button>
            </div>
        </div>
    </nav>

    <!-- Main Content -->
    <main class="max-w-4xl mx-auto px-4 py-6 space-y-6">

        <!-- Dashboard Section -->
        <section id="dashboard" class="bg-white rounded-lg shadow-sm p-4 border border-gray-200 hidden">
            <h2 class="text-lg font-semibold mb-3 border-b pb-2">Status</h2>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                <div class="p-3 bg-gray-50 rounded">
                    <div class="text-xs text-gray-500 uppercase tracking-wide">Power</div>
                    <div id="status-power" class="font-bold text-lg">-</div>
                </div>
                <div class="p-3 bg-gray-50 rounded">
                    <div class="text-xs text-gray-500 uppercase tracking-wide">Volume</div>
                    <div id="status-volume" class="font-bold text-lg">-</div>
                </div>
                <div class="p-3 bg-gray-50 rounded">
                    <div class="text-xs text-gray-500 uppercase tracking-wide">Muted</div>
                    <div id="status-muted" class="font-bold text-lg">-</div>
                </div>
                <div class="p-3 bg-gray-50 rounded">
                    <div class="text-xs text-gray-500 uppercase tracking-wide">App</div>
                    <div id="status-app" class="font-bold text-sm truncate" title="">-</div>
                </div>
            </div>
        </section>

        <div id="controls-container" class="hidden">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Power & Basic -->
                <section class="bg-white rounded-lg shadow-sm p-4 border border-gray-200">
                    <h2 class="text-lg font-semibold mb-3 border-b pb-2 flex items-center">
                        <svg class="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                        Power & Basics
                    </h2>
                    <div class="grid grid-cols-2 gap-3">
                        <button onclick="sendCommand('on')" class="bg-green-600 text-white rounded p-3 font-semibold hover:bg-green-700 transition">Turn On</button>
                        <button onclick="sendCommand('off')" class="bg-red-600 text-white rounded p-3 font-semibold hover:bg-red-700 transition">Turn Off</button>
                        <button onclick="sendCommand('screenOn')" class="bg-gray-200 text-gray-800 rounded p-2 hover:bg-gray-300 transition text-sm">Screen On</button>
                        <button onclick="sendCommand('screenOff')" class="bg-gray-200 text-gray-800 rounded p-2 hover:bg-gray-300 transition text-sm">Screen Off</button>
                    </div>
                </section>

                <!-- Audio -->
                <section class="bg-white rounded-lg shadow-sm p-4 border border-gray-200">
                    <h2 class="text-lg font-semibold mb-3 border-b pb-2 flex items-center">
                        <svg class="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5 10v4a2 2 0 002 2h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 001.707-.707V5.414a1 1 0 00-1.707-.707L10.293 8.121a1 1 0 01-.707.293H7a2 2 0 00-2 2z"></path></svg>
                        Audio
                    </h2>
                    <div class="flex items-center space-x-4 mb-4">
                        <button onclick="sendCommand('mute', {muted: true})" class="bg-gray-200 p-2 rounded hover:bg-gray-300 w-1/2">Mute</button>
                        <button onclick="sendCommand('mute', {muted: false})" class="bg-gray-200 p-2 rounded hover:bg-gray-300 w-1/2">Unmute</button>
                    </div>
                    <div class="flex items-center space-x-2">
                        <button onclick="sendCommand('volumeDown')" class="bg-gray-200 p-3 rounded hover:bg-gray-300 font-bold w-12">-</button>
                        <input type="range" id="vol-slider" min="0" max="100" class="w-full" onchange="sendCommand('setVolume', {level: parseInt(this.value)})">
                        <button onclick="sendCommand('volumeUp')" class="bg-gray-200 p-3 rounded hover:bg-gray-300 font-bold w-12">+</button>
                    </div>
                </section>

                <!-- D-Pad & Navigation -->
                <section class="bg-white rounded-lg shadow-sm p-4 border border-gray-200 md:col-span-2 lg:col-span-1">
                    <h2 class="text-lg font-semibold mb-3 border-b pb-2 flex items-center">
                        <svg class="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"></path></svg>
                        Navigation
                    </h2>
                    <div class="flex justify-center mb-4">
                        <div class="grid grid-cols-3 gap-2 w-48">
                            <div></div>
                            <button onclick="sendButton('up')" class="bg-gray-200 p-3 rounded shadow hover:bg-gray-300 flex justify-center"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"></path></svg></button>
                            <div></div>

                            <button onclick="sendButton('left')" class="bg-gray-200 p-3 rounded shadow hover:bg-gray-300 flex justify-center"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path></svg></button>
                            <button onclick="sendButton('enter')" class="bg-primary text-white p-3 rounded shadow hover:bg-pink-700 font-bold">OK</button>
                            <button onclick="sendButton('right')" class="bg-gray-200 p-3 rounded shadow hover:bg-gray-300 flex justify-center"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg></button>

                            <div></div>
                            <button onclick="sendButton('down')" class="bg-gray-200 p-3 rounded shadow hover:bg-gray-300 flex justify-center"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg></button>
                            <div></div>
                        </div>
                    </div>
                    <div class="grid grid-cols-3 gap-2 text-sm">
                        <button onclick="sendButton('back')" class="bg-gray-200 p-2 rounded hover:bg-gray-300">Back</button>
                        <button onclick="sendButton('home')" class="bg-gray-200 p-2 rounded hover:bg-gray-300">Home</button>
                        <button onclick="sendButton('exit')" class="bg-gray-200 p-2 rounded hover:bg-gray-300">Exit</button>
                    </div>
                </section>

                <!-- Media Controls -->
                <section class="bg-white rounded-lg shadow-sm p-4 border border-gray-200">
                    <h2 class="text-lg font-semibold mb-3 border-b pb-2 flex items-center">
                        <svg class="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                        Media Controls
                    </h2>
                    <div class="grid grid-cols-5 gap-2 mb-4">
                        <button onclick="sendCommand('inputMediaRewind')" class="bg-gray-200 p-2 rounded hover:bg-gray-300 flex justify-center" title="Rewind">«</button>
                        <button onclick="sendCommand('inputMediaPlay')" class="bg-gray-200 p-2 rounded hover:bg-gray-300 flex justify-center" title="Play">►</button>
                        <button onclick="sendCommand('inputMediaPause')" class="bg-gray-200 p-2 rounded hover:bg-gray-300 flex justify-center" title="Pause">❚❚</button>
                        <button onclick="sendCommand('inputMediaStop')" class="bg-gray-200 p-2 rounded hover:bg-gray-300 flex justify-center" title="Stop">■</button>
                        <button onclick="sendCommand('inputMediaFastForward')" class="bg-gray-200 p-2 rounded hover:bg-gray-300 flex justify-center" title="Fast Forward">»</button>
                    </div>
                    <div class="grid grid-cols-2 gap-2 text-sm">
                        <button onclick="sendCommand('inputChannelDown')" class="bg-gray-200 p-2 rounded hover:bg-gray-300">CH -</button>
                        <button onclick="sendCommand('inputChannelUp')" class="bg-gray-200 p-2 rounded hover:bg-gray-300">CH +</button>
                    </div>
                </section>

                <!-- Tools & Advanced -->
                <section class="bg-white rounded-lg shadow-sm p-4 border border-gray-200 md:col-span-2">
                    <h2 class="text-lg font-semibold mb-3 border-b pb-2 flex items-center">
                        <svg class="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                        Advanced
                    </h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div class="space-y-2">
                            <label class="block text-sm font-semibold text-gray-700">Send Notification</label>
                            <div class="flex">
                                <input type="text" id="notif-text" class="border p-2 rounded-l w-full outline-none focus:border-primary" placeholder="Message">
                                <button onclick="sendNotif()" class="bg-primary text-white p-2 rounded-r hover:bg-pink-700">Send</button>
                            </div>
                        </div>
                        <div class="space-y-2">
                            <label class="block text-sm font-semibold text-gray-700">Open URL / Browser</label>
                            <div class="flex">
                                <input type="text" id="url-text" class="border p-2 rounded-l w-full outline-none focus:border-primary" placeholder="https://...">
                                <button onclick="openUrl()" class="bg-primary text-white p-2 rounded-r hover:bg-pink-700">Open</button>
                            </div>
                        </div>
                    </div>
                </section>

            </div>
        </div>

        <!-- No TV State -->
        <div id="no-tv-container" class="bg-white rounded-lg shadow-sm p-8 text-center border border-gray-200 hidden">
            <svg class="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
            <h2 class="text-xl font-bold mb-2">No TV Connected</h2>
            <p class="text-gray-600 mb-4">Please scan for TVs on your network and pair with one to get started.</p>
            <button onclick="showScanModal()" class="bg-primary text-white px-6 py-2 rounded-lg font-semibold hover:bg-pink-700 shadow transition">Scan for TVs</button>
        </div>

    </main>

    <!-- Scan Modal -->
    <div id="scan-modal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center hidden z-50">
        <div class="bg-white rounded-lg shadow-xl p-6 w-full max-w-md mx-4">
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-lg font-bold">Scan for TVs</h3>
                <button onclick="hideScanModal()" class="text-gray-500 hover:text-gray-800"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg></button>
            </div>

            <div id="scan-loading" class="text-center py-4 hidden">
                <div class="animate-spin rounded-full h-10 w-10 border-b-2 border-primary mx-auto mb-2"></div>
                <p>Scanning local network...</p>
            </div>

            <div id="scan-results" class="space-y-3 hidden max-h-64 overflow-y-auto"></div>

            <div id="scan-initial" class="text-center py-4">
                <p class="text-gray-600 mb-4">Make sure your TV is turned on and connected to the same network.</p>
                <button onclick="startScan()" class="bg-primary text-white w-full py-2 rounded font-semibold hover:bg-pink-700">Start Scan</button>
            </div>

            <div id="auth-loading" class="text-center py-4 hidden">
                <div class="animate-spin rounded-full h-10 w-10 border-b-2 border-primary mx-auto mb-2"></div>
                <p class="font-bold text-lg mb-1">Pairing...</p>
                <p class="text-sm text-gray-600">Please look at your TV and accept the pairing request!</p>
            </div>
        </div>
    </div>

    <!-- Toast Notification -->
    <div id="toast" class="toast fixed bottom-4 right-4 bg-gray-800 text-white px-4 py-3 rounded shadow-lg flex items-center z-50">
        <span id="toast-icon" class="mr-2"></span>
        <span id="toast-message"></span>
    </div>

    <script>
        let currentTV = null;
        let dashboardInterval = null;

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
                select.innerHTML = '';

                const tvNames = Object.keys(data.tvs);

                if (tvNames.length === 0) {
                    document.getElementById('tv-select').classList.add('hidden');
                    document.getElementById('controls-container').classList.add('hidden');
                    document.getElementById('dashboard').classList.add('hidden');
                    document.getElementById('no-tv-container').classList.remove('hidden');
                    return;
                }

                document.getElementById('tv-select').classList.remove('hidden');
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

        async function updateDashboard() {
            if (!currentTV) return;
            try {
                const res = await fetch(`/api/dashboard?tv_name=${encodeURIComponent(currentTV)}`);
                const data = await res.json();

                if (data.status === 'success' && data.data) {
                    const d = data.data;
                    document.getElementById('status-power').textContent = 'ON';
                    document.getElementById('status-power').classList.replace('text-red-600', 'text-green-600') || document.getElementById('status-power').classList.add('text-green-600');

                    if (d.audio) {
                        document.getElementById('status-volume').textContent = d.audio.volume || 0;
                        document.getElementById('vol-slider').value = d.audio.volume || 0;
                        document.getElementById('status-muted').textContent = d.audio.mute ? 'Yes' : 'No';
                    }
                    if (d.app && d.app.appId) {
                        let appName = d.app.appId.split('.').pop() || 'Unknown';
                        appName = appName.charAt(0).toUpperCase() + appName.slice(1);
                        document.getElementById('status-app').textContent = appName;
                        document.getElementById('status-app').title = d.app.appId;
                    }
                }
            } catch (e) {
                document.getElementById('status-power').textContent = 'OFF / UNREACHABLE';
                document.getElementById('status-power').classList.replace('text-green-600', 'text-red-600') || document.getElementById('status-power').classList.add('text-red-600');
                document.getElementById('status-volume').textContent = '-';
                document.getElementById('status-muted').textContent = '-';
                document.getElementById('status-app').textContent = '-';
            }
        }

        function showScanModal() {
            document.getElementById('scan-modal').classList.remove('hidden');
            document.getElementById('scan-initial').classList.remove('hidden');
            document.getElementById('scan-loading').classList.add('hidden');
            document.getElementById('scan-results').classList.add('hidden');
            document.getElementById('auth-loading').classList.add('hidden');
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
                    loadConfig();
                } else {
                    showToast('Pairing failed: ' + (data.detail || 'Unknown error'), 'error');
                    hideScanModal();
                }
            } catch (e) {
                showToast('Pairing request failed', 'error');
                hideScanModal();
            }
        }

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
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def read_root():
    return get_html()

@app.get("/api/config")
def api_get_config():
    config, _ = get_config()
    tvs = {k: v for k, v in config.items() if k != "_default"}
    default_tv = config.get("_default")
    return {"tvs": tvs, "default": default_tv}

@app.post("/api/scan")
def api_scan():
    results = LGTVScan()
    return {"count": len(results), "list": results}

@app.post("/api/auth")
def api_auth(req: AuthRequest):
    config, filename = get_config()
    if not filename:
        raise HTTPException(status_code=500, detail="Cannot find config file")

    try:
        logger.info(f"Authenticating with {req.tv_name} at {req.host} using SSL")
        ws = LGTVAuth(req.tv_name, req.host, ssl=True)
        ws.connect()

        timer = threading.Timer(30.0, ws.close)
        timer.start()

        ws.run_forever()
        timer.cancel()

        config[req.tv_name] = ws.serialise()
        if "_default" not in config:
            config["_default"] = req.tv_name

        write_config(filename, config)
        return {"status": "success", "message": f"Successfully authenticated and saved config for {req.tv_name}"}
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/command")
def api_command(req: CommandRequest):
    config, filename = get_config()
    if req.tv_name not in config:
        raise HTTPException(status_code=404, detail=f"TV '{req.tv_name}' not found in config")

    tv_config = config[req.tv_name]
    command_response = None

    def callback(res):
        nonlocal command_response
        command_response = res
        logger.info(f"Callback response: {res}")

    try:
        kwargs = req.args or {}

        if req.command == "sendButton":
            cursor = LGTVCursor(req.tv_name, **tv_config, ssl=True)
            cursor.connect()
            button_args = kwargs.get("buttons", [])
            cursor.execute(button_args)
            return {"status": "success", "command": req.command}

        ws = LGTVRemote(req.tv_name, **tv_config, ssl=True)

        if req.command == "on":
            ws.on()
            return {"status": "success", "command": req.command}

        import inspect
        if hasattr(ws, req.command):
            method = getattr(ws, req.command)
            sig = inspect.signature(method)
            if 'callback' in sig.parameters:
                def close_callback(res):
                    nonlocal command_response
                    command_response = res
                    logger.info(f"Custom callback response: {res}")
                    ws.close()
                kwargs['callback'] = close_callback

            ws.connect()
            method(**kwargs)
        else:
            ws.connect()
            ws.execute(req.command, kwargs)

        timer = threading.Timer(5.0, ws.close)
        timer.start()

        ws.run_forever()
        timer.cancel()

        return {"status": "success", "command": req.command, "response": command_response}

    except Exception as e:
        logger.error(f"Command error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard")
def api_dashboard(tv_name: str):
    config, filename = get_config()
    if tv_name not in config:
        raise HTTPException(status_code=404, detail=f"TV '{tv_name}' not found")

    tv_config = config[tv_name]
    dashboard_data = {}

    def handle_audio(res):
        if "payload" in res:
            dashboard_data["audio"] = res["payload"]

    def handle_app(res):
        if "payload" in res:
            dashboard_data["app"] = res["payload"]

    try:
        ws = LGTVRemote(tv_name, **tv_config, ssl=True)
        ws.connect()

        expected_responses = 2
        received_responses = 0

        def handle_audio_close(res):
            nonlocal received_responses
            handle_audio(res)
            received_responses += 1
            if received_responses == expected_responses:
                ws.close()

        def handle_app_close(res):
            nonlocal received_responses
            handle_app(res)
            received_responses += 1
            if received_responses == expected_responses:
                ws.close()

        ws.audioStatus(callback=handle_audio_close)
        ws.getForegroundAppInfo(callback=handle_app_close)

        timer = threading.Timer(3.0, ws.close)
        timer.start()

        ws.run_forever()
        timer.cancel()

        return {"status": "success", "data": dashboard_data}
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def start_server(host="0.0.0.0", port=8000):
    uvicorn.run(app, host=host, port=port)
