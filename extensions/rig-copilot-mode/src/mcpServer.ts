import * as cp from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import * as z from 'zod/v4';

type RigArtifacts = {
  outputDir: string;
  rigPath: string;
  planPath: string;
  reportPath: string;
  rigViewPath: string;
  workflowViewPath: string;
};

type RuntimeOptions = {
  workspaceRoot: string;
  outputDirName: string;
  pythonPath: string;
  defaultIntent: string;
};

function parseArg(flag: string): string | undefined {
  const index = process.argv.indexOf(flag);
  if (index < 0 || index + 1 >= process.argv.length) {
    return undefined;
  }
  return process.argv[index + 1];
}

function resolveOptions(): RuntimeOptions {
  const workspaceRoot = path.resolve(
    parseArg('--workspace') ?? process.env.RIG_WORKSPACE_ROOT ?? process.cwd()
  );
  const outputDirName = parseArg('--output-dir') ?? process.env.RIG_OUTPUT_DIR ?? '.dist-rig';
  const pythonPath = parseArg('--python') ?? process.env.RIG_PYTHON ?? 'python';
  const defaultIntent =
    parseArg('--intent') ??
    process.env.RIG_INTENT ??
    'Refactor safely using repository intelligence and agent verification';

  return { workspaceRoot, outputDirName, pythonPath, defaultIntent };
}

function buildArtifacts(workspaceRoot: string, outputDirName: string): RigArtifacts {
  const outputDir = path.join(workspaceRoot, outputDirName);
  return {
    outputDir,
    rigPath: path.join(outputDir, 'rig.json'),
    planPath: path.join(outputDir, 'intent-plan.json'),
    reportPath: path.join(outputDir, 'generate-report.json'),
    rigViewPath: path.join(outputDir, 'rig-view.html'),
    workflowViewPath: path.join(outputDir, 'workflow-view.html'),
  };
}

function fileExists(filePath: string): boolean {
  return fs.existsSync(filePath);
}

async function safeReadJson(filePath: string): Promise<Record<string, unknown> | undefined> {
  try {
    const content = await fs.promises.readFile(filePath, 'utf-8');
    return JSON.parse(content) as Record<string, unknown>;
  } catch {
    return undefined;
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

async function refreshContextArtifacts(options: RuntimeOptions, intentOverride?: string, maxRounds = 2): Promise<RigArtifacts> {
  const artifacts = buildArtifacts(options.workspaceRoot, options.outputDirName);
  const intent = intentOverride ?? options.defaultIntent;

  await fs.promises.mkdir(artifacts.outputDir, { recursive: true });

  await runRigCli(options.pythonPath, ['build', '--repo', options.workspaceRoot, '--out', artifacts.rigPath], options.workspaceRoot);
  await runRigCli(options.pythonPath, ['view', '--rig', artifacts.rigPath, '--out', artifacts.rigViewPath], options.workspaceRoot);
  await runRigCli(
    options.pythonPath,
    ['plan', '--repo', options.workspaceRoot, '--intent', intent, '--out', artifacts.planPath],
    options.workspaceRoot
  );

  try {
    await runRigCli(
      options.pythonPath,
      [
        'generate',
        '--repo',
        options.workspaceRoot,
        '--intent',
        intent,
        '--python',
        options.pythonPath,
        '--max-rounds',
        String(maxRounds),
        '--auto-repair',
        '--dry-run-apply',
        '--artifact-dir',
        path.join(artifacts.outputDir, 'change-sets'),
        '--out',
        artifacts.reportPath,
      ],
      options.workspaceRoot
    );
  } catch {
  }

  await runRigCli(
    options.pythonPath,
    ['workflow-view', '--plan', artifacts.planPath, '--report', artifacts.reportPath, '--out', artifacts.workflowViewPath],
    options.workspaceRoot
  );

  return artifacts;
}

async function buildContextPayload(artifacts: RigArtifacts, maxTasks: number, includeExecutions: boolean): Promise<Record<string, unknown>> {
  const rig = await safeReadJson(artifacts.rigPath);
  const plan = await safeReadJson(artifacts.planPath);
  const report = await safeReadJson(artifacts.reportPath);

  const metadata = (rig?.metadata as Record<string, unknown> | undefined) ?? {};
  const nodeCount = Number(metadata.node_count ?? 0);
  const edgeCount = Number(metadata.edge_count ?? 0);

  const subtasks = Array.isArray(plan?.subtasks) ? (plan?.subtasks as Record<string, unknown>[]) : [];
  const executions = Array.isArray(report?.executions) ? (report?.executions as Record<string, unknown>[]) : [];
  const verification = (report?.verification as Record<string, unknown> | undefined) ?? {};

  const topTasks = subtasks.slice(0, maxTasks).map((task) => ({
    id: String(task.id ?? '?'),
    title: String(task.title ?? '<no-title>'),
    role: String(task.agent_role ?? 'generator'),
  }));

  const topExecutions = includeExecutions
    ? executions.slice(0, maxTasks).map((execution) => ({
        taskId: String(execution.task_id ?? '?'),
        status: String(execution.status ?? 'unknown'),
        candidateFiles: Array.isArray(execution.candidate_files)
          ? (execution.candidate_files as unknown[]).slice(0, 5).map(String)
          : [],
      }))
    : [];

  return {
    workspaceRoot: path.resolve(path.join(artifacts.outputDir, '..')),
    outputDir: artifacts.outputDir,
    files: {
      rig: artifacts.rigPath,
      plan: artifacts.planPath,
      report: artifacts.reportPath,
      rigView: artifacts.rigViewPath,
      workflowView: artifacts.workflowViewPath,
    },
    graph: {
      nodes: nodeCount,
      edges: edgeCount,
    },
    plan: {
      taskCount: subtasks.length,
      topTasks,
    },
    execution: {
      taskCount: executions.length,
      topExecutions,
    },
    verification: {
      passed: verification.passed ?? 'unknown',
      rounds: verification.rounds ?? 'unknown',
    },
    missingArtifacts: [artifacts.rigPath, artifacts.planPath, artifacts.reportPath].filter((f) => !fileExists(f)),
  };
}

function textResult(payload: Record<string, unknown>): { content: Array<{ type: 'text'; text: string }>; structuredContent: Record<string, unknown> } {
  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify(payload, null, 2),
      },
    ],
    structuredContent: payload,
  };
}

async function main(): Promise<void> {
  const options = resolveOptions();
  const server = new McpServer({
    name: 'rig-copilot-mode-mcp',
    version: '0.0.1',
  });

  server.registerTool(
    'rig_list_artifacts',
    {
      description: 'List expected RIG artifact files and their existence state.',
      inputSchema: {
        outputDir: z.string().optional(),
      },
    },
    async ({ outputDir }) => {
      const artifacts = buildArtifacts(options.workspaceRoot, outputDir ?? options.outputDirName);
      const payload = {
        workspaceRoot: options.workspaceRoot,
        outputDir: artifacts.outputDir,
        exists: {
          rig: fileExists(artifacts.rigPath),
          plan: fileExists(artifacts.planPath),
          report: fileExists(artifacts.reportPath),
          rigView: fileExists(artifacts.rigViewPath),
          workflowView: fileExists(artifacts.workflowViewPath),
        },
        files: artifacts,
      };
      return textResult(payload);
    }
  );

  server.registerTool(
    'rig_get_context',
    {
      description: 'Read repository-level RIG/plan/report artifacts and return structured context for prompts.',
      inputSchema: {
        outputDir: z.string().optional(),
        maxTasks: z.number().int().min(1).max(20).optional(),
        includeExecutions: z.boolean().optional(),
      },
    },
    async ({ outputDir, maxTasks, includeExecutions }) => {
      const artifacts = buildArtifacts(options.workspaceRoot, outputDir ?? options.outputDirName);
      const payload = await buildContextPayload(artifacts, maxTasks ?? 8, includeExecutions ?? true);
      return textResult(payload);
    }
  );

  server.registerTool(
    'rig_refresh_context',
    {
      description: 'Run rig_mvp build/plan/generate/view/workflow-view and refresh the context artifacts.',
      inputSchema: {
        outputDir: z.string().optional(),
        intent: z.string().optional(),
        maxRounds: z.number().int().min(1).max(5).optional(),
      },
    },
    async ({ outputDir, intent, maxRounds }) => {
      const mergedOptions: RuntimeOptions = {
        ...options,
        outputDirName: outputDir ?? options.outputDirName,
      };

      try {
        const artifacts = await refreshContextArtifacts(mergedOptions, intent, maxRounds ?? 2);
        const payload = await buildContextPayload(artifacts, 8, true);
        return textResult({
          refreshed: true,
          ...payload,
        });
      } catch (error) {
        return {
          content: [
            {
              type: 'text',
              text: `Failed to refresh context: ${error instanceof Error ? error.message : String(error)}`,
            },
          ],
          isError: true,
        };
      }
    }
  );

  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(`RIG MCP server running (workspace=${options.workspaceRoot}, out=${options.outputDirName})`);
}

main().catch((error) => {
  console.error('RIG MCP server failed:', error);
  process.exit(1);
});
