# HunterLeech

**Plataforma open-source de inteligencia anticorrupcion para Colombia.**

Agrega bases de datos publicas dispersas (SECOP I, SECOP II, SIGEP, SIRI, RUES, Contraloria) en una base de datos de grafos unificada, permitiendo a periodistas, veedurias ciudadanas y ONGs detectar patrones sospechosos en contratacion publica: redes de testaferros, contratos inflados, conflictos de interes y concentracion irregular de adjudicaciones.

> **2.3M+ nodos** | **1,307 alertas activas** | **6 fuentes de datos publicas**

---

## Tabla de contenido

- [Stack tecnologico](#stack-tecnologico)
- [Requisitos previos](#requisitos-previos)
- [Inicio rapido](#inicio-rapido)
- [Despliegue en produccion](#despliegue-en-produccion)
- [Variables de entorno](#variables-de-entorno)
- [Arquitectura](#arquitectura)
- [Fuentes de datos](#fuentes-de-datos)
- [ETL Pipeline](#etl-pipeline)
- [API REST](#api-rest)
- [Funcionalidades](#funcionalidades)
- [Deteccion de patrones](#deteccion-de-patrones)
- [Desarrollo local](#desarrollo-local)
- [Licencia](#licencia)

---

## Stack tecnologico

| Componente | Tecnologia | Version |
|------------|-----------|---------|
| Base de datos de grafos | Neo4j Community Edition | 5.26 LTS |
| Backend / API | FastAPI + Uvicorn | 0.135.x |
| ETL / Procesamiento | Polars + httpx | 1.39.x |
| Frontend | React + TypeScript + Tailwind CSS | 19.x |
| Visualizacion de grafos | Sigma.js (WebGL) + graphology | 3.0.x |
| Proxy reverso | Nginx | 1.27 |
| Infraestructura | Docker + Docker Compose | v2 |

---

## Requisitos previos

- [Docker](https://docs.docker.com/get-docker/) (20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) v2
- **4 GB de RAM minimo** (Neo4j usa hasta 1.5 GB de heap + page cache)
- **15 GB de disco** para datos de Neo4j despues de la carga completa
- (Opcional) [Node.js](https://nodejs.org/) 20+ para desarrollo del frontend
- (Opcional) [Python](https://www.python.org/) 3.12+ para ejecutar ETL manualmente

---

## Inicio rapido

### Opcion A: Carga automatica (recomendada)

La forma mas sencilla. Un solo comando levanta todo y carga los datos automaticamente.

```bash
# 1. Clonar el repositorio
git clone https://github.com/your-user/HunterLeech.git
cd HunterLeech

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env y cambiar NEO4J_PASSWORD a una contrasena segura

# 3. Activar la carga automatica (solo la primera vez)
# En .env, cambiar:
#   LOAD_DATA_BOOTLOADER=true

# 4. Compilar el frontend (genera dist/ para nginx)
cd frontend && npm ci && npm run build && cd ..

# 5. Levantar todos los servicios
docker compose up -d

# 6. Monitorear el progreso de la carga
docker compose logs -f etl

# La carga completa descarga ~10M registros desde datos.gov.co
# y toma varias horas dependiendo de tu conexion a internet.

# 7. Abrir en el navegador
open http://localhost
```

> **Importante:** Despues de la primera carga exitosa, cambiar `LOAD_DATA_BOOTLOADER=false` en `.env` para evitar re-ejecutar el ETL en cada reinicio.

### Opcion B: Carga manual (paso a paso)

Para mayor control sobre cada fuente de datos.

```bash
# 1. Clonar y configurar
git clone https://github.com/your-user/HunterLeech.git
cd HunterLeech
cp .env.example .env
# Editar NEO4J_PASSWORD en .env

# 2. Compilar frontend
cd frontend && npm ci && npm run build && cd ..

# 3. Levantar servicios (sin carga automatica)
docker compose up -d

# 4. Aplicar schema de Neo4j (constraints e indices)
docker exec hunterleech-neo4j-1 cypher-shell \
  -u neo4j -p TU_PASSWORD \
  < infra/neo4j/schema.cypher

# 5. Instalar dependencias del ETL
pip install -r etl/requirements.txt

# 6. Cargar cada fuente de datos
python3 -m etl.run secop_integrado       # ~1.6M contratos
python3 -m etl.run secop_ii_contratos    # Complementa SECOP I
python3 -m etl.run sigep_servidores      # ~80K funcionarios
python3 -m etl.run siri_sanciones        # ~16K sanciones
python3 -m etl.run secop_multas          # ~1.7K multas
python3 -m etl.run secop_ii_procesos     # ~8.4M procesos

# 7. Ejecutar deteccion de patrones
python3 -m etl.pattern_detection.run_flags

# 8. Abrir en el navegador
open http://localhost
```

---

## Despliegue en produccion

El proyecto incluye un `docker-compose.prod.yml` con seguridad reforzada para despliegue en servidores (probado con [Dokploy](https://dokploy.com/) + Traefik).

```bash
# 1. Configurar entorno de produccion
cp .env.prod.example .env

# Generar contrasena segura para Neo4j:
openssl rand -base64 32
# Pegar el resultado en NEO4J_PASSWORD dentro de .env

# 2. Primera carga: activar bootloader
# En .env, cambiar LOAD_DATA_BOOTLOADER=true

# 3. Levantar con el compose de produccion
docker compose -f docker-compose.prod.yml up -d

# 4. Monitorear la carga
docker compose -f docker-compose.prod.yml logs -f etl

# 5. Despues de la carga, desactivar bootloader
# En .env, cambiar LOAD_DATA_BOOTLOADER=false
docker compose -f docker-compose.prod.yml up -d etl  # Reiniciar solo ETL
```

### Seguridad en produccion

El compose de produccion aplica estas medidas:

| Control | Descripcion |
|---------|-------------|
| SEC-01 | Sin puertos expuestos excepto nginx (Traefik como ingress) |
| SEC-02 | Neo4j browser/bolt no accesible externamente |
| SEC-03 | Filesystem de solo lectura en API |
| SEC-04 | Usuarios no-root en todos los contenedores |
| SEC-05 | `no-new-privileges: true` en todos los servicios |
| SEC-06 | Capabilities de Linux reducidas al minimo |
| SEC-07 | Limites de memoria (Neo4j 2G, API 512M, ETL 1G, Nginx 128M) |
| SEC-08 | Red interna aislada |
| SEC-09 | Headers de seguridad en nginx (CSP, X-Frame, HSTS) |
| SEC-10 | Rate limiting en API (slowapi: 10-60 req/min por endpoint) |

---

## Variables de entorno

| Variable | Requerida | Default | Descripcion |
|----------|-----------|---------|-------------|
| `NEO4J_PASSWORD` | Si | `changeme_in_production` | Contrasena de Neo4j. Cambiar siempre. |
| `SOCRATA_APP_TOKEN` | No | (vacio) | Token de API de datos.gov.co. Aumenta el rate limit de 1,000 a 50,000 req/hr. Registrarse en [datos.gov.co](https://www.datos.gov.co/profile/edit/developer_settings). |
| `PUBLIC_MODE` | No | `true` | Filtra datos personales protegidos por Ley 1581/2012. Siempre `true` en produccion. |
| `LOAD_DATA_BOOTLOADER` | No | `false` | `true` para cargar automaticamente todos los datos al iniciar. Solo activar en el primer despliegue. |
| `PORT` | No | `80` | Puerto de nginx (solo en produccion). |

---

## Arquitectura

```
                     ┌─────────────┐
                     │  datos.gov.co│
                     │  (Socrata)   │
                     └──────┬──────┘
                            │ SODA API (httpx)
                     ┌──────▼──────┐
                     │     ETL     │
                     │   (Polars)  │
                     │  6 pipelines│
                     └──────┬──────┘
                            │ Bolt (neo4j driver)
                     ┌──────▼──────┐
                     │   Neo4j     │
                     │  5.26 LTS   │
                     │ 2.3M nodos  │
                     └──────┬──────┘
                            │ Bolt
     ┌──────────────────────▼──────────────────────┐
     │              FastAPI (API REST)              │
     │  /search  /contractor  /graph  /alertas ...  │
     └──────────────────────┬──────────────────────┘
                            │ HTTP (proxy)
     ┌──────────────────────▼──────────────────────┐
     │                    Nginx                     │
     │       /api/* → FastAPI  |  /* → React SPA    │
     └──────────────────────┬──────────────────────┘
                            │ :80
     ┌──────────────────────▼──────────────────────┐
     │              React + Sigma.js                │
     │     Busqueda, Grafos, Alertas, Perfiles      │
     └─────────────────────────────────────────────┘
```

### Servicios Docker

| Servicio | Imagen / Build | Puerto | Proposito |
|----------|---------------|--------|-----------|
| `neo4j` | `neo4j:5.26.24-community` | 7474, 7687 (dev) | Base de datos de grafos |
| `api` | Build `./api/Dockerfile` | 8000 (dev) | API REST (FastAPI + Uvicorn) |
| `etl` | Build `./etl/Dockerfile` | — | Cargador de datos (ejecuta una vez) |
| `nginx` | `nginx:1.27-alpine` (dev) / Build `./frontend/Dockerfile` (prod) | 80 | Proxy reverso + frontend estatico |

---

## Fuentes de datos

Toda la informacion proviene de bases de datos publicas colombianas accesibles bajo la [Ley 1712/2014 de Transparencia](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=56882).

| Fuente | Dataset ID | Registros | Nodos generados |
|--------|-----------|-----------|-----------------|
| SECOP Integrado | [`rpmr-utcd`](https://www.datos.gov.co/resource/rpmr-utcd.json) | ~1.6M | Contrato, Empresa, Persona, EntidadPublica |
| SECOP II Contratos | [`jbjy-vk9h`](https://www.datos.gov.co/resource/jbjy-vk9h.json) | (merge) | Complementa SECOP I |
| SIGEP Servidores | [`2jzx-383z`](https://www.datos.gov.co/resource/2jzx-383z.json) | ~80K | Persona, EntidadPublica (empleo publico) |
| SIRI Sanciones | [`iaeu-rcn6`](https://www.datos.gov.co/resource/iaeu-rcn6.json) | ~16K | Sancion, Persona |
| SECOP Multas | [`4n4q-k399`](https://www.datos.gov.co/resource/4n4q-k399.json) | ~1.7K | Sancion, Empresa, Persona |
| SECOP II Procesos | [`p6dx-8zbt`](https://www.datos.gov.co/resource/p6dx-8zbt.json) | ~8.4M | Proceso (oferentes, fechas, modalidad) |

Portal de datos abiertos: [datos.gov.co](https://www.datos.gov.co)

---

## ETL Pipeline

El pipeline ETL extrae, transforma y carga datos desde la API Socrata (SODA) hacia Neo4j.

### Ejecucion

```bash
# Carga individual (incremental por defecto)
python3 -m etl.run secop_integrado

# Carga completa (ignora estado previo)
python3 -m etl.run secop_integrado --full

# Deteccion de patrones (ejecutar despues de cargar datos)
python3 -m etl.pattern_detection.run_flags
```

### Caracteristicas

- **Incremental**: Solo procesa registros nuevos desde la ultima ejecucion (estado en `.etl_state/`)
- **Idempotente**: Usa `MERGE` en Neo4j — seguro para re-ejecutar sin duplicados
- **Resumible**: Si se interrumpe, retoma desde el ultimo batch procesado
- **Normalizacion**: NIT, cedulas y razones sociales normalizadas centralmente
- **Claves compuestas**: `contrato_id = numero + "_" + origen` para evitar colisiones SECOP I/II

### Schema de Neo4j

El schema se define en `infra/neo4j/schema.cypher` e incluye:

- **6 constraints de unicidad**: empresa_nit, persona_cedula, contrato_id, proceso_ref, sancion_id, entidad_codigo
- **5 indices de soporte**: nombre de empresa/persona, fecha de contrato, modalidad, nombre de entidad
- **1 indice fulltext**: busqueda por razon_social y nombre en Empresa, Persona, EntidadPublica

---

## API REST

**Base URL**: `http://localhost/api/v1`

La documentacion interactiva (Swagger) esta disponible en `http://localhost:8000/docs` durante desarrollo.

### Endpoints

| Metodo | Endpoint | Descripcion | Rate limit |
|--------|----------|-------------|------------|
| GET | `/health` | Estado del servicio + conectividad Neo4j | — |
| GET | `/search?q=texto&tipo=empresa&limit=20` | Busqueda fulltext de entidades | 60/min |
| GET | `/contractor/{id}` | Perfil completo (contratos, sanciones, relaciones) | 30/min |
| GET | `/contract/{id}` | Detalle de un contrato | 30/min |
| GET | `/graph/{id}?depth=2` | Subgrafo de N niveles alrededor de una entidad | 20/min |
| GET | `/graph/path?from_id=X&to_id=Y` | Camino mas corto entre dos entidades (max 6 saltos) | 20/min |
| GET | `/empresas?page=1&orden=contratos` | Listado paginado de empresas | 30/min |
| GET | `/sancionados?page=1` | Personas sancionadas con contratos activos | 30/min |
| GET | `/alertas/resumen` | Conteo de alertas por tipo de patron | 30/min |
| GET | `/alertas/{patron}?page=1` | Detalle de alertas de un patron especifico | 30/min |
| GET | `/meta/freshness` | Timestamp de ultima ingestion por fuente | — |

### Ejemplo de uso

```bash
# Buscar una empresa
curl "http://localhost/api/v1/search?q=servicios+postales&tipo=empresa"

# Ver perfil completo de un contratista por NIT
curl "http://localhost/api/v1/contractor/900062917"

# Explorar grafo de relaciones
curl "http://localhost/api/v1/graph/900062917?depth=2"

# Encontrar camino entre dos entidades
curl "http://localhost/api/v1/graph/path?from_id=6793361&to_id=892399999"
```

---

## Funcionalidades

### Landing page
Pagina de presentacion con estadisticas de la plataforma, descripcion de capacidades y acceso directo al explorador.

### Buscar (`/buscar`)
Busqueda fulltext de empresas, personas y entidades publicas por nombre, NIT o cedula.

### Empresas (`/empresas`)
Listado paginado de empresas contratistas ordenado por numero de contratos o nombre.

### Sancionados (`/sancionados`)
Personas con sanciones disciplinarias (SIRI/Procuraduria) que tambien tienen contratos publicos vigentes.

### Alertas (`/alertas`)
Dashboard de deteccion automatica de patrones sospechosos con conteos y listados por tipo.

### Perfil (`/perfil/:id`)
Pagina de perfil completa de un contratista:
- Grafica de timeline de contratos (montos por mes, coloreado por modalidad)
- Tabla de contratos detallada
- Sanciones y multas
- Entidades relacionadas
- Link al explorador de grafo

### Explorador de grafo (`/grafo/:id`)
Visualizacion WebGL (Sigma.js) del subgrafo de 2 niveles alrededor de cualquier entidad. Click en nodos para ver propiedades y navegar a perfiles.

### Buscar camino (`/camino`)
Encuentra la conexion mas corta entre dos entidades en el grafo (hasta 6 saltos).

**Ejemplos para probar:**

| Origen | Destino | Que muestra |
|--------|---------|-------------|
| `6793361` (Elber Guerra) | `892399999` (Gob. Cesar) | Persona sancionada → gobernacion via contrato |
| `254000001` (Gob. N. Santander) | `254099011` (Alc. Bochalema) | Entidades conectadas via persona sancionada |
| `900062917` (Servicios Postales) | `116001000` (Policia Nacional) | Empresa con concentracion directa |

---

## Deteccion de patrones

El sistema detecta automaticamente 5 patrones de riesgo en la contratacion publica:

| Patron | Descripcion | Severidad |
|--------|-------------|-----------|
| **Contratista Sancionado** | Personas/empresas con sanciones disciplinarias que tienen contratos activos | Peligro |
| **Concentracion Directa** | Empresa recibe >50% de adjudicaciones directas de una entidad | Peligro |
| **Contratista Recurrente** | Empresa con >100 contratos en una misma entidad | Advertencia |
| **Contrato Express** | Contratos >$500M COP con duracion <30 dias | Advertencia |
| **Red Amplia** | Persona contratando con >10 entidades publicas distintas | Advertencia |

Las alertas se generan ejecutando queries Cypher sobre el grafo completo (`etl/pattern_detection/queries/*.cypher`).

---

## Desarrollo local

### Backend (API)

```bash
cd api
pip install -r requirements.txt

# Variables de entorno necesarias
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=tu_password
export PUBLIC_MODE=true

# Iniciar servidor de desarrollo
uvicorn main:app --reload --port 8000

# Swagger UI disponible en http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
npm ci

# Iniciar servidor de desarrollo (proxy a API en localhost:8000)
npm run dev
# Abre http://localhost:5173

# Type check
npm run type-check

# Build de produccion
npm run build
```

### Estructura del proyecto

```
HunterLeech/
├── api/                        # Backend FastAPI
│   ├── main.py                 # Entry point
│   ├── config.py               # Configuracion (pydantic-settings)
│   ├── routers/                # Endpoints por recurso
│   ├── services/               # Logica de negocio (queries Neo4j)
│   ├── requirements.txt
│   └── Dockerfile
├── etl/                        # Pipeline de datos
│   ├── bootloader.py           # Cargador automatico
│   ├── run.py                  # CLI para carga manual
│   ├── pipelines/              # 6 pipelines (1 por fuente)
│   ├── loaders/                # Neo4j batch loader
│   ├── normalizers/            # Normalizacion de NIT, cedulas, etc.
│   ├── pattern_detection/      # Detector de patrones sospechosos
│   │   └── queries/            # Archivos .cypher por patron
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                   # React SPA
│   ├── src/
│   │   ├── pages/              # Paginas (Buscar, Empresas, Alertas, etc.)
│   │   ├── components/         # Componentes reutilizables
│   │   ├── hooks/              # Custom hooks (useSearch, useGraph, etc.)
│   │   ├── api/                # Cliente HTTP
│   │   ├── types/              # Interfaces TypeScript
│   │   ├── App.tsx             # Router
│   │   └── main.tsx            # Entry point
│   ├── nginx.conf              # Nginx dev config
│   ├── nginx.prod.conf         # Nginx produccion (+ security headers)
│   ├── package.json
│   ├── Dockerfile              # Multi-stage build (node → nginx)
│   └── vite.config.ts
├── infra/
│   └── neo4j/
│       └── schema.cypher       # Constraints e indices
├── docker-compose.yml          # Desarrollo local
├── docker-compose.prod.yml     # Produccion (Dokploy)
├── .env.example                # Variables de entorno (dev)
├── .env.prod.example           # Variables de entorno (produccion)
└── README.md
```

---

## Licencia

Open source. Datos de [datos.gov.co](https://www.datos.gov.co) bajo licencia [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

---

Inspirado en [br/acc](https://github.com/brunoclz/br-acc) (Brasil), adaptado al ecosistema de datos abiertos colombiano.
