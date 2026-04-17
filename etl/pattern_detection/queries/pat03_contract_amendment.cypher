// PAT-03: Red Amplia de Contratacion
// Flag Persona nodes that have executed contracts with more than 10 different
// EntidadPublica entities. Unusually broad reach may indicate a front person
// (testaferro) operating across many entities.
//
// Data source: (:Persona)-[:EJECUTA]->(:Contrato)<-[:ADJUDICO]-(:EntidadPublica)
// Written properties: flag_red_amplia (bool), flag_red_amplia_entidades (int), flag_computed_at

// --- SET TRUE ---
MATCH (persona:Persona)-[:EJECUTA]->(c:Contrato)<-[:ADJUDICO]-(entidad:EntidadPublica)
WITH persona, count(DISTINCT entidad) AS num_entidades
WHERE num_entidades > 10
SET persona.flag_red_amplia = true,
    persona.flag_red_amplia_entidades = num_entidades,
    persona.flag_computed_at = datetime()
RETURN count(persona) AS flagged_true;

// --- CLEAR ---
MATCH (persona:Persona)
WHERE persona.flag_red_amplia = true
OPTIONAL MATCH (persona)-[:EJECUTA]->(c:Contrato)<-[:ADJUDICO]-(entidad:EntidadPublica)
WITH persona, count(DISTINCT entidad) AS num_entidades
WHERE num_entidades <= 10
SET persona.flag_red_amplia = false,
    persona.flag_red_amplia_entidades = null,
    persona.flag_computed_at = datetime()
RETURN count(persona) AS cleared;
