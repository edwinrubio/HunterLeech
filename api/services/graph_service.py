"""
Graph traversal service.

Returns a subgraph centered on any entity with a maximum depth of 2 hops.
Hard limits:
  - MAX_NODES = 300: maximum nodes in response
  - MAX_EDGES = 500: maximum edges in response
  - QUERY_TIMEOUT = 30.0 seconds

Uses explicit two-layer expansion (layer1 + layer2) instead of [*..2]
to avoid the combinatorial path explosion on dense contractor networks.
See ARCHITECTURE.md Anti-Pattern 2 for rationale.

Privacy: Persona node properties are filtered via PrivacyFilter before
returning. All edge properties pass through unfiltered (no PRIVADA fields
are stored on relationships per the Phase 1 privacy inventory).
"""
from neo4j import AsyncSession
from neo4j.exceptions import ClientError
from neo4j.time import DateTime as Neo4jDateTime, Date as Neo4jDate
from middleware.privacy import PrivacyFilter


def _serialize_neo4j(obj: dict) -> dict:
    out = {}
    for k, v in obj.items():
        if isinstance(v, (Neo4jDateTime, Neo4jDate)):
            out[k] = v.iso_format()
        else:
            out[k] = v
    return out

MAX_NODES = 300
MAX_EDGES = 500
QUERY_TIMEOUT = 30.0  # seconds

# Maps relationship type strings to human-readable Spanish labels for PRIV-03
REL_LABELS = {
    "EJECUTA": "ejecuta contrato",
    "ADJUDICO": "adjudico contrato",
    "SANCIONADO": "recibio sancion",
    "REPRESENTA": "representa empresa",
    "EMPLEA_EN": "empleado en",
    "PARTICIPO": "participo en proceso",
    "PUBLICO": "publico proceso",
    "IMPUSO": "impuso sancion",
    "MULTADO": "recibio multa",
    "RELACIONADO_CON": "relacionado con",
}

# Node property used as the graph ID, keyed by label
NODE_ID_FIELDS = {
    "Empresa": "nit",
    "Persona": "cedula",
    "Contrato": "id_contrato",
    "EntidadPublica": "codigo_entidad",
    "Sancion": "id_sancion",
    "Proceso": "referencia_proceso",
}


def _node_id(label: str, props: dict) -> str:
    """Extract the canonical ID for a node based on its label."""
    id_field = NODE_ID_FIELDS.get(label)
    if id_field and props.get(id_field):
        return str(props[id_field])
    # Fallback: use Neo4j internal element ID if no business key found
    return props.get("_element_id", "unknown")


async def get_subgraph(
    id: str,
    session: AsyncSession,
    privacy: PrivacyFilter,
) -> dict | None:
    """
    Return a depth-2 subgraph centered on the entity identified by id.

    The id can be a NIT, cedula, id_contrato, or codigo_entidad.
    Returns None if no root entity is found.

    Raises asyncio.TimeoutError-like on Neo4j timeout (caller handles as 408).
    """
    # Resolve root entity
    root_result = await session.run(
        """
        MATCH (root)
        WHERE root.nit = $id
           OR root.cedula = $id
           OR root.id_contrato = $id
           OR root.codigo_entidad = $id
        RETURN root, labels(root)[0] AS label
        LIMIT 1
        """,
        id=id,
    )
    root_record = await root_result.single()
    if not root_record:
        return None

    root_label = root_record["label"]
    root_props = _serialize_neo4j(dict(root_record["root"]))
    root_id = _node_id(root_label, root_props)
    filtered_root_props = privacy.filter_node(root_label, root_props)

    nodes: dict[str, dict] = {
        root_id: {"id": root_id, "label": root_label, "properties": filtered_root_props}
    }
    edges: list[dict] = []

    # Layer 1: direct neighbors of root
    layer1: list[dict] = []
    layer2: list[dict] = []
    try:
        layer1_result = await session.run(
            """
            MATCH (root)-[r1]-(n1)
            WHERE root.nit = $id
               OR root.cedula = $id
               OR root.id_contrato = $id
               OR root.codigo_entidad = $id
            RETURN
              labels(n1)[0] AS n1_label,
              properties(n1) AS n1_props,
              type(r1) AS r1_type,
              properties(r1) AS r1_props,
              startNode(r1) = root AS r1_from_root
            LIMIT $limit
            """,
            id=id,
            limit=MAX_NODES,
        )
        layer1 = await layer1_result.data()

        # Layer 2: neighbors of layer-1 nodes (excluding root)
        if len(nodes) + len(layer1) < MAX_NODES:
            l1_ids = []
            for row in layer1:
                l1_label = row["n1_label"] or "Unknown"
                l1_props = _serialize_neo4j(row["n1_props"] or {})
                l1_id = _node_id(l1_label, l1_props)
                l1_ids.append(l1_id)

            if l1_ids:
                layer2_result = await session.run(
                    """
                    MATCH (n1)-[r2]-(n2)
                    WHERE (n1.nit IN $ids
                        OR n1.cedula IN $ids
                        OR n1.id_contrato IN $ids
                        OR n1.codigo_entidad IN $ids)
                      AND NOT (n2.nit = $root_id
                           OR n2.cedula = $root_id
                           OR n2.id_contrato = $root_id
                           OR n2.codigo_entidad = $root_id)
                    RETURN
                      labels(n2)[0] AS n2_label,
                      properties(n2) AS n2_props,
                      type(r2) AS r2_type,
                      properties(r2) AS r2_props,
                      (n1.nit IN $ids OR n1.cedula IN $ids
                       OR n1.id_contrato IN $ids
                       OR n1.codigo_entidad IN $ids) AS r2_from_l1,
                      coalesce(n1.nit, n1.cedula, n1.id_contrato, n1.codigo_entidad) AS n1_id
                    LIMIT $limit
                    """,
                    ids=l1_ids,
                    root_id=id,
                    limit=MAX_NODES - len(nodes) - len(layer1),
                )
                layer2 = await layer2_result.data()

    except ClientError as e:
        if "TransactionTimedOut" in str(e):
            raise TimeoutError("Graph query exceeded 30s timeout") from e
        raise

    truncated = False

    # Add layer-1 nodes and edges
    for row in layer1:
        n1_label = row["n1_label"] or "Unknown"
        n1_props = _serialize_neo4j(row["n1_props"] or {})
        n1_id = _node_id(n1_label, n1_props)
        filtered_n1 = privacy.filter_node(n1_label, n1_props)

        if n1_id not in nodes:
            if len(nodes) >= MAX_NODES:
                truncated = True
                break
            nodes[n1_id] = {"id": n1_id, "label": n1_label, "properties": filtered_n1}

        if len(edges) < MAX_EDGES:
            source_id, target_id = (root_id, n1_id) if row["r1_from_root"] else (n1_id, root_id)
            rel_props = _serialize_neo4j(row["r1_props"] or {})
            edges.append({
                "source": source_id,
                "target": target_id,
                "type": row["r1_type"],
                "properties": {
                    **rel_props,
                    "_label": REL_LABELS.get(row["r1_type"], row["r1_type"]),
                },
            })
        else:
            truncated = True

    # Add layer-2 nodes and edges
    for row in layer2:
        n2_label = row["n2_label"] or "Unknown"
        n2_props = _serialize_neo4j(row["n2_props"] or {})
        n2_id = _node_id(n2_label, n2_props)
        filtered_n2 = privacy.filter_node(n2_label, n2_props)

        if n2_id not in nodes:
            if len(nodes) >= MAX_NODES:
                truncated = True
                break
            nodes[n2_id] = {"id": n2_id, "label": n2_label, "properties": filtered_n2}

        if len(edges) < MAX_EDGES:
            n1_src = row.get("n1_id", "unknown")
            r2_type = row["r2_type"]
            rel_props = _serialize_neo4j(row["r2_props"] or {})
            edges.append({
                "source": n1_src if row.get("r2_from_l1") else n2_id,
                "target": n2_id if row.get("r2_from_l1") else n1_src,
                "type": r2_type,
                "properties": {
                    **rel_props,
                    "_label": REL_LABELS.get(r2_type, r2_type),
                },
            })
        else:
            truncated = True

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "truncated": truncated,
        "root_id": root_id,
    }
