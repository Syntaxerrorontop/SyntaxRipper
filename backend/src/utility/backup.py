import os
import shutil
import time
import zipfile
import logging
from .utility_vars import APPDATA_CACHE_PATH

class SaveBackupManager:
    def __init__(self):
        self.backup_root = os.path.join(APPDATA_CACHE_PATH, "Backups")
        if not os.path.exists(self.backup_root):
            os.makedirs(self.backup_root)
        self.logger = logging.getLogger("SaveBackup")

    def create_backup(self, game_name, save_path):
        if not save_path or not os.path.exists(save_path):
            return None
        
        try:
            game_backup_dir = os.path.join(self.backup_root, game_name)
            if not os.path.exists(game_backup_dir):
                os.makedirs(game_backup_dir)
            
            timestamp = int(time.time())
            archive_name = os.path.join(game_backup_dir, f"{timestamp}")
            
            shutil.make_archive(archive_name, 'zip', save_path)
            self.logger.info(f"Backup created for {game_name}: {archive_name}.zip")
            return f"{archive_name}.zip"
        except Exception as e:
            self.logger.error(f"Backup failed for {game_name}: {e}")
            return None

    def list_backups(self, game_name):
        game_backup_dir = os.path.join(self.backup_root, game_name)
        if not os.path.exists(game_backup_dir):
            return []
        
        backups = []
        for f in os.listdir(game_backup_dir):
            if f.endswith(".zip"):
                try:
                    ts = int(f.replace(".zip", ""))
                    backups.append({
                        "filename": f,
                        "timestamp": ts,
                        "date": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts)),
                        "path": os.path.join(game_backup_dir, f)
                    })
                except: pass
        
        return sorted(backups, key=lambda x: x["timestamp"], reverse=True)

    def restore_backup(self, game_name, save_path, backup_filename):
        if not save_path or not os.path.exists(save_path):
            self.logger.error("Restore target path invalid.")
            return False
            
        backup_path = os.path.join(self.backup_root, game_name, backup_filename)
        if not os.path.exists(backup_path):
            return False
            
        try:
            # Clear existing saves? Optional, but safer to avoid conflicts
            # For now, we overwrite
            shutil.unpack_archive(backup_path, save_path)
            self.logger.info(f"Restored backup {backup_filename} to {save_path}")
            return True
        except Exception as e:
            self.logger.error(f"Restore failed: {e}")
            return False
