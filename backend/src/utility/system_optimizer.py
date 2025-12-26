import subprocess
import logging
import psutil
import re

class SystemOptimizer:
    def __init__(self):
        self.logger = logging.getLogger("SystemOptimizer")
        self.original_plan = None
        self._find_plans()

    def _find_plans(self):
        # Cache GUIDs for Balanced and High Performance
        self.plans = {}
        try:
            output = subprocess.check_output("powercfg /list", text=True)
            for line in output.splitlines():
                match = re.search(r"GUID: ([0-9a-fA-F-]+) \s*\((.+)\)", line)
                if match:
                    guid, name = match.groups()
                    if "*" in line:
                        self.original_plan = guid
                    self.plans[name.lower()] = guid
        except Exception as e:
            self.logger.error(f"Power plan discovery failed: {e}")

    def optimize(self, game_process=None):
        self.logger.info("Enabling Gaming Mode...")
        
        # 1. Power Plan -> High Performance
        high_perf = None
        for name, guid in self.plans.items():
            if "high performance" in name or "höchstleistung" in name:
                high_perf = guid
                break
        
        if high_perf:
            try:
                subprocess.run(f"powercfg /setactive {high_perf}", check=True)
                self.logger.info(f"Power plan set to High Performance ({high_perf})")
            except: pass
        
        # 2. Process Priority
        if game_process:
            try:
                game_process.nice(psutil.HIGH_PRIORITY_CLASS)
                self.logger.info(f"Game process priority set to HIGH")
            except Exception as e:
                self.logger.warning(f"Could not set process priority: {e}")

    def revert(self):
        self.logger.info("Disabling Gaming Mode...")
        if self.original_plan:
            try:
                subprocess.run(f"powercfg /setactive {self.original_plan}", check=True)
                self.logger.info(f"Power plan reverted to {self.original_plan}")
            except: pass
