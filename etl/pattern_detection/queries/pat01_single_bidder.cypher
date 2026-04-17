// PAT-01: Contratista Recurrente
// Flag Empresa nodes that have > 100 contracts with a single EntidadPublica.
// Repeat-contractor pattern signals possible capture of an entity's procurement.
//
// Data source: (:Empresa)-[:EJECUTA]->(:Contrato)<-[:ADJUDICO]-(:EntidadPublica)
// Written properties: flag_contratista_recurrente (bool), flag_recurrente_entidades (list),
//                     flag_recurrente_max (int), flag_computed_at

// --- SET TRUE ---
MATCH (empresa:Empresa)-[:EJECUTA]->(c:Contrato)<-[:ADJUDICO]-(entidad:EntidadPublica)
WITH empresa, entidad, count(c) AS num_contratos
WHERE num_contratos > 100
WITH empresa, collect({entidad: entidad.nombre, codigo: entidad.codigo_entidad, contratos: num_contratos}) AS pares,
     max(num_contratos) AS max_contratos
SET empresa.flag_contratista_recurrente = true,
    empresa.flag_recurrente_entidades = [p IN pares | p.codigo],
    empresa.flag_recurrente_max = max_contratos,
    empresa.flag_computed_at = datetime()
RETURN count(empresa) AS flagged_true;

// --- CLEAR ---
MATCH (empresa:Empresa)
WHERE empresa.flag_contratista_recurrente = true
WITH empresa
OPTIONAL MATCH (empresa)-[:EJECUTA]->(c:Contrato)<-[:ADJUDICO]-(entidad:EntidadPublica)
WITH empresa, entidad, count(c) AS num_contratos
WITH empresa, max(num_contratos) AS max_contratos
WHERE max_contratos IS NULL OR max_contratos <= 100
SET empresa.flag_contratista_recurrente = false,
    empresa.flag_recurrente_entidades = [],
    empresa.flag_recurrente_max = null,
    empresa.flag_computed_at = datetime()
RETURN count(empresa) AS cleared;
