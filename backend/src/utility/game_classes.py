import logging
import os
import time
import subprocess
import psutil
import threading

from .utility_functions import _get_version_steamrip, save_json, load_json
from .utility_vars import CONFIG_FOLDER
from .SaveDetector import SavePathDetector
from .backup import SaveBackupManager
from .scripts import ScriptExecutor
from .rpc import DiscordRPCManager
from .system_optimizer import SystemOptimizer

class GameInstance:
    def __init__(self, name, path, args, parent_game):
        self.game_name = name
        self.executable_path = path
        self.logger = logging.getLogger('GameInstance')
        self.parent_game = parent_game
        self.abort_detection = threading.Event()
        
        # Resolve absolute path if relative
        if not os.path.isabs(path) and os.path.exists(os.path.join(os.getcwd(), path)):
            self.executable_path = os.path.join(os.getcwd(), path)
        
        self._start_time: float = 0
        self.args = args if args else []
        self._process = None
        self.backup_manager = SaveBackupManager()
        self.script_executor = ScriptExecutor()
        self.rpc_manager = DiscordRPCManager()
        self.optimizer = SystemOptimizer()
    
    def start(self, dry_launch=False):
        if self.parent_game.is_running:
            return
        
        # Pre-Launch Script
        self._execute_script("pre_launch_script", "pre-launch")

        self.parent_game.is_running = True
        self.abort_detection.clear()
        self._start_time = time.time()
        
        # Check for URL-based games (Steam/Uplay/Web)
        if self.executable_path.startswith(("steam://", "uplay://", "http")):
            try:
                os.startfile(self.executable_path)
                # For external URL games, we can't easily track process/playtime yet
                # So we just mark as running briefly then stop
                threading.Timer(5.0, self._set_not_running).start()
                return
            except Exception as e:
                self.logger.error(f"Failed to launch URL game: {e}")
                self.parent_game.is_running = False
                return

        # Normal EXE Launch
        try:
            run_data = [self.executable_path] + self.args
            cwd = os.path.dirname(self.executable_path)
            self._process = subprocess.Popen(run_data, cwd=cwd)
            
            # --- Features: RPC & Gaming Mode ---
            userconfig = load_json(os.path.join(CONFIG_FOLDER, "userconfig.json"))
            
            if userconfig.get("gaming_mode_enabled", True):
                try:
                    p = psutil.Process(self._process.pid)
                    self.optimizer.optimize(p)
                except: pass

            if userconfig.get("discord_rpc_enabled", True):
                self.rpc_manager.update(
                    details=f"Playing {self.game_name}",
                    state="In Game",
                    start_time=time.time()
                )
            # -----------------------------------

            # Start Wait Thread
            threading.Thread(target=self.wait, daemon=True).start()
            
        except Exception as e:
            self.logger.error(f"Failed to launch game executable: {e}")
            self.parent_game.is_running = False
            return

        if dry_launch:
            self.logger.info("Dry Launch enabled: Skipping Save Detection.")
            return

        # Background Save Detection
        threading.Thread(target=self._run_background_detection, daemon=True).start()

    def _set_not_running(self):
        self.parent_game.is_running = False

    def _run_background_detection(self):
        try:
            exe_name = os.path.basename(self.executable_path)
            detector = SavePathDetector()
            candidates = detector.detect(exe_name, timeout=120, abort_event=self.abort_detection)
            
            if candidates:
                # Top candidate is the default
                save_path = candidates[0]
                self.logger.info(f"✅ Save path detected: {save_path}")
                
                config_path = os.path.join(CONFIG_FOLDER, "games.json")
                data = load_json(config_path)
                if self.game_name in data:
                    data[self.game_name]["save_path"] = save_path
                    data[self.game_name]["save_candidates"] = candidates
                    save_json(config_path, data)
        except Exception as e:
            self.logger.error(f"Background detection error: {e}")

    def wait(self):
        if self._process:
            self._process.wait()
            played_time = time.time() - self._start_time
            
            # Abort detection if game closed too fast (crash or manual close)
            if played_time < 15:
                self.logger.info(f"Game closed quickly ({played_time:.1f}s). Aborting detection.")
                self.abort_detection.set()
            
            self.update_playtime(played_time)
        
        # Cleanup features
        self.optimizer.revert()
        self.rpc_manager.clear()
        self.rpc_manager.close()
        
        self.parent_game.is_running = False

    def _execute_script(self, config_key, phase):
        try:
            config_path = os.path.join(CONFIG_FOLDER, "games.json")
            data = load_json(config_path)
            if self.game_name in data:
                script_content = data[self.game_name].get(config_key, "")
                if script_content:
                    self.script_executor.execute(script_content, self.game_name, phase)
        except Exception as e:
            self.logger.error(f"Failed to execute {phase} script: {e}")

    def close(self):
        self.abort_detection.set()
        
        # Cleanup features
        self.optimizer.revert()
        self.rpc_manager.clear()
        self.rpc_manager.close()

        # Post-Exit Script
        self._execute_script("post_exit_script", "post-exit")
        
        # Auto-Backup Save
        try:
            config_path = os.path.join(CONFIG_FOLDER, "games.json")
            data = load_json(config_path)
            if self.game_name in data:
                save_path = data[self.game_name].get("save_path")
                if save_path:
                    self.backup_manager.create_backup(self.game_name, save_path)
        except Exception as e:
            self.logger.error(f"Auto-backup failed: {e}")

        if not self._process:
            return
        try:
            parent = psutil.Process(self._process.pid)
            for child in parent.children(recursive=True):
                child.terminate()
            parent.terminate()
        except psutil.NoSuchProcess:
            pass
        self._process = None
    
    def update_playtime(self, playtime: float):
        config_path = os.path.join(CONFIG_FOLDER, "games.json")
        data = load_json(config_path)
        if self.game_name in data:
            old_playtime = float(data[self.game_name].get("playtime", 0))
            data[self.game_name]["playtime"] = int(old_playtime + playtime)
            save_json(config_path, data)

class Game:
    def __init__(self, name, info, installed=False):
        self.name = name
        self.alias = info.get("alias", name)
        self.version = info.get("version", "N/A")
        self.start_path = info.get("exe", "")
        self.args = info.get("args", [])
        self.playtime = info.get("playtime", 0)
        self.is_running = False
        self.is_installed = installed
        
        if installed and self.start_path:
            self.run_instance = GameInstance(name, self.start_path, self.args, self)
        else:
            self.run_instance = None
    
    def start(self, dry_launch=False):
        if self.run_instance:
            self.run_instance.start(dry_launch=dry_launch)
            return True
        return False

    def stop(self):
        if self.run_instance:
            self.run_instance.close()
