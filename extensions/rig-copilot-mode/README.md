# RIG Copilot Mode Extension

This extension adds a **RIG Copilot Mode** in VS Code.

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
