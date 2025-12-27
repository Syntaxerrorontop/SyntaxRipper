# SyntaxRipper V3

> **DISCLAIMER:** This project is a proof-of-concept created for **research and educational purposes only**. It is intended to demonstrate automation and UI design patterns. The author provides no warranty and assumes no liability for how this code is used.

## ⚠️ MANDATORY LEGAL NOTICE & PROHIBITED USE

**Please read this carefully. By accessing or using this code, you agree to these terms.**

1.  **Educational Purpose Only:** This repository exists solely to showcase coding techniques, library management logic, and system integration. It is not intended to be used as a tool for acquiring media.
2.  **STRICTLY NO UNAUTHORIZED DOWNLOADS:** This software **must NOT** be used to download, stream, or distribute any copyrighted material without the express permission of the original creator or rights holder. 
3.  **User Accountability:** The author (`Syntaxerrorontop`) does not host any content, does not provide links to copyrighted media, and does not condone piracy in any form. The user is 100% responsible for their own actions and any legal consequences resulting from the misuse of this code.
4.  **No Piracy Support:** If you intend to use this software for any illegal activity, including the infringement of intellectual property rights, you are strictly prohibited from using this code.
5.  **Tool Purpose:** The built-in downloader is a generic HTTP client designed for fetching open-source assets, personal backups, or self-hosted files only.

---

## 🚀 Features

### 📚 Library Management
*   **Centralized Hub:** Automatically scans and organizes your games into a unified library.
*   **Metadata Enrichment:** Fetches covers, screenshots, and descriptions automatically.
*   **Smart Sorting:** Filter by Name, Playtime, or Date Added.
*   **Collections:** Organize games into custom categories.
*   **Profile Stats:** Track your total playtime and favorite genres.

### 🛠️ Advanced Tools
*   **Game Compression:** Save disk space by compressing game folders using Windows CompactOS (LZX) technology without affecting performance.
*   **Integrity Checker:** Generate and verify MD5 checksums to ensure your game files are not corrupted.
*   **Junk Cleaner:** Automatically detect and remove leftover installer files (`_CommonRedist`, `DirectX`, temporary files) to free up space.
*   **Save Backup System:** Automatically backs up your game saves upon exit. Restore previous saves with a single click.

### ⚡ Performance & Integration
*   **System Gaming Mode:** Automatically switches your PC to "High Performance" power plan and boosts process priority when a game is launched.
*   **Discord Rich Presence:** Show what you're playing on your Discord profile automatically.
*   **Real-Debrid Support:** Integrate your Real-Debrid account for premium download speeds (requires API key).
*   **Controller Support:** Full navigation support for Xbox/PlayStation controllers.

### 📜 Scripting & Automation
*   **Pre-Launch/Post-Exit Scripts:** Run custom batch commands before a game starts or after it closes.
*   **Universal Downloader:** A built-in download manager that supports various file hosts.
*   **Media Converter:** Convert audio and video files (MP3, MP4, PNG, etc.) using built-in FFmpeg integration.

---

## 📥 Installation

1.  Download the repository or the latest release.
2.  Run **`install.bat`**.
    *   This will automatically install Python and Git if they are missing.
    *   It will set up the environment and create a desktop shortcut.
3.  Launch **SyntaxRipper** from your Start Menu or Desktop.

## 🔄 Updating

To update to the latest version, simply run **`update.bat`** in the installation folder, or use the **"Check for Updates"** feature in the application settings.

---

## 🎮 Usage Tips

*   **Adding Games:** Go to Settings -> Library Locations to add folders where your games are installed.
*   **Controller:** Enable "Controller Support" in Settings to navigate using a gamepad.
*   **Maintenance:** Click the "Gear" icon on any game page to access Maintenance Tools (Compress, Backup, etc.).

---

**Developed by Syntaxerrorontop**
