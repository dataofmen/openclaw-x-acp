"""
X.com thread and article fetcher for MCP.
"""

import asyncio
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("openclaw-x-acp-fetcher")

@dataclass
class XContent:
    text: str
    is_article: bool

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
    """
    from twikit import Client
    import httpx
    
    tweet_id = extract_tweet_id(url_or_id)

    # Handle different cookie/auth formats
    if isinstance(cookies, dict) and "client" in cookies:
        # twikit client is already passed
        client = cookies["client"]
        logger.info("Using twikit client from auth")
    else:
        # SSL validation might need to be off for proxy environments
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
            logger.warning(f"Twikit layout change detected for {tweet_id}, falling back to Playwright parsing...")
            article_url = f"https://x.com/i/web/status/{tweet_id}"
            raw_text = await _fetch_article_with_playwright(article_url, cookies)
            if not raw_text or "[Failed" in raw_text:
                 raise RuntimeError(f"Failed to fetch content via both API and Playwright fallback for {tweet_id}")
            
            return XContent(text=f"# Fallback Extraction for Tweet {tweet_id}\n\n{raw_text}", is_article=False)
        raise
    except Exception as e:
        error_msg = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in error_msg or "SSL" in error_msg:
            raise RuntimeError(f"SSL Certificate Error: {e}")
        raise RuntimeError(f"Failed to fetch tweet {tweet_id}: {e}\nAuthentication might be expired or invalid.")

    if getattr(detailed_tweet, "text", None) is None and getattr(detailed_tweet, "full_text", None) is None:
        raise ValueError(f"Tweet {tweet_id} not found or inaccessible.")

    # 1. Extract Main Text (Prioritize note_tweet for long form)
    raw_text = ""
    if hasattr(detailed_tweet, "note_tweet") and detailed_tweet.note_tweet:
        raw_text = detailed_tweet.note_tweet.get("note_tweet_results", {}).get("result", {}).get("text", "")

    if not raw_text:
        raw_text = detailed_tweet.full_text if hasattr(detailed_tweet, "full_text") and detailed_tweet.full_text else detailed_tweet.text

    # 2. Extract Thread/Replies
    author_screen_name = detailed_tweet.user.screen_name
    thread_texts = []
    
    try:
        if hasattr(detailed_tweet, "replies") and detailed_tweet.replies:
            for reply in detailed_tweet.replies:
                if reply.user.screen_name == author_screen_name:
                    reply_text = reply.full_text if hasattr(reply, "full_text") and reply.full_text else reply.text
                    thread_texts.append(reply_text)
    except Exception as e:
        print(f"Failed to fetch thread replies: {e}")

    # 3. Check for Article Format (Playwright fallback)
    is_article = raw_text and raw_text.strip().startswith("https://t.co/")
    article_fetched = False

    if is_article and hasattr(detailed_tweet, "urls") and detailed_tweet.urls:
        for url_info in detailed_tweet.urls:
            expanded_url = url_info.get("expanded_url", "")
            if "/i/article/" in expanded_url:
                article_id = expanded_url.split("/i/article/")[-1].split("?")[0]
                article_url = f"https://x.com/i/article/{article_id}"
                raw_text = await _fetch_article_with_playwright(article_url, cookies)
                article_fetched = True
                break

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

    return XContent(text=markdown_output.strip(), is_article=article_fetched)

async def _fetch_article_with_playwright(article_url: str, cookies: dict) -> str:
    """Fallback to Playwright to extract X.com article text."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return f"[Error: Playwright not installed. Could not fetch article content from {article_url}]"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Setup context with X.com cookies
        context_cookies = [
            {"name": "auth_token", "value": cookies.get("auth_token", ""), "domain": ".x.com", "path": "/"},
            {"name": "ct0", "value": cookies.get("ct0", ""), "domain": ".x.com", "path": "/"},
        ]
        context = await browser.new_context(storage_state={"cookies": context_cookies})
        page = await context.new_page()
        
        try:
            await page.goto(article_url, wait_until="domcontentloaded", timeout=60000)
            
            # Wait for either regular tweet body or article body
            try:
                await page.wait_for_selector('[data-testid="tweetText"]', timeout=5000)
            except Exception:
                await page.wait_for_selector('article', timeout=5000)
                
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
                    // Filter out short texts or navigation noise
                    const combined = Array.from(elements)
                        .map(el => el.innerText.trim())
                        .filter(txt => txt.length > 10)
                        .join('\\n\\n');
                    if (combined.length > 20) return combined;
                }
            }
            return document.body.innerText; // Absolute fallback
        }""")
        
        await browser.close()
        
        if article_text and len(article_text) > 50:
            return article_text
        return f"[Failed to extract article content from {article_url}]"
