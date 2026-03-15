import asyncio
import sys
import json
from openclaw_x_acp.fetcher import fetch_x_thread
from openclaw_x_acp.auth import load_cookies

async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No URL provided"}))
        return

    url = sys.argv[1]
    cookies = await load_cookies()
    if not cookies:
        print(json.dumps({"error": "Cookies not configured"}))
        return

    try:
        content = await fetch_x_thread(url, cookies)
        print(json.dumps({"deliverable": content.text}))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    asyncio.run(main())
