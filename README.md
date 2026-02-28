# Repository Intelligence Graph MVP

This workspace now contains a concrete starter implementation for repository-scale architectural intelligence.

## Implemented Now

- Phase 1 MVP: deterministic RIG generation from build files, source ASTs, and test wiring.
- Strong three-pillar baseline:
	- RIG with confidence metadata and advanced stack-aware extraction (Python/CMake/Gradle/JS/Maven/.NET)
	- Multi-agent style workflow (decompose, generate, critic, repair)
	- Consistency enforcement (policy + verification + rollback + CI gate)

## Project Layout

- `src/rig_mvp/models.py`: graph node and edge data model with deterministic IDs.
- `src/rig_mvp/graph_store.py`: in-memory graph store and deterministic JSON serializer.
- `src/rig_mvp/extractors/build_extractor.py`: CMake/Gradle target + dependency extraction.
- `src/rig_mvp/extractors/python_build_extractor.py`: Python packaging/dependency metadata extraction (`pyproject.toml`, `requirements*.txt`, `setup.cfg`).
- `src/rig_mvp/extractors/javascript_build_extractor.py`: JavaScript/TypeScript dependency + test script extraction (`package.json`).
- `src/rig_mvp/extractors/javascript_source_extractor.py`: React/JS source extraction for modules, imports, components/hooks, and JSX usage relations.
- `src/rig_mvp/extractors/maven_extractor.py`: Maven module/dependency/test extraction (`pom.xml`).
- `src/rig_mvp/extractors/dotnet_extractor.py`: .NET project/package/test extraction (`*.csproj`).
- `src/rig_mvp/extractors/ast_extractor.py`: Python AST extraction for modules/classes/functions/imports/calls.
- `src/rig_mvp/extractors/test_extractor.py`: test-to-module/function wiring.
- `src/rig_mvp/pipeline.py`: end-to-end RIG construction pipeline.
- `src/rig_mvp/agents/rules.py`: `AGENTS.md` parser.
- `src/rig_mvp/agents/orchestrator.py`: intent decomposition scaffold.
- `src/rig_mvp/cli.py`: CLI entrypoint.

## Quick Start

From repository root:

```powershell
python -m pip install -e .
```

Build a graph:

```powershell
rig-build build --repo . --out .dist/rig.json
```

Create an intent plan:

```powershell
rig-build plan --repo . --intent "Migrate auth to OAuth2" --out .dist/intent-plan.json
```

Run verification + repair loop:

```powershell
rig-build verify --repo . --python python --max-rounds 2 --auto-repair --out .dist/verification-report.json
```

Verification now includes optional build-system checks for detected CMake/Gradle projects (skipped if tool binaries are unavailable).
Verification also attempts stack-specific test runners for JavaScript (`npm test`), Maven (`mvn test`), and .NET (`dotnet test`) when detected.
Verification now discovers Python test roots recursively and executes stack test commands from module/project directories.

Generate interactive graph viewer HTML:

```powershell
rig-build view --rig .dist/rig.json --out .dist/rig-view.html
```

Generate intent + agent workflow viewer HTML:

```powershell
rig-build workflow-view --plan .dist/intent-plan.json --report .dist/generate-report.json --out .dist/workflow-view.html
```

Serve graph viewer locally:

```powershell
rig-build serve --html .dist/rig-view.html --host 127.0.0.1 --port 8000 --open
rig-build serve --html .dist/workflow-view.html --host 127.0.0.1 --port 8001 --open
```

Query graph relationships:

```powershell
rig-build query --rig .dist/rig.json --mode find --name auth
rig-build query --rig .dist/rig.json --mode dependencies --name src.rig_mvp.cli
rig-build query --rig .dist/rig.json --mode impact --name src.rig_mvp.cli --explain --relation-filter depends_on --relation-filter imports --min-confidence medium --path-limit 50
rig-build query --rig .dist/rig.json --mode impact --name src.rig_mvp.cli --out .dist/impact-cli.json
rig-build query --rig .dist/rig.json --mode impact --name cli --explain --relation-filter imports,calls,tested_by
```

Non-`find` queries include `resolved_name` and optional `hints` to make fuzzy symbol lookup safer.

Export Neo4j import artifacts:

```powershell
rig-build neo4j-export --rig .dist/rig.json --out-dir .dist/neo4j
```

Diff baseline vs current graph:

```powershell
rig-build diff --out .dist/rig-diff.json
# defaults: --old .rig/baseline-rig.json, --new .dist/rig.json
```

Run architecture policy checks:

```powershell
rig-build policy --rig .dist/rig.json --forbid-file config/policy-rules.txt --out .dist/policy-report.json --fail-on-violation
rig-build policy --rig .dist/rig.json --forbid-file config/policy-rules.txt --forbid-file config/policy-rules-python.txt --forbid-file config/policy-rules-backend.txt --forbid-file config/policy-rules-frontend.txt --out .dist/policy-report.json --fail-on-violation
```

Create or refresh baseline snapshot:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap-baseline.ps1
```

Run full 5-minute demo flow:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/demo-5min.ps1
```

Run end-to-end generate workflow:

```powershell
rig-build generate --repo . --intent "Migrate auth to OAuth2" --python python --max-rounds 2 --auto-repair --artifact-dir .dist/change-sets --out .dist/generate-report.json
```

Apply deterministic edits during generate (guarded by `AGENTS.md` Critical Regions):

```powershell
rig-build generate --repo . --intent "Migrate auth to OAuth2" --python python --max-rounds 2 --auto-repair --apply --artifact-dir .dist/change-sets --out .dist/generate-report.json
```

Dry-run apply preview (no file writes):

```powershell
rig-build generate --repo . --intent "Migrate auth to OAuth2" --python python --max-rounds 2 --auto-repair --dry-run-apply --artifact-dir .dist/change-sets --out .dist/generate-report.json
```

Apply with explicit path filters:

```powershell
rig-build generate --repo . --intent "Migrate auth to OAuth2" --python python --max-rounds 2 --auto-repair --apply --apply-include "src/rig_mvp/agents/*.py" --apply-exclude "src/rig_mvp/agents/workflow.py" --artifact-dir .dist/change-sets --out .dist/generate-report.json
```

This command performs:

1. RIG build
2. Intent plan creation
3. Subtask execution artifact generation (`.dist/change-sets/*.json`)
4. Verification/repair loop
5. Consolidated report generation

When `--apply` is enabled, task agents:

- Apply deterministic text refactors for intents like `Migrate X to Y` on supported files (`.py`, `.md`, `.txt`, `.toml`, `.yml`, `.yaml`, `.ini`).
- Skip files in protected regions derived from `AGENTS.md` (for example, `.azure/` and CI workflows).
- Record `applied_files` and `skipped_files` in each per-task artifact.
- Respect optional glob filters:
	- `--apply-include` (only apply to matching paths)
	- `--apply-exclude` (skip matching paths)
- Use `--dry-run-apply` to simulate apply results without modifying files.
- Create backups (`--backup-dir`, default `.dist/backups`) and automatically rollback if verification fails.

## CI Gate

CI workflow is defined in `.github/workflows/rig-gate.yml` and runs on push/PR:

1. Install package
2. Build RIG
3. Run impact query summary
4. Run policy checks (fail on violations)
5. Run verification gate
6. Generate viewer + Neo4j export artifacts
7. Upload artifacts and markdown summary

## Team Operation

Use [docs/OPERATOR_RUNBOOK.md](docs/OPERATOR_RUNBOOK.md) as the standard operator checklist.

## Current Data Model

Node kinds:

- `Target`
- `Module`
- `Class`
- `Function`
- `Test`
- `ExternalDependency`

Primary relations:

- `depends_on`
- `contains`
- `imports`
- `calls`
- `tested_by`

All nodes and edges carry evidence paths, and all IDs are deterministic.
Edges also include confidence metadata (`high`, `medium`, `low`, `unknown`) and metadata now includes `confidence_counts`.

## Suggested Next Iterations

1. Add language adapters beyond Python AST.
2. Replace file-based output with a property graph backend (Neo4j/JanusGraph).
3. Add CAE memory and prompt-strategy feedback loops.
