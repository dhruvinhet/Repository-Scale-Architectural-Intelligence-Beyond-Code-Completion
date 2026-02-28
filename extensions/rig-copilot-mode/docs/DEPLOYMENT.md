# Deployment Guide (Public Use)

This guide helps you share the extension and MCP setup with everyone.

## Option A: Share as `.vsix` file (fastest)

Use this if your team installs manually.

### Steps

1. Open terminal in `extensions/rig-copilot-mode`
2. Install dependencies:
   - `npm install`
3. Build extension:
   - `npm run compile`
4. Create package:
   - `npm run package:vsix`
5. You will get a file like:
   - `rig-copilot-mode-0.0.1.vsix`

### Install `.vsix`

Each user can install by:
1. VS Code -> Extensions
2. Click `...` menu -> **Install from VSIX...**
3. Select the `.vsix` file

---

## Option B: Publish to VS Code Marketplace (best for broad use)

Use this for easy one-click install globally.

### One-time setup

1. Create a publisher on Marketplace:
   - https://marketplace.visualstudio.com/manage
2. Create a Personal Access Token (PAT) with Marketplace publish rights
3. Login with vsce:
   - `npx vsce login <your-publisher-name>`

### Before publish

1. Update `package.json`:
   - set `publisher` to your publisher name (not `local`)
   - bump `version` (example `0.0.2`)
2. Build:
   - `npm run compile`

### Publish

- `npm run publish:marketplace`

After publish, anyone can install from VS Code Extensions search.

---

## Option C: Keep MCP server only (without extension publish)

If you only need MCP tools, you can run server directly:

- `npm run mcp:start -- --workspace F:\\Seminar --output-dir .dist-rig --python F:\\Seminar\\.venv\\Scripts\\python.exe`

Then configure your MCP client to use this command.

---

## Recommended rollout plan

1. Pilot with `.vsix` in one team
2. Collect feedback (commands, prompt quality, latency)
3. Publish to Marketplace
4. Add short onboarding docs for all devs

---

## Security and governance notes

- MCP tools expose repository metadata and file paths.
- Use trusted workspaces only.
- Review generated code before commit.
- Keep Python/tooling versions consistent across team machines.

---

## Quick validation checklist (before sharing)

- `npm run compile` passes
- `npm run package:vsix` passes
- Extension commands visible in Command Palette
- `RIG Copilot Mode: Setup MCP Config` creates `.vscode/mcp.json`
- MCP tools return data (`rig_get_context`, `rig_refresh_context`)
