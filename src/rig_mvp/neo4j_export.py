from __future__ import annotations

import csv
import json
from pathlib import Path


def export_neo4j_artifacts(rig_json_path: Path, out_dir: Path) -> dict[str, str]:
    payload = json.loads(rig_json_path.read_text(encoding="utf-8"))
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])

    out_dir.mkdir(parents=True, exist_ok=True)
    nodes_csv = out_dir / "nodes.csv"
    edges_csv = out_dir / "edges.csv"
    import_cypher = out_dir / "import.cypher"

    with nodes_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["id", "kind", "name"])
        for node in nodes:
            if not isinstance(node, dict):
                continue
            writer.writerow([
                str(node.get("id", "")),
                str(node.get("kind", "")),
                str(node.get("name", "")),
            ])

    with edges_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["source", "target", "relation", "confidence"])
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            properties = edge.get("properties", {}) if isinstance(edge, dict) else {}
            confidence = "unknown"
            if isinstance(properties, dict) and isinstance(properties.get("confidence"), str):
                confidence = str(properties.get("confidence"))
            writer.writerow([
                str(edge.get("source", "")),
                str(edge.get("target", "")),
                str(edge.get("relation", "")),
                confidence,
            ])

    import_cypher.write_text(
        "\n".join(
            [
                "// Run in Neo4j Browser after placing CSV files in Neo4j import directory.",
                "MATCH (n) DETACH DELETE n;",
                "",
                "LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row",
                "MERGE (n:Entity {id: row.id})",
                "SET n.kind = row.kind, n.name = row.name;",
                "",
                "LOAD CSV WITH HEADERS FROM 'file:///edges.csv' AS row",
                "MATCH (s:Entity {id: row.source})",
                "MATCH (t:Entity {id: row.target})",
                "MERGE (s)-[rel:RELATES_TO {relation: row.relation, confidence: row.confidence}]->(t)",
                "RETURN count(rel) AS relationships_created;",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "nodes_csv": str(nodes_csv),
        "edges_csv": str(edges_csv),
        "import_cypher": str(import_cypher),
    }
