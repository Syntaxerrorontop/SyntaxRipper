from .exceptions import InvalidUrlException, UnknownProviderException
from .scraper import UniversalScraper

import logging
import re
import time
import random
import string

import requests
import json

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


logging.basicConfig(level=logging.INFO)

class DownloadableContext:
    def __init__(self, url: str, method: str, extension: str, payload: dict = {}, headers: dict = {}, session: requests.Session = None, worker: int = 1, delay: float = 0.5):
        self.url = url
        self.payload = payload if payload is not None else {}
        self.headers = headers if headers is not None else {}
        self.method = method
        self.session = session
        self.file_extension = extension
        
        self.worker = worker
        self.delay = delay
    
    def get_headers(self, changes: dict = {}) -> dict:
        updated_headers = self.headers.copy()
        updated_headers.update(changes)
        return updated_headers

class DDLExtractor:
    @staticmethod
    def gofile(url: str) -> DownloadableContext:
        pass
    
    @staticmethod
    def buzzheavier(url: str) -> DownloadableContext:
        logging.info(f"Starting Buzzheavier for: {url}")
        
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": url
        }

        try:
            r_main = session.get(url, headers=headers)
            r_main.raise_for_status()
            
            soup = BeautifulSoup(r_main.text, 'html.parser')
            filename = "downloaded_file.rar" # Fallback
            title_tag = soup.find("title")
            if title_tag:
                filename = title_tag.text.replace(" - Buzzheavier", "").strip()
                
            logging.info(f"Gefundener Dateiname: {filename}")
            download_endpoint = url.rstrip('/') + "/download"
            headers["HX-Request"] = "true"
            
            r_trigger = session.get(download_endpoint, headers=headers, allow_redirects=False)

            direct_link = r_trigger.headers.get("hx-redirect") or r_trigger.headers.get("Location")
            
            extension = filename.split('.')[-1]
            
            return DownloadableContext(direct_link, "get", extension, session=session, worker=_download_data["provider_support"]["buzzheavier"]["worker"], delay=_download_data["provider_support"]["buzzheavier"]["delay"])

        except Exception as e:
            logging.error(f"Downloader:buzzheavier Error: {e}")
    
    @staticmethod
    def fichier(url: str) -> DownloadableContext:
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            'Referer': url
        }
        logging.info(f"1. Analysiere Seite: {url}")
        try:
            response = session.get(url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            form = soup.find("form", id="f1")
            if not form:
                return "Fehler: Formular 'f1' nicht gefunden. Layout geaendert?"

            adz_input = form.find("input", {"name": "adz"})
            if not adz_input:
                return "Fehler: Token 'adz' nicht gefunden."
            
            filename_element = soup.find("span", style="font-weight:bold")
            extension = filename_element.text.split(".")[-1]
            
            adz_value = adz_input['value']
            logging.info(f"   -> Token gefunden: {adz_value}")

            post_url = form.get("action")
            if not post_url:
                post_url = url

            logging.info("2. Wartezeit laeuft (62 Sekunden Sicherheitsabstand)...")
            time.sleep(62)

            payload = {
                "adz": adz_value
            }

            logging.info("3. Sende Download-Anfrage...")
            final_response = session.post(post_url, data=payload, headers=headers)

            final_soup = BeautifulSoup(final_response.text, 'html.parser')

            direct_link_btn = final_soup.find("a", class_="ok btn-general btn-orange")
            
            if direct_link_btn:
                return DownloadableContext(direct_link_btn['href'], "get", extension, worker=_download_data["provider_support"]["fichier"]["worker"], delay=_download_data["provider_support"]["fichier"]["delay"])#{"url": direct_link_btn['href'], "payload": {}, "headers": {}, "method": "get"} 


        except Exception as e:
            logging.error(f"{e}")
    
    @staticmethod
    def datanode(url: str) -> DownloadableContext:
        pass
    
    @staticmethod
    def megadb(url: str) -> DownloadableContext:
        logging.info("1. Konfiguriere den Schnueffler...")
    
        # Wir müssen Chrome sagen, dass er uns Zugriff auf die Netzwerk-Logs gibt
        options = webdriver.ChromeOptions()
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        options.add_argument("--start-minimized")
        
        # Damit der Download nicht deinen Ordner vollspammt, setzen wir ihn auf ein Temp-Verzeichnis
        # oder ignorieren ihn. Hier lassen wir ihn kurz anlaufen, da wir eh gleich schließen.
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.minimize_window()
        try:
            # --- PHASE 1: Navigation ---
            driver.get(url)
            logging.info("2. Seite geladen.")

            # Klick auf ersten "Free Download" (falls vorhanden)
            try:
                start_btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, "//input[@value='Free Download'] | //button[contains(text(), 'Free Download')]"))
                )
                start_btn.click()
            except:
                pass 

            # --- PHASE 2: Captcha & Wartezeit ---
            logging.info("3. Löse Captcha automatisch...")
            try:
                WebDriverWait(driver, 5).until(
                    EC.frame_to_be_available_and_switch_to_it((By.XPATH, "//iframe[starts-with(@name, 'a-') and starts-with(@src, 'https://www.google.com/recaptcha')]"))
                )
                WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "recaptcha-anchor"))).click()
                driver.switch_to.default_content()
            except:
                logging.info("   -> (Manuelles Eingreifen beim Captcha evtl. nötig)")
                driver.switch_to.default_content()

            logging.info("4. Warte auf den Countdown (Geduld)...")
            # Warten bis der finale Button klickbar ist
            final_btn = WebDriverWait(driver, 60).until(
                EC.element_to_be_clickable((By.ID, "downloadbtn"))
            )
            
            # --- PHASE 3: Der Zugriff ---
            logging.info("5. Klicke Button und hoere Netzwerk ab...")
            
            # Zeitstempel merken, damit wir nur NEUE Requests anschauen
            driver.get_log("performance") # Löscht den alten Log-Puffer
            
            # Klick!
            driver.execute_script("arguments[0].click();", final_btn)
            
            # Jetzt scannen wir 10 Sekunden lang hektisch die Logs nach dem Download-Link
            found_url = None
            end_time = time.time() + 15
            
            while time.time() < end_time:
                logs = driver.get_log("performance")
                
                for entry in logs:
                    message = json.loads(entry["message"])["message"]
                    
                    # Wir suchen nach "Network.requestWillBeSent" Ereignissen
                    if message["method"] == "Network.requestWillBeSent":
                        request_url = message["params"]["request"]["url"]
                        
                        # --- DER FILTER ---
                        # Ein echter Download-Link bei MegaDB hat oft "/files/" oder "/d/" 
                        # oder endet auf typische Dateiendungen.
                        # Wir ignorieren .js, .css, .png, etc.
                        
                        if any(x in request_url for x in [".rar"]):
                            found_url = request_url
                            break
                        
                        # Manchmal sieht der Link auch so aus: https://s18.megadb.net/d/TOKEN/filename
                        if "/d/" in request_url and "megadb.net" in request_url:
                            found_url = request_url
                            break
                
                if found_url:
                    break
                time.sleep(0.5)

            if found_url:
                return DownloadableContext(found_url, "get", found_url.split(".")[-1], worker=_download_data["provider_support"]["megadb"]["worker"], delay=_download_data["provider_support"]["megadb"]["delay"])
            else:
                logging.warning("Kein eindeutiger File-Link im Netzwerkverkehr gefunden.")
                return None

        except Exception as e:
            logging.error(f"Fehler: {e}")
        finally:
            logging.info("Browser wird geschlossen.")
            driver.quit()
    
    @staticmethod
    def vikingfile(url: str) -> DownloadableContext:
        pass
    
    @staticmethod
    def voe(url: str) -> DownloadableContext:
        session = requests.Session()
        response = session.get(url)
        response, current_url = DownloadUtils._detect_redirect(response, session)

        download_url = current_url.rstrip('/') + "/download"
        response = session.get(download_url)

        response, final_url = DownloadUtils._detect_redirect(response, session)
        soup = BeautifulSoup(response.text, 'html.parser')
        target_element = soup.select_one("a.btn:nth-child(1)")

        if target_element:
            link = target_element.get('href')

            try:
                extension = link.split('?')[0].split('.')[-1]
                
            except Exception:
                logging.warning("Could not determine file extension, defaulting to 'mp4'")
                extension = "mp4"
            
            return DownloadableContext(link, "get", extension, session=session, worker=_download_data["provider_support"]["voe"]["worker"], delay=_download_data["provider_support"]["voe"]["delay"])
        
    @staticmethod
    def veev(url: str) -> DownloadableContext:
        pass
    
    @staticmethod
    def strmup(url: str) -> DownloadableContext:
        pass

class SiteScraper:
    @staticmethod
    def source_1(url: str, scraper: UniversalScraper) -> dict:
        try:
            page_content = scraper.get_html(url)
            soup = BeautifulSoup(page_content, 'html.parser')
            
            # Generic extraction - assumes H1 contains Name and Version in some format
            h1 = soup.h1.get_text() if soup.h1 else "Unknown"
            
            if "Download" in h1:
                parts = h1.split("Download")
                name = parts[0].strip()
                version = parts[1].strip().strip("() ") if len(parts) > 1 else "N/A"
            else:
                name = h1
                version = "N/A"
            
            logging.info("Source 1: Extracting downloadable links")
            
            found_links = {}
            
            for key, data_ in _download_data["provider_support"].items():
                regex_finder = re.findall(data_["pattern"], page_content)
                if regex_finder and len(regex_finder) == 1:
                    found_links[key] = data_["formaturl"].format(detected_link = regex_finder[0])
                else:
                    found_links[key] = None
            
            return found_links, name, version
                
        except Exception as e:
            logging.error(f"Source 1 Fetch Error: {e}")
            return {}, "Unknown", "N/A"
    
    @staticmethod
    def source_2(url):
        r = requests.get(url)
        r.raise_for_status()
        page_content = r.text
        
        soup = BeautifulSoup(page_content, 'html.parser')
        
        found_links = {}
            
        for key, data_ in _download_data["provider_support"].items():
            if key == "voe":
                link_element = soup.find("a", href=re.compile(r'voe\.sx'))
                if link_element:
                    found_links[key] = link_element['href']
                else:
                    found_links[key] = None
            else:
                regex_finder = re.findall(data_["pattern"], page_content)
                if regex_finder and len(regex_finder) == 1:
                    found_links[key] = data_["formaturl"].format(detected_link = regex_finder[0])
                else:
                    found_links[key] = None

        return found_links

_download_data = {
    "site_support": {
        "source_1": {
            "provider": [
                "gofile", "filecrypt", "buzzheavier", "fichier", "datanode", "megadb", "vikingfile"
            ],
            "file_ending": "rar",
            "has_compression": True,
            "compression_type": "rar",
            "extractor": SiteScraper.source_1,
            "need_scraper": True
        },
        "source_2": {
            "provider": [
                "voe", "veev", "strmup",
            ],
            "file_ending": "mp4",
            "has_compression": False,
            "compression_type": "",
            "extractor": SiteScraper.source_2,
            "need_scraper": False
        }
    },
    "provider_support": {
        "gofile": {
            "formaturl": "https://gofile.io/d/{detected_link}",
            "priority": 2,
            "identifier": r"https://gofile\.io/d/(.+)",
            "pattern": r'href="//gofile\.io/d/([^"]+)"',
            "enabled": False,
            "worker": 2,
            "delay": 0.5,
            "ddl": DDLExtractor.gofile
        },
        "buzzheavier": {
            "formaturl": "https://buzzheavier.com/{detected_link}",
            "priority": 1,
            "identifier": r"https://buzzheavier\.com/(.+)",
            "pattern": r'href="//buzzheavier\.com/([^"]+)"',
            "enabled": True,
            "worker": 5,
            "delay": 0.5,
            "ddl": DDLExtractor.buzzheavier
        },
        "fichier": {
            "formaturl": "https://1fichier.com/?{detected_link}",
            "priority": 7,
            "identifier": r"https://1fichier\.com/\?(.+)",
            "pattern": r'href="//1fichier\.com/\?([^"]+)"',
            "enabled": True,
            "worker": 1,
            "delay": 0.5,
            "ddl": DDLExtractor.fichier
        },
        "datanode": {
            "formaturl": "https://datanodes.to/{detected_link}",
            "priority": 5,
            "identifier": r"https://datanodes\.to/(.+)",
            "pattern": r'href="//datanodes\.to/([^"]+)"',
            "enabled": False,
            "worker": 2,
            "delay": 0.5,
            "ddl": DDLExtractor.datanode
        },
        "megadb": {
            "formaturl": "https://megadb.net/{detected_link}",
            "priority": 4,
            "identifier": r"https://megadb\.net/(.+)",
            "pattern": r'href="//megadb\.net/([^"]+)"',
            "enabled": True,
            "worker": 12,
            "delay": 2,
            "ddl": DDLExtractor.megadb
        },
        "vikingfile": {
            "formaturl": "https://vikingfile.com/f/{detected_link}",
            "priority": 6,
            "identifier": r"https://vikingfile\.com/(.+)",
            "pattern": r'href="//vikingfile\.com/([^"]+)"',
            "enabled": True,
            "worker": 0,
            "delay": 0.5,
            "ddl": DDLExtractor.vikingfile
        },
        # ------ Streaming Providers ------
        "voe": {
            "formaturl": "https://voe.sx/{detected_link}",
            "priority": 101,
            "identifier": r"https://voe\.sx/(.*)",
            "pattern": r'href="//voe\.sx/([^"]+)"',
            "enabled": True,
            "worker": 25,
            "delay": 0.5,
            "ddl": DDLExtractor.voe
        },
        "veev": {
            "formaturl": "https://veev.to/{detected_link}",
            "priority": 102,
            "identifier": r"https://veev\.to/e/(.*)",
            "pattern": r'href="//veev\.to/e/([^"]+)"',
            "enabled": False,
            "worker": 0,
            "delay": 0.5,
            "ddl": DDLExtractor.veev
        },
        "strmup": {
            "formaturl": "https://strmup.to/{detected_link}",
            "priority": 100,
            "identifier": r"https://strmup\.to/(.*)",
            "pattern": r'href="strmup\.to/([^"]+)"',
            "enabled": False,
            "worker": 0,
            "delay": 0.5,
            "ddl": DDLExtractor.strmup
        }
    }
}

class ValidatedUrl:
    def __init__(self, key: str, is_site: bool, is_provider: bool):
        self.key = key
        self.is_site = is_site
        self.is_provider = is_provider

class DownloaderData:
    def __init__(self, data: dict, url, key):
        self.key = key
        self.formaturl = data.get("formaturl")
        self.priority = data.get("priority")
        self.identifier = data.get("identifier")
        self.enabled = data.get("enabled")
        self.worker = data.get("worker")
        self.delay = data.get("delay")
        self.extract = data.get("ddl")
        
        self.url = url
        self.data = {}
    
    def add_data(self, key, value):
        self.data[key] = value
    
    def get_context(self) -> DownloadableContext:
        ctx = self.extract(self.url)
        if ctx:
            # Ensure worker and delay are always set from the provider data
            ctx.worker = getattr(self, 'worker', 1)
            ctx.delay = getattr(self, 'delay', 0.5)
        return ctx

class DownloadUtils:
    @staticmethod
    def _validate_url(url: str) -> ValidatedUrl:
        url = url.lower()
        
        if not url.startswith("http"):
            raise InvalidUrlException()
        
        is_site = False
        is_provider = False
        
        key = None
        
        # Load sources from config
        try:
            # We need to find the config folder path. 
            # In LIBB, we might need a better way to find it if it's not absolute.
            # But based on utility_vars, we know where it is in AppData.
            # For simplicity, I'll try to find it relative to PROJECT_ROOT if I had it.
            # Let's assume we can use a helper or just check the sources we know.
            
            # Temporary: Check source URLs from a loaded config if we had a global way.
            # For now, I'll use a dynamic check based on the sources in site_support 
            # and try to match with the config.
            
            # Since I can't easily import from src.utility here without circular imports maybe,
            # I'll use a generic approach.
            
            # Let's try to find project root to get the config
            from pathlib import Path
            appdata = os.getenv('APPDATA')
            config_file = Path(appdata) / "SyntaxRipper" / "Config" / "config.json"
            
            if config_file.exists():
                with open(config_file, "r") as f:
                    config = json.load(f)
                    for sid, sdata in config.get("sources", {}).items():
                        surl = sdata.get("source_url", "").lower()
                        if surl and surl in url:
                            is_site = True
                            key = sid
                            break
        except Exception as e:
            logging.error(f"Error validating via config: {e}")

        if key != None:
            return ValidatedUrl(key=key, is_site=is_site, is_provider=is_provider)
        
        for provider in _download_data["provider_support"].keys():
            if provider in url:
                is_provider = True
                key = provider
                break
            
        if key != None:
            return ValidatedUrl(key=key, is_site=is_site, is_provider=is_provider)

        raise UnknownProviderException()
    
    @staticmethod
    def _get_parent_key(validated: ValidatedUrl) -> str:
        if validated.is_site:
            return "site_support"
        
        elif validated.is_provider:
            return "provider_support"
        
        raise UnknownProviderException()
    
    @staticmethod
    def _get_best_downloader(urls: dict, ignore: list = []) -> DownloaderData:
        __best_downloader = None
        __best_key = None
        url = None
        
        for key, download_link in urls.items():
            if key in ignore:
                continue

            if not _download_data["provider_support"][key]["enabled"]:
                continue
            
            if download_link != None:
                if __best_downloader == None:
                    __best_downloader = _download_data["provider_support"][key]
                    __best_key = key
                    url = download_link
                    continue
                
                if _download_data["provider_support"][key]["priority"] < __best_downloader["priority"]:
                    __best_downloader = _download_data["provider_support"][key]
                    __best_key = key
                    url = download_link
        
        if __best_downloader:
            return DownloaderData(__best_downloader, url, __best_key)
        return None
    
    @staticmethod
    def _detect_redirect(response, session, headers={}):
        """
        Checks for JS redirect. 
        Returns: (response object, current_url string)
        """
        current_url = response.url 
        if "window.location.href" in response.text:
            print("Javascript redirect detected. Extracting new URL...")
            match = re.search(r"window\.location\.href\s*=\s*'([^']+)'", response.text)
            if match:
                new_url = match.group(1)
                print(f"Following redirect to: {new_url}")
                response = session.get(new_url, headers=headers)
                current_url = new_url
            else:
                print("Could not extract the redirect URL regex.")
        return response, current_url

class Downloader:
    @staticmethod
    def get_downloader(url: str, scraper: UniversalScraper = None, ignore = []) -> DownloaderData:
        validated = DownloadUtils._validate_url(url)
        
        parrent_key = DownloadUtils._get_parent_key(validated)
        
        if validated.is_provider:
            
            data = _download_data[parrent_key][validated.key]
            return DownloaderData(data, url, validated.key)
        
        data = _download_data[parrent_key][validated.key]
        
        extractor = data.get("extractor")
        
        if data.get("need_scraper"):
            dict_data, name, version = extractor(url, scraper)
        
        else:
            dict_data = extractor(url)
        
        best_downloader = DownloadUtils._get_best_downloader(dict_data, ignore = ignore)
        
        if data.get("need_scraper"):
            best_downloader.add_data("name", name)
            best_downloader.add_data("version", version)
            
        return best_downloader
