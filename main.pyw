import json
import os
import subprocess
import uuid
import time
import requests
import hashlib
import shutil
import zipfile
import threading
from datetime import datetime
from flask import Flask, request, render_template_string, redirect, url_for, jsonify
import webview
import keyboard
import psutil
import socket

app = Flask(__name__)

# Конфигурация
CLIENT_CONFIG = {
    'server_url': 'http://memsip.ru:5000',
    'last_checked': None,
    'modpack_version': None,
    'total_mods': 0
}

LAUNCHER_SETTINGS = {
    'username': None,
    'window_width': 1280,
    'window_height': 800,
    'server_port': 5001,
    'theme': 'dark_minimal'
}

# Константы для системы контроля оверлея
OVERLAY_LOCK_PORT = 5002  # Порт для проверки запущенного overlay
OVERLAY_CHECK_INTERVAL = 0.1  # Интервал проверки в секундах

# Глобальные переменные
overlay_process = None
overlay_running = False
tab_pressed_time = 0  # Время последнего нажатия Tab
tab_cooldown = 0.3  # КД между нажатиями в секундах

# HTML шаблоны (остаются без изменений)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>NaraLauncher</title>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
        body { background: linear-gradient(135deg, #0a0a0f 0%, #121212 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; color: #e0e0e0; }
        .container { width: 900px; height: 700px; background: rgba(20, 20, 25, 0.95); border-radius: 15px; box-shadow: 0 10px 40px rgba(0,0,0,0.5); overflow: hidden; border: 1px solid rgba(255,255,255,0.05); }
        .header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 25px; text-align: center; border-bottom: 1px solid rgba(255,255,255,0.1); }
        .header h1 { font-size: 28px; margin-bottom: 5px; }
        .header .subtitle { opacity: 0.8; font-size: 12px; }
        .content { padding: 25px; display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; height: calc(100% - 120px); overflow-y: auto; }
        .tile { background: rgba(30,30,40,0.8); border-radius: 10px; padding: 20px; border: 1px solid rgba(255,255,255,0.08); cursor: pointer; transition: all 0.2s; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 140px; }
        .tile:hover { transform: translateY(-2px); background: rgba(40,40,50,0.9); }
        .tile-icon { font-size: 32px; color: #5d8aa8; margin-bottom: 10px; }
        .tile-title { font-size: 16px; font-weight: 600; margin-bottom: 5px; }
        .tile-description { font-size: 12px; color: #a0a0a0; text-align: center; }
        .status-area { grid-column: 1 / -1; background: rgba(25,25,35,0.9); border-radius: 10px; padding: 15px; margin-top: 10px; min-height: 120px; max-height: 200px; overflow-y: auto; }
        .status-message { padding: 10px; margin-bottom: 5px; border-radius: 6px; font-size: 13px; background: rgba(255,255,255,0.05); border-left: 3px solid #5d8aa8; }
        .status-success { background: rgba(46,213,115,0.1); border-left-color: #2ed573; }
        .status-warning { background: rgba(255,193,7,0.1); border-left-color: #ffc107; }
        .status-error { background: rgba(255,71,87,0.1); border-left-color: #ff4757; }
        .progress-bar { width: 100%; height: 4px; background: rgba(255,255,255,0.05); border-radius: 2px; margin-top: 10px; overflow: hidden; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #5d8aa8, #2c3e50); width: 0%; transition: width 0.3s; }
        .account-info { background: rgba(30,30,40,0.9); padding: 15px; border-radius: 10px; margin-bottom: 15px; display: flex; align-items: center; gap: 15px; grid-column: 1 / -1; }
        .footer { margin-top: auto; text-align: center; color: #666; font-size: 11px; padding: 15px; border-top: 1px solid rgba(255,255,255,0.05); grid-column: 1 / -1; }
        button { padding: 12px 20px; border: none; border-radius: 8px; font-size: 14px; cursor: pointer; transition: all 0.2s; background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%); color: white; }
        button:hover { transform: translateY(-1px); }
        .modal { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); z-index: 1000; }
        .modal-content { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); margin: 100px auto; width: 400px; border-radius: 12px; padding: 25px; }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-cube"></i> NaraLauncher</h1>
            <div class="subtitle">Minecraft 1.12.2 | Simple & Fast</div>
            <div id="serverStatus" style="margin-top: 10px; font-size: 12px;">
                <span id="statusDot" style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #ff4757; margin-right: 5px;"></span>
                <span id="statusText">Checking connection...</span>
            </div>
        </div>
        
        <div class="content">
            <div class="account-info">
                <div style="font-size: 24px; color: #5d8aa8;">
                    <i class="fas fa-user"></i>
                </div>
                <div>
                    <div style="font-size: 16px; font-weight: 600;" id="currentUsername">Not logged in</div>
                    <div style="display: flex; gap: 15px; margin-top: 5px; font-size: 11px; color: #888;">
                        <div><i class="fas fa-server"></i> <span id="modCount">0 mods</span></div>
                        <div><i class="fas fa-clock"></i> <span id="lastUpdate">Never</span></div>
                    </div>
                </div>
            </div>
            
            <div class="tile" onclick="launchGame()">
                <div class="tile-icon"><i class="fas fa-play"></i></div>
                <div class="tile-title">Launch Game</div>
                <div class="tile-description">Start Minecraft with modpack</div>
            </div>
            
            <div class="tile" onclick="reinstallModpack()">
                <div class="tile-icon"><i class="fas fa-redo"></i></div>
                <div class="tile-title">Install/Update</div>
                <div class="tile-description">Download modpack</div>
            </div>
            
            <div class="tile" onclick="openModsFolder()">
                <div class="tile-icon"><i class="fas fa-folder"></i></div>
                <div class="tile-title">Mods Folder</div>
                <div class="tile-description">Open mods directory</div>
            </div>
            
            <div class="tile" onclick="showSettings()">
                <div class="tile-icon"><i class="fas fa-cog"></i></div>
                <div class="tile-title">Settings</div>
                <div class="tile-description">Launcher configuration</div>
            </div>
            
            <div class="status-area" id="statusArea"></div>
            
            <div class="progress-bar" id="progressBar" style="display: none;">
                <div class="progress-fill" id="progressFill"></div>
            </div>
            
            <div class="footer">
                <div>NaraLauncher v3.3 • <span id="modpackVersion">Loading...</span></div>
            </div>
        </div>
    </div>
    
    <div class="modal" id="settingsModal">
        <div class="modal-content">
            <h2 style="color: white; margin-bottom: 20px;"><i class="fas fa-cog"></i> Settings</h2>
            
            <div style="margin-bottom: 15px;">
                <label style="display: block; margin-bottom: 5px; color: #fff; font-size: 13px;">Username:</label>
                <input type="text" id="username" placeholder="Minecraft username" style="width: 100%; padding: 10px; border-radius: 6px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); color: white;">
            </div>
            
            <div style="margin-bottom: 15px;">
                <label style="display: block; margin-bottom: 5px; color: #fff; font-size: 13px;">Server URL:</label>
                <input type="text" id="serverUrl" placeholder="http://server:port" style="width: 100%; padding: 10px; border-radius: 6px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); color: white;">
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px;">
                <div>
                    <label style="display: block; margin-bottom: 5px; color: #fff; font-size: 13px;">Width:</label>
                    <input type="number" id="windowWidth" min="700" max="1920" style="width: 100%; padding: 10px; border-radius: 6px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); color: white;">
                </div>
                <div>
                    <label style="display: block; margin-bottom: 5px; color: #fff; font-size: 13px;">Height:</label>
                    <input type="number" id="windowHeight" min="500" max="1080" style="width: 100%; padding: 10px; border-radius: 6px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); color: white;">
                </div>
            </div>
            
            <div style="display: flex; gap: 10px;">
                <button onclick="saveSettings()" style="background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%); flex: 1;"><i class="fas fa-save"></i> Save</button>
                <button onclick="hideSettings()" style="background: rgba(255,255,255,0.1); flex: 1;"><i class="fas fa-times"></i> Cancel</button>
            </div>
        </div>
    </div>
    
    <script>
        function addStatusMessage(text, type = 'info') {
            const area = document.getElementById('statusArea');
            const msg = document.createElement('div');
            msg.className = `status-message status-${type}`;
            msg.innerHTML = `<i class="fas fa-${type === 'success' ? 'check' : type === 'error' ? 'times' : 'info'}"></i> ${text}`;
            area.appendChild(msg);
            area.scrollTop = area.scrollHeight;
        }
        
        function updateProgress(percent) {
            document.getElementById('progressBar').style.display = 'block';
            document.getElementById('progressFill').style.width = percent + '%';
        }
        
        function checkServerStatus() {
            fetch('/api/server_status')
                .then(r => r.json())
                .then(data => {
                    const dot = document.getElementById('statusDot');
                    const text = document.getElementById('statusText');
                    const version = document.getElementById('modpackVersion');
                    
                    if (data.online) {
                        dot.style.background = '#2ed573';
                        text.textContent = `Online • v${data.version}`;
                        text.style.color = '#2ed573';
                        version.textContent = `v${data.version} (${data.total_mods} mods)`;
                    } else {
                        dot.style.background = '#ff4757';
                        text.textContent = 'Offline';
                        text.style.color = '#ff4757';
                    }
                });
        }
        
        function launchGame() {
            fetch('/launch', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        addStatusMessage(data.message, 'success');
                    } else {
                        addStatusMessage(data.message, 'error');
                    }
                });
        }
        
        function reinstallModpack() {
            if (!confirm('Download and install modpack? This will replace existing mods.')) return;
            
            updateProgress(0);
            addStatusMessage('Starting download...', 'info');
            
            fetch('/reinstall_modpack', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        updateProgress(100);
                        addStatusMessage(data.message, 'success');
                        setTimeout(() => {
                            document.getElementById('progressBar').style.display = 'none';
                            checkServerStatus();
                            loadUserData();
                        }, 1000);
                    } else {
                        addStatusMessage(data.message, 'error');
                        document.getElementById('progressBar').style.display = 'none';
                    }
                })
                .catch(err => {
                    addStatusMessage('Download failed: ' + err, 'error');
                    document.getElementById('progressBar').style.display = 'none';
                });
        }
        
        function openModsFolder() {
            fetch('/api/open_mods_folder', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    addStatusMessage(data.message, data.success ? 'success' : 'error');
                });
        }
        
        function showSettings() {
            fetch('/api/settings')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('username').value = data.username || '';
                    document.getElementById('serverUrl').value = data.server_url;
                    document.getElementById('windowWidth').value = data.window_width;
                    document.getElementById('windowHeight').value = data.window_height;
                    document.getElementById('settingsModal').style.display = 'block';
                });
        }
        
        function hideSettings() {
            document.getElementById('settingsModal').style.display = 'none';
        }
        
        function saveSettings() {
            const data = {
                username: document.getElementById('username').value.trim(),
                server_url: document.getElementById('serverUrl').value,
                window_width: parseInt(document.getElementById('windowWidth').value),
                window_height: parseInt(document.getElementById('windowHeight').value)
            };
            
            fetch('/api/update_settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(res => {
                if (res.success) {
                    addStatusMessage('Settings saved', 'success');
                    document.getElementById('currentUsername').textContent = data.username || 'Not logged in';
                    hideSettings();
                    checkServerStatus();
                } else {
                    addStatusMessage(res.message, 'error');
                }
            });
        }
        
        function loadUserData() {
            fetch('/api/settings')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('currentUsername').textContent = data.username || 'Not logged in';
                    document.getElementById('modCount').textContent = data.mod_count + ' mods';
                    document.getElementById('lastUpdate').textContent = data.last_update;
                });
        }
        
        document.addEventListener('DOMContentLoaded', function() {
            loadUserData();
            checkServerStatus();
            setInterval(checkServerStatus, 30000);
            
            // Check for updates
            fetch('/check_updates')
                .then(r => r.json())
                .then(data => {
                    if (data.updates_available) {
                        addStatusMessage('Modpack update available! Click "Install/Update"', 'warning');
                    }
                });
            
            // Close modal on outside click
            document.getElementById('settingsModal').addEventListener('click', function(e) {
                if (e.target === this) hideSettings();
            });
        });
    </script>
</body>
</html>
"""

REGISTER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Register</title>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
        body { background: linear-gradient(135deg, #0a0a0f 0%, #121212 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }
        .container { background: rgba(20,20,25,0.95); width: 400px; border-radius: 15px; padding: 30px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }
        h1 { color: white; text-align: center; margin-bottom: 30px; font-size: 24px; }
        input { width: 100%; padding: 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1); background: rgba(0,0,0,0.3); color: white; margin-bottom: 20px; font-size: 14px; }
        button { width: 100%; padding: 12px; border-radius: 8px; border: none; background: linear-gradient(135deg, #2c3e50, #34495e); color: white; font-size: 14px; cursor: pointer; transition: all 0.2s; }
        button:hover { transform: translateY(-1px); }
        .error { color: #ff4757; font-size: 12px; margin-top: -15px; margin-bottom: 15px; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Enter Minecraft Username</h1>
        <input type="text" id="username" placeholder="Username (3-16 characters)" autofocus>
        <div class="error" id="error">Invalid username</div>
        <button onclick="register()">Continue</button>
    </div>
    
    <script>
        function register() {
            const username = document.getElementById('username').value.trim();
            const error = document.getElementById('error');
            
            if (username.length < 3 || username.length > 16) {
                error.style.display = 'block';
                return;
            }
            
            error.style.display = 'none';
            
            fetch('/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'username=' + encodeURIComponent(username)
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    window.location.href = '/';
                } else {
                    error.textContent = data.message;
                    error.style.display = 'block';
                }
            });
        }
        
        document.getElementById('username').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') register();
        });
    </script>
</body>
</html>
"""

# ==================== ФУНКЦИИ ДЛЯ СИСТЕМЫ КОНТРОЛЯ OVERLAY ====================

def is_overlay_running():
    """
    Проверяет, запущен ли процесс overlay.py через порт
    """
    try:
        # Проверяем, слушает ли порт OVERLAY_LOCK_PORT
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)  # Короткий таймаут
        result = sock.connect_ex(('127.0.0.1', OVERLAY_LOCK_PORT))
        sock.close()
        
        if result == 0:
            # Порт занят - overlay запущен
            return True
        
        # Дополнительная проверка через процессы
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline')
                if cmdline and len(cmdline) > 1:
                    cmdline_str = ' '.join(cmdline).lower()
                    if 'overlay.py' in cmdline_str:
                        # Проверяем, что это не текущий процесс лаунчера
                        current_pid = os.getpid()
                        if proc.info.get('pid') != current_pid:
                            return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                continue
        
        return False
    except Exception as e:
        print(f"⚠️ Error checking overlay: {e}")
        return False

def start_overlay():
    """
    Запускает overlay.py, если он не запущен
    """
    global overlay_process, overlay_running
    
    try:
        # Проверяем, не запущен ли уже overlay
        if is_overlay_running():
            print("✅ Overlay уже запущен")
            overlay_running = True
            return True
        
        # Проверяем существование файла overlay.py
        if not os.path.exists('overlay.py'):
            print("❌ Файл overlay.py не найден")
            return False
        
        print("🚀 Запускаю overlay...")
        
        # Запускаем overlay.py как отдельный процесс
        # Убираем CREATE_NO_WINDOW для лучшей видимости
        try:
            overlay_process = subprocess.Popen(
                ['python', 'overlay.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
        except FileNotFoundError:
            # Попробуем с python3
            overlay_process = subprocess.Popen(
                ['python3', 'overlay.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
        
        # Даем время на запуск (увеличиваем время ожидания)
        time.sleep(2)
        
        # Проверяем, запустился ли
        if is_overlay_running():
            print("✅ Overlay успешно запущен")
            overlay_running = True
            return True
        else:
            # Проверяем, может быть процесс уже завершился
            if overlay_process and overlay_process.poll() is not None:
                stdout, stderr = overlay_process.communicate()
                print(f"❌ Overlay завершился с кодом: {overlay_process.returncode}")
                if stderr:
                    print(f"Ошибка: {stderr}")
            else:
                print("❌ Overlay не запустился или не отвечает")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка запуска overlay: {e}")
        import traceback
        traceback.print_exc()
        return False

def terminate_overlay():
    """
    Завершает процесс overlay.py
    """
    global overlay_process, overlay_running
    
    try:
        # Сначала пробуем через HTTP запрос (если overlay имеет API)
        try:
            import requests
            response = requests.post(f'http://127.0.0.1:{OVERLAY_LOCK_PORT}/api/close', timeout=1)
            print("📤 Отправлена команда закрытия overlay")
            time.sleep(0.5)
        except:
            pass
        
        # Затем завершаем наш процесс
        if overlay_process and overlay_process.poll() is None:
            try:
                overlay_process.terminate()
                overlay_process.wait(timeout=2)
                print("✅ Overlay процесс завершен")
            except subprocess.TimeoutExpired:
                try:
                    overlay_process.kill()
                    print("⚠️ Overlay процесс принудительно завершен")
                except:
                    pass
        
        # Ищем и завершаем все остальные процессы overlay.py
        terminated = False
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                cmdline = proc.cmdline()
                if cmdline and len(cmdline) > 1 and 'overlay.py' in ' '.join(cmdline):
                    proc.terminate()
                    terminated = True
                    print(f"Завершен процесс overlay: {proc.pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if terminated:
            print("✅ Все процессы overlay завершены")
        
        overlay_process = None
        overlay_running = False
        return True
        
    except Exception as e:
        print(f"❌ Ошибка завершения overlay: {e}")
        return False

def handle_tab_press():
    """
    Обработчик нажатия клавиши Tab
    Следит за тем, чтобы был запущен только один экземпляр overlay
    """
    global tab_pressed_time, overlay_running
    
    try:
        current_time = time.time()
        
        # Проверяем кд между нажатиями
        if current_time - tab_pressed_time < tab_cooldown:
            return
        
        tab_pressed_time = current_time
        
        # Проверяем текущее состояние overlay
        is_running = is_overlay_running()
        
        print(f"🔍 Tab pressed. Overlay running: {is_running}")
        
        if not is_running:
            # Overlay не запущен - запускаем
            print("🚀 Launching overlay...")
            success = start_overlay()
            
            if success:
                print("✅ Overlay launched")
                overlay_running = True
            else:
                print("❌ Failed to launch overlay")
                overlay_running = False
        else:
            # Overlay уже запущен - НИЧЕГО НЕ ДЕЛАЕМ
            print("⚠️ Overlay already running - ignoring Tab press")
            print("ℹ️ Press Tab again will have no effect while overlay is running")
            return
        
    except Exception as e:
        print(f"❌ Error in handle_tab_press: {e}")
        import traceback
        traceback.print_exc()

def start_tab_listener():
    """
    Запускает слушатель нажатия клавиши Tab в отдельном потоке
    """
    def tab_listener():
        print("👂 Tab key listener started...")
        print("ℹ️ Press Tab to launch overlay")
        print("⚠️ If overlay is already running, Tab will be ignored")
        
        # Регистрируем горячую клавишу
        keyboard.add_hotkey('tab', handle_tab_press, suppress=False)
        
        # Бесконечный цикл для поддержания потока активным
        try:
            while True:
                time.sleep(1)
                # Периодически проверяем состояние overlay
                global overlay_running
                current_state = is_overlay_running()
                if current_state != overlay_running:
                    overlay_running = current_state
                    if overlay_running:
                        print("📊 Overlay detected as running")
                    else:
                        print("📊 Overlay detected as stopped")
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"❌ Error in tab listener: {e}")
    
    listener_thread = threading.Thread(target=tab_listener, daemon=True)
    listener_thread.start()
    return listener_thread

# ==================== ОСТАЛЬНЫЕ ФУНКЦИИ (БЕЗ ИЗМЕНЕНИЙ) ====================

def get_data_folder():
    """Возвращает путь к папке data"""
    folder = "data/"
    os.makedirs(folder, exist_ok=True)
    return folder

def get_settings_path():
    return os.path.join(get_data_folder(), 'settings.json')

def get_config_path():
    return os.path.join(get_data_folder(), 'config.json')

def get_mods_folder():
    """Путь к папке mods"""
    appdata = os.getenv('APPDATA')
    prism_path = os.path.join(appdata, 'PrismLauncher/instances/1.12.2/.minecraft')
    return prism_path

def get_temp_folder():
    temp = os.path.join(get_data_folder(), 'temp')
    os.makedirs(temp, exist_ok=True)
    return temp

def save_settings():
    with open(get_settings_path(), 'w', encoding='utf-8') as f:
        json.dump(LAUNCHER_SETTINGS, f, indent=2)

def load_settings():
    path = get_settings_path()
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            LAUNCHER_SETTINGS.update(json.load(f))

def save_config():
    with open(get_config_path(), 'w', encoding='utf-8') as f:
        json.dump(CLIENT_CONFIG, f, indent=2)

def load_config():
    path = get_config_path()
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            CLIENT_CONFIG.update(json.load(f))
    save_config()

def download_modpack():
    """Скачивает и устанавливает модпак"""
    try:
        mods_folder = get_mods_folder()
        temp_folder = get_temp_folder()
        zip_path = os.path.join(temp_folder, 'modpack.zip')
        
        server_url = CLIENT_CONFIG.get('server_url', 'http://memsip.ru:5000')
        download_url = f"{server_url}/download_modpack"
        
        print(f"📥 Downloading modpack from: {download_url}")
        
        response = requests.get(download_url, stream=True, timeout=30)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        
        with open(zip_path, 'wb') as f:
            if total_size == 0:
                f.write(response.content)
            else:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
        
        print(f" Downloaded: {os.path.getsize(zip_path) / (1024*1024):.1f} MB")
        
        if os.path.exists(mods_folder):
            for file in os.listdir(mods_folder):
                file_path = os.path.join(mods_folder, file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except:
                    pass
        
        print(f" Extracting to: {mods_folder}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(mods_folder)
        
        mods = [f for f in os.listdir(mods_folder) if f.endswith('.jar')]
        print(f" Extracted {len(mods)} mods")
        
        CLIENT_CONFIG['last_checked'] = datetime.now().isoformat()
        CLIENT_CONFIG['total_mods'] = len(mods)
        
        try:
            stats_url = f"{server_url}/api/stats"
            stats_resp = requests.get(stats_url, timeout=5)
            if stats_resp.status_code == 200:
                stats = stats_resp.json()
                CLIENT_CONFIG['modpack_version'] = stats.get('modpack_version', '1.0')
        except:
            CLIENT_CONFIG['modpack_version'] = '1.0'
        
        save_config()
        
        try:
            os.remove(zip_path)
        except:
            pass
        
        return True, f"Installed {len(mods)} mods"
        
    except Exception as e:
        print(f" Error: {str(e)}")
        return False, str(e)

def check_updates():
    """Проверяет обновления"""
    try:
        server_url = CLIENT_CONFIG.get('server_url')
        response = requests.get(f"{server_url}/api/stats", timeout=5)
        
        if response.status_code == 200:
            server_data = response.json()
            server_version = server_data.get('modpack_version')
            client_version = CLIENT_CONFIG.get('modpack_version')
            
            mods_folder = get_mods_folder()
            has_mods = os.path.exists(mods_folder) and any(f.endswith('.jar') for f in os.listdir(mods_folder))
            
            if not has_mods or server_version != client_version:
                return True, server_data.get('total_mods', 0)
        
        return False, 0
    except:
        return False, 0

def create_minecraft_account(username):
    """Создает аккаунт Minecraft в формате PrismLauncher"""
    try:
        appdata = os.getenv('APPDATA')
        prism_path = os.path.join(appdata, 'PrismLauncher', 'accounts.json')
        
        profile_id = str(uuid.uuid4()).replace('-', '')
        client_token = str(uuid.uuid4()).replace('-', '')
        iat = int(time.time())
        
        account_data = {
            "accounts": [
                {
                    "entitlement": {
                        "canPlayMinecraft": True,
                        "ownsMinecraft": True
                    },
                    "profile": {
                        "capes": [],
                        "id": profile_id,
                        "name": username,
                        "skin": {
                            "id": "",
                            "url": "",
                            "variant": ""
                        }
                    },
                    "type": "Offline",
                    "ygg": {
                        "extra": {
                            "clientToken": client_token,
                            "userName": username
                        },
                        "iat": iat,
                        "token": "offline"
                    }
                }
            ],
            "formatVersion": 3
        }
        
        os.makedirs(os.path.dirname(prism_path), exist_ok=True)
        
        with open(prism_path, 'w', encoding='utf-8') as f:
            json.dump(account_data, f, indent=2)
        
        print(f" Created Minecraft account: {username}")
        print(f" Saved to: {prism_path}")
        return True
    except Exception as e:
        print(f" Could not create account: {e}")
        return False

# ==================== МАРШРУТЫ FLASK (БЕЗ ИЗМЕНЕНИЙ) ====================

@app.route('/')
def index():
    if not LAUNCHER_SETTINGS.get('username'):
        return redirect('/register')
    return render_template_string(HTML_TEMPLATE)

@app.route('/register')
def register_page():
    if LAUNCHER_SETTINGS.get('username'):
        return redirect('/')
    return render_template_string(REGISTER_TEMPLATE)

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username', '').strip()
    
    if not username or len(username) < 3 or len(username) > 16:
        return jsonify({'success': False, 'message': 'Username must be 3-16 characters'})
    
    LAUNCHER_SETTINGS['username'] = username
    save_settings()
    
    create_minecraft_account(username)
    
    return jsonify({'success': True})

@app.route('/launch', methods=['POST'])
def launch_game():
    username = LAUNCHER_SETTINGS.get('username')
    if not username:
        return jsonify({'success': False, 'message': 'Set username first'})
    
    prism_path = get_prismlauncher_path()
    if not prism_path:
        return jsonify({'success': False, 'message': 'PrismLauncher not found'})
    
    try:
        prism_exe = os.path.abspath(prism_path)
        cmd = f'"{prism_exe}" -l 1.12.2 -a {username} -s memsip.ru --alive'
        print(f"Launching: {cmd}")
        
        subprocess.Popen(cmd, shell=True)
        return jsonify({'success': True, 'message': 'Launching Minecraft...'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/reinstall_modpack', methods=['POST'])
def reinstall_modpack_route():
    try:
        success, message = download_modpack()
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/check_updates')
def check_updates_route():
    try:
        updates_available, mod_count = check_updates()
        return jsonify({
            'success': True,
            'updates_available': updates_available,
            'total_mods': mod_count
        })
    except:
        return jsonify({'success': False})

@app.route('/api/server_status')
def server_status():
    try:
        response = requests.get(f"{CLIENT_CONFIG['server_url']}/api/stats", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                'online': True,
                'version': data.get('modpack_version', '1.0'),
                'total_mods': data.get('total_mods', 0)
            })
    except:
        pass
    
    return jsonify({'online': False, 'version': 'unknown', 'total_mods': 0})

@app.route('/api/settings')
def get_settings():
    mods_folder = get_mods_folder()
    mod_count = 0
    if os.path.exists(mods_folder):
        mod_count = len([f for f in os.listdir(mods_folder) if f.endswith('.jar')])
    
    last_update = "Never"
    if CLIENT_CONFIG.get('last_checked'):
        try:
            dt = datetime.fromisoformat(CLIENT_CONFIG['last_checked'].replace('Z', '+00:00'))
            last_update = dt.strftime("%d.%m.%Y %H:%M")
        except:
            pass
    
    return jsonify({
        'username': LAUNCHER_SETTINGS.get('username'),
        'server_url': CLIENT_CONFIG.get('server_url'),
        'window_width': LAUNCHER_SETTINGS.get('window_width'),
        'window_height': LAUNCHER_SETTINGS.get('window_height'),
        'mod_count': mod_count,
        'last_update': last_update
    })

@app.route('/api/update_settings', methods=['POST'])
def update_settings():
    data = request.get_json()
    
    if 'username' in data:
        username = data['username'].strip()
        if username and 3 <= len(username) <= 16:
            LAUNCHER_SETTINGS['username'] = username
            create_minecraft_account(username)
    
    if 'server_url' in data:
        CLIENT_CONFIG['server_url'] = data['server_url']
        CLIENT_CONFIG['modpack_version'] = None
    
    if 'window_width' in data:
        LAUNCHER_SETTINGS['window_width'] = max(700, min(1920, int(data['window_width'])))
    
    if 'window_height' in data:
        LAUNCHER_SETTINGS['window_height'] = max(500, min(1080, int(data['window_height'])))
    
    save_settings()
    save_config()
    
    return jsonify({'success': True})

@app.route('/api/open_mods_folder', methods=['POST'])
def open_mods_folder():
    try:
        mods_folder = get_mods_folder()
        if os.path.exists(mods_folder):
            os.startfile(mods_folder)
            return jsonify({'success': True, 'message': 'Opened mods folder'})
        else:
            return jsonify({'success': False, 'message': 'Mods folder not found'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

def get_prismlauncher_path():
    """Находим путь к PrismLauncher"""
    possible_paths = [
        os.path.join("bin", "prismlauncher.exe"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "prismlauncher.exe"),
        os.path.join("..", "bin", "prismlauncher.exe"),
        "prismlauncher.exe",
        "bin/prismlauncher.exe"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            print(f" Found PrismLauncher: {path}")
            return path
    
    if os.path.exists("prismlauncher.exe"):
        print(" Found PrismLauncher in current directory")
        return "prismlauncher.exe"
    
    print(" PrismLauncher not found. Place prismlauncher.exe in bin/ folder.")
    return None

# ==================== ОСНОВНАЯ ФУНКЦИЯ ====================

def main():
    # Загружаем настройки
    load_settings()
    load_config()
    
    # Проверяем PrismLauncher
    prism_path = get_prismlauncher_path()
    
    print("=" * 60)
    print(" NaraLauncher v3.3 - SINGLE OVERLAY CONTROL")
    print("=" * 60)
    print(f" Server: {CLIENT_CONFIG['server_url']}")
    if LAUNCHER_SETTINGS.get('username'):
        print(f" Username: {LAUNCHER_SETTINGS['username']}")
    print(f" Mods folder: {get_mods_folder()}")
    if prism_path:
        print(f" PrismLauncher: Found")
    else:
        print(f"  PrismLauncher: Not found")
    print("-" * 60)
    print(" Overlay Control:")
    print(" • Press Tab to launch overlay")
    print(" • If overlay is running, Tab will be ignored")
    print(" • Only one instance of overlay can run at a time")
    print("=" * 60)
    
    # Запускаем Flask в отдельном потоке
    def run_flask():
        app.run(
            host='127.0.0.1',
            port=LAUNCHER_SETTINGS.get('server_port', 5001),
            debug=False,
            use_reloader=False,
            threaded=True
        )
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    time.sleep(1)
    
    # Создаем окно
    start_url = f"http://127.0.0.1:{LAUNCHER_SETTINGS.get('server_port', 5001)}"
    if not LAUNCHER_SETTINGS.get('username'):
        start_url += '/register'
    
    window = webview.create_window(
        'NaraLauncher',
        start_url,
        width=LAUNCHER_SETTINGS.get('window_width', 900),
        height=LAUNCHER_SETTINGS.get('window_height', 700),
        resizable=False
    )
    
    # Запускаем слушатель клавиши Tab
    print("👂 Starting Tab key listener...")
    tab_listener_thread = start_tab_listener()
    
    print("✅ Launcher is ready!")
    print("📋 Press Tab to launch overlay (single instance only)")
    
    # Запускаем веб-окно
    try:
        webview.start()
    except KeyboardInterrupt:
        print("\n🛑 Keyboard interrupt received")
    except Exception as e:
        print(f"❌ Error in webview: {e}")
    finally:
        # Очищаем при выходе
        print("\n🧹 Cleaning up...")
        print("👋 Goodbye!")

if __name__ == '__main__':
    main()