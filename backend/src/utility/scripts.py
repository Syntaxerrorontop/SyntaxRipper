import subprocess
import logging
import os

class ScriptExecutor:
    def __init__(self):
        self.logger = logging.getLogger("ScriptExecutor")

    def execute(self, script_content, game_name, phase="pre-launch"):
        if not script_content or not script_content.strip():
            return
        
        self.logger.info(f"Executing {phase} script for {game_name}...")
        try:
            # Determine if it's a simple command or a block
            # We'll run it as a temporary batch file to support multiple lines
            temp_script = f"temp_{phase}_{int(os.times().system)}.bat"
            with open(temp_script, "w") as f:
                f.write("@echo off\n")
                f.write(script_content)
            
            subprocess.run([temp_script], shell=True, check=True)
            
            try:
                os.remove(temp_script)
            except: pass
            
            self.logger.info(f"{phase} script executed successfully.")
        except Exception as e:
            self.logger.error(f"{phase} script failed: {e}")
