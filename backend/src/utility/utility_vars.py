import os

# Use the standard Windows AppData/Roaming folder
# This matches the path: C:\Users\<User>\AppData\Roaming\SyntaxRipper
APPDATA_CACHE_PATH = os.path.join(os.getenv('APPDATA'), "SyntaxRipper")

if not os.path.exists(APPDATA_CACHE_PATH):
    os.makedirs(APPDATA_CACHE_PATH)

CONFIG_FOLDER = os.path.join(APPDATA_CACHE_PATH, "Config")
if not os.path.exists(CONFIG_FOLDER):
    os.makedirs(CONFIG_FOLDER)

CACHE_FOLDER = os.path.join(APPDATA_CACHE_PATH, "Cached")
if not os.path.exists(CACHE_FOLDER):
    os.makedirs(CACHE_FOLDER)

ASSET_FOLDER = os.path.join(APPDATA_CACHE_PATH, "Assets")
if not os.path.exists(ASSET_FOLDER):
    os.makedirs(ASSET_FOLDER)