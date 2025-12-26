import os
import subprocess
import logging
import threading

class GameCompressor:
    def __init__(self):
        self.logger = logging.getLogger("Compressor")

    def compress(self, game_path, callback=None):
        if not os.path.exists(game_path):
            return {"error": "Path not found"}

        self.logger.info(f"Starting compression for {game_path}")
        
        initial_size = self._get_size(game_path)
        
        # Run compact in the directory to avoid path issues
        # Target all files (*) including hidden (/a) and subfolders (/s)
        cmd = ['compact.exe', '/c', '/s', '/a', '/i', '/exe:lzx', '*']
        
        try:
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                cwd=game_path,
                shell=False
            )
            
            stdout, stderr = process.communicate()
            
            # Note: compact.exe returns 0 even if some files failed (due to /i)
            # We check if it actually did anything
            final_size = self._get_size(game_path)
            saved = initial_size - final_size
            
            self.logger.info(f"Compression finished. Output: {stdout[:200]}...") # Log start of output
            
            return {
                "initial": initial_size,
                "final": final_size,
                "saved": saved,
                "ratio": (saved / initial_size) * 100 if initial_size > 0 else 0,
                "raw_output": stdout[-500:] # Return end of summary
            }
            
        except Exception as e:
            self.logger.error(f"Compression error: {e}")
            return {"error": str(e)}

    def _get_size(self, start_path):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(start_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                # skip if symbolic link
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
        return total_size
