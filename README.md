# OpenClaw X-to-ACP

An MCP (Model Context Protocol) server designed specifically for OpenClaw to fetch and read X.com (Twitter) threads and long-form articles natively. 

## Monetization & Support
With OpenClaw v2026.3.8+, this tool supports the `--provenance meta+receipt` flag natively. OpenClaw will automatically generate monetization receipts for tool usage.

Additionally, if you find this tool valuable, please consider supporting the development:

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-EA4AAA?style=for-the-badge&logo=github)](https://github.com/sponsors/dataofmen)

### Why sponsor?
- **Sustainability**: X.com backend changes frequently; sponsorship keeps the maintenance alive.
- **Priority Features**: Bulk processing, advanced analytics, and PDF export are on the roadmap for sponsors.
- **Community**: Help us keep AI agents capable of understanding real-time social context.

## Installation & Setup

We recommend using `pipx` to install this globally so OpenClaw can always access it.

1. **Install the package:**
   ```bash
   pipx install .
   # OR for development:
   # pip install -e .
   ```
   
2. **Install Playwright Browsers:**
   ```bash
   playwright install chromium
   ```

3. **Zero-Touch Configuration:**
   Run the following setup command. Thanks to the integrated `browser-cookie3` module, the server will **automatically** extract your X.com session from your local browser (Chrome/Safari/Edge) at runtime.
   You simply need to run the setup script to register the tool with OpenClaw. It will ask if you want to provide manual fallback cookies (optional):
   ```bash
   openclaw-x-acp-setup
   ```

## Connecting to OpenClaw

Add the following to your OpenClaw or AI Agent configuration file (e.g. `gateway.config.json`):

```json
{
  "mcpServers": {
    "openclaw-x-acp": {
      "command": "/path/to/openclaw-x-acp/.venv/bin/python",
      "args": [
        "/path/to/openclaw-x-acp/server.py"
      ]
    }
  }
}
```

Start OpenClaw with provenance enabled to track receipts:
```bash
openclaw acp --provenance meta+receipt
```

## How to use
When using the agent, simply provide a URL.
- "Summarize this X thread: https://x.com/aiedge_/status/2032466807043580159"
- "Read this X article and give me the key points: https://x.com/aiedge_/status/2032466807043580159"

The agent will seamlessly request the data from the local server using your cookies, parsing standard short text, threaded replies, and navigating via Playwright to parse long-form articles.
