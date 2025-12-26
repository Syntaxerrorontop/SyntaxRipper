import requests
import logging
import urllib.parse

class DebridManager:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.logger = logging.getLogger("RealDebrid")
        self.base_url = "https://api.real-debrid.com/rest/1.0"

    def set_key(self, key):
        self.api_key = key

    def resolve_link(self, link):
        if not self.api_key:
            return None
        
        try:
            # 1. Unrestrict
            self.logger.info(f"Unrestricting link via Real-Debrid: {link}")
            headers = {"Authorization": f"Bearer {self.api_key}"}
            payload = {"link": link}
            
            resp = requests.post(f"{self.base_url}/unrestrict/link", data=payload, headers=headers)
            
            if resp.status_code == 200:
                data = resp.json()
                if "download" in data:
                    self.logger.info("Real-Debrid resolution successful.")
                    return data["download"]
            elif resp.status_code == 401:
                self.logger.error("Real-Debrid API Key invalid.")
            else:
                self.logger.warning(f"Real-Debrid failed: {resp.text}")
                
        except Exception as e:
            self.logger.error(f"Real-Debrid error: {e}")
            
        return None
