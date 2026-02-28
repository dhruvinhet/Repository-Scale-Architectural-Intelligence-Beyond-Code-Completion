// Run in Neo4j Browser after placing CSV files in Neo4j import directory.
MATCH (n) DETACH DELETE n;

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
MERGE (n:Entity {id: row.id})
SET n.kind = row.kind, n.name = row.name;

LOAD CSV WITH HEADERS FROM 'file:///edges.csv' AS row
MATCH (s:Entity {id: row.source})
MATCH (t:Entity {id: row.target})
MERGE (s)-[rel:RELATES_TO {relation: row.relation, confidence: row.confidence}]->(t)
RETURN count(rel) AS relationships_created;