"""
Graph response models for the /graph/{id} endpoint.

These models serialize the two-layer Neo4j subgraph expansion into
a JSON format suitable for consumption by Sigma.js/graphology in Phase 4.
"""
from pydantic import BaseModel


class NodeDTO(BaseModel):
    """A single node in the subgraph."""
    id: str              # Unique node identifier (nit, cedula, id_contrato, etc.)
    label: str           # Neo4j label: Empresa, Persona, Contrato, EntidadPublica, Sancion
    properties: dict     # Node properties (privacy-filtered by service layer)


class EdgeDTO(BaseModel):
    """A single relationship (edge) in the subgraph."""
    source: str          # Source node id
    target: str          # Target node id
    type: str            # Relationship type: EJECUTA, ADJUDICO, SANCIONO, REPRESENTA, EMPLEA
    properties: dict     # Relationship properties (always includes fuente if present)


class PathResponse(BaseModel):
    """Shortest path between two entities."""
    nodes: list[NodeDTO]
    edges: list[EdgeDTO]
    path_order: list[str]  # Ordered node IDs along the path
    from_id: str
    to_id: str


class GraphResponse(BaseModel):
    """
    Subgraph centered on a root entity.

    nodes: Deduplicated list of all nodes within depth=2 of the root.
    edges: All relationships connecting those nodes.
    truncated: True when the graph was cut at MAX_NODES or MAX_EDGES to prevent overload.
    root_id: The identifier of the root entity for client-side centering.
    """
    nodes: list[NodeDTO]
    edges: list[EdgeDTO]
    truncated: bool
    root_id: str
