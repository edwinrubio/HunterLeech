#!/usr/bin/env bash
# Apply Neo4j schema constraints after first docker compose up
# Usage: ./scripts/apply-schema.sh
set -euo pipefail
source .env
docker compose exec neo4j cypher-shell \
    -u neo4j \
    -p "${NEO4J_PASSWORD}" \
    --file /var/lib/neo4j/import/infra/schema.cypher
