import logging, os, json

from .utility_functions import load_json, save_json

class Payload:
    def __init__(self):
        logging.debug("Payload created")
        self._payload = {}
    
    def add_operation(self, operation):
        logging.debug(f"PAYLOAD: operation added: {operation}")
        self._payload["op"] = operation
    
    def add_id(self, id):
        logging.debug(f"PAYLOAD: id added: {id}")
        self._payload["id"] = id
    
    def add_rand(self, rand):
        logging.debug(f"PAYLOAD: rand added: {rand}")
        self._payload["rand"] = rand
    
    def add_referer(self, referer):
        logging.debug(f"PAYLOAD: referer added: {referer}")
        self._payload["referer"] = referer
    
    def add_method_free(self, method):
        logging.debug(f"PAYLOAD: free_method added: {method}")
        self._payload["method_free"] = method
    
    def add_method_premium(self, method):
        logging.debug(f"PAYLOAD: premium_method added: {method}")
        self._payload["method_premium"] = method
    
    def add_dl(self, dl):
        logging.debug(f"PAYLOAD: dl added: {dl}")
        self._payload["dl"] = dl
    
    def get(self):
        logging.debug(f"Payload generated: {self._payload}")
        return self._payload

class Header:
    def __init__(self):
        self._headers = {}
    
    def add_user_agent(self, user_agent):
        self._headers['user-agent'] = user_agent
    
    def add_authority(self, authority):
        self._headers['authority'] = authority
    
    def add_method(self, method):
        self._headers['method'] = method
    
    def add_path(self, path):
        self._headers["path"] = path
    
    def add_referer(self, referer):
        self._headers['referer'] = referer
    
    def add_hx_request(self, hx_request):
        self._headers['hx_request'] = hx_request
    
    def add_others(self, key, value):
        self._headers[key] = value
    
    def get_headers(self):
        return self._headers

class File:
    @staticmethod
    def check_existence(in_path, file_name, create = True, add_conten = "", use_json = False, quite=False) -> bool:
        if not quite:
            logging.debug(f"Checking {file_name} existence in {in_path}.")

        if not file_name in os.listdir(in_path):
            if not quite:
                logging.debug(f"File not found")
            with open(os.path.join(in_path, file_name), "w") as file:
                file.close()
                if not quite:
                    logging.debug(f"File created: {create} {file_name}")
                
                if add_conten != "":
                    with open(os.path.join(in_path, file_name), "w") as file:
                        if use_json:
                            json.dump(add_conten, file, indent=4)
                        else:
                            file.write(add_conten)
                        file.close()
                    if not quite:
                        logging.debug(f"Added content to {file_name}")
                
                return True
            
            return False
        if not quite:
            logging.debug("File already exists")
        
        return True

class UserConfig:
    def __init__(self, in_path, filename, quite=False):
        
        # Define the Documents folder path for large files
        doc_path = os.path.join(os.path.expanduser("~"), "Documents", "SyntaxRipper")
        
        default_data = {
            "install_commen_redist": True, 
            "shutil_move_error_replace": True, 
            "search": {"games": True, "movies": False, "series": False}, 
            "start_up_update": True, 
            "speed": 0, 
            "speed_limit_enabled": False,
            "excluded": False, 
            "exclude_message": True, 
            "resume_on_startup": True,
            "dry_launch": False,
            "game_paths": [os.path.join(doc_path, "Games")],
            "download_path": os.path.join(doc_path, "Downloads"),
            "download_cache_path": os.path.join(doc_path, "DownloadCache"),
            "installed_games_path": os.path.join(doc_path, "Games"),
            "media_output_path": os.path.join(doc_path, "ConvertedMedia"),
            "default_username": "Guest",
            "rawg_api_key": "",
            "auto_update_games": False,
            "real_debrid_key": "",
            "controller_support": False,
            "controller_mapping": {"select": 0, "back": 1},
            "collapsed_categories": []
        }
        
        File.check_existence(in_path, filename, add_conten=default_data, use_json=True, quite=quite)
        
        self._path = os.path.join(in_path, filename)
        self._data = load_json(self._path)
        logging.debug("Verifying Config")
        adding = {}
        for key, item in default_data.items():
            if not key in self._data.keys():
                adding[key] = item
                # If we just added the whole dict, no need to check sub-keys against the non-existent original
                continue
            
            if isinstance(item, dict):
                # Ensure the existing item is actually a dict before checking keys
                if not isinstance(self._data[key], dict):
                    self._data[key] = item # Overwrite if type mismatch (rare/safe fallback)
                    continue

                for sub_key, sub_i in item.items():
                    if not sub_key in self._data[key].keys():
                        # We can't write to 'adding' deeply if 'adding[key]' doesn't exist yet
                        if key not in adding:
                            adding[key] = {}
                        adding[key][sub_key] = sub_i
        
        if adding != {}:
            # Deep merge 'adding' into 'self._data'
            for k, v in adding.items():
                if k in self._data and isinstance(self._data[k], dict) and isinstance(v, dict):
                    self._data[k].update(v)
                else:
                    self._data[k] = v
            
            save_json(os.path.join(in_path, filename), self._data)
        
        self.SHUTIL_MOVE_ERROR_REPLACE = self._data["shutil_move_error_replace"]
        self.INSTALL_COMMENREDIST_STEAMRIP = self._data["install_commen_redist"]
        self.SEARCH_GAMES = self._data["search"]
        self.SEARCH_MOVIES = self._data["search"]["movies"]
        self.SEARCH_SERIES = self._data["search"]["series"]
        self.UPDATE_ON_STARTUP_ONLY = self._data["start_up_update"]
        self.DOWNLOAD_SPEED = self._data["speed"]
        self.DOWNLOAD_SPEED_ENABLED = self._data.get("speed_limit_enabled", False)
        self.RESUME_ON_STARTUP = self._data.get("resume_on_startup", True)
        self.DRY_LAUNCH = self._data.get("dry_launch", False)
        self.VERBOSE_LOGGING = self._data.get("verbose_logging", False)
        self.EXCLUDE_MESSAGE = self._data["exclude_message"]
        self.EXCLUDED = self._data["excluded"]
        self.GAME_PATHS = self._data.get("game_paths", [])
        self.DOWNLOAD_PATH = self._data.get("download_path", os.path.join(os.getcwd(), "Downloads"))
        self.DOWNLOAD_CACHE_PATH = self._data.get("download_cache_path", os.path.join(os.getcwd(), "DownloadCache"))
        self.INSTALLED_GAMES_PATH = self._data.get("installed_games_path", os.path.join(os.getcwd(), "Games"))
        self.USERNAME = self._data.get("default_username", "Guest")
        self.LANGUAGE = self._data.get("default_language", "english")
        self.RAWG_API_KEY = self._data.get("rawg_api_key", "")
        self.CATEGORY_ORDER = self._data.get("category_order", [])
        self.AUTO_UPDATE_GAMES = self._data.get("auto_update_games", False)
        self.REAL_DEBRID_KEY = self._data.get("real_debrid_key", "")
        self.CONTROLLER_SUPPORT = self._data.get("controller_support", False)
        self.CONTROLLER_MAPPING = self._data.get("controller_mapping", {"select": 0, "back": 1})
        self.COLLAPSED_CATEGORIES = self._data.get("collapsed_categories", [])
        self.MEDIA_OUTPUT_PATH = self._data.get("media_output_path", os.path.join(os.getcwd(), "ConvertedMedia"))
        self.DISCORD_RPC_ENABLED = self._data.get("discord_rpc_enabled", True)
        self.GAMING_MODE_ENABLED = self._data.get("gaming_mode_enabled", True)
        self.LAST_SELECTED_GAME_ID = self._data.get("last_selected_game_id", None)
        self.SHOW_HIDDEN_GAMES = self._data.get("show_hidden_games", False)

    def save(self):
        self._data["shutil_move_error_replace"] = self.SHUTIL_MOVE_ERROR_REPLACE
        self._data["install_commen_redist"] = self.INSTALL_COMMENREDIST_STEAMRIP
        self._data["search"] = self.SEARCH_GAMES
        self._data["search"]["movies"] = self.SEARCH_MOVIES
        self._data["search"]["series"] = self.SEARCH_SERIES
        self._data["start_up_update"] = self.UPDATE_ON_STARTUP_ONLY
        self._data["speed"] = self.DOWNLOAD_SPEED
        self._data["speed_limit_enabled"] = self.DOWNLOAD_SPEED_ENABLED
        self._data["exclude_message"] = self.EXCLUDE_MESSAGE
        self._data["excluded"] = self.EXCLUDED
        self._data["resume_on_startup"] = self.RESUME_ON_STARTUP
        self._data["dry_launch"] = self.DRY_LAUNCH
        self._data["verbose_logging"] = self.VERBOSE_LOGGING
        self._data["game_paths"] = self.GAME_PATHS
        self._data["download_path"] = self.DOWNLOAD_PATH
        self._data["download_cache_path"] = self.DOWNLOAD_CACHE_PATH
        self._data["installed_games_path"] = self.INSTALLED_GAMES_PATH
        self._data["default_username"] = self.USERNAME
        self._data["default_language"] = self.LANGUAGE
        self._data["rawg_api_key"] = self.RAWG_API_KEY
        self._data["category_order"] = self.CATEGORY_ORDER
        self._data["auto_update_games"] = self.AUTO_UPDATE_GAMES
        self._data["real_debrid_key"] = self.REAL_DEBRID_KEY
        self._data["controller_support"] = self.CONTROLLER_SUPPORT
        self._data["controller_mapping"] = self.CONTROLLER_MAPPING
        self._data["collapsed_categories"] = self.COLLAPSED_CATEGORIES
        self._data["media_output_path"] = self.MEDIA_OUTPUT_PATH
        self._data["discord_rpc_enabled"] = self.DISCORD_RPC_ENABLED
        self._data["gaming_mode_enabled"] = self.GAMING_MODE_ENABLED
        self._data["last_selected_game_id"] = self.LAST_SELECTED_GAME_ID
        self._data["show_hidden_games"] = self.SHOW_HIDDEN_GAMES
        
        save_json(self._path, self._data)