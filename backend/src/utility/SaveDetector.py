import os
import subprocess
import time
import csv
import logging
import shutil
from pathlib import Path
from collections import Counter
from .utility_vars import CACHE_FOLDER

class SavePathDetector:
    def __init__(self, procmon_path=None):
        self.logger = logging.getLogger("SaveDetector")
        self.procmon = procmon_path if procmon_path else self._find_tool("Procmon.exe")
        
        self.temp_dir = os.path.join(CACHE_FOLDER, "DetectionLogs")
        os.makedirs(self.temp_dir, exist_ok=True)
        
        self.logfile = os.path.join(self.temp_dir, "game_log.pml")
        self.csvfile = os.path.join(self.temp_dir, "game_log.csv")

    def _find_tool(self, tool_name):
        """Locates a tool in PATH or specific common locations."""
        path = shutil.which(tool_name)
        if path:
            return path
        cwd_path = os.path.join(os.getcwd(), tool_name)
        if os.path.exists(cwd_path):
            return cwd_path
        return tool_name

    def detect(self, game_exe_name, timeout=120, abort_event=None):
        self._cleanup()
        try:
            self.logger.info(f"Starting Process Monitor scan for {timeout}s...")
            cmd_start_procmon = [
                self.procmon,
                f"/BackingFile", self.logfile,
                "/AcceptEula", "/Quiet", "/Minimized"
            ]
            subprocess.Popen(cmd_start_procmon)
            
            # Wait with abort check
            start_time = time.time()
            while time.time() - start_time < timeout:
                if abort_event and abort_event.is_set():
                    self.logger.info("Detection aborted by game exit.")
                    break
                time.sleep(1)

            self.logger.info("Stopping Process Monitor scan...")
            subprocess.run([self.procmon, "/Terminate"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2) 

            # Check if aborted before proceeding to heavy export tasks
            if abort_event and abort_event.is_set():
                self.logger.info("Killing Process Monitor forcefully due to abort...")
                subprocess.run(["taskkill", "/F", "/IM", "Procmon.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._cleanup()
                return None

            self.logger.info("Exporting log to CSV...")
            cmd_export = [
                self.procmon,
                f"/OpenLog", self.logfile,
                f"/SaveAs", self.csvfile,
                "/AcceptEula", "/Quiet", "/Minimized"
            ]
            subprocess.run(cmd_export, check=True)
            
            if not os.path.exists(self.csvfile):
                self.logger.error("CSV export failed.")
                return None

            self.logger.info("Parsing results...")
            return self._parse_log(self.csvfile, game_exe_name)

        except Exception as e:
            self.logger.error(f"Error during detection: {e}")
            return None

    def _cleanup(self):
        if os.path.exists(self.logfile):
            try: os.remove(self.logfile)
            except: pass
        if os.path.exists(self.csvfile):
            try: os.remove(self.csvfile)
            except: pass

    def _parse_log(self, csv_path, target_process_name):
        exclude_prefixes = [
            r"C:\Windows".upper(),
            r"C:\Program Files".upper(),
            r"C:\ProgramData".upper(),
            os.getcwd().upper(),
            r"C:\$",
        ]
        exclude_keywords = ["NVIDIA", "GLCache", "Unreal Engine", "CurrentControlSet", "Windows NT", "Microsoft", "Steam"]

        def is_excluded(path_str):
            p = path_str.upper()
            if len(p) < 3: return True 
            if p.startswith(r"C:\$") or p.startswith(r"D:\$"): return True
            if any(p.startswith(e) for e in exclude_prefixes): return True
            if any(k.upper() in p for k in exclude_keywords): return True
            return False

        file_paths = []
        
        try:
            with open(csv_path, newline="", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Process Name", "").lower() != target_process_name.lower():
                        continue
                    
                    path = row.get("Path", "")
                    if not path or is_excluded(path):
                        continue
                        
                    op = row.get("Operation", "")
                    if op in ["CreateFile", "WriteFile", "DeleteFile"]:
                        try:
                            p_obj = Path(path)
                            if "Users" in p_obj.parts or "Documents" in p_obj.parts or "AppData" in p_obj.parts or "Saved Games" in p_obj.parts:
                                file_paths.append(p_obj)
                        except:
                            pass

            if not file_paths:
                return None

            parents = []
            for p in file_paths:
                try:
                    if len(p.parts) > 2:
                        parents.append(p.parent.parent)
                    else:
                        parents.append(p.parent)
                except: pass
            
            if not parents:
                return []

            counts = Counter(parents)
            # Return top 3 candidates as strings
            return [str(p) for p, c in counts.most_common(3)]

        except Exception as e:
            self.logger.error(f"Error parsing CSV: {e}")
            return []
