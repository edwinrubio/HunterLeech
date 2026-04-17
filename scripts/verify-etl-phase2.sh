#!/usr/bin/env bash
# Verify Phase 2 ETL graph integrity.
# Runs against live Neo4j via cypher-shell inside docker container.
# Usage: bash scripts/verify-etl-phase2.sh
# Prerequisites: docker compose up (Neo4j running)

set -euo pipefail

NEO4J_CONTAINER="${NEO4J_CONTAINER:-hunterleech-neo4j-1}"
CYPHER="docker exec -i ${NEO4J_CONTAINER} cypher-shell -u neo4j -p ${NEO4J_PASSWORD:-password} --format plain"

echo "=== Phase 2 ETL Verification ==="
echo ""

echo "--- Node counts by label ---"
$CYPHER "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC;"

echo ""
echo "--- Relationship counts by type ---"
$CYPHER "MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS count ORDER BY count DESC;"

echo ""
echo "--- Provenance coverage: nodes with fuente property ---"
$CYPHER "MATCH (n) WHERE n.fuente IS NOT NULL RETURN n.fuente AS source, count(n) AS nodes ORDER BY nodes DESC;"

echo ""
echo "--- Cross-source entity linking check ---"
echo "Personas with both EMPLEA_EN (SIGEP) and SANCIONADO (SIRI):"
$CYPHER "MATCH (p:Persona)-[:EMPLEA_EN]->() WHERE (p)-[:SANCIONADO]->() RETURN count(p) AS linked_persons_sigep_siri;"

echo "Personas with both EJECUTA (SECOP) and SANCIONADO (SIRI):"
$CYPHER "MATCH (p:Persona)-[:EJECUTA]->() WHERE (p)-[:SANCIONADO]->() RETURN count(p) AS linked_persons_secop_siri;"

echo "Empresas with EJECUTA from multiple sources:"
$CYPHER "MATCH (e:Empresa)-[:EJECUTA]->(c:Contrato) WITH e, collect(distinct c.fuente) AS sources WHERE size(sources) > 1 RETURN count(e) AS cross_source_empresas;"

echo ""
echo "--- Super node check: any node with > 10000 relationships ---"
$CYPHER "MATCH (n) WITH n, size((n)--()) AS degree WHERE degree > 10000 RETURN labels(n)[0] AS label, n.nombre AS nombre, degree ORDER BY degree DESC LIMIT 10;"

echo ""
echo "--- Sancion node samples ---"
$CYPHER "MATCH (p:Persona)-[:SANCIONADO]->(s:Sancion) RETURN p.cedula AS cedula, s.id_sancion AS sancion, s.fuente AS fuente LIMIT 5;"
$CYPHER "MATCH (e:Empresa)-[:MULTADO]->(s:Sancion) RETURN e.nit AS nit, s.id_sancion AS sancion LIMIT 5;"

echo ""
echo "=== Verification complete ==="
