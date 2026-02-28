import * as cp from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

type RigOutputs = {
  outputDir: string;
  rigPath: string;
  rigViewPath: string;
  planPath: string;
  reportPath: string;
  workflowViewPath: string;
};

const STATE_KEY_LAST_REFRESH = 'rigCopilotMode.lastRefreshIso';
const STATE_KEY_LAST_OUTPUT_DIR = 'rigCopilotMode.lastOutputDir';
const RIG_BLOCK_START = '<!-- RIG-COPILOT-MODE:START -->';
const RIG_BLOCK_END = '<!-- RIG-COPILOT-MODE:END -->';

let statusBar: vscode.StatusBarItem | undefined;

export function activate(context: vscode.ExtensionContext): void {
  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 200);
  statusBar.command = 'rigCopilotMode.toggle';
  context.subscriptions.push(statusBar);

  context.subscriptions.push(
    vscode.commands.registerCommand('rigCopilotMode.toggle', async () => {
      const cfg = getConfig();
      const enabled = cfg.get<boolean>('enabled', false);
      await cfg.update('enabled', !enabled, vscode.ConfigurationTarget.Workspace);
      updateStatusBar(!enabled);
      if (!enabled) {
        await runAndPublishContext(context, true);
      } else {
        vscode.window.showInformationMessage('RIG Copilot Mode disabled.');
      }
    }),

    vscode.commands.registerCommand('rigCopilotMode.runNow', async () => {
      await runAndPublishContext(context, true);
    }),

    vscode.commands.registerCommand('rigCopilotMode.promptWithContext', async () => {
      await promptWithRigContext(context);
    }),

    vscode.commands.registerCommand('rigCopilotMode.openWorkflowView', async () => {
      await openOutputHtml(context, 'workflow-view.html');
    }),

    vscode.commands.registerCommand('rigCopilotMode.openRigView', async () => {
      await openOutputHtml(context, 'rig-view.html');
    }),

    vscode.commands.registerCommand('rigCopilotMode.setupMcpConfig', async () => {
      await setupMcpConfig();
    })
  );

  const enabled = getConfig().get<boolean>('enabled', false);
  updateStatusBar(enabled);

  if (enabled) {
    void runAndPublishContext(context, false);
  }
}

export function deactivate(): void {
  statusBar?.dispose();
}

function updateStatusBar(enabled: boolean): void {
  if (!statusBar) {
    return;
  }
  statusBar.text = enabled ? '$(graph) RIG Mode: ON' : '$(graph) RIG Mode: OFF';
  statusBar.tooltip = enabled
    ? 'RIG Copilot Mode is enabled. Click to disable.'
    : 'RIG Copilot Mode is disabled. Click to enable.';
  statusBar.show();
}

function getConfig(): vscode.WorkspaceConfiguration {
  return vscode.workspace.getConfiguration('rigCopilotMode');
}

function getWorkspaceRoot(): string | undefined {
  const folder = vscode.workspace.workspaceFolders?.[0];
  return folder?.uri.fsPath;
}

async function runAndPublishContext(context: vscode.ExtensionContext, notify: boolean): Promise<void> {
  const root = getWorkspaceRoot();
  if (!root) {
    vscode.window.showErrorMessage('RIG Copilot Mode: Open a workspace folder first.');
    return;
  }

  const cfg = getConfig();
  const pythonPath = cfg.get<string>('pythonPath', 'python');
  const intent = cfg.get<string>(
    'intent',
    'Refactor safely using repository intelligence and agent verification'
  );
  const outputDirName = cfg.get<string>('outputDir', '.dist-rig');
  const outputDir = path.join(root, outputDirName);

  const outputs: RigOutputs = {
    outputDir,
    rigPath: path.join(outputDir, 'rig.json'),
    rigViewPath: path.join(outputDir, 'rig-view.html'),
    planPath: path.join(outputDir, 'intent-plan.json'),
    reportPath: path.join(outputDir, 'generate-report.json'),
    workflowViewPath: path.join(outputDir, 'workflow-view.html'),
  };

  await fs.promises.mkdir(outputDir, { recursive: true });

  const progressTitle = 'RIG Copilot Mode: refreshing repository intelligence context';
  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: progressTitle, cancellable: false },
    async (progress) => {
      progress.report({ message: 'Building RIG graph...' });
      await runRigCli(pythonPath, ['build', '--repo', root, '--out', outputs.rigPath], root);

      progress.report({ message: 'Building RIG HTML view...' });
      await runRigCli(pythonPath, ['view', '--rig', outputs.rigPath, '--out', outputs.rigViewPath], root);

      progress.report({ message: 'Creating intent plan...' });
      await runRigCli(
        pythonPath,
        ['plan', '--repo', root, '--intent', intent, '--out', outputs.planPath],
        root
      );

      progress.report({ message: 'Running generate workflow (dry-run)...' });
      try {
        await runRigCli(
          pythonPath,
          [
            'generate',
            '--repo',
            root,
            '--intent',
            intent,
            '--python',
            pythonPath,
            '--max-rounds',
            '2',
            '--auto-repair',
            '--dry-run-apply',
            '--artifact-dir',
            path.join(outputDir, 'change-sets'),
            '--out',
            outputs.reportPath,
          ],
          root
        );
      } catch (error) {
        // Keep going: generate-report is often still produced with useful context.
        void error;
      }

      progress.report({ message: 'Building workflow HTML view...' });
      await runRigCli(
        pythonPath,
        ['workflow-view', '--plan', outputs.planPath, '--report', outputs.reportPath, '--out', outputs.workflowViewPath],
        root
      );
    }
  );

  const contextText = await buildRigContextBlock(outputs);
  await writeCopilotInstructions(root, contextText);

  await context.workspaceState.update(STATE_KEY_LAST_REFRESH, new Date().toISOString());
  await context.workspaceState.update(STATE_KEY_LAST_OUTPUT_DIR, outputDir);

  if (notify) {
    vscode.window.showInformationMessage(
      `RIG Copilot Mode refreshed. Context injected into .github/copilot-instructions.md (${outputDirName}).`
    );
  }
}

function runRigCli(pythonPath: string, args: string[], cwd: string): Promise<void> {
  const cliArgs = ['-m', 'rig_mvp.cli', ...args];
  return new Promise((resolve, reject) => {
    const child = cp.spawn(pythonPath, cliArgs, {
      cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
      shell: false,
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (buf) => {
      stdout += String(buf);
    });

    child.stderr.on('data', (buf) => {
      stderr += String(buf);
    });

    child.on('error', (err) => {
      reject(new Error(`Failed to run rig_mvp CLI: ${err.message}`));
    });

    child.on('close', (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(
        new Error(
          `rig_mvp CLI failed (${code}).\nArgs: ${cliArgs.join(' ')}\nStdout:\n${stdout}\nStderr:\n${stderr}`
        )
      );
    });
  });
}

async function buildRigContextBlock(outputs: RigOutputs): Promise<string> {
  const rig = await safeReadJson(outputs.rigPath);
  const plan = await safeReadJson(outputs.planPath);
  const report = await safeReadJson(outputs.reportPath);

  const metadata = (rig?.metadata as Record<string, unknown> | undefined) ?? {};
  const nodeCount = Number(metadata.node_count ?? 0);
  const edgeCount = Number(metadata.edge_count ?? 0);

  const subtasks = Array.isArray(plan?.subtasks) ? plan?.subtasks : [];
  const executions = Array.isArray(report?.executions) ? report?.executions : [];
  const verification = (report?.verification as Record<string, unknown> | undefined) ?? {};

  const taskSummaries = subtasks
    .slice(0, 8)
    .map((task) => {
      const t = task as Record<string, unknown>;
      const id = String(t.id ?? '?');
      const title = String(t.title ?? '<no-title>');
      const role = String(t.agent_role ?? 'generator');
      return `- ${id} [${role}]: ${title}`;
    })
    .join('\n');

  const executionSummaries = executions
    .slice(0, 8)
    .map((exe) => {
      const e = exe as Record<string, unknown>;
      const id = String(e.task_id ?? '?');
      const status = String(e.status ?? 'unknown');
      const files = Array.isArray(e.candidate_files) ? (e.candidate_files as unknown[]).slice(0, 3).join(', ') : '';
      return `- ${id}: status=${status}${files ? `, files=${files}` : ''}`;
    })
    .join('\n');

  const verificationPassed = String(verification.passed ?? 'unknown');
  const verificationRounds = String(verification.rounds ?? '0');

  return [
    'RIG MODE CONTEXT (AUTO-GENERATED)',
    `- Rig output dir: ${outputs.outputDir}`,
    `- Graph: nodes=${nodeCount}, edges=${edgeCount}`,
    `- Plan tasks: ${subtasks.length}`,
    `- Execution tasks: ${executions.length}`,
    `- Verification: passed=${verificationPassed}, rounds=${verificationRounds}`,
    `- Workflow view: ${outputs.workflowViewPath}`,
    `- RIG view: ${outputs.rigViewPath}`,
    '',
    'Top fragmented intent tasks:',
    taskSummaries || '- <none>',
    '',
    'Top agent execution summaries:',
    executionSummaries || '- <none>',
    '',
    'Instruction for Copilot:',
    '- Use these generated artifacts as source of truth before proposing edits.',
    '- Prefer impacted files and acceptance criteria from plan/report for changes.',
  ].join('\n');
}

async function writeCopilotInstructions(workspaceRoot: string, generatedText: string): Promise<void> {
  const githubDir = path.join(workspaceRoot, '.github');
  const filePath = path.join(githubDir, 'copilot-instructions.md');

  await fs.promises.mkdir(githubDir, { recursive: true });

  let existing = '';
  if (fs.existsSync(filePath)) {
    existing = await fs.promises.readFile(filePath, 'utf-8');
  }

  const block = `${RIG_BLOCK_START}\n${generatedText}\n${RIG_BLOCK_END}`;

  let next = existing;
  if (!existing.trim()) {
    next = `# Copilot Instructions\n\n${block}\n`;
  } else if (existing.includes(RIG_BLOCK_START) && existing.includes(RIG_BLOCK_END)) {
    const start = existing.indexOf(RIG_BLOCK_START);
    const end = existing.indexOf(RIG_BLOCK_END) + RIG_BLOCK_END.length;
    next = `${existing.slice(0, start).trimEnd()}\n\n${block}\n\n${existing.slice(end).trimStart()}`;
  } else {
    next = `${existing.trimEnd()}\n\n${block}\n`;
  }

  await fs.promises.writeFile(filePath, next, 'utf-8');
}

async function safeReadJson(filePath: string): Promise<Record<string, unknown> | undefined> {
  try {
    const raw = await fs.promises.readFile(filePath, 'utf-8');
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return parsed;
  } catch {
    return undefined;
  }
}

async function promptWithRigContext(context: vscode.ExtensionContext): Promise<void> {
  const root = getWorkspaceRoot();
  if (!root) {
    vscode.window.showErrorMessage('RIG Copilot Mode: Open a workspace folder first.');
    return;
  }

  const prompt = await vscode.window.showInputBox({
    title: 'RIG Prompt With Context',
    prompt: 'Enter your Copilot prompt',
    placeHolder: 'e.g., Refactor booking route with safer validation',
    ignoreFocusOut: true,
  });

  if (!prompt) {
    return;
  }

  const outputDir =
    (context.workspaceState.get<string>(STATE_KEY_LAST_OUTPUT_DIR) as string | undefined) ||
    path.join(root, getConfig().get<string>('outputDir', '.dist-rig'));
  const lastRefresh = (context.workspaceState.get<string>(STATE_KEY_LAST_REFRESH) as string | undefined) ?? 'unknown';

  const composed = [
    'RIG MODE IS ENABLED',
    `Workspace: ${root}`,
    `RIG output dir: ${outputDir}`,
    `Last refresh: ${lastRefresh}`,
    'Use generated plan/report/view artifacts before proposing changes.',
    '',
    'User request:',
    prompt,
  ].join('\n');

  await vscode.env.clipboard.writeText(composed);

  try {
    await vscode.commands.executeCommand('workbench.action.chat.open');
    vscode.window.showInformationMessage('Prompt with RIG context copied to clipboard. Paste it into Copilot Chat.');
  } catch {
    vscode.window.showInformationMessage('Prompt with RIG context copied to clipboard. Open Copilot Chat and paste it.');
  }
}

async function openOutputHtml(context: vscode.ExtensionContext, fileName: 'rig-view.html' | 'workflow-view.html'): Promise<void> {
  const root = getWorkspaceRoot();
  if (!root) {
    vscode.window.showErrorMessage('RIG Copilot Mode: Open a workspace folder first.');
    return;
  }

  const outputDir =
    (context.workspaceState.get<string>(STATE_KEY_LAST_OUTPUT_DIR) as string | undefined) ||
    path.join(root, getConfig().get<string>('outputDir', '.dist-rig'));

  const htmlPath = path.join(outputDir, fileName);
  if (!fs.existsSync(htmlPath)) {
    vscode.window.showWarningMessage(`${fileName} not found. Run "RIG Copilot Mode: Refresh Context Now" first.`);
    return;
  }

  await vscode.env.openExternal(vscode.Uri.file(htmlPath));
}

async function setupMcpConfig(): Promise<void> {
  const root = getWorkspaceRoot();
  if (!root) {
    vscode.window.showErrorMessage('RIG Copilot Mode: Open a workspace folder first.');
    return;
  }

  const extension = vscode.extensions.getExtension('local.rig-copilot-mode');
  const extensionPath = extension?.extensionPath;
  if (!extensionPath) {
    vscode.window.showErrorMessage('RIG Copilot Mode: Unable to resolve extension installation path.');
    return;
  }

  const mcpServerPath = path.join(extensionPath, 'out', 'mcpServer.js');
  const configDir = path.join(root, '.vscode');
  const configPath = path.join(configDir, 'mcp.json');

  const config = {
    servers: {
      'rig-copilot-mode': {
        command: 'node',
        args: [mcpServerPath, '--workspace', root],
        env: {
          RIG_OUTPUT_DIR: getConfig().get<string>('outputDir', '.dist-rig'),
          RIG_PYTHON: getConfig().get<string>('pythonPath', 'python'),
          RIG_INTENT: getConfig().get<string>(
            'intent',
            'Refactor safely using repository intelligence and agent verification'
          ),
        },
      },
    },
  };

  await fs.promises.mkdir(configDir, { recursive: true });
  await fs.promises.writeFile(configPath, JSON.stringify(config, null, 2), 'utf-8');

  const doc = await vscode.workspace.openTextDocument(configPath);
  await vscode.window.showTextDocument(doc, { preview: false });
  vscode.window.showInformationMessage('Created .vscode/mcp.json for rig-copilot-mode MCP server.');
}
