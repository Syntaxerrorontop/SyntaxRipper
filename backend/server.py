import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio
import logging
import os
import signal
import sys
import psutil
import time
import threading
import json
import re
import urllib.parse
import queue
from contextlib import asynccontextmanager

# Force UTF-8 for stdout/stderr to handle emojis on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Local imports
from src.scraper import UniversalScraper
from src.DownloadManager import AsyncDownloadManager
from src.Searcher import Searcher
from src.utility.utility_functions import load_json, save_json, hash_url, get_name_from_url, _game_naming
from src.utility.utility_vars import CONFIG_FOLDER, CACHE_FOLDER, APPDATA_CACHE_PATH, APP_VERSION
from src.utility.ExternalLibraryScanner import ExternalLibraryScanner
from src.utility.utility_classes import UserConfig
from src.utility.game_classes import Game
from src.utility.startup import run_startup_tasks
from src.utility.metadata import MetadataFetcher
from src.utility.config_updater import update_game_configs
from src.utility.backup import SaveBackupManager
from src.utility.scripts import ScriptExecutor
from src.utility.hltb import HLTBFetcher
from src.utility.debrid import DebridManager
from src.utility.tools_manager import ToolsManager
from src.utility.compression import GameCompressor
from src.utility.integrity import IntegrityChecker
from src.utility.junk_cleaner import JunkCleaner
from src.utility.media_converter import MediaConverter

# Configure logging
log_file = os.path.join(APPDATA_CACHE_PATH, "server.log")
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("Server")

# Global State
scraper = None
download_manager = None
metadata_fetcher = None
save_backup_manager = SaveBackupManager()
script_executor = ScriptExecutor()
hltb_fetcher = HLTBFetcher()
debrid_manager = DebridManager()
tools_manager = ToolsManager()
game_compressor = GameCompressor()
integrity_checker = IntegrityChecker()
junk_cleaner = JunkCleaner()
active_websockets = []
parent_pid = None
loop = None
scraper_ready = False
active_games = {} # {game_id: GameInstance}
metadata_queue = queue.Queue()

def run_metadata_scan():
    """Background task to queue metadata fetch for all games."""
    if not metadata_fetcher:
        logger.warning("Metadata fetcher not initialized.")
        return
    
    if not metadata_fetcher.api_key:
        logger.info("No RAWG API Key found. Metadata scan skipped.")
        return
    
    logger.info("Queuing metadata background scan...")
    names_to_scan = set()
    
    try:
        config_path = os.path.join(CONFIG_FOLDER, "games.json")
        if os.path.exists(config_path):
            config_games = load_json(config_path)
            for info in config_games.values():
                name = info.get("name") or info.get("alias")
                if name: names_to_scan.add(name)
    except Exception as e:
        logger.error(f"Error reading games config for scan: {e}")
    
    try:
        scanner = ExternalLibraryScanner()
        ext_games = scanner.scan()
        for g in ext_games:
            names_to_scan.add(g["name"])
    except Exception as e:
        logger.error(f"Error scanning external libraries: {e}")
    
    logger.info(f"Found {len(names_to_scan)} unique games to check for metadata.")
    
    for name in names_to_scan:
        metadata_queue.put(name)

def metadata_worker():
    """Worker thread that processes the metadata queue."""
    logger.info("Metadata worker started.")
    while True:
        try:
            game_name = metadata_queue.get()
            if game_name is None: break # Sentinel
            
            # Check if metadata fetcher is ready
            if metadata_fetcher and metadata_fetcher.api_key:
                # Fetch (blocking)
                data = metadata_fetcher.get_metadata(game_name, cached_only=False)
                if data:
                    # Notify frontend to refresh library (or specific game if we add that logic)
                    broadcast_event("complete", {"message": f"Metadata updated for {game_name}"})
            
            metadata_queue.task_done()
            time.sleep(1.0) # Rate limit to avoid hitting API limits
            
        except Exception as e:
            logger.error(f"Metadata worker error: {e}")
            time.sleep(1)

def check_updates_task():
    """Background task to check for game updates."""
    time.sleep(30) # Initial delay
    while True:
        try:
            # Check if scraper is ready before attempting anything
            if scraper_ready:
                user_config = UserConfig(CONFIG_FOLDER, "userconfig.json")
                logger.info("Running update check...")
                
                # Fetch full list once
                versions_map = Searcher.fetch_versions_map(scraper)
                
                if versions_map:
                    config_path = os.path.join(CONFIG_FOLDER, "games.json")
                    if os.path.exists(config_path):
                        games_config = load_json(config_path)
                        updates_found = 0
                        
                        for game_hash, info in games_config.items():
                            url = info.get("link", "")
                            current_version = info.get("version", "N/A")
                            
                            # Only check installed SteamRIP games
                            if "steamrip.com" in url and current_version != "N/A" and "Pending" not in current_version:
                                try:
                                    # Normalize URL to key (e.g., https://steamrip.com/foo/ -> /foo/)
                                    parsed = urllib.parse.urlparse(url)
                                    key = parsed.path
                                    if not key.endswith("/"): key += "/"
                                    
                                    raw_title = versions_map.get(key)
                                    if raw_title:
                                        # Extraction: "split at Free Download then part 1..."
                                        part1 = raw_title.split("Free Download")[0]
                                        match = re.search(r"\((.*?)\)", part1)
                                        
                                        if match:
                                            latest_version = match.group(1).strip()
                                            
                                            # Normalize for comparison
                                            norm_latest = latest_version.lower().replace(" ", "")
                                            norm_current = current_version.lower().replace(" ", "")
                                            
                                            # Check mismatch: 
                                            # If the website version (norm_latest) is NOT inside our local version (norm_current),
                                            # we consider it an update (or at least a difference worth flagging).
                                            if norm_latest not in norm_current:
                                                # Avoid spamming logs/broadcasts if already flagged
                                                was_flagged = info.get("update_available", False)
                                                
                                                if not was_flagged or info.get("latest_version") != latest_version:
                                                    logger.info(f"Update available for {info['alias']}: {current_version} -> {latest_version}")
                                                    
                                                    games_config[game_hash]["latest_version"] = latest_version
                                                    games_config[game_hash]["update_available"] = True
                                                    updates_found += 1
                                                    
                                                    broadcast_event("update_available", {
                                                        "id": game_hash,
                                                        "name": info["alias"],
                                                        "current": current_version,
                                                        "latest": latest_version
                                                    })

                                                # Auto-Update Logic
                                                if user_config.AUTO_UPDATE_GAMES:
                                                    # Check if already in queue to avoid duplicates
                                                    queue = download_manager.get_queue()
                                                    if not any(item['hash'] == game_hash for item in queue):
                                                        logger.info(f"Auto-update enabled. Starting download for {info['alias']}...")
                                                        download_manager.start_download(url, "auto_update", info["alias"])
                                            
                                            else:
                                                # Versions match (norm_latest is in norm_current), clear flag if it was set
                                                if info.get("update_available", False):
                                                    logger.info(f"Version match for {info['alias']} ({current_version}). Clearing update flag.")
                                                    games_config[game_hash]["update_available"] = False
                                                    games_config[game_hash]["latest_version"] = current_version
                                                    updates_found += 1
                                        
                                except Exception as e:
                                    logger.warning(f"Failed to check update for {info['alias']}: {e}")
                        
                        if updates_found > 0:
                            save_json(config_path, games_config)
                            logger.info(f"Updates processed. Config saved.")
            
        except Exception as e:
            logger.error(f"Auto-update check failed: {e}")
        
        # Check every 6 hours
        time.sleep(21600)

def hltb_background_task():
    """Background task to fetch HLTB data for games that miss it."""
    time.sleep(10) # Initial delay
    while True:
        try:
            config_path = os.path.join(CONFIG_FOLDER, "games.json")
            if os.path.exists(config_path):
                data = load_json(config_path)
                updated = False
                
                # Create a list of IDs to check to avoid modifying dict while iterating if we were doing that
                # But we load a fresh copy each loop
                
                for game_id, info in data.items():
                    # Skip if already has valid data
                    if "hltb" in info:
                        cached = info["hltb"]
                        if cached and "main" in cached and cached["main"] != "N/A":
                            continue
                    
                    game_name = info.get("alias") or info.get("name")
                    if not game_name: continue
                    
                    # Fetch
                    logger.info(f"Background HLTB fetch for {game_name}...")
                    hltb_data = hltb_fetcher.search(game_name)
                    
                    if hltb_data:
                        info["hltb"] = hltb_data
                        data[game_id] = info
                        updated = True
                        
                        # Broadcast update immediately
                        broadcast_event("hltb_update", {
                            "id": game_id,
                            "data": hltb_data
                        })
                        
                        # Save incrementally to be safe
                        save_json(config_path, data)
                        
                        # Sleep to be polite to HLTB
                        time.sleep(2) 
                    else:
                        # Mark as checked but failed to avoid infinite loop? 
                        # For now, we just skip saving if failed, so it will retry next loop (6h)
                        # or we can set a flag "hltb_checked": timestamp
                        pass
                
        except Exception as e:
            logger.error(f"HLTB background task error: {e}")
        
        # Run every 4 hours
        time.sleep(14400)

def init_scraper_background():
    global scraper, scraper_ready
    logger.info("Warm-starting Scraper...")
    time.sleep(2) # Brief delay to ensure WS connections are up
    broadcast_event("scraper_status", "initializing")
    try:
        if scraper:
            scraper.start() # Launches Chrome
            scraper_ready = True
            logger.info("Scraper is Ready.")
            broadcast_event("scraper_status", "ready")
    except Exception as e:
        logger.error(f"Scraper failed to start: {e}")
        broadcast_event("scraper_status", "error")

# --- Lifecycle ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    global scraper, download_manager, parent_pid, loop, metadata_fetcher
    loop = asyncio.get_event_loop()
    
    # 1. Maintenance Tasks
    run_startup_tasks()
    
    # 2. Check for Parent PID
    if len(sys.argv) > 1:
        try:
            parent_pid = int(sys.argv[1])
            logger.info(f"Monitoring parent PID: {parent_pid}")
            threading.Thread(target=monitor_parent, args=(parent_pid,), daemon=True).start()
        except ValueError:
            pass
            
    # 3. Init Scraper
    logger.info("Initializing Scraper...")
    scraper = UniversalScraper(headless=True, hide_window=True)
    
    # 4. Init Download Manager
    logger.info("Initializing DownloadManager...")
    download_manager = AsyncDownloadManager(scraper, status_callback=broadcast_event)
    
    # 5. Init Metadata
    user_config = UserConfig(CONFIG_FOLDER, "userconfig.json")
    metadata_fetcher = MetadataFetcher(user_config.RAWG_API_KEY)
    if user_config.RAWG_API_KEY:
        threading.Thread(target=run_metadata_scan, daemon=True).start()
    else:
        logger.warning("RAWG API Key is missing! Metadata will not be fetched.")

    # 5.5 Start Metadata Worker
    threading.Thread(target=metadata_worker, daemon=True).start()

    # 6. Start Scraper Warmup
    threading.Thread(target=init_scraper_background, daemon=True).start()
    
    # 7. Start Auto-Update Task
    threading.Thread(target=check_updates_task, daemon=True).start()

    # 8. Start HLTB Background Task
    threading.Thread(target=hltb_background_task, daemon=True).start()
    
    yield
    
    # --- Shutdown ---
    logger.info("Shutting down...")
    
    # Stop all active games
    for gid in list(active_games.keys()):
        try:
            logger.info(f"Stopping game {gid} during shutdown...")
            active_games[gid].stop()
        except: pass
    
    # Kill any lingering procmon
    try:
        subprocess.run(["taskkill", "/F", "/IM", "Procmon.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

    if download_manager:
        download_manager.stop()
    if scraper:
        scraper.close()

# FastAPI App
app = FastAPI(lifespan=lifespan)

# CORS for Electron
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Cache (Images)
if not os.path.exists(CACHE_FOLDER):
    os.makedirs(CACHE_FOLDER)
app.mount("/cache", StaticFiles(directory=CACHE_FOLDER), name="cache")

def monitor_parent(pid):
    """Kills server if parent process dies."""
    while True:
        try:
            if not psutil.pid_exists(pid):
                logger.info(f"Parent process {pid} is gone. Exiting...")
                # Hard exit to ensure no hanging threads/subprocesses keep us alive
                os._exit(0)
                break
        except Exception:
             break
        time.sleep(2)

# --- WebSocket ---

def broadcast_event(type: str, data: any):
    """
    Callback for DownloadManager to push updates to frontend.
    """
    if loop is None: return
    
    message = {"type": type, "data": data}
    json_msg = json.dumps(message)
    
    to_remove = []
    for ws in active_websockets:
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(json_msg), loop)
        except Exception:
            to_remove.append(ws)
    
    for ws in to_remove:
        if ws in active_websockets:
            active_websockets.remove(ws)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    
    # Send initial scraper status
    status = "ready" if scraper_ready else "initializing"
    await websocket.send_text(json.dumps({"type": "scraper_status", "data": status}))
    
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)

# --- API Models ---

class SearchRequest(BaseModel):
    query: str
    category: str = "Games"

class DownloadRequest(BaseModel):
    url: str
    alias: str = None
    source: str = "manager"

class SettingsUpdate(BaseModel):
    game_paths: list[str]
    download_path: str
    download_cache_path: str
    installed_games_path: str
    username: str
    language: str = "english"
    rawg_api_key: str = ""
    dry_launch: bool = False
    resume_on_startup: bool = True
    verbose_logging: bool = False
    speed: int = 0
    speed_enabled: bool = False
    auto_update_games: bool = False
    real_debrid_key: str = ""
    controller_support: bool = False
    controller_mapping: dict = {}
    media_output_path: str = ""
    show_hidden_games: bool = False

class AddLibraryRequest(BaseModel):
    title: str
    url: str

class RemoveLibraryRequest(BaseModel):
    id: str

class UpdateCategoriesRequest(BaseModel):
    id: str
    categories: list[str]

class UpdateGameSettingsRequest(BaseModel):
    id: str
    alias: str
    exe: str = ""
    args: list[str] = []
    save_path: str = ""
    tags: list[str] = []

@app.get("/api/game/{game_id}/hltb")
async def get_hltb_data(game_id: str, refresh: bool = False):
    config_path = os.path.join(CONFIG_FOLDER, "games.json")
    data = load_json(config_path)
    
    game_name = None
    is_external = False
    
    if game_id in data:
        game_name = data[game_id].get("alias") or data[game_id].get("name")
    elif game_id.startswith("ext_"):
        game_name = game_id[4:] # Remove 'ext_' prefix
        is_external = True
    else:
        raise HTTPException(status_code=404, detail="Game not found")
        
    # Check cache first (only for local games currently, or in memory for external?)
    # For now, we only cache local games in games.json to avoid clutter.
    if not is_external and not refresh and "hltb" in data[game_id]:
        # Validate cache integrity
        cached = data[game_id]["hltb"]
        if cached and "main" in cached and cached["main"] != "undefined Hours" and cached["main"] != "N/A":
             return cached
        
    # Fetch
    logger.info(f"Fetching HLTB data for {game_name}...")
    hltb_data = hltb_fetcher.search(game_name)
    
    if hltb_data:
        logger.info(f"HLTB Result: {hltb_data}")
        
        # Save to config (even for external games)
        if game_id not in data:
            # Create minimal entry for external game to store HLTB cache
            data[game_id] = {
                "name": game_name,
                "alias": game_name,
                "categorys": [f"External:Cached"], # Marker category
                "exe": "",
                "version": "External",
                "hltb": hltb_data
            }
        else:
            data[game_id]["hltb"] = hltb_data
            
        save_json(config_path, data)
        return hltb_data
    else:
        logger.warning(f"HLTB returned None for {game_name}")
    
    return {"main": "N/A", "main_extra": "N/A", "completionist": "N/A"}

@app.get("/api/game/{game_id}/backups")
async def get_backups(game_id: str):
    config_path = os.path.join(CONFIG_FOLDER, "games.json")
    data = load_json(config_path)
    if game_id in data:
        name = data[game_id].get("alias") or data[game_id].get("name")
        return save_backup_manager.list_backups(name)
    return []

class RestoreBackupRequest(BaseModel):
    filename: str

@app.post("/api/game/{game_id}/restore")
async def restore_backup(game_id: str, request: RestoreBackupRequest):
    config_path = os.path.join(CONFIG_FOLDER, "games.json")
    data = load_json(config_path)
    
    if game_id not in data:
        raise HTTPException(status_code=404, detail="Game not found")
        
    info = data[game_id]
    name = info.get("alias") or info.get("name")
    save_path = info.get("save_path")
    
    if not save_path:
        raise HTTPException(status_code=400, detail="No save path known for this game")
        
    success = save_backup_manager.restore_backup(name, save_path, request.filename)
    if success:
        return {"status": "restored"}
    raise HTTPException(status_code=500, detail="Restore failed")

class GameScriptsRequest(BaseModel):
    pre_launch: str
    post_exit: str

@app.post("/api/game/{game_id}/scripts")
async def save_game_scripts(game_id: str, request: GameScriptsRequest):
    config_path = os.path.join(CONFIG_FOLDER, "games.json")
    data = load_json(config_path)
    
    if game_id in data:
        data[game_id]["pre_launch_script"] = request.pre_launch
        data[game_id]["post_exit_script"] = request.post_exit
        save_json(config_path, data)
        return {"status": "saved"}
    raise HTTPException(status_code=404, detail="Game not found")

@app.post("/api/game/{game_id}/backup")
async def trigger_manual_backup(game_id: str):
    config_path = os.path.join(CONFIG_FOLDER, "games.json")
    data = load_json(config_path)
    
    if game_id in data:
        info = data[game_id]
        save_path = info.get("save_path")
        name = info.get("alias") or info.get("name")
        if save_path:
            res = save_backup_manager.create_backup(name, save_path)
            if res: return {"status": "created", "file": res}
            
    raise HTTPException(status_code=400, detail="Backup failed (unknown path?)")

@app.get("/api/tools/status")
async def get_tools_status():
    return tools_manager.get_status()

@app.post("/api/tools/install/{tool_id}")
async def install_tool(tool_id: str):
    success = tools_manager.install_tool(tool_id)
    if success: return {"status": "installed"}
    raise HTTPException(status_code=500, detail="Installation failed")

@app.post("/api/tools/run/vc_redist")
async def run_vc_redist():
    if tools_manager.run_vc_install():
        return {"status": "started"}
    raise HTTPException(status_code=500, detail="Failed to start installer")

class ConvertRequest(BaseModel):
    input_path: str
    output_format: str

@app.post("/api/tools/convert")
async def convert_media(request: ConvertRequest):
    ffmpeg_path = tools_manager._get_tool_path("ffmpeg")
    if not ffmpeg_path:
        raise HTTPException(status_code=400, detail="FFmpeg not installed")
        
    config = UserConfig(CONFIG_FOLDER, "userconfig.json")
    output_dir = config.MEDIA_OUTPUT_PATH
    
    converter = MediaConverter(ffmpeg_path)
    # Pass output_dir to converter
    res = converter.convert(request.input_path, request.output_format, output_dir)
    if "error" in res:
        raise HTTPException(status_code=500, detail=res["error"])
    return res

@app.post("/api/game/{game_id}/compress")
async def compress_game(game_id: str):
    config_path = os.path.join(CONFIG_FOLDER, "games.json")
    data = load_json(config_path)
    if game_id not in data: raise HTTPException(status_code=404, detail="Game not found")
    
    path = _get_game_path(data[game_id], game_id)
    if not path: raise HTTPException(status_code=400, detail="Game path not found")
    
    # Run in thread? Compress is blocking.
    # For now we block (simple), but ideally background task
    res = game_compressor.compress(path)
    return res

@app.post("/api/game/{game_id}/junk/scan")
async def scan_junk(game_id: str):
    config_path = os.path.join(CONFIG_FOLDER, "games.json")
    data = load_json(config_path)
    if game_id not in data: raise HTTPException(status_code=404, detail="Game not found")
    
    path = _get_game_path(data[game_id], game_id)
    if not path: raise HTTPException(status_code=400, detail="Game path not found")
    
    return junk_cleaner.scan(path)

class CleanJunkRequest(BaseModel):
    items: list[dict]

@app.post("/api/game/{game_id}/junk/clean")
async def clean_junk(game_id: str, request: CleanJunkRequest):
    deleted, failed = junk_cleaner.clean(request.items)
    return {"deleted": deleted, "failed": failed}

@app.post("/api/game/{game_id}/integrity/generate")
async def generate_integrity(game_id: str):
    config_path = os.path.join(CONFIG_FOLDER, "games.json")
    data = load_json(config_path)
    if game_id not in data: raise HTTPException(status_code=404, detail="Game not found")
    
    path = _get_game_path(data[game_id], game_id)
    if not path: raise HTTPException(status_code=400, detail="Game path not found")
    
    # Background this later?
    res = integrity_checker.generate_hash(path)
    return res

@app.post("/api/game/{game_id}/integrity/verify")
async def verify_integrity(game_id: str):
    config_path = os.path.join(CONFIG_FOLDER, "games.json")
    data = load_json(config_path)
    if game_id not in data: raise HTTPException(status_code=404, detail="Game not found")
    
    path = _get_game_path(data[game_id], game_id)
    if not path: raise HTTPException(status_code=400, detail="Game path not found")
    
    res = integrity_checker.verify_hash(path)
    return res

def _get_game_path(info, game_id):
    user_config = UserConfig(CONFIG_FOLDER, "userconfig.json")
    exe = info.get("exe")
    if exe and os.path.exists(os.path.dirname(exe)):
        return os.path.dirname(exe)
    
    # Fallback to searching paths
    for p in user_config.GAME_PATHS:
        candidate = os.path.join(p, game_id)
        if os.path.exists(candidate): return candidate
        candidate = os.path.join(p, info.get("name", ""))
        if os.path.exists(candidate): return candidate
    return None

@app.get("/api/random-game")
async def get_random_game():
    import random
    config_path = os.path.join(CONFIG_FOLDER, "games.json")
    data = load_json(config_path)
    
    installed_ids = [gid for gid, info in data.items() if info.get("exe") and "Not Installed" not in info.get("categorys", [])]
    
    if installed_ids:
        return {"id": random.choice(installed_ids)}
    return {"id": None}

@app.get("/api/library/game/{game_id}")
async def get_game_details(game_id: str):
    """Returns full details for a single game from config."""
    config_path = os.path.join(CONFIG_FOLDER, "games.json")
    data = load_json(config_path)
    if game_id in data:
        return data[game_id]
    raise HTTPException(status_code=404, detail="Game not found")

@app.post("/api/library/update_settings")
async def update_game_settings(request: UpdateGameSettingsRequest):
    """Updates various settings for a game in the library."""
    try:
        config_path = os.path.join(CONFIG_FOLDER, "games.json")
        data = load_json(config_path)
        
        if request.id in data:
            data[request.id]["alias"] = request.alias
            data[request.id]["exe"] = request.exe
            data[request.id]["args"] = request.args
            data[request.id]["tags"] = request.tags
            if request.save_path:
                data[request.id]["save_path"] = request.save_path
            save_json(config_path, data)
            return {"status": "updated", "id": request.id}
        else:
            raise HTTPException(status_code=404, detail="Game not found in library")
            
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/library/set_categories")
async def set_game_categories(request: UpdateCategoriesRequest):
    """Updates the category list for a game. Promotes external games to local config if needed."""
    try:
        config_path = os.path.join(CONFIG_FOLDER, "games.json")
        data = load_json(config_path)
        
        if request.id in data:
            data[request.id]["categorys"] = request.categories
            save_json(config_path, data)
            return {"status": "updated", "id": request.id, "categories": request.categories}
        
        # Handle External Game Promotion
        elif request.id.startswith("ext_"):
            game_name = request.id[4:] # Remove 'ext_' prefix
            logger.info(f"Promoting external game '{game_name}' to managed library...")
            
            scanner = ExternalLibraryScanner()
            ext_games = scanner.scan()
            found_game = next((g for g in ext_games if g["name"] == game_name), None)
            
            if found_game:
                # Add to games.json
                # We use the original ID (ext_Name) to maintain frontend link, 
                # or we could hash it. Keeping ext_Name ensures immediate consistency.
                data[request.id] = {
                    "name": found_game["name"],
                    "alias": found_game["name"],
                    "exe": found_game["exe"],
                    "version": found_game["version"],
                    "platform": found_game["platform"],
                    "link": found_game.get("link", ""),
                    "categorys": request.categories,
                    "playtime": 0
                }
                save_json(config_path, data)
                return {"status": "promoted_and_updated", "id": request.id, "categories": request.categories}
            else:
                logger.warning(f"Could not find external game details for: {game_name}")
                raise HTTPException(status_code=404, detail="External game source not found")
        
        else:
            raise HTTPException(status_code=404, detail="Game not found in library")
            
    except Exception as e:
        logger.error(f"Failed to update categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class PreviewRequest(BaseModel):
    name: str

@app.post("/api/preview")
async def preview_game(request: PreviewRequest):
    """Fetches and returns metadata for a game (and caches it)."""
    if not metadata_fetcher:
        raise HTTPException(status_code=503, detail="Metadata service unavailable")
    
    # Fetch metadata (this handles caching/downloading)
    meta = metadata_fetcher.get_metadata(request.name)
    
    if meta:
        return meta
    else:
        # Return minimal if not found
        return {"name": request.name, "description": "No metadata found."}

class DeleteCategoryRequest(BaseModel):
    category: str

@app.post("/api/library/delete_category")
async def delete_category(request: DeleteCategoryRequest):
    """Removes a category tag from all games."""
    try:
        config_path = os.path.join(CONFIG_FOLDER, "games.json")
        data = load_json(config_path)
        
        count = 0
        cat_to_remove = request.category
        
        for game_id, info in data.items():
            cats = info.get("categorys", [])
            if cat_to_remove in cats:
                cats.remove(cat_to_remove)
                info["categorys"] = cats
                count += 1
        
        if count > 0:
            save_json(config_path, data)
            
        return {"status": "deleted", "category": cat_to_remove, "games_updated": count}
            
    except Exception as e:
        logger.error(f"Failed to delete category: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/library/remove")
async def remove_from_library(request: RemoveLibraryRequest):
    """Removes a game from the library configuration."""
    try:
        config_path = os.path.join(CONFIG_FOLDER, "games.json")
        data = load_json(config_path)
        
        if request.id in data:
            del data[request.id]
            save_json(config_path, data)
            return {"status": "removed", "id": request.id}
        else:
            raise HTTPException(status_code=404, detail="Game not found in library")
            
    except Exception as e:
        logger.error(f"Failed to remove from library: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/library/uninstall")
async def uninstall_game(request: RemoveLibraryRequest):
    """Uninstalls a game (deletes files) and updates config to Not Installed."""
    import shutil
    try:
        config_path = os.path.join(CONFIG_FOLDER, "games.json")
        data = load_json(config_path)
        
        if request.id not in data:
            raise HTTPException(status_code=404, detail="Game not found in library")

        info = data[request.id]
        
        # 1. Attempt to find and delete game folder
        # We look for a folder matching the ID or Alias in the game paths
        user_config = UserConfig(CONFIG_FOLDER, "userconfig.json")
        deleted = False
        
        for path in user_config.GAME_PATHS:
            if not os.path.exists(path): continue
            
            # Check by ID (Hash)
            folder_by_id = os.path.join(path, request.id)
            if os.path.exists(folder_by_id) and os.path.isdir(folder_by_id):
                try:
                    shutil.rmtree(folder_by_id)
                    logger.info(f"Deleted game folder: {folder_by_id}")
                    deleted = True
                    break
                except Exception as e:
                    logger.error(f"Failed to delete {folder_by_id}: {e}")

            # Check by Name/Alias (if different)
            name = info.get("alias") or info.get("name")
            if name:
                # Sanitize name for folder (simple check)
                folder_by_name = os.path.join(path, name)
                if os.path.exists(folder_by_name) and os.path.isdir(folder_by_name):
                     try:
                        shutil.rmtree(folder_by_name)
                        logger.info(f"Deleted game folder: {folder_by_name}")
                        deleted = True
                        break
                     except Exception as e:
                        logger.error(f"Failed to delete {folder_by_name}: {e}")
        
        if not deleted:
            logger.warning(f"Could not locate game folder to delete for {request.id}")

        # 2. Track Orphaned Save Data
        if "save_path" in info and info["save_path"]:
            orphaned_path = os.path.join(CONFIG_FOLDER, "orphaned_saves.json")
            orphaned_data = load_json(orphaned_path)
            if not isinstance(orphaned_data, list):
                orphaned_data = []
            
            # Avoid duplicates
            if not any(item['path'] == info["save_path"] for item in orphaned_data):
                orphaned_data.append({
                    "name": info.get("alias") or info.get("name") or request.id,
                    "path": info["save_path"],
                    "timestamp": time.time()
                })
                save_json(orphaned_path, orphaned_data)
                logger.info(f"Marked save data for cleaning: {info['save_path']}")

        # 3. Update Config
        info["exe"] = ""
        info["version"] = ""
        info["categorys"] = ["Not Installed"]
        info["save_path"] = "" # Clear from game entry
        data[request.id] = info
        
        save_json(config_path, data)
        return {"status": "uninstalled", "id": request.id, "files_deleted": deleted}
            
    except Exception as e:
        logger.error(f"Failed to uninstall game: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/library/add")
async def add_to_library(request: AddLibraryRequest):
    """Adds a game to the library configuration without downloading."""
    try:
        config_path = os.path.join(CONFIG_FOLDER, "games.json")
        data = load_json(config_path)
        
        url = request.url
        if not url.startswith("http"):
            url = "https://steamrip.com" + url
            
        game_hash = hash_url(url)
        
        if game_hash not in data:
            # Always clean the name for SteamRIP
            clean_name = get_name_from_url(url) if "steamrip.com" in url.lower() else request.title
            
            # Try to get version immediately if scraper is ready
            version = "N/A"
            if scraper_ready:
                try:
                    version = _get_version_steamrip(url, scraper)
                except: pass

            data[game_hash] = {
                "name": clean_name,
                "alias": clean_name,
                "link": url,
                "exe": "",
                "args": [],
                "version": version,
                "playtime": 0,
                "categorys": ["Not Installed"]
            }
            save_json(config_path, data)
            return {"status": "added", "id": game_hash}
        else:
            return {"status": "exists", "id": game_hash}
            
    except Exception as e:
        logger.error(f"Failed to add to library: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search")
async def search(request: SearchRequest):
    if request.category == "Games":
        import difflib
        data = Searcher.fetch_game_list(scraper)
        query = request.query.lower()
        
        results_with_scores = []
        
        for name, url in data.items():
            name_lower = name.lower()
            score = 0
            
            # Priority 1: Starts with query (Highest)
            if name_lower.startswith(query):
                score = 1.2
            # Priority 2: Substring match
            elif query in name_lower:
                score = 1.0
            
            if score > 0:
                full_url = url if url.startswith("http") else "https://steamrip.com" + url
                results_with_scores.append({
                    "title": name,
                    "url": full_url,
                    "score": score
                })
        
        # Sort by score (descending), then by title length (ascending) for cleaner results
        results_with_scores.sort(key=lambda x: (-x["score"], len(x["title"])))
        
        # Limit to top 50
        final_results = [{"title": r["title"], "url": r["url"]} for r in results_with_scores[:50]]
        return {"results": final_results}
        
    elif request.category in ["Movies", "Series", "Animes"]:
        results = Searcher.movie(request.query)
        return results
    
    return {"results": []}

@app.post("/api/download")
async def start_download(request: DownloadRequest):
    # Always clean the name for SteamRIP if it's from the manager
    alias = request.alias
    if "steamrip.com" in request.url.lower():
        alias = get_name_from_url(request.url)

    success = download_manager.start_download(request.url, request.source, alias)
    if success:
        # Also ensure it's in games.json with 'Not Installed' status so it persists
        try:
            config_path = os.path.join(CONFIG_FOLDER, "games.json")
            data = load_json(config_path)
            game_hash = hash_url(request.url)
            if game_hash not in data:
                data[game_hash] = {
                    "name": alias,
                    "alias": alias,
                    "link": request.url,
                    "exe": "",
                    "args": [],
                    "version": "Pending",
                    "playtime": 0,
                    "categorys": ["Not Installed"]
                }
                save_json(config_path, data)
        except: pass
        return {"status": "started", "url": request.url}
    else:
        raise HTTPException(status_code=400, detail="Download already active or failed to start")

@app.get("/api/download/status")
async def get_download_status():
    if not download_manager:
        return {"active": False, "queue": []}
    return download_manager.get_status()

class ReorderQueueRequest(BaseModel):
    hashes: list[str]

@app.post("/api/download/queue/reorder")
async def reorder_queue(request: ReorderQueueRequest):
    download_manager.reorder_queue(request.hashes)
    return {"status": "ok"}

@app.post("/api/download/queue/remove/{item_hash}")
async def remove_from_queue(item_hash: str):
    download_manager.remove_from_queue(item_hash)
    return {"status": "ok"}

@app.post("/api/download/cache/clean")
async def clean_download_cache():
    if not download_manager:
        raise HTTPException(status_code=503, detail="Download manager unavailable")
    count = download_manager.wipe_cache()
    return {"status": "cleaned", "count": count}

@app.post("/api/stop")
async def stop_download():
    download_manager.stop()
    return {"status": "stopped"}

@app.post("/api/pause")
async def pause_download():
    download_manager.pause()
    return {"status": "paused"}

@app.post("/api/resume")
async def resume_download():
    download_manager.resume()
    return {"status": "resumed"}

@app.get("/api/version")
async def get_version():
    return {"version": APP_VERSION}

@app.get("/api/settings")
def get_settings():
    config = UserConfig(CONFIG_FOLDER, "userconfig.json")
    return {
        "game_paths": config.GAME_PATHS,
        "download_path": config.DOWNLOAD_PATH,
        "download_cache_path": config.DOWNLOAD_CACHE_PATH,
        "installed_games_path": config.INSTALLED_GAMES_PATH,
        "username": config.USERNAME,
        "language": config.LANGUAGE,
        "rawg_api_key": config.RAWG_API_KEY,
        "category_order": config.CATEGORY_ORDER,
        "dry_launch": config.DRY_LAUNCH,
        "resume_on_startup": config.RESUME_ON_STARTUP,
        "verbose_logging": config.VERBOSE_LOGGING,
        "speed": config.DOWNLOAD_SPEED,
        "speed_enabled": config.DOWNLOAD_SPEED_ENABLED,
        "auto_update_games": config.AUTO_UPDATE_GAMES,
        "real_debrid_key": config.REAL_DEBRID_KEY,
        "controller_support": config.CONTROLLER_SUPPORT,
        "controller_mapping": config.CONTROLLER_MAPPING,
        "collapsed_categories": config.COLLAPSED_CATEGORIES,
        "media_output_path": config.MEDIA_OUTPUT_PATH,
        "last_selected_game_id": config.LAST_SELECTED_GAME_ID,
        "show_hidden_games": config.SHOW_HIDDEN_GAMES
    }

class ReorderCategoriesRequest(BaseModel):
    order: list[str]

@app.post("/api/library/reorder_categories")
def reorder_categories(request: ReorderCategoriesRequest):
    config = UserConfig(CONFIG_FOLDER, "userconfig.json")
    config.CATEGORY_ORDER = request.order
    config.save()
    return {"status": "ok", "order": request.order}

class CollapsedCategoriesRequest(BaseModel):
    collapsed: list[str]

@app.post("/api/library/collapsed_categories")
def save_collapsed_categories(request: CollapsedCategoriesRequest):
    config = UserConfig(CONFIG_FOLDER, "userconfig.json")
    config.COLLAPSED_CATEGORIES = request.collapsed
    config.save()
    return {"status": "ok"}

class LastGameRequest(BaseModel):
    id: str

@app.post("/api/library/last_selected")
def save_last_selected(request: LastGameRequest):
    config = UserConfig(CONFIG_FOLDER, "userconfig.json")
    config.LAST_SELECTED_GAME_ID = request.id
    config.save()
    return {"status": "ok"}

@app.post("/api/settings")
def update_settings(settings: SettingsUpdate):
    global metadata_fetcher
    
    config = UserConfig(CONFIG_FOLDER, "userconfig.json")
    
    # Check for changes
    old_key = config.RAWG_API_KEY
    old_user = config.USERNAME
    old_lang = config.LANGUAGE
    
    new_key = config.RAWG_API_KEY
    new_user = settings.username
    new_lang = settings.language if hasattr(settings, "language") else old_lang
    
    config.GAME_PATHS = settings.game_paths
    config.DOWNLOAD_PATH = settings.download_path
    config.DOWNLOAD_CACHE_PATH = settings.download_cache_path
    config.INSTALLED_GAMES_PATH = settings.installed_games_path
    config.USERNAME = new_user
    config.LANGUAGE = new_lang
    config.DRY_LAUNCH = settings.dry_launch
    config.RESUME_ON_STARTUP = settings.resume_on_startup
    config.VERBOSE_LOGGING = settings.verbose_logging
    config.DOWNLOAD_SPEED = settings.speed
    config.DOWNLOAD_SPEED_ENABLED = settings.speed_enabled
    config.AUTO_UPDATE_GAMES = settings.auto_update_games
    config.CONTROLLER_SUPPORT = settings.controller_support
    if settings.controller_mapping:
        config.CONTROLLER_MAPPING = settings.controller_mapping
    
    config.MEDIA_OUTPUT_PATH = settings.media_output_path
    config.SHOW_HIDDEN_GAMES = settings.show_hidden_games

    # New Settings
    if hasattr(settings, "real_debrid_key"):
        config.REAL_DEBRID_KEY = settings.real_debrid_key
        debrid_manager.set_key(settings.real_debrid_key)

    if hasattr(settings, "rawg_api_key"):
        config.RAWG_API_KEY = settings.rawg_api_key
        new_key = settings.rawg_api_key
        
    config.save()
    
    # Update Game Configs (Ini/Info) if User/Lang changed
    if new_user != old_user or new_lang != old_lang:
        logger.info(f"User/Language changed. Updating game configs across {len(config.GAME_PATHS)} paths...")
        for path in config.GAME_PATHS:
            if os.path.exists(path):
                # Run in background to avoid blocking
                threading.Thread(target=update_game_configs, args=(path, new_user, new_lang), daemon=True).start()

    # Update Runtime Metadata Fetcher
    if new_key and new_key != old_key:
        logger.info("RAWG API Key updated. Refreshing metadata fetcher...")
        if metadata_fetcher:
            metadata_fetcher.api_key = new_key
        else:
            metadata_fetcher = MetadataFetcher(new_key)
            
        # Trigger scan
        threading.Thread(target=run_metadata_scan, daemon=True).start()
        
    return {"status": "ok"}

@app.get("/api/settings/orphaned-saves")
async def get_orphaned_saves():
    orphaned_path = os.path.join(CONFIG_FOLDER, "orphaned_saves.json")
    return load_json(orphaned_path)

class CleanSavesRequest(BaseModel):
    indices: list[int]

@app.post("/api/settings/clean-saves")
async def clean_orphaned_saves(request: CleanSavesRequest):
    import shutil
    orphaned_path = os.path.join(CONFIG_FOLDER, "orphaned_saves.json")
    data = load_json(orphaned_path)
    
    if not isinstance(data, list):
        return {"status": "empty", "deleted_count": 0}
        
    indices = sorted(request.indices, reverse=True)
    deleted_count = 0
    
    for idx in indices:
        if 0 <= idx < len(data):
            path = data[idx].get("path")
            if path and os.path.exists(path):
                try:
                    shutil.rmtree(path)
                    deleted_count += 1
                    logger.info(f"Deleted save data: {path}")
                except Exception as e:
                    logger.error(f"Failed to delete {path}: {e}")
            
            # Remove from list regardless of file deletion
            del data[idx]
            
    save_json(orphaned_path, data)
    return {"status": "cleaned", "deleted_count": deleted_count}

@app.post("/api/settings/clean-cache")
async def clean_cache():
    """Deletes all cached images and metadata."""
    import shutil
    try:
        count = 0
        if os.path.exists(CACHE_FOLDER):
            for item in os.listdir(CACHE_FOLDER):
                item_path = os.path.join(CACHE_FOLDER, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        count += 1
                    elif os.path.isfile(item_path):
                        os.remove(item_path)
                        count += 1
                except Exception as e:
                    logger.error(f"Failed to delete {item}: {e}")
        
        # Reset runtime cache if it exists
        if metadata_fetcher:
            metadata_fetcher.cache = {}
            
        logger.info(f"Cache cleaned. Removed {count} items.")
        return {"status": "cleaned", "count": count}
    except Exception as e:
        logger.error(f"Error cleaning cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class PathRequest(BaseModel):
    path: str

@app.post("/api/system/open-path")
async def open_any_path(request: PathRequest):
    if os.path.exists(request.path):
        os.startfile(request.path)
        return {"status": "opened"}
    raise HTTPException(status_code=404, detail="Path not found")

@app.post("/api/system/open-logs")
async def open_log_dir():
    if os.path.exists(APPDATA_CACHE_PATH):
        os.startfile(APPDATA_CACHE_PATH)
        return {"status": "opened"}
    raise HTTPException(status_code=404, detail="Log directory not found")

@app.post("/api/library/force-update")
async def force_update_config():
    """Forces a re-scan of game executables and metadata."""
    user_config = UserConfig(CONFIG_FOLDER, "userconfig.json")
    for path in user_config.GAME_PATHS:
        if os.path.exists(path):
            threading.Thread(target=update_game_configs, args=(path, user_config.USERNAME, user_config.LANGUAGE), daemon=True).start()
    
    # Also trigger metadata scan
    if user_config.RAWG_API_KEY:
        threading.Thread(target=run_metadata_scan, daemon=True).start()
        
    return {"status": "started"}

@app.post("/api/library/check_updates")
async def trigger_update_check():
    """Manually triggers the update checker."""
    threading.Thread(target=check_updates_task, daemon=True).start()
    return {"status": "started"}

@app.post("/api/game/{game_id}/setup")
async def run_game_setup(game_id: str):
    """Searches for and runs a Setup.exe/ISO in the game's folder."""
    user_config = UserConfig(CONFIG_FOLDER, "userconfig.json")
    for path in user_config.GAME_PATHS:
        game_folder = os.path.join(path, game_id)
        if os.path.exists(game_folder):
            # 1. Search for Setup.exe
            for root, dirs, files in os.walk(game_folder):
                for file in files:
                    if file.lower() in ["setup.exe", "install.exe"]:
                        setup_path = os.path.join(root, file)
                        try:
                            os.startfile(setup_path)
                            return {"status": "started", "file": setup_path}
                        except Exception as e:
                             raise HTTPException(status_code=500, detail=f"Failed to start setup: {e}")
            
            # 2. Search for ISO
            for root, dirs, files in os.walk(game_folder):
                 for file in files:
                    if file.lower().endswith(".iso"):
                         iso_path = os.path.join(root, file)
                         try:
                             os.startfile(iso_path) # Windows mounts ISOs automatically on open
                             return {"status": "mounted", "file": iso_path}
                         except Exception as e:
                             raise HTTPException(status_code=500, detail=f"Failed to mount ISO: {e}")

    raise HTTPException(status_code=404, detail="No setup file or ISO found.")

@app.post("/api/launch/{game_id}")
async def launch_game(game_id: str):
    user_config = UserConfig(CONFIG_FOLDER, "userconfig.json")
    dry_launch = user_config._data.get("dry_launch", False)
    
    config_games = load_json(os.path.join(CONFIG_FOLDER, "games.json"))
    
    # Handle External
    if game_id.startswith("ext_"):
        scanner = ExternalLibraryScanner()
        ext_games = scanner.scan()
        name = game_id.replace("ext_", "")
        found = next((g for g in ext_games if g['name'] == name), None)
        if found:
            os.startfile(found['exe'])
            return {"status": "launched", "type": "external"}
        raise HTTPException(status_code=404, detail="External game not found")

    # Handle Local
    if game_id not in config_games:
        raise HTTPException(status_code=404, detail="Game not found in config")
    
    info = config_games[game_id]
    exe = info.get("exe", "")
    resolved_exe = None

    # 1. Check if already absolute
    if exe and os.path.isabs(exe) and os.path.exists(exe):
        resolved_exe = exe
    else:
        # 2. Search in all Game Paths
        for path in user_config.GAME_PATHS:
            if not os.path.exists(path): continue
            
            # A) Try path + exe (e.g., D:/Games/Folder/Game.exe)
            if exe:
                candidate_direct = os.path.join(path, exe)
                if os.path.exists(candidate_direct):
                    resolved_exe = candidate_direct
                    break
                
                # B) Try path + game_id + exe (e.g., D:/Games/HashID/Game.exe)
                candidate_nested = os.path.join(path, game_id, exe)
                if os.path.exists(candidate_nested):
                    resolved_exe = candidate_nested
                    break

            # C) If exe invalid/missing, try auto-detect in game folder
            game_folder = os.path.join(path, game_id)
            if os.path.exists(game_folder):
                detected = _game_naming(game_id, search_path=game_folder)
                if detected:
                    resolved_exe = detected
                    logger.info(f"Auto-detected exe for {game_id}: {resolved_exe}")
                    break
    
    if resolved_exe:
        info["exe"] = resolved_exe
    else:
        logger.warning(f"Could not resolve exe path for {game_id}. Tried: {exe}")

    game = Game(game_id, info, installed=True)
    if game.start(dry_launch=dry_launch):
        active_games[game_id] = game
        return {"status": "launched", "type": "local"}
    
    raise HTTPException(status_code=500, detail=f"Failed to start game. Exe not found: {exe}")

@app.post("/api/stop/{game_id}")
async def stop_game(game_id: str):
    if game_id in active_games:
        active_games[game_id].stop()
        # Clean up is handled by wait() thread in Game class resetting is_running,
        # but we can remove it here if it's no longer active.
        if not active_games[game_id].run_instance or not active_games[game_id].run_instance._process or active_games[game_id].run_instance._process.poll() is not None:
            del active_games[game_id]
        return {"status": "stopped"}
    raise HTTPException(status_code=404, detail="Game not found or not running")

@app.get("/api/running-games")
async def get_running_games():
    running = []
    to_remove = []
    for gid, game in active_games.items():
        if game.run_instance and game.run_instance._process and game.run_instance._process.poll() is None:
            running.append(gid)
        else:
            to_remove.append(gid)
    
    for gid in to_remove:
        del active_games[gid]
        
    return {"running": running}

@app.post("/api/open-folder/{game_id}")
async def open_game_folder(game_id: str):
    user_config = UserConfig(CONFIG_FOLDER, "userconfig.json")
    for path in user_config.GAME_PATHS:
        full_path = os.path.join(path, game_id)
        if os.path.exists(full_path):
            os.startfile(full_path)
            return {"status": "opened"}
    
    raise HTTPException(status_code=404, detail="Folder not found")

@app.get("/api/library")
async def get_library():
    """Returns list of installed games/media."""
    library = []
    
    user_config = UserConfig(CONFIG_FOLDER, "userconfig.json")
    game_paths = user_config.GAME_PATHS
    if not game_paths:
        game_paths = [os.path.join(os.getcwd(), "Games")]

    config_games = load_json(os.path.join(CONFIG_FOLDER, "games.json"))
    found_ids = set()
    
    logged_posters = 0
    def enrich_game(game_obj):
        nonlocal logged_posters
        try:
            if metadata_fetcher:
                # Look up by name in cache (non-blocking)
                key = game_obj["name"].lower().strip()
                meta = metadata_fetcher.get_metadata(game_obj["name"], cached_only=True)
                
                if meta:
                    # Merge all metadata fields
                    for k, v in meta.items():
                        if k not in game_obj:
                            game_obj[k] = v
                    
                    # Prefer high-res RAWG poster if available
                    if meta.get("poster"):
                        game_obj["poster"] = meta["poster"]
                    
                    game_obj["banner"] = meta.get("banner", "")
                    game_obj["screenshots"] = meta.get("screenshots", [])
                    
                    if logged_posters < 5:
                        # logger.info(f"Assigned poster for {game_obj['name']}: {game_obj['poster']}")
                        logged_posters += 1
                else:
                    # Not in cache, queue for background fetch
                    if metadata_fetcher.api_key:
                        metadata_queue.put(game_obj["name"])
            
            # Detect Theme Music
            if "path" in game_obj and os.path.exists(game_obj["path"]):
                for f in os.listdir(game_obj["path"]):
                    if f.lower().startswith("theme.") and f.lower().endswith((".mp3", ".wav", ".ogg")):
                        # We need to serve this file. Since it's outside 'static', 
                        # we might need a dedicated endpoint or symlink. 
                        # For now, we return the absolute path and let frontend handle it 
                        # (frontend can't access local files directly easily in browser, but Electron can via 'file://' or custom protocol)
                        game_obj["theme_music"] = os.path.join(game_obj["path"], f)
                        break

            # HLTB Enrichment (Lazy or Cached?)
            # To avoid slowing down library load, we might skip this here or implement caching.
            # Ideally, HLTB data should be saved to games.json once fetched.
            # We will rely on a separate endpoint for HLTB to update the UI on demand.
            if "hltb" in game_obj:
                pass # Already has data
                
        except Exception as e:
            logger.error(f"Failed to enrich game '{game_obj.get('name')}': {e}")
        return game_obj
    
    for path in game_paths:
        if not os.path.exists(path): continue
        try:
            installed_folders = os.listdir(path)
        except OSError as e:
            logger.warning(f"Could not access library path '{path}': {e}")
            continue

        for folder_name in installed_folders:
            full_path = os.path.join(path, folder_name)
            if not os.path.isdir(full_path): continue
            
            game_id = folder_name 
            info = config_games.get(game_id, {})
            
            if game_id in found_ids: continue 
            found_ids.add(game_id)
            
            exe_path = info.get("exe", "")
            if not exe_path:
                exe_path = _game_naming(game_id, search_path=full_path)
            
            library.append(enrich_game({
                "id": game_id,
                "name": info.get("alias", folder_name),
                "version": info.get("version", "Local"),
                "latest_version": info.get("latest_version", ""),
                "update_available": info.get("update_available", False),
                "link": info.get("link", ""),
                "exe": exe_path,
                "playtime": info.get("playtime", 0),
                "platform": "Local",
                "installed": True,
                "poster": f"http://127.0.0.1:12345/cache/{game_id}.png",
                "categories": info.get("categorys", []),
                "tags": info.get("tags", []),
                "hidden": info.get("hidden", False),
                "path": full_path
            }))

    for game_id, info in config_games.items():
        if game_id not in found_ids:
            # Skip cache-only entries for external games (let the scanner handle them)
            if "External:Cached" in info.get("categorys", []):
                continue

            library.append(enrich_game({
                "id": game_id,
                "name": info.get("alias", game_id),
                "version": info.get("version", "N/A"),
                "link": info.get("link", ""),
                "exe": "",
                "playtime": info.get("playtime", 0),
                "platform": "Local",
                "installed": False,
                "poster": f"http://127.0.0.1:12345/cache/{game_id}.png",
                "categories": info.get("categorys", []),
                "tags": info.get("tags", []),
                "hidden": info.get("hidden", False)
            }))

    try:
        scanner = ExternalLibraryScanner()
        ext_games = scanner.scan()
        for g in ext_games:
            if not any(x['name'] == g['name'] for x in library):
                # Check for cached HLTB data in config
                hltb_cache = None
                config_entry = config_games.get(f"ext_{g['name']}")
                if config_entry and "hltb" in config_entry:
                    hltb_cache = config_entry["hltb"]
                
                is_hidden = config_entry.get("hidden", False) if config_entry else False

                game_obj = enrich_game({
                    "id": f"ext_{g['name']}",
                    "name": g['name'],
                    "version": g['version'],
                    "exe": g['exe'],
                    "playtime": 0,
                    "platform": g['platform'],
                    "installed": True,
                    "poster": "", 
                    "categories": [f"External:{g['platform']}"],
                    "hidden": is_hidden
                })
                
                if hltb_cache:
                    game_obj["hltb"] = hltb_cache
                    
                library.append(game_obj)
    except Exception as e:
        logger.error(f"External scan failed: {e}")
    
    # Log all image paths to a dedicated file
    # (Removed as per request)

    logger.info(f"Serving library with {len(library)} items")
    return {"library": library}

@app.post("/api/game/{game_id}/hide")
async def toggle_hide_game(game_id: str):
    config_path = os.path.join(CONFIG_FOLDER, "games.json")
    data = load_json(config_path)
    
    if game_id in data:
        data[game_id]["hidden"] = not data[game_id].get("hidden", False)
        save_json(config_path, data)
        return {"status": "ok", "hidden": data[game_id]["hidden"]}
    
    # Handle external games (need to create entry)
    if game_id.startswith("ext_"):
        data[game_id] = {
            "name": game_id[4:],
            "alias": game_id[4:],
            "categorys": [f"External:Cached"], 
            "hidden": True
        }
        save_json(config_path, data)
        return {"status": "ok", "hidden": True}
        
    raise HTTPException(status_code=404, detail="Game not found")

@app.get("/api/library/stats")
async def get_library_stats():
    config_path = os.path.join(CONFIG_FOLDER, "games.json")
    data = load_json(config_path)
    user_config = UserConfig(CONFIG_FOLDER, "userconfig.json")
    
    total_playtime = user_config.TOTAL_PLAYTIME_GLOBAL
    total_games = 0
    genres = {}
    
    # Calculate local stats
    for info in data.values():
        # Use HLTB genres if available, otherwise skip
        if "hltb" in info and info["hltb"]:
            # HLTB doesn't return genres in my simplified fetcher, only times. 
            # Ideally we'd fetch genres from RAWG or the scraper.
            # Assuming genres might be in 'genres' if using RAWG metadata fetcher?
            pass
        if "genres" in info:
            for g in info["genres"]:
                genres[g] = genres.get(g, 0) + 1

    # Total size (expensive, so maybe cache or simplified)
    total_size = 0
    # Scan installed folders
    for path in user_config.GAME_PATHS:
        if os.path.exists(path):
            try:
                for f in os.listdir(path):
                    fp = os.path.join(path, f)
                    if os.path.isdir(fp):
                        total_games += 1
                        # Checking size of every folder is slow. 
                        # We could do it, but maybe just count games for now?
            except: pass
            
    return {
        "playtime": total_playtime,
        "count": total_games,
        "genres": genres
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=12345)