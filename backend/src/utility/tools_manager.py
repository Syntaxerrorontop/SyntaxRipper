import os
import shutil
import json
import requests
import zipfile
import subprocess
import logging
from .utility_vars import APPDATA_CACHE_PATH

TOOLS_CONFIG = {
    "ffmpeg": {
        "name": "FFmpeg",
        "url": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "check_file": "ffmpeg.exe",
        "subfolder": "ffmpeg/bin", # It extracts to a folder usually
        "is_zip": True
    },
    "vc_redist": {
        "name": "Visual C++ Redistributable AIO",
        "url": "https://github.com/abbodi1406/vcredist/releases/latest/download/VisualCppRedist_AIO_x86_x64.zip",
        "check_file": "VisualCppRedist_AIO_x86_x64.exe",
        "subfolder": "vc_redist",
        "is_zip": True,
        # "install_script": "install_all.bat" # Optional now
    }
}

class ToolsManager:
    def __init__(self):
        self.logger = logging.getLogger("ToolsManager")
        self.tools_dir = os.path.join(APPDATA_CACHE_PATH, "Tools")
        if not os.path.exists(self.tools_dir):
            os.makedirs(self.tools_dir)
        
        self.status_file = os.path.join(self.tools_dir, "tools.json")
        self.installed_tools = self._load_status()

    def _load_status(self):
        if os.path.exists(self.status_file):
            with open(self.status_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_status(self):
        with open(self.status_file, 'w') as f:
            json.dump(self.installed_tools, f)

    def get_status(self):
        # Verify physical existence
        status = {}
        for key, conf in TOOLS_CONFIG.items():
            path = self._get_tool_path(key)
            installed = False
            if path and os.path.exists(path):
                installed = True
            
            # If we think it's installed but file missing, update
            if self.installed_tools.get(key) and not installed:
                self.installed_tools[key] = False
                self._save_status()
            
            status[key] = {
                "name": conf["name"],
                "installed": installed,
                "path": path
            }
        return status

    def _get_tool_path(self, key):
        if key == "ffmpeg":
            # FFmpeg extracts to a folder like 'ffmpeg-6.0-essentials_build', we need to find it
            base = os.path.join(self.tools_dir, "ffmpeg")
            if os.path.exists(base):
                for root, dirs, files in os.walk(base):
                    if "ffmpeg.exe" in files:
                        return os.path.join(root, "ffmpeg.exe")
            return None
        elif key == "vc_redist":
            # Check for EXE first (common in newer repack zips)
            base = os.path.join(self.tools_dir, "vc_redist")
            exe_path = os.path.join(base, "VisualCppRedist_AIO_x86_x64.exe")
            if os.path.exists(exe_path):
                return exe_path
            # Check for BAT (older zips)
            bat_path = os.path.join(base, "install_all.bat")
            if os.path.exists(bat_path):
                return bat_path
        return None

    def install_tool(self, key):
        if key not in TOOLS_CONFIG:
            return False
        
        conf = TOOLS_CONFIG[key]
        target_dir = os.path.join(self.tools_dir, key if key != "ffmpeg" else "ffmpeg_temp")
        
        try:
            download_url = conf["url"]
            
            # Dynamic GitHub Asset Resolution for VC Redist
            if key == "vc_redist" and "github.com" in download_url and "latest" in download_url:
                try:
                    api_url = download_url.replace("github.com", "api.github.com/repos").replace("releases/latest/download", "releases/latest").split(".zip")[0]
                    # Clean up the URL construction hack:
                    # Target: https://api.github.com/repos/abbodi1406/vcredist/releases/latest
                    api_url = "https://api.github.com/repos/abbodi1406/vcredist/releases/latest"
                    
                    self.logger.info(f"Resolving latest VC++ asset from {api_url}...")
                    resp = requests.get(api_url)
                    if resp.status_code == 200:
                        assets = resp.json().get("assets", [])
                        for asset in assets:
                            if asset["name"].endswith(".zip"):
                                download_url = asset["browser_download_url"]
                                self.logger.info(f"Resolved to: {download_url}")
                                break
                except Exception as e:
                    self.logger.warning(f"Failed to resolve dynamic URL, trying default: {e}")

            self.logger.info(f"Downloading {conf['name']}...")
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            os.makedirs(target_dir)
            
            zip_path = os.path.join(target_dir, "tool.zip")
            
            with requests.get(download_url, stream=True) as r:
                r.raise_for_status()
                with open(zip_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            self.logger.info(f"Extracting {conf['name']}...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(target_dir)
            
            os.remove(zip_path)
            
            # Post-processing: Handle nested folders
            # Check if the expected file is in a subdirectory
            expected_file = conf.get("install_script") or conf.get("check_file")
            if expected_file:
                found_path = None
                for root, dirs, files in os.walk(target_dir):
                    if expected_file in files:
                        found_path = root
                        break
                
                if found_path and found_path != target_dir:
                    self.logger.info(f"Found nested tool in {found_path}, moving to root...")
                    # Move all items from found_path to target_dir
                    for item in os.listdir(found_path):
                        shutil.move(os.path.join(found_path, item), target_dir)
                    # Clean up empty folders? Optional, but safer to leave or delete specifically if known
            
            # Post-processing special cases
            if key == "ffmpeg":
                # Rename temp folder to final
                final_dir = os.path.join(self.tools_dir, "ffmpeg")
                if os.path.exists(final_dir): shutil.rmtree(final_dir)
                os.rename(target_dir, final_dir)
            
            self.installed_tools[key] = True
            self._save_status()
            self.logger.info(f"{conf['name']} installed successfully.")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to install {key}: {e}")
            return False

    def run_vc_install(self):
        path = self._get_tool_path("vc_redist")
        if path and os.path.exists(path):
            self.logger.info(f"Running VC++ Installer: {path}")
            
            # Determine args based on file type
            args = ""
            if path.endswith(".exe"):
                args = "/ai" # Auto Install for abbodi exe
            
            import ctypes
            try:
                # ShellExecuteW(hwnd, verb, file, params, directory, showcmd)
                ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", path, args, os.path.dirname(path), 1)
                return ret > 32
            except Exception as e:
                self.logger.error(f"VC++ Install launch failed: {e}")
                return False
        return False
