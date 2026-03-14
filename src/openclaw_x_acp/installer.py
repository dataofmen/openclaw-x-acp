import os
import sys
import json
from pathlib import Path

def run_setup():
    print("🚀 Welcome to OpenClaw X-to-ACP Installer! 🚀")
    print("This script will guide you through setting up the Model Context Protocol server for your OpenClaw agent.\n")
    
    # Cookie Configuration
    cookies_path = Path.home() / ".openclaw-x-acp-cookies.json"
    
    print("1️⃣ X.com (Twitter) Cookies Configuration")
    print("✨ Good news! openclaw-x-acp now features ZERO-TOUCH automatic cookie extraction.")
    print("✨ It will securely read your login session directly from Chrome/Safari/Edge when requested by OpenClaw.")
    
    if cookies_path.exists():
        print(f"✅ Found existing fallback cookies file at: {cookies_path}")
        overwrite = input("Do you want to override the automatic extraction with manual cookies? (y/N): ").strip().lower()
        if overwrite == 'y':
            _setup_cookies(cookies_path)
    else:
        manual = input("Do you want to configure manual fallback cookies? (y/N): ").strip().lower()
        if manual == 'y':
            _setup_cookies(cookies_path)
        
    # OpenClaw Integration
    print("\n2️⃣ OpenClaw Configuration")
    # For Zero-Touch, we use the global ~/.openclaw/ discovery path
    openclaw_config_path = Path.home() / ".openclaw" / "openclaw_mcp_settings.json"
    
    executable_path = sys.executable
    script_path = str(Path(executable_path).parent.parent / "bin" / "openclaw-x-acp") # If running via pipx
    
    # Fallback to current path if not standard
    if not Path(script_path).exists():
        import shutil
        script_path = shutil.which("openclaw-x-acp") or sys.executable
    
    mcp_config = {
        "mcpServers": {
            "openclaw-x-acp": {
                "command": script_path,
                "args": []
            }
        }
    }
    
    import subprocess
    
    try:
        # Register the MCP server via the acpx plugin config
        mcp_server_config = {
            "openclaw-x-acp": {
                "command": script_path,
                "args": []
            }
        }
        config_json_str = json.dumps(mcp_server_config)
        
        # Inject into acpx config
        subprocess.run(["openclaw", "config", "set", "plugins.entries.acpx.config.mcpServers", config_json_str], check=True, capture_output=True)
        
        # Ensure acpx plugin is enabled
        subprocess.run(["openclaw", "plugins", "enable", "acpx"], check=False, capture_output=True)
        
        # Cleanup stale mcp entry if any
        subprocess.run(["python3", "-c", "import json; from pathlib import Path; p = Path.home() / '.openclaw' / 'openclaw.json'; data = json.loads(p.read_text()); data.get('plugins', {}).get('entries', {}).pop('mcp', None); p.write_text(json.dumps(data, indent=2))"], check=False, capture_output=True)
        
        print(f"✅ Automatically updated OpenClaw config via CLI (acpx plugin)")
    except Exception as e:
        print(f"⚠️ Failed to auto-configure OpenClaw via CLI: {e}")
        print("Please ensure OpenClaw is installed and accessible in your PATH.")
        
    print("\n🎉 Setup Complete!")
    print("\nNext Steps:")
    print("1. Launch the OpenClaw agent and enable provenance tracking for monetization:")
    print("   👉 openclaw acp --provenance meta+receipt")
    print("2. Ask OpenClaw to 'Summarize the whole thread for https://x.com/username/status/12345'")
    print("\n💰 Monetization Hack:")
    print("   OpenClaw v2026.3.8 supports native monetization receipts.")
    print("   Don't forget to set up your GitHub Sponsors page to build a sustainable product! 🦉")

def _setup_cookies(cookies_path: Path):
    print("Please provide your authorization cookies.")
    print("You can get these from your web browser developer tools (Application -> Storage -> Cookies (x.com))")
    
    auth_token = input("Enter 'auth_token' value: ").strip()
    ct0 = input("Enter 'ct0' value: ").strip()
    
    if not auth_token or not ct0:
        print("⚠️ Skipped manual cookie setup. Relying on zero-touch browser extraction.")
        return
        
    config = {
        "auth_token": auth_token,
        "ct0": ct0
    }
    
    with open(cookies_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"✅ Cookies saved securely to: {cookies_path}")

if __name__ == "__main__":
    run_setup()
