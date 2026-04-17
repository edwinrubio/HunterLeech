// PAT-05: Contratista Sancionado con Contratos
// Flag Empresa or Persona nodes that have at least one Sancion linked
// AND at least one Contrato. A sanctioned entity holding public contracts
// is a high-severity alert regardless of contract date.
//
// Data source: (:Empresa|:Persona)-[:SANCIONADO]->(:Sancion)
//              (:Empresa|:Persona)-[:EJECUTA]->(:Contrato)
// Written properties: flag_contratista_sancionado (bool), flag_computed_at

// --- SET TRUE for Empresa ---
MATCH (e:Empresa)-[:SANCIONADO]->(:Sancion)
WHERE (e)-[:EJECUTA]->(:Contrato)
WITH DISTINCT e
SET e.flag_contratista_sancionado = true,
    e.flag_computed_at = datetime()
RETURN count(e) AS flagged_empresas;

// --- SET TRUE for Persona ---
MATCH (p:Persona)-[:SANCIONADO]->(:Sancion)
WHERE (p)-[:EJECUTA]->(:Contrato)
WITH DISTINCT p
SET p.flag_contratista_sancionado = true,
    p.flag_computed_at = datetime()
RETURN count(p) AS flagged_personas;

// --- CLEAR Empresa that no longer qualify ---
MATCH (e:Empresa)
WHERE e.flag_contratista_sancionado = true
  AND NOT (
    (e)-[:SANCIONADO]->(:Sancion)
    AND (e)-[:EJECUTA]->(:Contrato)
  )
SET e.flag_contratista_sancionado = false,
    e.flag_computed_at = datetime()
RETURN count(e) AS cleared_empresas;

// --- CLEAR Persona that no longer qualify ---
MATCH (p:Persona)
WHERE p.flag_contratista_sancionado = true
  AND NOT (
    (p)-[:SANCIONADO]->(:Sancion)
    AND (p)-[:EJECUTA]->(:Contrato)
  )
SET p.flag_contratista_sancionado = false,
    p.flag_computed_at = datetime()
RETURN count(p) AS cleared_personas;
