# RIG Copilot Mode Extension

This extension adds a **RIG Copilot Mode** in VS Code.

If you are new, start here:

- User guide (easy language): `docs/USER_GUIDE.md`
- Deployment guide (share with everyone): `docs/DEPLOYMENT.md`

## What it does

- Adds a toggle mode (`RIG Copilot Mode: Toggle`).
- When enabled (or manually refreshed), it runs:
  - `rig_mvp.cli build`
  - `rig_mvp.cli plan`
  - `rig_mvp.cli generate --dry-run-apply`
  - `rig_mvp.cli view`
  - `rig_mvp.cli workflow-view`
- Updates `.github/copilot-instructions.md` with a generated **RIG context block** so Copilot can use it in later prompts.
- Adds helpers to open generated HTML views.

## Commands

- `RIG Copilot Mode: Toggle`
- `RIG Copilot Mode: Refresh Context Now`
- `RIG Copilot Mode: Prompt With Context`
- `RIG Copilot Mode: Open Workflow View`
- `RIG Copilot Mode: Open RIG View`
- `RIG Copilot Mode: Setup MCP Config`

## Settings

- `rigCopilotMode.enabled`
- `rigCopilotMode.pythonPath`
- `rigCopilotMode.intent`
- `rigCopilotMode.outputDir`

## Quick start

1. Install extension dependencies and compile:
  - `npm install`
  - `npm run compile`
2. Press `F5` in this extension folder to launch the Extension Development Host.
3. In your target workspace, run **RIG Copilot Mode: Toggle**.
4. Use **RIG Copilot Mode: Prompt With Context** to generate a context-prefixed prompt and paste it into Copilot Chat.

## MCP server

This extension now ships a local MCP server (`out/mcpServer.js`) with three tools:

- `rig_list_artifacts`
- `rig_get_context`
- `rig_refresh_context`

### Enable MCP for this workspace

1. Compile once in the extension folder:
  - `npm run compile`
2. In the Extension Development Host, run:
  - **RIG Copilot Mode: Setup MCP Config**
3. This creates `.vscode/mcp.json` in your target workspace with the right command/env wiring.
4. Reload the window so your MCP-capable chat client picks up the new server.

### Manual MCP run (optional)

- `npm run mcp:start`
- Optional args: `--workspace F:\\Seminar --output-dir .dist-rig --python F:\\Seminar\\.venv\\Scripts\\python.exe`

## Deploy this for everyone

You can deploy in two ways:

1. Package `.vsix` and share file:
  - `npm run package:vsix`
2. Publish on VS Code Marketplace:
  - `npm run publish:marketplace`

Detailed steps: `docs/DEPLOYMENT.md`
