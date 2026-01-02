# Preset configurations for known sources
# This allows the app to remain generic while providing "magic" auto-config for common sites.

PRESETS = {
    "source_type_1": {
        "domains": ["steamrip.com"],
        "config": {
            "name": "Source Alpha",
            "search_url": "{source_url}/page/{page}/?s={query}",
            "list_url": "{source_url}/games-list-page/",
            "update_check_enabled": True,
            "version_extraction_pattern": r"\((.*?)\)",
            "selectors": {
                "grid": "#masonry-grid",
                "item": "container-wrapper.post-element",
                "list_container": "#tie-block_1793 > div > div.mag-box-container.clearfix",
                "version_selector": "#the-post > div.entry-content.entry.clearfix > div.plus.tie-list-shortcode > ul > li:nth-child(6)"
            },
            "title_clean_pattern": " Free Download"
        }
    },
    "source_type_2": {
        "domains": ["filmpalast.to"],
        "config": {
            "name": "Source Beta",
            "search_url": "{source_url}/search/title/{query}/{page}",
            "selectors": {
                "content": "#content"
            }
        }
    }
}

def get_preset_for_url(url):
    # Normalization: Ensure protocol and remove trailing slash
    normalized_url = url.strip().lower()
    if not normalized_url.startswith(("http://", "https://")):
        normalized_url = "https://" + normalized_url
    normalized_url = normalized_url.rstrip('/')

    for source_key, data in PRESETS.items():
        for domain in data["domains"]:
            if domain in normalized_url:
                # Return a copy of the config with the actual normalized source_url injected
                config = data["config"].copy()
                config["source_url"] = normalized_url
                # Also update nested fields if they use the placeholder
                if "search_url" in config:
                    config["search_url"] = config["search_url"].replace("{source_url}", normalized_url)
                if "list_url" in config:
                    config["list_url"] = config["list_url"].replace("{source_url}", normalized_url)
                return config, source_key
    
    # If no preset found, return a generic config with the normalized URL
    generic_config = {
        "source_url": normalized_url,
        "name": "Custom Source",
        "search_url": normalized_url + "/?s={query}"
    }
    return generic_config, None
