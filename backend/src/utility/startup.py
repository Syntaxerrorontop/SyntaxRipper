import os
import shutil
import logging
import time
import subprocess
import ctypes
from .utility_functions import load_json, save_json
from .utility_vars import CONFIG_FOLDER, CACHE_FOLDER

logger = logging.getLogger("Startup")

def run_startup_tasks():
    info_path = os.path.join(CONFIG_FOLDER, "programm_info.json")
    if os.path.exists(info_path):
        programm_info = load_json(info_path)
    else:
        programm_info = {}

    # 1. Legacy Cache
    if not programm_info.get("legacy_cache_cleared"):
        migrate_legacy_cache()
        programm_info["legacy_cache_cleared"] = True
        save_json(info_path, programm_info)

    # 2. Fix Config
    if not programm_info.get("fixxed_config"):
        fix_config()
        programm_info["fixxed_config"] = True
        save_json(info_path, programm_info)

    # 3. Cleanup Folders
    # Always check for these, as they are "unnecessary" and should not exist locally
    delete_unnecessary_folders()
    if not programm_info.get("unaccessary_folder"):
        programm_info["unaccessary_folder"] = True
        save_json(info_path, programm_info)

    # 4. Defender Exclusion (Simplified for headless)
    if not programm_info.get("excluded") and programm_info.get("allow_exclusion_request"):
        logger.info("Windows Defender exclusion not set. Run manually if needed.")

def migrate_legacy_cache():
    """
    Deletes legacy flat cache files (images in root of Cache folder).
    Forces the new folder-based metadata system to re-fetch assets.
    """
    logger.info("Migrating legacy cache (cleaning up old images)...")
    if not os.path.exists(CACHE_FOLDER):
        return

    count = 0
    for filename in os.listdir(CACHE_FOLDER):
        file_path = os.path.join(CACHE_FOLDER, filename)
        if os.path.isfile(file_path):
            # Check for image extensions
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                try:
                    os.remove(file_path)
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to remove legacy cache file {filename}: {e}")
    
    if count > 0:
        logger.info(f"Removed {count} legacy cache files. Metadata will be re-fetched.")

def fix_config():
    games_json_path = os.path.join(CONFIG_FOLDER, "games.json")
    if not os.path.exists(games_json_path):
        return

    config_games = load_json(games_json_path)
    
    # 1. Fix Nested "Games" Key
    if "Games" in config_games.keys():
        logger.warning("Config corrupted (nested 'Games' key found). Fixing...")
        
        games_from_key = config_games["Games"]
        
        for key, item in games_from_key.items():
            if key not in config_games:
                config_games[key] = item
            else:
                try:
                    if isinstance(item, list):
                        continue
                    
                    # Merge logic
                    game = config_games[key]
                    if isinstance(game, dict) and isinstance(item, dict):
                        # Merge playtime/categories if simple append
                        if "playtime" in item:
                            game["playtime"] = game.get("playtime", 0) + item["playtime"]
                        if "categorys" in item:
                            current_cats = game.get("categorys", [])
                            game["categorys"] = list(set(current_cats + item["categorys"]))
                        
                        # Merge critical fields if missing/empty
                        for field in ["args", "exe", "link", "alias", "version"]:
                            if not game.get(field) and item.get(field):
                                game[field] = item[field]
                        
                        config_games[key] = game
                except Exception as e:
                    logger.error(f"Error merging key {key}: {e}")
                
        config_games.pop("Games", None)
        logger.info("Config structure fixed.")

    # 2. Fix Paths (Strip "Games/" prefix)
    changes_made = False
    for key, game in config_games.items():
        if isinstance(game, dict):
            exe = game.get("exe", "")
            if exe and (exe.startswith("Games/") or exe.startswith("Games\\")):
                new_exe = exe[6:] # Remove 'Games/'
                # Remove extra slash if present
                if new_exe.startswith("/") or new_exe.startswith("\\"):
                    new_exe = new_exe[1:]
                
                game["exe"] = new_exe
                config_games[key] = game
                logger.info(f"Fixed path for {key}: {exe} -> {new_exe}")
                changes_made = True
    
    if "Games" in config_games or changes_made:
        save_json(games_json_path, config_games)
        logger.info("Config saved with fixes.")

def delete_unnecessary_folders():
    """
    Deletes legacy folders (.Meta, Cached, Assets, Config) from the local directory 
    and the project root if they exist. 
    (V3 uses AppData, so these are garbage from V2/Legacy)
    """
    folders_to_delete = [".Meta", "Cached", "Assets", "Config"]
    
    # Check Current Dir (backend/) and Parent Dir (v3/)
    cwd = os.getcwd()
    parent_dir = os.path.dirname(cwd)
    search_paths = [cwd, parent_dir]

    logger.info(f"Scanning for legacy folders in: {search_paths}")

    for base_path in search_paths:
        if not os.path.exists(base_path): continue
        
        for folder in folders_to_delete:
            folder_path = os.path.join(base_path, folder)
            
            # Safety check: Don't delete if it resolves to our actual active AppData paths
            # (In case user is running in portable mode or mapped weirdly)
            try:
                abs_path = os.path.abspath(folder_path)
                if (abs_path == os.path.abspath(CONFIG_FOLDER) or 
                    abs_path == os.path.abspath(CACHE_FOLDER)):
                    continue
            except: pass

            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                try:
                    shutil.rmtree(folder_path)
                    logger.info(f"Deleted legacy folder: {folder_path}")
                except OSError as e:
                    logger.error(f"Error deleting {folder}: {e}")