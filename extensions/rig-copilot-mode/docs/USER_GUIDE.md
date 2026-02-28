# RIG Copilot Mode - Easy User Guide

This guide explains how to use the extension and MCP in simple steps.

## What this extension does

Think of this extension as a **project memory helper** for Copilot.

When you run it, it prepares:
- a repository graph
- an intent plan
- a generation/verification report
- visual views (`rig-view.html`, `workflow-view.html`)

Then Copilot can use this context instead of guessing from only open files.

---

## Before you start

You need:
1. VS Code
2. Node.js + npm
3. Python (same one that can run `python -m rig_mvp.cli`)

---

## Daily usage (quick path)

1. Open your project workspace.
2. Run command: **RIG Copilot Mode: Toggle**
3. Wait until refresh finishes.
4. Run command: **RIG Copilot Mode: Prompt With Context**
5. Type your request and paste generated prompt in Copilot Chat.

### Example prompt

`Add Google OAuth login without breaking existing password login. Also update tests and keep current API response format.`

---

## MCP usage (recommended for multi-file changes)

If your chat client supports MCP tools, use MCP mode.

1. In Extension Host, run: **RIG Copilot Mode: Setup MCP Config**
2. This creates `.vscode/mcp.json`
3. Reload window
4. Start chat and let it call tools:
   - `rig_refresh_context`
   - `rig_get_context`
   - `rig_list_artifacts`

### What you gain

Without MCP, Copilot may patch only one file.
With MCP, Copilot can see candidate files, subtasks, and verification status.

---

## Real example (login method)

User request:
`Add OTP login method in addition to password login.`

Expected MCP flow:
1. `rig_refresh_context` updates latest graph/plan/report
2. `rig_get_context` returns impacted modules + top subtasks + candidate files
3. Copilot proposes changes for service, route/controller, provider, and tests
4. You review and apply

---

## Common commands

- **RIG Copilot Mode: Toggle** -> turn mode on/off
- **RIG Copilot Mode: Refresh Context Now** -> force refresh artifacts
- **RIG Copilot Mode: Prompt With Context** -> build prompt text with context
- **RIG Copilot Mode: Open RIG View** -> open graph HTML
- **RIG Copilot Mode: Open Workflow View** -> open workflow HTML
- **RIG Copilot Mode: Setup MCP Config** -> create MCP config file

---

## Troubleshooting

### Command not visible
- Run `npm run compile`
- Restart Extension Development Host (`F5` again)

### Python errors
- Set `rigCopilotMode.pythonPath` in VS Code settings
- Example path: `F:\\Seminar\\.venv\\Scripts\\python.exe`

### MCP server not picked up
- Confirm `.vscode/mcp.json` exists
- Reload VS Code window

### Views not found
- Run **RIG Copilot Mode: Refresh Context Now** first

---

## When to use MCP vs normal prompt

Use MCP when:
- change touches 3+ files
- auth/payment/security work
- interface or contract changes
- test updates are needed

You can skip MCP when:
- tiny text/UI-only change
- one small local fix

---

## Tip

Use clear prompts with constraints.

Good prompt:
`Add GitHub login method, keep old login, update unit tests, do not change response schema.`

This gives better and safer results.
