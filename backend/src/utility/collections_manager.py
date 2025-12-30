import os
import uuid
import logging
from .utility_functions import load_json, save_json
from .utility_vars import CONFIG_FOLDER

class CollectionsManager:
    def __init__(self):
        self.logger = logging.getLogger("CollectionsManager")
        self.config_path = os.path.join(CONFIG_FOLDER, "collections.json")
        self.logger.info(f"Collections config path: {self.config_path}")
        self._ensure_config()

    def _ensure_config(self):
        if not os.path.exists(CONFIG_FOLDER):
            try:
                os.makedirs(CONFIG_FOLDER)
            except Exception as e:
                self.logger.error(f"Failed to create config folder {CONFIG_FOLDER}: {e}")

        if not os.path.exists(self.config_path):
            self.logger.info("Initializing new collections.json")
            save_json(self.config_path, {"collections": []})

    def get_collections(self):
        data = load_json(self.config_path)
        return data.get("collections", [])

    def create_collection(self, name):
        data = load_json(self.config_path)
        if "collections" not in data:
            data["collections"] = []
            
        for col in data["collections"]:
            if col["name"].lower() == name.lower():
                return {"error": "Collection with this name already exists"}

        new_col = {
            "id": str(uuid.uuid4()),
            "name": name,
            "items": []
        }
        data["collections"].append(new_col)
        
        if self._save(data):
            self.logger.info(f"Created collection: {name}")
            return new_col
        else:
            return {"error": "Failed to save collection to disk"}

    def delete_collection(self, collection_id):
        data = load_json(self.config_path)
        original_len = len(data.get("collections", []))
        
        data["collections"] = [c for c in data.get("collections", []) if c["id"] != collection_id]
        
        if len(data["collections"]) < original_len:
            if self._save(data):
                self.logger.info(f"Deleted collection: {collection_id}")
                return True
        return False

    def rename_collection(self, collection_id, new_name):
        data = load_json(self.config_path)
        for col in data.get("collections", []):
            if col["id"] == collection_id:
                col["name"] = new_name
                return self._save(data)
        return False

    def add_item(self, collection_id, item_name):
        data = load_json(self.config_path)
        for col in data.get("collections", []):
            if col["id"] == collection_id:
                if any(item["name"].lower() == item_name.lower() for item in col["items"]):
                     return {"error": "Item already exists in this collection"}

                new_item = {
                    "id": str(uuid.uuid4()),
                    "name": item_name,
                    "status": "planned"
                }
                col["items"].append(new_item)
                if self._save(data):
                    return new_item
                else:
                    return {"error": "Failed to save item"}
        return {"error": "Collection not found"}

    def remove_item(self, collection_id, item_id):
        data = load_json(self.config_path)
        for col in data.get("collections", []):
            if col["id"] == collection_id:
                original_len = len(col["items"])
                col["items"] = [i for i in col["items"] if i["id"] != item_id]
                
                if len(col["items"]) < original_len:
                    return self._save(data)
                return False
        return False

    def update_item_status(self, collection_id, item_id, status):
        data = load_json(self.config_path)
        for col in data.get("collections", []):
            if col["id"] == collection_id:
                for item in col["items"]:
                    if item["id"] == item_id:
                        item["status"] = status
                        return self._save(data)
        return False

    def _save(self, data):
        """Helper to ensure directory exists and save."""
        if not os.path.exists(CONFIG_FOLDER):
            try:
                os.makedirs(CONFIG_FOLDER)
            except Exception as e:
                self.logger.error(f"Failed to create config folder during save: {e}")
                return False
        
        try:
            save_json(self.config_path, data)
            return True
        except Exception as e:
            self.logger.error(f"Failed to save collections: {e}")
            return False
