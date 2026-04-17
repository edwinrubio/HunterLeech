// HunterLeech — Neo4j Schema Constraints
// Run before any ETL pipeline executes.
// All statements use IF NOT EXISTS for idempotent re-runs.

// --- Node uniqueness constraints ---

CREATE CONSTRAINT empresa_nit IF NOT EXISTS
  FOR (e:Empresa) REQUIRE e.nit IS UNIQUE;

CREATE CONSTRAINT persona_cedula IF NOT EXISTS
  FOR (p:Persona) REQUIRE p.cedula IS UNIQUE;

CREATE CONSTRAINT contrato_id IF NOT EXISTS
  FOR (c:Contrato) REQUIRE c.id_contrato IS UNIQUE;

CREATE CONSTRAINT proceso_ref IF NOT EXISTS
  FOR (p:Proceso) REQUIRE p.referencia_proceso IS UNIQUE;

CREATE CONSTRAINT sancion_id IF NOT EXISTS
  FOR (s:Sancion) REQUIRE s.id_sancion IS UNIQUE;

CREATE CONSTRAINT entidad_codigo IF NOT EXISTS
  FOR (e:EntidadPublica) REQUIRE e.codigo_entidad IS UNIQUE;

// --- Supporting indexes for Phase 3 search ---

CREATE INDEX empresa_nombre IF NOT EXISTS
  FOR (e:Empresa) ON (e.razon_social);

CREATE INDEX persona_nombre IF NOT EXISTS
  FOR (p:Persona) ON (p.nombre);

CREATE INDEX contrato_fecha IF NOT EXISTS
  FOR (c:Contrato) ON (c.fecha_firma);

CREATE INDEX contrato_modalidad IF NOT EXISTS
  FOR (c:Contrato) ON (c.modalidad);

// Added for Phase 2: SIGEP entities merge on nombre, not codigo_entidad
CREATE INDEX entidad_nombre IF NOT EXISTS
  FOR (e:EntidadPublica) ON (e.nombre);

// --- Phase 3: Fulltext search index ---

CREATE FULLTEXT INDEX entity_search_idx IF NOT EXISTS
FOR (n:Empresa|Persona|EntidadPublica)
ON EACH [n.razon_social, n.nombre];

// --- Phase 3: SourceIngestion tracking (written by ETL pipelines) ---

CREATE INDEX source_ingestion_dataset IF NOT EXISTS
  FOR (si:SourceIngestion) ON (si.dataset_id);
