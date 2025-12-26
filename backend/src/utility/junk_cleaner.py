import os
import logging
import shutil

class JunkCleaner:
    def __init__(self):
        self.logger = logging.getLogger("JunkCleaner")
        self.junk_folders = ["_CommonRedist", "Redist", "DirectX", "vcredist", "Support"]
        self.junk_extensions = [".tmp", ".log", ".bak"]
        self.junk_files = ["setup.exe", "installer.exe", "autorun.inf"]

    def scan(self, game_path):
        if not os.path.exists(game_path):
            return []
            
        found = []
        
        # Scan
        for root, dirs, files in os.walk(game_path):
            # Check folders
            for d in dirs:
                if d in self.junk_folders:
                    found.append({"path": os.path.join(root, d), "type": "folder", "name": d})
            
            # Check files
            for f in files:
                if f.lower() in self.junk_files or os.path.splitext(f)[1].lower() in self.junk_extensions:
                    found.append({"path": os.path.join(root, f), "type": "file", "name": f})
                    
        return found

    def clean(self, items):
        deleted = 0
        failed = 0
        for item in items:
            path = item["path"]
            try:
                if os.path.exists(path):
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    deleted += 1
            except:
                failed += 1
        return deleted, failed
