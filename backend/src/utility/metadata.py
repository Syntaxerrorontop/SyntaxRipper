import requests
import logging
import time
import os
import hashlib
from difflib import SequenceMatcher
from .utility_functions import load_json, save_json
from .utility_vars import CACHE_FOLDER

logger = logging.getLogger("Metadata")

class MetadataFetcher:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.rawg.io/api"
        self.cache_file = os.path.join(CACHE_FOLDER, "metadata_cache.json")
        self.cache = self._load_cache()

    def _load_cache(self):
        return load_json(self.cache_file)

    def _save_cache(self):
        save_json(self.cache_file, self.cache)

    def _download_asset(self, url, folder_path, filename):
        if not url: return ""
        try:
            # Check extension
            ext = "jpg"
            if "." in url:
                ext = url.split(".")[-1].split("?")[0]
                if len(ext) > 4: ext = "jpg"
            
            full_filename = f"{filename}.{ext}"
            file_path = os.path.join(folder_path, full_filename)
            
            if os.path.exists(file_path):
                return full_filename

            # Download
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                with open(file_path, "wb") as f:
                    f.write(res.content)
                return full_filename
        except Exception as e:
            logger.warning(f"Failed to download asset {url}: {e}")
        return ""

    def get_metadata(self, game_name):
        """
        Retrieves metadata for a game.
        Checks cache first. If missing and API key exists, fetches from RAWG.
        Downloads assets to local cache folder (hashed name).
        """
        # Normalize name
        norm_name = game_name.lower().strip()
        cache_key = norm_name
        
        # Create hash folder
        name_hash = hashlib.md5(norm_name.encode('utf-8')).hexdigest()
        game_cache_dir = os.path.join(CACHE_FOLDER, name_hash)
        
        if cache_key in self.cache:
            data = self.cache[cache_key]
            # Check if valid data
            if data.get("banner"):
                # VALIDATION: Ensure physical assets exist AND screenshots are present in data
                # Strict check: Must have at least 3 files (Banner, Poster, +1 Screenshot)
                # and at least 1 screenshot in metadata.
                files_in_dir = os.listdir(game_cache_dir) if os.path.exists(game_cache_dir) else []
                has_enough_files = len(files_in_dir) >= 3
                has_screenshots_data = isinstance(data.get("screenshots"), list) and len(data["screenshots"]) > 0
                
                if has_enough_files and has_screenshots_data:
                    # logger.debug(f"Cache valid for {game_name}: {len(files_in_dir)} files")
                    return data
                else:
                    logger.info(f"Cache incomplete for '{game_name}' (Files: {len(files_in_dir)}, Screenshots: {len(data.get('screenshots', []))}). Re-fetching.")
        
        if not self.api_key:
            return None

        # Fetch from API
        logger.info(f"Fetching RAWG metadata for: {game_name}")
        masked_key = f"{self.api_key[:4]}...{self.api_key[-4:]}" if self.api_key and len(self.api_key) > 8 else "INVALID"
        logger.debug(f"Using API Key: {masked_key}")

        try:
            if not os.path.exists(game_cache_dir):
                os.makedirs(game_cache_dir)

            # 1. Search to get Slug
            search_url = f"{self.base_url}/games"
            params = {"key": self.api_key, "search": game_name, "page_size": 1}
            res = requests.get(search_url, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()
            
            if not data.get("results"):
                logger.warning(f"No results found for {game_name}")
                self.cache[cache_key] = {} 
                self._save_cache()
                return None

            search_result = data["results"][0]
            slug = search_result["slug"]
            game_id = search_result["id"]
            
            # 2. Fetch Detailed Info
            details_url = f"{self.base_url}/games/{slug}"
            res_details = requests.get(details_url, params={"key": self.api_key}, timeout=10)
            if res_details.status_code == 200:
                details = res_details.json()
            else:
                logging.warning(f"Failed to fetch details for {slug}, using search result fallback.")
                details = search_result # Fallback (missing desc, reqs, etc.)

            # 3. Extract Data
            description = details.get("description", "") # HTML format
            rating = details.get("rating", 0)
            rating_top = details.get("rating_top", 0)
            
            # Ratings breakdown
            ratings_list = []
            for r in details.get("ratings", []):
                ratings_list.append({
                    "title": r.get("title"),
                    "count": r.get("count"),
                    "percent": r.get("percent")
                })
            
            # PC Requirements
            pc_requirements = {"minimum": "", "recommended": ""}
            platforms = details.get("platforms", [])
            for p_wrapper in platforms:
                p = p_wrapper.get("platform", {})
                if p.get("name") == "PC":
                    reqs = p_wrapper.get("requirements", {})
                    pc_requirements["minimum"] = reqs.get("minimum", "")
                    pc_requirements["recommended"] = reqs.get("recommended", "")
                    break

            # Lists
            developers = [d["name"] for d in details.get("developers", [])]
            genres = [g["name"] for g in details.get("genres", [])]
            tags = [t["name"] for t in details.get("tags", [])]
            publishers = [p["name"] for p in details.get("publishers", [])]

            # 4. Download Assets (Banner/Poster)
            banner_url = details.get("background_image", "") or search_result.get("background_image", "")
            poster_url = details.get("background_image_additional", "") or banner_url # Fallback
            
            banner_file = self._download_asset(banner_url, game_cache_dir, "banner")
            poster_file = self._download_asset(poster_url, game_cache_dir, "poster")
            
            # 5. Download Screenshots (Separate Request if needed, or use search result short_screenshots)
            # The details endpoint usually doesn't return full screenshots list like the specific endpoint does.
            # But search result has 'short_screenshots'.
            # Or we can use the screenshots endpoint as before.
            screenshots = []
            try:
                scr_url = f"{self.base_url}/games/{slug}/screenshots"
                scr_res = requests.get(scr_url, params={"key": self.api_key, "page_size": 20}, timeout=10)
                if scr_res.status_code == 200:
                    scr_data = scr_res.json()
                    for i, s in enumerate(scr_data.get("results", [])):
                        fname = self._download_asset(s["image"], game_cache_dir, f"screenshot_{i}")
                        if fname:
                            screenshots.append(f"http://127.0.0.1:12345/cache/{name_hash}/{fname}")
                else:
                    # Fallback to search result short_screenshots
                    for i, s in enumerate(search_result.get("short_screenshots", [])):
                         if s.get("id") != -1:
                            fname = self._download_asset(s["image"], game_cache_dir, f"screenshot_{i}")
                            if fname:
                                screenshots.append(f"http://127.0.0.1:12345/cache/{name_hash}/{fname}")
            except Exception:
                pass

            # Construct paths
            banner_path = f"http://127.0.0.1:12345/cache/{name_hash}/{banner_file}" if banner_file else ""
            poster_path = f"http://127.0.0.1:12345/cache/{name_hash}/{poster_file}" if poster_file else ""

            metadata = {
                "name": details.get("name_original", details.get("name")),
                "rawg_id": game_id,
                "slug": slug,
                "description": description,
                "rating": rating,
                "rating_top": rating_top,
                "ratings": ratings_list,
                "pc_requirements": pc_requirements,
                "developers": developers,
                "genres": genres,
                "tags": tags,
                "publishers": publishers,
                "banner": banner_path,
                "poster": poster_path,
                "screenshots": screenshots
            }
            
            self.cache[cache_key] = metadata
            self._save_cache()
            return metadata

        except Exception as e:
            logger.error(f"RAWG API error for {game_name}: {e}", exc_info=True)
            return None

    def _download_asset(self, url, folder_path, filename):
        if not url: return ""
        try:
            # Check extension
            ext = "jpg"
            if "." in url:
                ext = url.split(".")[-1].split("?")[0]
                if len(ext) > 4: ext = "jpg"
            
            full_filename = f"{filename}.{ext}"
            file_path = os.path.join(folder_path, full_filename)
            
            # Simple check: if exists and > 0 bytes, skip
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                return full_filename

            # Download
            logger.debug(f"Downloading {filename} from {url}...")
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                with open(file_path, "wb") as f:
                    f.write(res.content)
                logger.debug(f"Saved {full_filename}")
                return full_filename
            else:
                logger.warning(f"Failed to download {url}: Status {res.status_code}")
        except Exception as e:
            logger.warning(f"Failed to download asset {url}: {e}")
        return ""
