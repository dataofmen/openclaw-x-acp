"""
X.com thread and article fetcher for MCP.

Optimized with:
- Stage 1: Enhanced twikit API usage to minimize Playwright fallback
- Stage 2: Playwright singleton pattern (no cold start per request)
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("openclaw-x-acp-fetcher")

@dataclass
class XContent:
    text: str
    is_article: bool


# ============================================================
# Stage 2: Playwright Singleton Manager
# ============================================================
class _PlaywrightManager:
    """
    Manages a single long-lived Chromium instance across requests.
    Eliminates the 10-30s cold start per Playwright call.
    """
    _instance: Optional["_PlaywrightManager"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._last_used = 0.0
        self._idle_timeout = 300  # Close browser after 5 min idle

    @classmethod
    async def get(cls) -> "_PlaywrightManager":
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    async def get_browser(self):
        """Return a warm browser instance, launching only if needed."""
        from playwright.async_api import async_playwright

        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                if self._playwright is None:
                    self._playwright = await async_playwright().start()
                logger.info("Launching Playwright Chromium (singleton)...")
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-gpu",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                        "--disable-extensions",
                        "--disable-background-networking",
                    ]
                )
                logger.info("Playwright Chromium ready.")
            self._last_used = time.monotonic()
            return self._browser

    async def close(self):
        """Gracefully shut down browser and Playwright."""
        async with self._lock:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None
        logger.info("Playwright singleton closed.")


def extract_tweet_id(url_or_id: str) -> str:
    """Extract tweet ID from various X.com or Twitter URL formats, or return if it's already an ID."""
    if url_or_id.isdigit():
        return url_or_id

    # Match pattern like https://x.com/username/status/1234567890
    match = re.search(r"status/(\d+)", url_or_id)
    if match:
        return match.group(1)

    raise ValueError(f"Could not extract a valid Tweet ID from: {url_or_id}")


async def fetch_x_thread(url_or_id: str, cookies: dict, verify_ssl: bool = True) -> XContent:
    """
    Fetch an X.com thread or article by its ID or URL.
    Returns the content formatted as Markdown.

    Stage 1 optimizations:
    - Enhanced note_tweet parsing for long-form posts
    - Improved thread reply collection
    - Smarter article detection (reduces unnecessary Playwright calls)
    """
    from twikit import Client
    import httpx

    tweet_id = extract_tweet_id(url_or_id)
    start_time = time.monotonic()

    # Handle different cookie/auth formats
    if isinstance(cookies, dict) and "client" in cookies:
        client = cookies["client"]
        logger.info("Using twikit client from auth")
    else:
        if not verify_ssl:
            httpx_client = httpx.AsyncClient(verify=False)
            client = Client("en-US", httpx_client=httpx_client)
        else:
            client = Client("en-US")
        client.set_cookies(cookies)

    try:
        detailed_tweet = await client.get_tweet_by_id(tweet_id)
    except KeyError as e:
        if 'itemContent' in str(e):
            logger.warning(f"Twikit layout change detected for {tweet_id}, falling back to Playwright...")
            article_url = f"https://x.com/i/web/status/{tweet_id}"
            raw_text = await _fetch_with_playwright(article_url, cookies)
            if not raw_text or "[Failed" in raw_text:
                raise RuntimeError(f"Failed to fetch content via both API and Playwright fallback for {tweet_id}")

            elapsed = time.monotonic() - start_time
            logger.info(f"Fetched tweet {tweet_id} via Playwright fallback in {elapsed:.1f}s")
            return XContent(text=f"# Fallback Extraction for Tweet {tweet_id}\n\n{raw_text}", is_article=False)
        raise
    except Exception as e:
        error_msg = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in error_msg or "SSL" in error_msg:
            raise RuntimeError(f"SSL Certificate Error: {e}")
        raise RuntimeError(f"Failed to fetch tweet {tweet_id}: {e}\nAuthentication might be expired or invalid.")

    if getattr(detailed_tweet, "text", None) is None and getattr(detailed_tweet, "full_text", None) is None:
        raise ValueError(f"Tweet {tweet_id} not found or inaccessible.")

    # ── Stage 1: Enhanced text extraction ──────────────────────

    # 1. Extract Main Text — prioritize note_tweet for long-form
    raw_text = ""
    note_tweet_data = getattr(detailed_tweet, "note_tweet", None)

    if note_tweet_data and isinstance(note_tweet_data, dict):
        # Deep extraction from note_tweet structure
        result = note_tweet_data.get("note_tweet_results", {}).get("result", {})
        raw_text = result.get("text", "")

        # Also extract rich text entities (URLs, mentions) from note_tweet
        if not raw_text:
            # Try alternate note_tweet paths
            raw_text = result.get("body", {}).get("text", "")

    if not raw_text:
        raw_text = (
            detailed_tweet.full_text
            if hasattr(detailed_tweet, "full_text") and detailed_tweet.full_text
            else detailed_tweet.text
        )

    # 2. Extract Thread/Replies — improved collection
    author_screen_name = detailed_tweet.user.screen_name
    thread_texts = []

    try:
        if hasattr(detailed_tweet, "replies") and detailed_tweet.replies:
            for reply in detailed_tweet.replies:
                if reply.user.screen_name == author_screen_name:
                    # Prioritize note_tweet in replies too
                    reply_note = getattr(reply, "note_tweet", None)
                    if reply_note and isinstance(reply_note, dict):
                        reply_text = reply_note.get("note_tweet_results", {}).get("result", {}).get("text", "")
                    else:
                        reply_text = ""

                    if not reply_text:
                        reply_text = (
                            reply.full_text
                            if hasattr(reply, "full_text") and reply.full_text
                            else reply.text
                        )
                    thread_texts.append(reply_text)
    except Exception as e:
        logger.warning(f"Failed to fetch thread replies: {e}")

    # 3. Smarter article detection — only fall back to Playwright for true articles
    is_article = False
    article_fetched = False

    # Check if content is just a t.co link (true article indicator)
    if raw_text and raw_text.strip().startswith("https://t.co/"):
        article_url_candidates = []

        # Check embedded URLs for article links
        if hasattr(detailed_tweet, "urls") and detailed_tweet.urls:
            for url_info in detailed_tweet.urls:
                expanded_url = url_info.get("expanded_url", "")
                if "/i/article/" in expanded_url:
                    article_url_candidates.append(expanded_url)

        if article_url_candidates:
            is_article = True
            article_url = article_url_candidates[0]
            logger.info(f"Article detected, fetching via Playwright: {article_url}")
            raw_text = await _fetch_with_playwright(article_url, cookies)
            article_fetched = True
        else:
            # Content is a t.co link but not a formal article — try expanding URL text
            logger.info("Content is a t.co link but not an article. Keeping raw text.")

    # 4. Format Output as Markdown
    markdown_output = f"# Tweet by @{author_screen_name}\n\n"
    markdown_output += f"{raw_text}\n\n"

    if thread_texts and not article_fetched:
        markdown_output += "## Thread Continuation\n\n"
        for i, text in enumerate(thread_texts, 1):
            markdown_output += f"### Part {i+1}\n{text}\n\n---\n\n"

    # Include Media URLs
    if hasattr(detailed_tweet, "media") and detailed_tweet.media:
        markdown_output += "\n## Attached Media\n"
        for m in detailed_tweet.media:
            media_url = getattr(m, "media_url_https", None) or getattr(m, "media_url", None)
            if media_url:
                markdown_output += f"- {media_url}\n"

    elapsed = time.monotonic() - start_time
    api_or_pw = "Playwright" if article_fetched else "twikit API"
    logger.info(f"Fetched tweet {tweet_id} via {api_or_pw} in {elapsed:.1f}s (text length: {len(markdown_output)})")

    return XContent(text=markdown_output.strip(), is_article=article_fetched)


# ============================================================
# Stage 2: Playwright fetcher using singleton
# ============================================================
async def _fetch_with_playwright(article_url: str, cookies: dict) -> str:
    """
    Fetch X.com article/page content using Playwright singleton.
    Much faster than the original (reuses warm browser instance).
    """
    try:
        from playwright.async_api import async_playwright  # noqa: F401 — validate import
    except ImportError:
        return f"[Error: Playwright not installed. Could not fetch article content from {article_url}]"

    start_time = time.monotonic()

    try:
        manager = await _PlaywrightManager.get()
        browser = await manager.get_browser()
    except Exception as e:
        logger.error(f"Failed to get Playwright browser: {e}")
        return f"[Error: Could not start browser: {e}]"

    context = None
    page = None
    try:
        # Setup context with X.com cookies
        context_cookies = [
            {"name": "auth_token", "value": cookies.get("auth_token", ""), "domain": ".x.com", "path": "/"},
            {"name": "ct0", "value": cookies.get("ct0", ""), "domain": ".x.com", "path": "/"},
        ]
        context = await browser.new_context(
            storage_state={"cookies": context_cookies},
            # Block unnecessary resources for speed
            java_script_enabled=True,
        )

        # Block images, fonts, and media to speed up loading
        await context.route("**/*.{png,jpg,jpeg,gif,svg,webp,mp4,mp3,woff,woff2,ttf}", lambda route: route.abort())
        await context.route("**/analytics**", lambda route: route.abort())
        await context.route("**/ads/**", lambda route: route.abort())

        page = await context.new_page()

        # Navigate with shorter timeout
        await page.goto(article_url, wait_until="domcontentloaded", timeout=15000)

        # Wait for tweet text to appear
        try:
            await page.wait_for_selector('[data-testid="tweetText"]', timeout=5000)
        except Exception:
            try:
                await page.wait_for_selector('article', timeout=3000)
            except Exception:
                logger.warning(f"Timeout waiting for elements on {article_url}, attempting extraction anyway")

        article_text = await page.evaluate("""() => {
            const selectors = [
                '[data-testid="tweetText"]',
                'article [data-testid="tweetText"]',
                '[data-testid="article-body"]',
                'article',
                'main'
            ];
            for (const selector of selectors) {
                const elements = document.querySelectorAll(selector);
                if (elements.length > 0) {
                    const combined = Array.from(elements)
                        .map(el => el.innerText.trim())
                        .filter(txt => txt.length > 10)
                        .join('\\n\\n');
                    if (combined.length > 20) return combined;
                }
            }
            return document.body.innerText;
        }""")

        elapsed = time.monotonic() - start_time
        logger.info(f"Playwright extraction completed in {elapsed:.1f}s (text length: {len(article_text or '')})")

        if article_text and len(article_text) > 50:
            return article_text
        return f"[Failed to extract article content from {article_url}]"

    except Exception as e:
        elapsed = time.monotonic() - start_time
        logger.error(f"Playwright extraction failed after {elapsed:.1f}s: {e}")
        return f"[Error extracting content from {article_url}: {e}]"

    finally:
        # Always clean up context and page, but keep browser alive
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass
