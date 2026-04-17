"""
Shortest path service.

Finds the shortest path between two entities in the procurement graph
using Neo4j's shortestPath() algorithm, limited to 6 hops.
"""
from neo4j import AsyncSession
from neo4j.time import DateTime as Neo4jDateTime, Date as Neo4jDate
from middleware.privacy import PrivacyFilter
from services.graph_service import REL_LABELS, NODE_ID_FIELDS, _serialize_neo4j

MAX_DEPTH = 6


def _node_id(label: str, props: dict) -> str:
    id_field = NODE_ID_FIELDS.get(label)
    if id_field and props.get(id_field):
        return str(props[id_field])
    return props.get("_element_id", "unknown")


async def get_shortest_path(
    from_id: str,
    to_id: str,
    session: AsyncSession,
    privacy: PrivacyFilter,
) -> dict | None:
    """
    Find shortest path between two entities identified by any business key.
    Returns {nodes, edges, path_order, from_id, to_id} or None.
    """
    result = await session.run(
        f"""
        MATCH (a), (b)
        WHERE (a.nit = $from_id OR a.cedula = $from_id
               OR a.id_contrato = $from_id OR a.codigo_entidad = $from_id
               OR a.referencia_proceso = $from_id)
          AND (b.nit = $to_id OR b.cedula = $to_id
               OR b.id_contrato = $to_id OR b.codigo_entidad = $to_id
               OR b.referencia_proceso = $to_id)
        WITH a, b LIMIT 1
        MATCH p = shortestPath((a)-[*..{MAX_DEPTH}]-(b))
        RETURN nodes(p) AS path_nodes, relationships(p) AS path_rels
        """,
        from_id=from_id,
        to_id=to_id,
    )
    record = await result.single()
    if not record:
        return None

    path_nodes_raw = record["path_nodes"]
    path_rels_raw = record["path_rels"]

    nodes = []
    node_ids_ordered = []
    seen_nodes = set()

    for neo_node in path_nodes_raw:
        label = list(neo_node.labels)[0] if neo_node.labels else "Unknown"
        props = _serialize_neo4j(dict(neo_node))
        nid = _node_id(label, props)

        if nid not in seen_nodes:
            seen_nodes.add(nid)
            filtered = privacy.filter_node(label, props) if label == "Persona" else props
            nodes.append({
                "id": nid,
                "label": label,
                "properties": filtered,
            })
        node_ids_ordered.append(nid)

    edges = []
    for rel in path_rels_raw:
        rel_type = rel.type
        start_label = list(rel.start_node.labels)[0] if rel.start_node.labels else "Unknown"
        end_label = list(rel.end_node.labels)[0] if rel.end_node.labels else "Unknown"
        start_props = _serialize_neo4j(dict(rel.start_node))
        end_props = _serialize_neo4j(dict(rel.end_node))

        source_id = _node_id(start_label, start_props)
        target_id = _node_id(end_label, end_props)

        rel_props = _serialize_neo4j(dict(rel))
        rel_props["_label"] = REL_LABELS.get(rel_type, rel_type.lower())

        edges.append({
            "source": source_id,
            "target": target_id,
            "type": rel_type,
            "properties": rel_props,
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "path_order": node_ids_ordered,
        "from_id": from_id,
        "to_id": to_id,
    }
