import logging
from mcp.server.fastmcp import FastMCP
from openclaw_x_acp.auth import load_cookies
from openclaw_x_acp.fetcher import fetch_x_thread

# Initialize FastMCP Server
mcp = FastMCP(
    "OpenClaw X Content Fetcher", 
    dependencies=["twikit", "playwright", "httpx"]
)

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("openclaw-x-acp")

@mcp.tool()
async def get_x_content(url_or_id: str) -> str:
    """
    Fetch the complete text of an X.com (Twitter) thread or long-form article.
    Use this tool when you need to read the full context of a tweet link provided by the user.
    
    Args:
        url_or_id: The full URL to the tweet (e.g. https://x.com/username/status/12345) or just the numeric Tweet ID.
    
    Returns:
        A Markdown formatted string containing the main tweet text, all threaded replies by the author, and any media links.
    """
    logger.info(f"Attempting to fetch X content for: {url_or_id}")
    
    cookies = await load_cookies()
    if not cookies or "auth_token" not in cookies:
        return "Error: X.com cookies not configured correctly. 'auth_token' is missing in cookies.json, and X_PASSWORD was not provided."
        
    try:
        content = await fetch_x_thread(url_or_id, cookies)
        prefix = "📄 Successfully extracted Article:\n\n" if content.is_article else "🧵 Successfully extracted Thread:\n\n"
        return prefix + content.text
    except Exception as e:
        logger.error(f"Failed to fetch content: {str(e)}")
        return f"Error fetching X content: {str(e)}"

def main():
    # Standard Stdio execution for local ACP coupling
    logger.info("Starting OpenClaw X-to-ACP local server...")
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
