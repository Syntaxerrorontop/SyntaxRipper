import os

# Root Directory (v3/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PORTABLE_MODE = os.path.exists(os.path.join(PROJECT_ROOT, "portable.mode"))

# Use local 'Data' folder if in portable mode, otherwise standard AppData
if PORTABLE_MODE:
    APPDATA_CACHE_PATH = os.path.join(PROJECT_ROOT, "Data")
else:
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

# Version
try:
    with open(os.path.join(PROJECT_ROOT, "version.txt"), "r") as f:
        APP_VERSION = f.read().strip()
except:
    APP_VERSION = "3.0.0"