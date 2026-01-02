import os, hashlib, json, re, subprocess, psutil, logging, requests, shutil, time
from bs4 import BeautifulSoup
import urllib.parse

from .utility_vars import CACHE_FOLDER

def hash_url(url: str) -> str:
    return hashlib.md5(url.encode('utf-8')).hexdigest()

def get_hashed_file(hash, extension):
    return f"{hash}{extension}"

def save_json(path, data):
    # Atomic write: write to unique temp file then rename
    # Use timestamp/random to avoid collision between threads
    import uuid
    temp_path = f"{path}.{uuid.uuid4()}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno()) # Ensure write to disk
        
        # Retry loop for rename (Windows file locking)
        retries = 3
        while retries > 0:
            try:
                os.replace(temp_path, path)
                break
            except OSError as e:
                retries -= 1
                if retries == 0:
                    raise e
                time.sleep(0.1)
                
    except Exception as e:
        logging.error(f"Failed to save JSON to {path}: {e}")
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except: pass

def load_json(path):
    retries = 3
    while retries > 0:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        return {}
                    return json.loads(content)
            except (json.JSONDecodeError, OSError) as e:
                # If permission denied (locking), retry
                if isinstance(e, OSError) and e.errno == 13: # Permission denied
                    retries -= 1
                    time.sleep(0.1)
                    if retries > 0: continue
                
                logging.warning(f"JSON load failed for {path} (corrupted?): {e}")
                # Backup corrupted file
                try:
                    if os.path.exists(path) and os.path.getsize(path) > 0:
                        shutil.copy(path, f"{path}.bak")
                        logging.info(f"Backed up corrupted file to {path}.bak")
                except: pass
                return {}
        else:
            return {}
    return {}

def get_name_from_url(url):
    """
    Extracts a clean title from a URL slug.
    """
    # 1. Strip protocol and common domains
    myurl = url.rstrip("/")
    parsed = urllib.parse.urlparse(myurl)
    path = parsed.path.strip("/")
    
    if not path:
        return "Unknown"
        
    slug = path.split("/")[-1]
    
    # 2. Handle 'free-download' slug if present
    if "free-download" in slug.lower():
        data = slug.lower().split("free-download")[0].rstrip("-")
    else:
        data = slug.lower()
    
    # 3. Remove common version/rip suffixes (e.g., -v1-0, -rip, -build-123)
    data = re.sub(r"-v?\d+[\d\.-]*.*$", "", data)
    data = re.sub(r"-build-\d+.*$", "", data)
    data = re.sub(r"-rip.*$", "", data)
    
    # 4. Final cleanup and formatting
    finished = data.replace("-", " ").title().strip()
    
    # Remove generic 'Free Download' if still present
    finished = re.sub(r" Free Download.*$", "", finished, flags=re.IGNORECASE)
    
    return finished

def powershell(cmd, popen=False):
    if popen:
        return subprocess.Popen(["powershell", "-Command", cmd], text=True)
    else:
        return subprocess.run(["powershell", "-Command", cmd], text=True)

def process_running(name: str) -> bool:
    """Check if a process with this name is running"""
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and proc.info['name'].lower() == name.lower():
            return True
    return False

def kill_process(name: str):
    """Kill a process by name"""
    logging.debug(f"Killing {name} ...")
    subprocess.run(["taskkill", "/F", "/IM", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def cloud_flare_request(url_r):
    url = "http://127.0.0.1:20080/get_page/"
    headers = {"Content-Type": "application/json"}
    data = {
        "cmd": "request.get",
        "url": url_r,
        "maxTimeout": 60000
    }
    response = requests.post(url, headers = headers, json = data)

    json_response = response.json()
    if json_response.get("status") != "ok":
        logging.error(f"Cloudflare request failed: {json_response}")
        return None
    best_cookies = {c['name']: c['value'] for c in json_response.get('solution').get('cookies') if c['name'] == 'cf_clearance'}
    logging.debug(f"Cloudflare cookies: {best_cookies}")
    return json_response.get('solution').get('response'), best_cookies

def get_png(page_content) -> str:
    soup = BeautifulSoup(page_content, "html.parser")
    soup.find()
    img_tag = soup.select_one("#tie-wrapper > div.container.fullwidth-featured-area-wrapper > div > div > figure > img")
    if img_tag and 'src' in img_tag.attrs:
        img_url = img_tag.attrs['srcset'].split(" ")[0]
    download_url = img_url
    return download_url

def get_screenshots(page_content) -> list:
    """
    Extracts up to 2 screenshot URLs by locating the 'SCREENSHOTS' header within .entry-content.
    Scans elements immediately following the header until the next section starts.
    """
    screenshots = []
    try:
        soup = BeautifulSoup(page_content, "html.parser")
        
        # 1. Restrict search to main content area to avoid sidebar/footer noise
        content_area = soup.select_one(".entry-content")
        if not content_area:
            content_area = soup # Fallback
            
        # 2. Find the marker
        target_marker = content_area.find(lambda tag: tag.name in ['h2', 'h3', 'h4', 'span', 'strong', 'b', 'p'] 
                                            and 'SCREENSHOTS' in tag.get_text(strip=True).upper())
        
        if target_marker:
            # 3. Scan forward until we hit the next section header or find enough images
            # We iterate through all next elements (tags) in document order
            for tag in target_marker.find_all_next():
                # Stop if we hit a new section header (e.g. "System Requirements")
                if tag.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] and tag != target_marker:
                    # Ignore empty headers or headers nested inside the marker (unlikely)
                    if tag.get_text(strip=True): 
                        break
                
                if tag.name == 'a':
                    href = tag.get('href')
                    if not href: continue
                    
                    processed_href = href

                    # Handle Pinterest
                    if "pinterest.com/pin/create/button/" in href:
                        try:
                            parsed = urllib.parse.urlparse(href)
                            qs = urllib.parse.parse_qs(parsed.query)
                            if 'media' in qs:
                                processed_href = qs['media'][0]
                        except: pass

                    # Relative URLs
                    if processed_href.startswith("/"):
                        base_url = "/".join(url.split("/")[:3]) if 'url' in locals() else ""
                        processed_href = urljoin(base_url, processed_href)
                    
                    # Validation
                    if "/wp-content/uploads/" in processed_href:
                        if any(ext in processed_href.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                            if processed_href not in screenshots:
                                screenshots.append(processed_href)
                                if len(screenshots) >= 2:
                                    break
        else:
             logging.warning("Could not find 'SCREENSHOTS' section.")

    except Exception as e:
        logging.error(f"Error extracting screenshots: {e}")
    
    return screenshots


def get_version_from_source(url, scraper, selector=None) -> str:
    """
    Fetches the version string from a source URL using a provided CSS selector.
    """
    if not url.startswith("https"):
        return ""
    
    # If no selector provided, try to load from config
    if not selector:
        from .utility_vars import CONFIG_FILE
        config = load_json(CONFIG_FILE)
        # Attempt to find which source this URL belongs to
        for source_id, source_data in config.get("sources", {}).items():
            source_url = source_data.get("source_url", "")
            if source_url and source_url in url:
                selector = source_data.get("selectors", {}).get("version_selector")
                break
    
    if not selector:
        logging.warning(f"No version selector found for {url}")
        return "N/A"

    try:
        response = scraper.get_html(url)
        soup = BeautifulSoup(response, 'html.parser')

        element = soup.select_one(selector=selector)
        if element:
            version = element.text.strip().replace("Version: ", "")
            logging.debug(f"Version found: {version}")
            return version
        else:
            logging.warning(f"Version element not found with selector: {selector}")
            return "Unknown"
    except Exception as e:
        logging.error(f"Error fetching version for {url}: {e}")
        return f"Error: {e}"

def _game_naming(folder, search_path=None):
    """
    Determines the main executable for a game.
    If search_path is provided, looks there.
    Otherwise defaults to os.getcwd()/Games/folder (Legacy behavior).
    """
    if search_path:
        target_dir = search_path
    else:
        target_dir = os.path.join(os.getcwd(), "Games", folder)

    logging.debug(f"Attempting to determine main executable for: {target_dir}")
    
    if not os.path.exists(target_dir):
        logging.warning(f"Path does not exist: {target_dir}")
        return ""

    exes = []
    full_path_game_execution = None
    
    # First pass: look for a direct match in the root of the game folder
    try:
        for name in os.listdir(target_dir):
            if name.endswith(".exe"):
                if "unity" not in name.lower(): # Exclude common engine executables if possible
                    full_path_game_execution = os.path.join(target_dir, name)
                    logging.debug(f"Main executable found in root: {full_path_game_execution}")
                    return full_path_game_execution
    except OSError as e:
        logging.error(f"Error accessing directory {target_dir}: {e}")
        return ""
    
    # Second pass: recursive search within the game folder
    if full_path_game_execution is None:
        logging.debug(f"No direct executable found. Performing recursive search...")
        for path, subdirs, files in os.walk(target_dir):
            if full_path_game_execution is not None:
                break # Stop if already found in a deeper subdir
            for name in files:
                if name.endswith(".exe"):
                    exes.append(os.path.join(path, name)) # Store full path for later
                    if folder.replace(" ", "").lower() in name.replace(" ", "").lower():
                        full_path_game_execution = os.path.join(path, name)
                        logging.debug(f"Main executable found during recursive search: {full_path_game_execution}")
                        break
        
        # Fallback if no specific match, pick the first non-Unity exe
        if full_path_game_execution is None:
            logging.debug(f"No specific executable match. Falling back to first non-Unity exe...")
            for file_path in exes:
                if "unity" not in os.path.basename(file_path).lower():
                    full_path_game_execution = file_path
                    logging.debug(f"Fallback executable selected: {full_path_game_execution}")
                    break
    
    if full_path_game_execution is None:
        logging.warning(f"Could not determine main executable for: {folder}. Returning empty string.")
        return "" 
        
    return full_path_game_execution

def format_playtime(seconds):
    if not isinstance(seconds, (int, float)):
        return "N/A"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes}m"

def clean_unused_cache_files() -> int:
    """
    Deletes files in CACHE_FOLDER that do not correspond to any game in games.json.
    Returns the number of files deleted.
    """
    count = 0
    try:
        from .utility_vars import CONFIG_FOLDER, CACHE_FOLDER # Ensure imports inside if moved, but they are global in file
        games_data = load_json(os.path.join(CONFIG_FOLDER, "games.json"))
        active_hashes = set(games_data.keys())
        
        if not os.path.exists(CACHE_FOLDER):
            return 0

        for filename in os.listdir(CACHE_FOLDER):
            # Skip known non-hash files
            if filename in ["CachedGameList.json"]:
                continue
            
            # Extract potential hash (first 32 chars)
            if len(filename) >= 32:
                file_hash = filename[:32]
                
                # Verify if it looks like an MD5 hash (hexadecimal)
                if re.match(r'^[0-9a-fA-F]{32}', file_hash):
                    if file_hash not in active_hashes:
                        try:
                            os.remove(os.path.join(CACHE_FOLDER, filename))
                            logging.info(f"Cleaned unused cache file: {filename}")
                            count += 1
                        except Exception as e:
                            logging.error(f"Failed to remove {filename}: {e}")
    except Exception as e:
        logging.error(f"Error during cache cleanup: {e}")
        
    return count