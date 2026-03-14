from twikit import Client
import asyncio

async def main():
    client = Client('en-US')
    # 사용자 쿠키 로드
    try:
        from openclaw_x_acp.auth import load_cookies
        cookies = load_cookies()
        if cookies:
            client.set_cookies(cookies)
            print("Cookies loaded successfully")
            return client
        else:
            print("Failed to load cookies")
            return None
    except Exception as e:
        print(f"Error loading cookies: {e}")
        return None

asyncio.run(main())
