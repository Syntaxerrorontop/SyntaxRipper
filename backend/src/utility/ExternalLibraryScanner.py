import os
import json
import winreg
import re

class ExternalLibraryScanner:
    def __init__(self):
        self.games = []

    def scan(self):
        self.games = []
        self._scan_steam()
        self._scan_epic()
        self._scan_ubisoft()
        self._scan_ea()
        self._scan_gog()
        return self.games

    def _parse_acf(self, file_path):
        """Simple ACF parser to extract name and appid."""
        data = {}
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                # Find "name" "Game Name"
                name_match = re.search(r'"name"\s+"([^"]+)"', content, re.IGNORECASE)
                if name_match:
                    data["name"] = name_match.group(1)
                
                # Find "appid" "123"
                appid_match = re.search(r'"appid"\s+"(\d+)"', content, re.IGNORECASE)
                if appid_match:
                    data["appid"] = appid_match.group(1)
        except Exception as e:
            print(f"Error parsing ACF {file_path}: {e}")
        return data

    def _parse_vdf(self, file_path):
        """Simple VDF parser for libraryfolders.vdf to extract paths."""
        paths = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                # Look for "path" "C:\\Steam" pattern
                # Modern libraryfolders.vdf uses numeric keys for folders, inside which there is a "path" key.
                # Example: "1" { "path" "C:\\Games\\Steam" ... }
                matches = re.findall(r'"path"\s+"([^"]+)"', content, re.IGNORECASE)
                for m in matches:
                    paths.append(m.replace("\\\\", "\\"))
        except Exception as e:
            print(f"Error parsing VDF {file_path}: {e}")
        return paths

    def _scan_steam(self):
        steam_path = None
        try:
            # 1. Get Steam Path from Registry
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            steam_path = winreg.QueryValueEx(key, "SteamPath")[0]
            winreg.CloseKey(key)
        except Exception:
            pass

        if not steam_path:
            # Fallback to default
            default_path = r"C:\Program Files (x86)\Steam"
            if os.path.exists(default_path):
                steam_path = default_path
        
        if not steam_path:
            return

        # Normalize path
        steam_path = os.path.normpath(steam_path)
        library_folders = [steam_path]

        # 2. Read libraryfolders.vdf to find other libraries
        vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf_path):
            found_paths = self._parse_vdf(vdf_path)
            for path in found_paths:
                if path and os.path.normpath(path) not in [os.path.normpath(p) for p in library_folders]:
                    library_folders.append(path)

        # 3. Scan each library for .acf files
        for lib in library_folders:
            steamapps = os.path.join(lib, "steamapps")
            if not os.path.exists(steamapps):
                continue

            for file in os.listdir(steamapps):
                if file.endswith(".acf"):
                    acf_path = os.path.join(steamapps, file)
                    app_data = self._parse_acf(acf_path)
                    
                    name = app_data.get("name")
                    appid = app_data.get("appid")
                    
                    if name and appid and name != "Steamworks Common Redistributables":
                        self.games.append({
                            "name": name,
                            "version": "Steam",
                            "exe": f"steam://run/{appid}",
                            "path": f"steam://run/{appid}", # Special marker
                            "link": f"https://store.steampowered.com/app/{appid}/",
                            "platform": "Steam"
                        })

    def _scan_epic(self):
        manifests_path = r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"
        if not os.path.exists(manifests_path):
            return

        for file in os.listdir(manifests_path):
            if file.endswith(".item"):
                try:
                    with open(os.path.join(manifests_path, file), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                        name = data.get("DisplayName")
                        install_loc = data.get("InstallLocation")
                        launch_exe = data.get("LaunchExecutable")
                        
                        if name and install_loc and launch_exe:
                            full_exe_path = os.path.join(install_loc, launch_exe)
                            self.games.append({
                                "name": name,
                                "version": "Epic",
                                "exe": full_exe_path,
                                "path": full_exe_path,
                                "link": "https://store.epicgames.com/",
                                "platform": "Epic"
                            })
                except Exception as e:
                    print(f"Error parsing Epic manifest {file}: {e}")

    def _scan_ubisoft(self):
        """Scans Ubisoft Connect games via Registry."""
        try:
            # Look into the Uninstall keys for Uplay games
            uninstall_key_path = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, uninstall_key_path) as key:
                for i in range(0, winreg.QueryInfoKey(key)[0]):
                    try:
                        sub_key_name = winreg.EnumKey(key, i)
                        if sub_key_name.startswith("Uplay Install "):
                            with winreg.OpenKey(key, sub_key_name) as sub_key:
                                display_name = winreg.QueryValueEx(sub_key, "DisplayName")[0]
                                install_loc = winreg.QueryValueEx(sub_key, "InstallLocation")[0]
                                
                                # Extract ID from key name "Uplay Install <ID>"
                                game_id = sub_key_name.split(" ")[-1]
                                
                                # Prefer launching via Uplay protocol
                                exe_path = f"uplay://launch/{game_id}/0"
                                
                                self.games.append({
                                    "name": display_name,
                                    "version": "Ubisoft",
                                    "exe": exe_path,
                                    "path": exe_path, # Marker
                                    "link": "https://store.ubisoft.com/",
                                    "platform": "Ubisoft"
                                })
                    except OSError:
                        continue
        except Exception as e:
            print(f"Error scanning Ubisoft: {e}")

    def _scan_ea(self):
        """Scans EA App games via Registry."""
        try:
            # Check EA Games key
            ea_games_path = r"SOFTWARE\WOW6432Node\Electronic Arts\EA Games"
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ea_games_path)
            except FileNotFoundError:
                return

            with key:
                for i in range(0, winreg.QueryInfoKey(key)[0]):
                    try:
                        game_key_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, game_key_name) as game_key:
                            try:
                                install_dir = winreg.QueryValueEx(game_key, "InstallDir")[0]
                                display_name = winreg.QueryValueEx(game_key, "DisplayName")[0]
                            except FileNotFoundError:
                                # Sometimes DisplayName isn't there, fallback to key name
                                display_name = game_key_name
                                try:
                                    install_dir = winreg.QueryValueEx(game_key, "InstallDir")[0]
                                except FileNotFoundError:
                                    continue

                            # Try to find an EXE in the install dir
                            found_exe = None
                            if os.path.exists(install_dir):
                                # 1. Try Name.exe
                                candidate = os.path.join(install_dir, f"{display_name}.exe")
                                if os.path.exists(candidate):
                                    found_exe = candidate
                                else:
                                    # 2. Find largest EXE
                                    largest_size = 0
                                    for root, dirs, files in os.walk(install_dir):
                                        for file in files:
                                            if file.lower().endswith(".exe") and "cleanup" not in file.lower() and "touchup" not in file.lower():
                                                full_path = os.path.join(root, file)
                                                size = os.path.getsize(full_path)
                                                if size > largest_size:
                                                    largest_size = size
                                                    found_exe = full_path
                            
                            if found_exe:
                                self.games.append({
                                    "name": display_name,
                                    "version": "EA",
                                    "exe": found_exe,
                                    "path": found_exe,
                                    "link": "https://www.ea.com/games",
                                    "platform": "EA"
                                })
                    except OSError:
                        continue
        except Exception as e:
            print(f"Error scanning EA: {e}")

    def _scan_gog(self):
        """Scans GOG Galaxy games via Registry."""
        try:
            gog_games_path = r"SOFTWARE\WOW6432Node\GOG.com\Games"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, gog_games_path) as key:
                for i in range(0, winreg.QueryInfoKey(key)[0]):
                    try:
                        game_id = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, game_id) as game_key:
                            display_name = winreg.QueryValueEx(game_key, "gameName")[0]
                            # exe value often points to the main executable relative to path, or absolute
                            exe_file = winreg.QueryValueEx(game_key, "exe")[0]
                            path = winreg.QueryValueEx(game_key, "path")[0]
                            
                            full_exe_path = os.path.join(path, exe_file)
                            
                            self.games.append({
                                "name": display_name,
                                "version": "GOG",
                                "exe": full_exe_path,
                                "path": full_exe_path,
                                "link": f"https://www.gog.com/game/{display_name.replace(' ', '_').lower()}",
                                "platform": "GOG"
                            })
                    except OSError:
                        continue
        except Exception as e:
            print(f"Error scanning GOG: {e}")
