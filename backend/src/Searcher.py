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
    def search_source_1(query, scraper, page=1):
        from .utility.utility_vars import CONFIG_FILE
        config = load_json(CONFIG_FILE)
        source = config.get("sources", {}).get("source_1", {})
        
        url_template = source.get("search_url")
        if not url_template:
            logging.error("No search URL configured for source_1")
            return {"amount": 0, "results": [], "pages": 0, "page_amount": 0}
            
        url = url_template.format(query=query, page=page)
        data = {"amount": 0, "results": [], "pages": 0, "page_amount": 0}
        
        try:
            soup: BeautifulSoup = scraper.get_soup(url, timeout=10)
            selectors = source.get("selectors", {})
            grid_selector = selectors.get("grid")
            item_selector = selectors.get("item")
            
            if not grid_selector:
                return data

            element = soup.select_one(grid_selector)
            if element:
                all_game_elements = element.find_all(class_=item_selector.split(".")) # Simplified class match
                if not all_game_elements:
                     # Fallback if class list is tricky
                     all_game_elements = element.select("." + item_selector.replace(" ", "."))

                if not all_game_elements:
                    return {"amount": 0, "results": [], "pages": 0, "page_amount": 0}
                
                for game in all_game_elements:
                    a_tag = game.select_one("a")
                    div_tag = game.select_one("div")
                    
                    picture_url = div_tag.get("data-back") if div_tag else None
                    base_url = "/".join(url.split("/")[:3]) # e.g. https://example.com
                    href_url = urljoin(base_url, a_tag.get("href")) if a_tag else ""
                    
                    title_clean_pattern = source.get("title_clean_pattern", " Free Download")
                    name = a_tag.text.strip().split(title_clean_pattern)[0] if a_tag else "Unknown"
                    
                    data["results"].append({
                        "title": name,
                        "url": href_url, 
                        "picture": picture_url
                    })
                
            return data
        except Exception as e:
            logging.error(f"Source 1 search error: {e}")
            return data
        
    @staticmethod
    def search_source_2(query, page=1):
        from .utility.utility_vars import CONFIG_FILE
        config = load_json(CONFIG_FILE)
        source = config.get("sources", {}).get("source_2", {})
        
        url_template = source.get("search_url")
        if not url_template:
            logging.error("No search URL configured for source_2")
            return {"amount": 0, "results": [], "pages": 0, "page_amount": 0}

        data = {"amount": 0, "results": [], "pages": 0, "page_amount": 0}
        
        try:
            url = url_template.format(query=query, page=page)
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                logging.error(f"Failed to fetch search results: {response.status_code}")
                return data
            
            soup = BeautifulSoup(response.text, "html.parser")
            selectors = source.get("selectors", {})
            content_selector = selectors.get("content")
            
            if not content_selector:
                return data

            element = soup.select_one(content_selector)
            if not element:
                return data
                
            try:
                # Amount detection logic
                amount_text = element.find("h3").text if element.find("h3") else ""
                if ": " in amount_text:
                    amount = amount_text.split(": ")[1].strip()
                    data["amount"] = int(amount)
            except:
                 data["amount"] = 0
            
            articles = element.find_all("article")
            for article in articles:
                cite = article.find("cite")
                series = False
                a_tag = cite.find("a") if cite else None
                if not a_tag: continue
                
                href = a_tag["href"]
                title = a_tag.text.strip()
                
                match = re.search(r"S(\d{1,2})E(\d{1,2})", title, re.IGNORECASE)
                episode_info = None
                
                img_tag = article.find("img", class_="cover-opacity")
                base_url = "/".join(url.split("/")[:3])
                img_url = urljoin(base_url, img_tag['src']) if img_tag else None
                
                if match:
                    series = True
                    episode_info = match.group(0)
                    title = title.replace(episode_info, "").strip()
                
                if series:
                    continue
                
                data["results"].append({
                    "title": title,
                    "url": "https:" + href if href.startswith("//") else href,
                    "series": series,
                    "episode_info": episode_info if series else None,
                    "picture": img_url
                })
            
            data["pages"] = math.ceil(data["amount"] / 20) if len(data["results"]) > 0 else 0
            
            return data
            
        except Exception as e:
            logging.error(f"Source 2 search error: {e}")
            return data

    @staticmethod
    def fetch_source_1_list(scraper, force_refresh=False):
        """
        Fetches the item list from Source 1.
        """
        from .utility.utility_vars import CONFIG_FILE
        config = load_json(CONFIG_FILE)
        source = config.get("sources", {}).get("source_1", {})
        
        list_url = source.get("list_url")
        if not list_url:
            return {}

        cache_path = os.path.join(CACHE_FOLDER, "CachedSource1List.json")
        
        # 1. Memory Cache
        if not force_refresh and Searcher._game_cache and (time.time() - Searcher._cache_timestamp < Searcher.CACHE_DURATION):
            return Searcher._game_cache

        # 2. Disk Cache
        if not force_refresh and os.path.exists(cache_path):
            try:
                if time.time() - os.path.getmtime(cache_path) < Searcher.CACHE_DURATION:
                    data = load_json(cache_path)
                    if data:
                        Searcher._game_cache = data
                        Searcher._cache_timestamp = time.time()
                        return data
            except Exception as e:
                logging.error(f"Error reading source 1 cache: {e}")

        # 3. Web Fetch
        logging.info(f"Fetching fresh list from Source 1...")
        try:
            response = scraper.get_html(list_url)
            data = {}
            if response:
                soup = BeautifulSoup(response, "html.parser")
                selectors = source.get("selectors", {})
                container_selector = selectors.get("list_container")

                if not container_selector:
                    return {}

                list_container = soup.select_one(container_selector)

                if list_container:
                    base_url = "/".join(list_url.split("/")[:3])
                    for item in list_container.select(".az-list-item"):
                        a_tag = item.find("a")
                        if a_tag:
                            href = a_tag["href"]
                            full_url = urljoin(base_url, href)
                            item_name = get_name_from_url(full_url)
                            data[item_name] = href
                    
                    if not os.path.exists(CACHE_FOLDER):
                        os.makedirs(CACHE_FOLDER)
                    save_json(cache_path, data)
                    
                    Searcher._game_cache = data
                    Searcher._cache_timestamp = time.time()
                else:
                    logging.error("Source 1 list container not found.")
                    data = load_json(cache_path)
            else:
                logging.error("Failed to fetch page response empty.")
                data = load_json(cache_path)
        except Exception as e:
            logging.error(f"Error fetching source 1 list: {e}")
            data = load_json(cache_path)

        return data

    @staticmethod
    def fetch_source_versions(scraper, source_config=None):
        """
        Fetches the versions map for a source and returns it.
        Useful for validation and update checks.
        """
        if not source_config:
            from .utility.utility_vars import CONFIG_FILE
            config = load_json(CONFIG_FILE)
            source_config = config.get("sources", {}).get("source_1", {})
            
        list_url = source_config.get("list_url")
        if not list_url:
            logging.warning("fetch_source_versions: No list_url provided in config.")
            return {}

        logging.info(f"Validating source versions from: {list_url}")
        versions = {}
        try:
            response = scraper.get_html(list_url)
            if response:
                soup = BeautifulSoup(response, "html.parser")
                selectors = source_config.get("selectors", {})
                container_selector = selectors.get("list_container")
                
                if not container_selector:
                    logging.error("fetch_source_versions: No container selector defined.")
                    return {}

                list_container = soup.select_one(container_selector)

                if list_container:
                    items = list_container.select(".az-list-item")
                    for item in items:
                        a_tag = item.find("a")
                        if a_tag:
                            href = a_tag["href"] 
                            raw_title = a_tag.text.strip() 
                            versions[href] = raw_title
                    logging.info(f"Successfully fetched {len(versions)} versions.")
                else:
                    logging.error(f"fetch_source_versions: Container '{container_selector}' not found in HTML.")
            else:
                logging.error("fetch_source_versions: Received empty response from scraper.")
        except Exception as e:
            logging.error(f"Error fetching versions map: {e}")
        
        return versions