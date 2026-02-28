# RIG Operator Runbook (5-Minute Flow)

This runbook is the standard operator sequence for local use and PR checks.

## 0) One-time setup

```powershell
python -m pip install -e .
```

## 1) Build graph snapshot

```powershell
rig-build build --repo . --out .dist/rig.json
```

## 2) Run impact query before changes

```powershell
rig-build query --rig .dist/rig.json --mode impact --name src.rig_mvp.cli --explain --relation-filter depends_on --relation-filter imports --min-confidence medium --path-limit 50 --out .dist/impact-pre.json
```

## 3) Run policy + verification gates

```powershell
rig-build policy --rig .dist/rig.json --forbid "src.ui.->src.data." --out .dist/policy-report.json --fail-on-violation
rig-build verify --repo . --python python --max-rounds 2 --auto-repair --out .dist/verification-report.json
```

## 4) Run AI workflow (safe preview first)

```powershell
rig-build generate --repo . --intent "Migrate auth to OAuth2" --python python --max-rounds 2 --auto-repair --dry-run-apply --artifact-dir .dist/change-sets --out .dist/generate-report.json
```

If output is acceptable, run with apply:

```powershell
rig-build generate --repo . --intent "Migrate auth to OAuth2" --python python --max-rounds 2 --auto-repair --apply --artifact-dir .dist/change-sets --out .dist/generate-report.json
```

## 5) Compare with baseline and post-change impact

```powershell
rig-build query --rig .dist/rig.json --mode impact --name src.rig_mvp.cli --explain --relation-filter depends_on --relation-filter imports --min-confidence medium --path-limit 50 --out .dist/impact-post.json
rig-build diff --old .rig/baseline-rig.json --new .dist/rig.json --out .dist/rig-diff.json
```

## 6) Visualize and export for reviewers

```powershell
rig-build view --rig .dist/rig.json --out .dist/rig-view.html
rig-build neo4j-export --rig .dist/rig.json --out-dir .dist/neo4j
```

## Expected artifacts

- `.dist/rig.json`
- `.dist/impact-pre.json`
- `.dist/impact-post.json`
- `.dist/policy-report.json`
- `.dist/verification-report.json`
- `.dist/generate-report.json`
- `.dist/rig-diff.json`
- `.dist/rig-view.html`
- `.dist/neo4j/*`
