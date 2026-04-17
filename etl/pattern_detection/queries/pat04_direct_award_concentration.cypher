// PAT-04: Concentracion de Contratacion Directa
// Flag Empresa nodes that receive > 50% of a single EntidadPublica's direct-award
// contract value (all time — date filter removed because loaded data goes up to 2014).
//
// Data source: :Contrato.modalidad, :Contrato.valor
//              (:EntidadPublica)-[:ADJUDICO]->(:Contrato)<-[:EJECUTA]-(:Empresa)
// Written properties: flag_concentracion_directa (bool), flag_concentracion_entidades (list)

// --- COMPUTE concentration per (Empresa, EntidadPublica) pair ---
MATCH (empresa:Empresa)-[:EJECUTA]->(c:Contrato)<-[:ADJUDICO]-(entidad:EntidadPublica)
WHERE c.modalidad CONTAINS 'Directa'
  AND c.valor IS NOT NULL AND toFloat(c.valor) > 0

WITH entidad, empresa,
     sum(toFloat(c.valor)) AS empresa_valor

// Total direct-award value for each entity
MATCH (entidad)-[:ADJUDICO]->(c2:Contrato)
WHERE c2.modalidad CONTAINS 'Directa'
  AND c2.valor IS NOT NULL AND toFloat(c2.valor) > 0

WITH entidad, empresa, empresa_valor,
     sum(toFloat(c2.valor)) AS entidad_total

WHERE entidad_total > 0
  AND empresa_valor / entidad_total > 0.50

// Aggregate flagging entities per empresa
WITH empresa,
     collect(entidad.codigo_entidad) AS flagging_entidades

SET empresa.flag_concentracion_directa = true,
    empresa.flag_concentracion_entidades = flagging_entidades,
    empresa.flag_computed_at = datetime()

RETURN count(empresa) AS flagged_true;

// --- CLEAR empresas that no longer qualify ---
MATCH (empresa:Empresa)
WHERE empresa.flag_concentracion_directa = true

WITH empresa

OPTIONAL MATCH (empresa)-[:EJECUTA]->(c:Contrato)<-[:ADJUDICO]-(entidad:EntidadPublica)
WHERE c.modalidad CONTAINS 'Directa'
  AND c.valor IS NOT NULL AND toFloat(c.valor) > 0

WITH empresa, entidad,
     CASE WHEN entidad IS NOT NULL THEN sum(toFloat(c.valor)) ELSE 0 END AS empresa_valor

OPTIONAL MATCH (entidad)-[:ADJUDICO]->(c2:Contrato)
WHERE c2.modalidad CONTAINS 'Directa'
  AND c2.valor IS NOT NULL AND toFloat(c2.valor) > 0

WITH empresa, entidad, empresa_valor,
     CASE WHEN entidad IS NOT NULL THEN sum(toFloat(c2.valor)) ELSE 0 END AS entidad_total

WITH empresa,
     CASE WHEN entidad_total > 0 AND empresa_valor / entidad_total > 0.50 THEN 1 ELSE 0 END AS still_qualifies

WITH empresa, sum(still_qualifies) AS qualifying_count
WHERE qualifying_count = 0

SET empresa.flag_concentracion_directa = false,
    empresa.flag_concentracion_entidades = [],
    empresa.flag_computed_at = datetime()

RETURN count(empresa) AS cleared;
