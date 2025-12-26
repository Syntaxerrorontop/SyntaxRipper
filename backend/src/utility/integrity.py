import os
import hashlib
import logging

class IntegrityChecker:
    def __init__(self):
        self.logger = logging.getLogger("Integrity")

    def generate_hash(self, game_path, callback=None):
        if not os.path.exists(game_path):
            return {"error": "Path not found"}
            
        hash_file = os.path.join(game_path, "checksums.md5")
        
        try:
            hashes = {}
            total_files = sum([len(files) for r, d, files in os.walk(game_path)])
            processed = 0
            
            with open(hash_file, "w", encoding="utf-8") as f:
                for root, dirs, files in os.walk(game_path):
                    for file in files:
                        if file == "checksums.md5": continue
                        
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, game_path)
                        
                        file_hash = self._hash_file(full_path)
                        f.write(f"{file_hash} *{rel_path}\n")
                        
                        processed += 1
                        if callback: callback(processed, total_files)
                        
            return {"status": "generated", "count": processed}
        except Exception as e:
            self.logger.error(f"Hash gen failed: {e}")
            return {"error": str(e)}

    def verify_hash(self, game_path, callback=None):
        hash_file = os.path.join(game_path, "checksums.md5")
        if not os.path.exists(hash_file):
            return {"error": "No checksum file found. Generate one first."}
            
        mismatches = []
        missing = []
        
        try:
            lines = []
            with open(hash_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            total = len(lines)
            processed = 0
            
            for line in lines:
                parts = line.strip().split(" *")
                if len(parts) != 2: continue
                
                expected_hash = parts[0]
                rel_path = parts[1]
                full_path = os.path.join(game_path, rel_path)
                
                if not os.path.exists(full_path):
                    missing.append(rel_path)
                else:
                    actual_hash = self._hash_file(full_path)
                    if actual_hash != expected_hash:
                        mismatches.append(rel_path)
                
                processed += 1
                if callback: callback(processed, total)
                
            return {
                "status": "verified",
                "total": total,
                "mismatches": mismatches,
                "missing": missing,
                "ok": (len(mismatches) == 0 and len(missing) == 0)
            }
            
        except Exception as e:
            return {"error": str(e)}

    def _hash_file(self, path):
        md5 = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5.update(chunk)
        return md5.hexdigest()
