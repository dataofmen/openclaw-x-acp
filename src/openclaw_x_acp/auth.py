import json
import logging
from pathlib import Path

logger = logging.getLogger("openclaw-x-acp-auth")

async def load_cookies() -> dict:
    """
    Load X.com cookies automatically from the user's local browsers (Chrome, Safari, etc.)
    Falls back to a local cookies.json file if no browser cookies are found.
    """
    try:
        import browser_cookie3
        
        logger.info("Attempting to automatically extract X.com cookies from local browsers...")
        # Load from all supported browsers
        cj = browser_cookie3.load(domain_name=".x.com")
        
        cookies_dict = {}
        for cookie in cj:
            if cookie.name in ["auth_token", "ct0"]:
                cookies_dict[cookie.name] = cookie.value
                
        if "auth_token" in cookies_dict and "ct0" in cookies_dict:
            logger.info("✅ Successfully extracted auth_token and ct0 from local browser!")
            return cookies_dict
        else:
            logger.warning("Could not find auth_token and ct0 in local browsers. You might not be logged into X.com.")
            
    except ImportError:
        logger.warning("browser-cookie3 not installed, skipping automatic extraction.")
    except Exception as e:
        logger.info(f"Browser cookie extraction failed: {e}")
        logger.info("Proceeding with twikit login (no cookies required)...")

    # Use twikit client login (if password is provided in env)
    try:
        from twikit import Client
        import os
        
        logger.info("Using twikit client for X.com login fallback...")
        
        username = os.environ.get("X_USERNAME", "hyuckmin80")
        email = os.environ.get("X_EMAIL", "hyuckmin80@gmail.com")
        password = os.environ.get("X_PASSWORD")
        
        if password:
            client = Client('en-US')
            logger.info(f"Attempting login as {username}...")
            
            await client.login(auth_info_1=username, auth_info_2=email, password=password)
            logger.info("✅ Successfully authenticated via twikit explicit login!")
            
            # Extract cookies from client and save to file to avoid re-login
            cookies_dict = client.get_cookies()
            try:
                cookie_file = Path.home() / ".openclaw-x-acp-cookies.json"
                with open(cookie_file, "w") as f:
                    json.dump(cookies_dict, f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to auto-save twikit login cookies: {e}")
                
            return cookies_dict
        else:
            logger.warning("X_PASSWORD environment variable not set. Skipping twikit explicit login.")
            
    except Exception as e:
        logger.error(f"twikit client login failed: {e}")

    # Fallback to cookies.json
    cookie_file = Path.home() / ".openclaw-x-acp-cookies.json"
    if cookie_file.exists():
        try:
            with open(cookie_file, "r") as f:
                logger.info(f"Loaded cookies from {cookie_file}")
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {cookie_file}: {e}")
            
    # Legacy fallback
    local_cookie = Path("cookies.json")
    if local_cookie.exists():
        try:
            with open(local_cookie, "r") as f:
                logger.info("Loaded cookies from local cookies.json")
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading cookies.json: {e}")
            
    return {}
