import os
import re
import logging
from .utility_vars import CONFIG_FOLDER
from .utility_functions import load_json

logger = logging.getLogger(__name__)

def update_game_configs(games_path="Games", username=None, language=None):
    """
    Iterates through all games in the Games directory and updates their configuration files
    with the default username and language.
    
    If username or language are not provided, they are loaded from userconfig.json.
    """
    logger.info("Starting game configuration update...")
    
    config_path = os.path.join(CONFIG_FOLDER, "userconfig.json")
    user_config = load_json(config_path)
    
    if username is None:
        username = user_config.get("default_username", "").strip()
    if language is None:
        language = user_config.get("default_language", "").strip()
    
    if not username and not language:
        logger.info("No default username or language set. Skipping update.")
        return

    if not os.path.exists(games_path):
        logger.warning(f"Games path '{games_path}' does not exist.")
        return

    # Helper to update ini/info content
    def update_ini_content(lines):
        modified = False
        new_lines = []
        for line in lines:
            # Check for Username/Nickname keys
            if username:
                # Matches "Key=Value" or "Key = Value", case insensitive
                if re.match(r"^\s*(UserName|PlayerName|AccountName|Name|NickName)\s*=", line, re.IGNORECASE):
                    key, sep, val = line.partition('=')
                    # Preserve key and separator (including potential whitespace), replace value
                    # We assume the value ends at the newline.
                    new_line = f"{key}{sep}{username}\n"
                    if new_line != line:
                        line = new_line
                        modified = True

            # Check for Language keys
            if language:
                if re.match(r"^\s*(Language|ForceLanguage)\s*=", line, re.IGNORECASE):
                    key, sep, val = line.partition('=')
                    new_line = f"{key}{sep}{language}\n"
                    if new_line != line:
                        line = new_line
                        modified = True
            
            new_lines.append(line)
        return new_lines, modified

    # Process a single file
    def process_file(file_path):
        filename = os.path.basename(file_path).lower()
        
        try:
            # Handle specific text files
            if filename == "language.txt" and language:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().strip()
                if content != language:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(language)
                    logger.info(f"Updated language in {file_path}")
                return
            
            if filename == "account_name.txt" and username:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().strip()
                if content != username:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(username)
                    logger.info(f"Updated username in {file_path}")
                return

            # Handle .ini and .info files
            if filename.endswith(('.ini', '.info')):
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                
                new_lines, modified = update_ini_content(lines)
                
                if modified:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.writelines(new_lines)
                    logger.info(f"Updated config in {file_path}")

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")

    # Walk through Games directory
    for root, dirs, files in os.walk(games_path):
        for file in files:
            process_file(os.path.join(root, file))
    
    logger.info("Game configuration update finished.")
