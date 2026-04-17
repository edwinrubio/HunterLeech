"""
PrivacyFilter: enforces Ley 1581/2012 field-level privacy in PUBLIC_MODE.

Called from service functions (not HTTP middleware) so that node label
context is available when filtering. See 03-CONTEXT.md for rationale.
"""

# Fields stripped per node label when PUBLIC_MODE=true.
# Classification source: Phase 1 privacy inventory (PRIV-01).
PROTECTED_FIELDS: dict[str, set[str]] = {
    "Persona": {
        "email",
        "telefono_personal",
        "direccion_residencia",
        "fecha_nacimiento",
        "numero_documento",  # exposed via cedula field only when needed
    },
    "Empresa": set(),        # legal entities: all fields are public record
    "EntidadPublica": set(), # public institutions: all fields public
    "Contrato": set(),       # contract data: all fields public (SECOP)
    "Sancion": set(),        # sanctions: all fields public (SIRI/Procuraduria)
    "Proceso": set(),        # procurement processes: all fields public
}


class PrivacyFilter:
    """Apply field-level privacy filtering based on PUBLIC_MODE setting."""

    def __init__(self, public_mode: bool):
        self.public_mode = public_mode

    def filter_node(self, label: str, props: dict) -> dict:
        """Remove protected fields from a node's property dict.

        Args:
            label: Neo4j node label (e.g. 'Persona', 'Empresa')
            props: Raw property dict from Neo4j

        Returns:
            Filtered property dict — protected fields absent in public mode.
        """
        if not self.public_mode:
            return props
        blocked = PROTECTED_FIELDS.get(label, set())
        if not blocked:
            return props
        return {k: v for k, v in props.items() if k not in blocked}

    def filter_graph_nodes(self, nodes: list[dict]) -> list[dict]:
        """Apply filter_node to each node in a graph response list.

        Each node dict must have 'label' and 'properties' keys.
        """
        return [
            {**n, "properties": self.filter_node(n["label"], n["properties"])}
            for n in nodes
        ]
