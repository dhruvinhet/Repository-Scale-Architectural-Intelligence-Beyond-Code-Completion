$ErrorActionPreference = "Stop"

Write-Host "[RIG] Step 1/6 build"
rig-build build --repo . --out .dist/rig.json

Write-Host "[RIG] Step 2/6 impact query"
rig-build query --rig .dist/rig.json --mode impact --name src.rig_mvp.cli --explain --relation-filter depends_on --relation-filter imports --min-confidence medium --path-limit 50 --out .dist/impact-demo.json

Write-Host "[RIG] Step 3/6 policy + verify"
rig-build policy --rig .dist/rig.json --forbid "src.ui.->src.data." --out .dist/policy-report.json
rig-build verify --repo . --python python --max-rounds 2 --auto-repair --out .dist/verification-report.json

Write-Host "[RIG] Step 4/6 dry-run generate"
rig-build generate --repo . --intent "Migrate auth to OAuth2" --python python --max-rounds 2 --auto-repair --dry-run-apply --artifact-dir .dist/change-sets --out .dist/generate-report.json

Write-Host "[RIG] Step 5/6 viewer + Neo4j"
rig-build view --rig .dist/rig.json --out .dist/rig-view.html
rig-build neo4j-export --rig .dist/rig.json --out-dir .dist/neo4j

Write-Host "[RIG] Step 6/6 done. Open .dist/rig-view.html"
