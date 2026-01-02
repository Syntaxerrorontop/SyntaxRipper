# SyntaxRipper - Universal Library & Automation Framework

[![Version](https://img.shields.io/badge/version-3.19.0-blue.svg)](version.txt)
[![License](https://img.shields.io/badge/license-Educational-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)

SyntaxRipper is a high-performance, local-first management framework designed for indexing, organizing, and optimizing large-scale digital libraries. It combines advanced system-level integration with a modular automation engine, providing users with a unified "Command Center" for their local assets.

Built as a **source-agnostic shell**, the application provides the infrastructure for metadata indexing and asset management. It requires user-defined configuration to interact with external web sources, operating under a model similar to generic automation tools or extensible media centers.

---

> **⚠️ MANDATORY LEGAL NOTICE**
> This software is a proof-of-concept developed for **educational and research purposes** within the fields of asynchronous backend architecture, browser automation, and human-computer interaction (HCI). 
> 
> 1. **User Responsibility:** The developers do not provide, host, or curate any content. Users are strictly responsible for ensuring that any configured data sources and downloaded materials comply with their respective local and international copyright laws.
> 2. **Neutral Technology:** This tool is a generic framework. Misuse of this software for infringing on intellectual property is strictly prohibited and not condoned by the authors.

---

## 🚀 Core Competencies

### 📚 Advanced Library Management
*   **Recursive File Indexing:** High-speed scanning of multiple local directories to build a structured database of installed software and media.
*   **Asynchronous Metadata Enrichment:** Utilizes a background worker queue to fetch descriptions and assets via standard APIs (e.g., RAWG), ensuring a zero-latency user interface.
*   **Dynamic Collections:** Advanced categorization system using nested tags and custom collections with full drag-and-drop support.
*   **Usage Analytics:** Persistent tracking of interaction time and category distribution with visual data representations.

### 🛠️ System Optimization & Maintenance
*   **Transparent LZX Compression:** Native integration with Windows CompactOS technology to significantly reduce the storage footprint of local directories without performance degradation.
*   **Automated State Backups:** Intelligent snapshot system for user data and metadata, allowing for one-click restoration of previous library states.
*   **Data Integrity Indexing:** Generation and verification of MD5/SHA-256 checksums to detect and mitigate data corruption.
*   **Redundancy Cleaner:** Heuristic scanning for temporary files and redundant deployment artifacts to reclaim storage space.

### ⚡ Automation & Transfer Engine
*   **Multi-threaded Transfer Manager:** A robust, queue-based HTTP/S download manager supporting pause/resume, speed throttling, and automated archive extraction.
*   **Generic Web Automation:** Advanced browser orchestration logic for handling complex web sessions and automated navigation patterns.
*   **Extensible Provider Logic:** A plugin-based architecture allowing users to define custom scraping patterns and source URLs via standardized JSON configurations.

---

## 🏗️ Technical Architecture

*   **Backend:** Python 3.10+ / FastAPI. High-concurrency server handling I/O-bound tasks and system API hooks.
*   **Frontend:** Electron / HTML5 / CSS Grid. A modern, GPU-accelerated interface designed for fluidity and responsiveness.
*   **Automation:** Selenium with specialized anti-detection profiles for generic web interaction and session persistence.
*   **Data Tier:** Schema-less JSON-based persistence for maximum portability and human-readable configurations.

---

## 📥 Deployment

1.  **Environment Setup:** Execute `install.bat` to initialize the local environment and dependencies.
2.  **Framework Initialization:** Upon launch, configure local "Library Locations" to begin the indexing process.
3.  **Provider Configuration:** Define external metadata and search providers in the **Source Configuration** panel within the settings.

---

**Developed for Educational Web Automation & Advanced Data Management.**
