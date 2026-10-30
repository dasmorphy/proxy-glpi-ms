# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# proxy-glpi-ms

API Flask/Connexion (`swagger_server/`) definida en `swagger_server/swagger/swagger.yaml`.

## Lógica de negocio

Los flujos de negocio (qué los dispara, qué tablas tocan, reglas) están en
`docs/logica-negocio.md`. Leerlo antes de modificar un flujo y actualizar su
sección en el mismo cambio.

`AGENTS.md` repite estas instrucciones para otros agentes; mantenerlos alineados.

## Comandos

Hay un virtualenv en `venv/` (Windows: `venv/Scripts/python.exe`).

```bash
pip install -r requirements.txt
python -m swagger_server                     # dev, puerto 2127
# UI: http://localhost:2127/rest/proxy-glpi-api/v1.0/ui/
docker compose up --build                    # prod: gunicorn swagger_server.__main__:app

# Tests (unittest, no hay pytest ni tox.ini aunque el README mencione tox)
python -m unittest discover -s swagger_server/test -t .
python -m unittest swagger_server.test.test_material_delivery.TestTechnicalPendingMaterials
python -m unittest swagger_server.test.test_material_delivery.TestTechnicalPendingMaterials.<test_name>
```

No hay linter configurado. Algunos tests fallan hoy (p. ej. `test_internal_management`,
`test_inspection_documents`); varios porque `config/access.py` hace `.strip()` sobre
`TELEARSEG_PASSWORD`/`ZENTINEL_PASSWORD` y revienta si no están en `.env`.

## Configuración

`swagger_server/config/access.py` es la única fuente de configuración (lee `.env`
con python-dotenv). Variables reales: `TELEARSEG_*` y `ZENTINEL_*` (USER, PASSWORD,
HOST, PORT, DB), `REDIS_HOST/PORT`, `API_GLPI`, `APP_TOKEN`, `USER_TOKEN_SESSION`,
`GLPI_TIMEOUT`, `INSPECTION_DOCUMENTS_PATH`. `.env.example` está desactualizado
(usa `POSTGRESQL_*`).

## Arquitectura

Capas: **swagger.yaml → controller → use case → repository → modelos SQLAlchemy**.

- **Ruteo**: cada operación del YAML usa `x-openapi-router-controller:
  swagger_server.controllers.glpi_proxy_controller.GlpiProxyView` y un
  `operationId` que es el nombre del método en esa `MethodView`. Agregar un
  endpoint = path en `swagger.yaml` + método en `GlpiProxyView` con el mismo nombre.
  Base path: `/rest/proxy-glpi-api/v1.0`.
- **Dos dominios en un mismo controller**:
  - Proxy GLPI (`/glpi-by-pass`, `/generate-document-glpi`): `ProxyUseCase`
    reenvía a `API_GLPI/<endpoint>` (el query param `endpoint` no se reenvía),
    reemplaza `App-Token`/`Session-Token` con el token de sesión cacheado en Redis
    (`ProxyRepository`, clave `glpi:session-token`) y ante token ausente o 401 hace
    `initSession` y reintenta una vez.
  - Gestión interna (inspecciones, registros técnico/comercial/financiero,
    proformas, materiales, entregas, dashboard): `InternalManagementUseCase` es
    casi un passthrough; la lógica y las transacciones viven en
    `repository/internal_management_repository.py`.
- **BD**: `resources/databases/postgresql.py` crea un engine por base (`"TELEARSEG"`,
  `"ZENTINEL"`); el repositorio abre sesiones con
  `self.db_telearseg.session_factory()` y hace `session.commit()` explícito.
  Los modelos ORM están en `swagger_server/models/db/` (schemas Postgres
  `internal_management` y `technical`); el resto de `swagger_server/models/` son
  modelos generados por swagger-codegen para las respuestas. `scripts.sql` tiene
  el DDL de referencia de las tablas.
- **Respuestas y errores**: los controllers devuelven un dict con `error_code`,
  `message`, `data`, `internal_transaction_id`, `external_transaction_id`. Los
  errores esperados se lanzan como `CustomAPIException(message, status_code)` y
  se convierten con `CustomAPIException.check_exception`. `__main__.py` registra
  un handler global para errores de Connexion/validación.
- **Contexto/log**: `controllers/__init__.py` (before/after request) guarda en `g`
  los headers `X-Channel`, `X-System`, `X-External-Transaction-Id` y genera el id
  interno; loguru recibe `internal=`/`external=` en cada log.
- **Archivos**: endpoints multipart (`data` JSON en texto + `files`) se parsean en
  `GlpiProxyView._parse_multipart_request`; los documentos se guardan en
  `INSPECTION_DOCUMENTS_PATH` (`utils/inspection_documents.py`). Los PDFs de
  proforma se generan con reportlab en `utils/proforma_pdf.py`.

## Tests

Los use cases y repositorios aceptan dependencias inyectadas
(`ProxyUseCase(repository, http_client, settings)`,
`InternalManagementUseCase(repository)`). Los tests de repositorio usan SQLite en
memoria adjuntando los schemas `internal_management` y `technical` y construyen el
repositorio con `InternalManagementRepository.__new__` + `db_telearseg` falso; ver
`sqlite_repository()` en `swagger_server/test/test_material_delivery.py`.
