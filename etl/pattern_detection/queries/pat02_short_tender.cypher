// PAT-02: Contrato Express
// Flag Contrato nodes with duration under 30 days and valor > 500,000,000 COP.
// Very short high-value contracts may indicate urgency manipulation.
//
// Data source: :Contrato.fecha_inicio, :Contrato.fecha_fin, :Contrato.valor
// Written properties: flag_contrato_express (bool), flag_express_dias (int), flag_computed_at
//
// Uses CALL IN TRANSACTIONS to avoid OOM on large datasets.

// --- SET TRUE ---
MATCH (c:Contrato)
WHERE c.fecha_inicio IS NOT NULL AND c.fecha_inicio <> ''
  AND c.fecha_fin IS NOT NULL AND c.fecha_fin <> ''
  AND c.valor IS NOT NULL AND toFloat(c.valor) > 500000000
  AND substring(c.fecha_fin, 0, 10) <= substring(c.fecha_inicio, 0, 10) + '-99'
WITH c,
     duration.between(
       date(substring(c.fecha_inicio, 0, 10)),
       date(substring(c.fecha_fin, 0, 10))
     ).days AS dias
WHERE dias >= 0 AND dias < 30
SET c.flag_contrato_express = true,
    c.flag_express_dias = dias,
    c.flag_computed_at = datetime()
RETURN count(c) AS flagged_true;

// --- CLEAR ---
MATCH (c:Contrato)
WHERE c.flag_contrato_express = true
WITH c,
     CASE
       WHEN c.fecha_inicio IS NOT NULL AND c.fecha_inicio <> ''
            AND c.fecha_fin IS NOT NULL AND c.fecha_fin <> ''
       THEN duration.between(
              date(substring(c.fecha_inicio, 0, 10)),
              date(substring(c.fecha_fin, 0, 10))
            ).days
       ELSE 999
     END AS dias
WHERE dias >= 30 OR toFloat(c.valor) <= 500000000
SET c.flag_contrato_express = false,
    c.flag_express_dias = null,
    c.flag_computed_at = datetime()
RETURN count(c) AS cleared;
