import os
import logging
import requests
import math
import re
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Local imports
try:
    from .utility.utility_functions import save_json, load_json, hash_url, get_name_from_url
    from .utility.utility_vars import CONFIG_FOLDER, CACHE_FOLDER
except ImportError:
    # Fallback for direct execution
    from utility.utility_functions import save_json, load_json, hash_url, get_name_from_url
    from utility.utility_vars import CONFIG_FOLDER, CACHE_FOLDER

class Searcher:
    _game_cache = None
    _cache_timestamp = 0
    CACHE_DURATION = 3600 * 24 # 24 Hours
    
    @staticmethod
    def games(query, scraper, page=1):
        url = f"https://steamrip.com/page/{page}/?s={query}"
        data = {"amount": 0, "results": [], "pages": 0, "page_amount": 0}
        
        try:
            soup: BeautifulSoup = scraper.get_soup(url, timeout=10)
            element = soup.select_one("#masonry-grid")
            if element:
                all_game_elements = element.find_all(class_="container-wrapper post-element tie-standard masonry-brick tie-animate-slideInUp")
                if not all_game_elements:
                    all_game_elements = element.find_all(class_="container-wrapper post-element tie-standard masonry-brick")
                
                if not all_game_elements:
                    return {"amount": 0, "results": [], "pages": 0, "page_amount": 0}
                
                for game in all_game_elements:
                    a_tag = game.select_one("a")
                    div_tag = game.select_one("div")
                    
                    picture_url = div_tag.get("data-back")
                    href_url = urljoin("https://steamrip.com", a_tag.get("href"))
                    name = a_tag.text.strip().split(" Free Download")[0]
                    
                    data["results"].append({
                        "title": name,
                        "url": href_url, 
                        "picture": picture_url # Can directly be shown is like an image typicly 584x800 I would love to have like a cachel system were the name is above the picture Please downscale that its matches with movies
                    })
                
            return data
        except Exception as e:
            logging.error(f"Game search error: {e}")
            return data
        
    @staticmethod
    def movie(query, page=1):
        data = {"amount": 0, "results": [], "pages": 0, "page_amount": 0}
        
        try:
            url = f"https://filmpalast.to/search/title/{query}/{page}"
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                logging.error(f"Failed to fetch search results: {response.status_code}")
                return data
            
            soup = BeautifulSoup(response.text, "html.parser")
            element = soup.select_one("#content")
            if not element:
                return data
                
            try:
                h3 = element.find("h3")
                if h3:
                    amount = h3.text.split(": ")[1].strip()
                    data["amount"] = int(amount)
            except:
                 data["amount"] = 0
            
            articles = element.find_all("article")
            for article in articles:
                cite = article.find("cite")
                series = False
                a_tag = cite.find("a")
                if not a_tag: continue
                
                href = a_tag["href"]
                title = a_tag.text.strip()
                
                match = re.search(r"S(\d{1,2})E(\d{1,2})", title, re.IGNORECASE)
                episode_info = None
                
                img_tag = article.find("img", class_="cover-opacity")
                img_url = f"https://filmpalast.to{img_tag['src']}" if img_tag else None
                
                if match:
                    series = True
                    episode_info = match.group(0)
                    title = title.replace(episode_info, "").strip()
                
                if series:
                    logging.debug(f"Found series: {title} - {episode_info}")
                    continue
                
                data["results"].append({
                    "title": title,
                    "url": "https:" + href,
                    "series": series,
                    "episode_info": episode_info if series else None,
                    "picture": img_url
                })
            
            data["pages"] = math.ceil(data["amount"] / 20) if len(data["results"]) > 0 else 0
            
            return data
            
        except Exception as e:
            logging.error(f"Movie search error: {e}")
            return data

    @staticmethod
    def fetch_game_list(scraper, force_refresh=False):
        """
        Fetches the game list from SteamRIP. 
        Uses memory cache -> disk cache -> web fetch in that order.
        """
        cache_path = os.path.join(CACHE_FOLDER, "CachedGameList.json")
        
        # 1. Memory Cache
        if not force_refresh and Searcher._game_cache and (time.time() - Searcher._cache_timestamp < Searcher.CACHE_DURATION):
            return Searcher._game_cache

        # 2. Disk Cache (if valid and not forced)
        if not force_refresh and os.path.exists(cache_path):
            try:
                # Check file age (simple check)
                if time.time() - os.path.getmtime(cache_path) < Searcher.CACHE_DURATION:
                    data = load_json(cache_path)
                    if data:
                        Searcher._game_cache = data
                        Searcher._cache_timestamp = time.time()
                        return data
            except Exception as e:
                logging.error(f"Error reading game cache: {e}")

        # 3. Web Fetch
        logging.info("Fetching fresh game list from SteamRIP...")
        try:
            response = scraper.get_html("https://steamrip.com/games-list-page/")
            data = {}
            if response:
                soup = BeautifulSoup(response, "html.parser")
                game_list_container = soup.select_one("#tie-block_1793 > div > div.mag-box-container.clearfix")

                if game_list_container:
                    for upper_container in game_list_container.find_all(class_="az-list-container"):
                        for item in upper_container.find_all(class_="az-list"):
                            for game in item.find_all(class_="az-list-item"):
                                a_tag = game.find("a")
                                if a_tag:
                                    href = a_tag["href"]
                                    url = "https://steamrip.com" + href
                                    # Use the utility function to strip 'Free Download' and versions
                                    game_name = get_name_from_url(url)
                                    data[game_name] = href
                    
                    if not os.path.exists(CACHE_FOLDER):
                        os.makedirs(CACHE_FOLDER)
                    save_json(cache_path, data)
                    
                    Searcher._game_cache = data
                    Searcher._cache_timestamp = time.time()
                else:
                    logging.error("Game list container not found in HTML.")
                    data = load_json(cache_path) # Fallback to whatever we have
            else:
                logging.error("Failed to fetch page response empty.")
                data = load_json(cache_path)
        except Exception as e:
            logging.error(f"Error fetching game list: {e}")
            data = load_json(cache_path)

        return data

    @staticmethod
    def fetch_versions_map(scraper):
        """
        Fetches the game list and returns a map of {url_suffix: raw_title}
        for version extraction.
        """
        logging.info("Fetching versions map from SteamRIP...")
        versions = {}
        try:
            response = scraper.get_html("https://steamrip.com/games-list-page/")
            if response:
                soup = BeautifulSoup(response, "html.parser")
                game_list_container = soup.select_one("#tie-block_1793 > div > div.mag-box-container.clearfix")

                if game_list_container:
                    for upper_container in game_list_container.find_all(class_="az-list-container"):
                        for item in upper_container.find_all(class_="az-list"):
                            for game in item.find_all(class_="az-list-item"):
                                a_tag = game.find("a")
                                if a_tag:
                                    href = a_tag["href"] # e.g. /game-name/
                                    raw_title = a_tag.text.strip() # e.g. Game Name (v1.0) Free Download
                                    versions[href] = raw_title
        except Exception as e:
            logging.error(f"Error fetching versions map: {e}")
        
        return versions