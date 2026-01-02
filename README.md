# SyntaxRipper V3

[![Version](https://img.shields.io/badge/version-3.18.3-blue.svg)](version.txt)
[![License](https://img.shields.io/badge/license-Educational-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)

SyntaxRipper is a high-performance, modern Game Manager and Launcher built with a focus on automation, system optimization, and a seamless user experience. It serves as a unified hub for your local game library, providing tools that go beyond simple launching—including advanced file compression, automated save backups, and deep system integration.

---

> **DISCLAIMER:** This project is a proof-of-concept created for **research and educational purposes only**. It is intended to demonstrate automation techniques, asynchronous backend patterns, and modern UI/UX design. The author provides no warranty and assumes no liability for how this code is used.

## ⚠️ MANDATORY LEGAL NOTICE & PROHIBITED USE

**Please read this carefully. By accessing or using this code, you agree to these terms.**

1.  **Educational Purpose Only:** This repository exists solely to showcase coding techniques, library management logic, and system integration. It is not intended to be used as a tool for acquiring copyrighted media.
2.  **STRICTLY NO UNAUTHORIZED DOWNLOADS:** This software **must NOT** be used to download, stream, or distribute any copyrighted material without the express permission of the original creator or rights holder. 
3.  **User Accountability:** The author (`Syntaxerrorontop`) does not host any content, does not provide links to copyrighted media, and does not condone piracy in any form. The user is 100% responsible for their own actions and any legal consequences resulting from the misuse of this code.
4.  **No Piracy Support:** If you intend to use this software for any illegal activity, including the infringement of intellectual property rights, you are strictly prohibited from using this code.
5.  **Tool Purpose:** The built-in downloader is a generic HTTP client designed for fetching open-source assets, personal backups, or self-hosted files only.

---

## 🚀 Key Features

### 📚 Advanced Library Management
*   **Automated Scanning:** Efficiently scans multiple user-defined directories to build a comprehensive library of installed games. Supports dynamic tracking of added/removed folders.
*   **Asynchronous Metadata:** Fetches covers, high-resolution banners, and detailed descriptions using a background queue system (RAWG API integration). The UI remains responsive and loads instantly while metadata populates in the background.
*   **HLTB Integration:** Automatically retrieves "How Long To Beat" statistics so you can plan your gaming sessions based on story length and completion time.
*   **Dynamic Collections:** Organize your library into nested categories and custom collections with full drag-and-drop support. Categorize by genre, platform, or personal priority.
*   **Profile Analytics:** Track your gaming habits with persistent playtime tracking and detailed genre distribution charts.

### 🔍 Unified Store & Media Search
*   **Integrated Game Search:** Directly search supported providers (like SteamRIP) from within the app. Results are displayed in a clean, animated card-based grid with full pagination.
*   **Multimedia Support:** Search for Movies, Series, and Anime alongside your games. Includes detailed metadata and poster previews for a complete media catalog experience.
*   **Interactive Previews:** Click on any game result to see a full-screen high-resolution overlay with screenshots, system requirements, descriptions, and direct "Add to Library" or "Download" actions.

### 🎨 Powerful Theme Editor
*   **Real-time Customization:** Create your own look with the built-in Theme Editor. Adjust every color variable—from background and sidebar to accent colors and shadows—with immediate live previews.
*   **Preset Themes:** Includes high-quality presets like **Dark, OLED (True Black), Cyberpunk, Dracula, Nord, Midnight, Forest,** and more.
*   **Import/Export:** Share your custom themes or backup your creations by exporting them to standard JSON files. Import them back with a single click.
*   **Persistent Variables:** Custom themes are saved to your configuration and load automatically on application restart.

### 🛠️ Maintenance & Optimization Tools
*   **Game Folder Compression:** Utilizes Windows CompactOS (LZX) technology to compress game directories significantly without sacrificing performance or load times. Perfect for maximizing SSD space.
*   **Save Backup & Recovery:** Creates timestamped backups of your game saves automatically upon exit. Restore to a previous state with a single click in the maintenance menu.
*   **Integrity Verification:** Generate baseline MD5 checksums for your game files and verify them later to detect and fix corruption caused by drive errors or antivirus interference.
*   **Junk Cleaner:** Scans game directories for unnecessary leftover files like old installers, temporary caches, and redundant redistributables (`_CommonRedist`, `DirectX`).
*   **Windows Defender Exclusions:** Automatically add your game libraries and download caches to Defender exclusions to prevent false positives and missing executable files.

### ⚡ System Integration
*   **Gaming Mode:** Automatically optimizes your PC for gaming by switching to the "High Performance" power plan and boosting the process priority of the active game.
*   **Big Picture Mode:** A dedicated, fullscreen interface optimized for controllers and 10-foot viewing. Features a controller-friendly grid and large-scale navigation.
*   **Windows Sandbox Launcher:** Securely launch untrusted games within an isolated Windows Sandbox environment. Protects your host system from potential threats using a Zero Trust approach.
*   **Discord Rich Presence:** Share your current game and playtime on your Discord profile automatically with high-quality icons.
*   **Real-Debrid Integration:** Connect your Real-Debrid account to unlock premium speeds for supported file hosts within the internal download manager.

---

## 🏗️ Technical Architecture

SyntaxRipper uses a decoupled client-server architecture designed for speed and reliability:

*   **Backend (The "Engine"):** Powered by **FastAPI (Python)**. It handles all heavy lifting, including:
    *   **Asynchronous I/O:** Non-blocking file operations and network requests.
    *   **Automation:** Selenium-based scraping with `undetected-chromedriver` to bypass bot detection.
    *   **Download Management:** A custom queue-based manager with pause/resume, speed limiting, and automatic extraction.
    *   **System Hooks:** Direct interaction with Windows APIs for power management and process priority.
*   **Frontend (The "Cockpit"):** A sleek, reactive interface built with **HTML5/CSS3/JavaScript** and hosted within **Electron**.
    *   **Inter-Process Communication (IPC):** Uses Electron's IPC to securely communicate with the Python backend.
    *   **CSS Grid & Flexbox:** A modern, responsive layout that adapts to any window size or Big Picture viewing.
    *   **Animations:** Smooth transitions and staggered fade-ins for a premium feel.
*   **Data Persistence:** Configured settings and library data are stored in structured JSON files, ensuring easy portability and human-readable backups.

---

## 📥 Installation & Setup

1.  **Standard Installation:**
    Double-click **`install.bat`**. This sets up the application in your `AppData` directory, installs the Python virtual environment, and creates a Start Menu shortcut.
2.  **Portable Installation:**
    Double-click **`install_portable.bat`**. Everything (including configs, cache, and downloaded games) will stay within the current directory. This mode is activated by the presence of a `portable.mode` file. Perfect for external SSDs or USB drives.

---

## 🔄 Updating

SyntaxRipper features a built-in automated update mechanism. To update:
1.  Run **`update.bat`** in the application folder.
2.  Alternatively, use the **"Check for Updates"** button in the Settings tab.
*Note: The update process safely stashes your local configuration changes before pulling the latest code from GitHub to ensure no data loss.*

---

## 🛠️ Troubleshooting & Logs

If you encounter issues, SyntaxRipper maintains detailed logs:
*   **Main Application Log:** Found at `latest.log` in the root directory. This captures output from both the frontend and backend processes.
*   **Server Detailed Log:** Found in `%APPDATA%\SyntaxRipper\server.log` (Standard) or the `backend/` folder (Portable).
*   **Common Fix:** If the library appears empty, check your "Library Locations" in Settings and ensure your RAWG API key is valid.

---

## 🎮 Developing & Contributing

Contributions are welcome for research purposes!
*   **Backend Source:** Located in `backend/src/`.
*   **Frontend Source:** Located in `frontend/`.
*   **Debug Mode:** Launch `start.bat` directly to see real-time console output from the FastAPI server and Electron renderer.

---

**Developed with ❤️ by Syntaxerrorontop**