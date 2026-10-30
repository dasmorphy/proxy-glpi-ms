# Lógica de negocio

Documento vivo con los flujos de negocio de la API. Cada sección describe un
flujo: qué lo dispara, qué tablas toca y qué reglas aplica. Al cambiar un flujo,
actualizar su sección; al agregar uno nuevo, añadirlo al índice.

Las referencias a código apuntan a funciones (no a números de línea, que
cambian). Salvo que se indique otra cosa, están en
`swagger_server/repository/internal_management_repository.py`.

## Índice

1. [Materiales pendientes de creación](#1-materiales-pendientes-de-creación)
2. [Documentos de la inspección](#2-documentos-de-la-inspección)
3. [Tipo de inspección (Soporte)](#3-tipo-de-inspección-soporte)

---

## 1. Materiales pendientes de creación

### Propósito

Los **productos nuevos** son productos que todavía no existen en el catálogo
(`technical.technical_equipment`). Pueden aparecer en dos momentos:

- **Registro técnico** (`/register-technical`): el técnico agrega un producto
  que no está en el catálogo. El pendiente se genera **al guardar el técnico**,
  para que logística pueda crearlo en el catálogo antes de que exista la
  proforma.
- **Proforma** (`/register-commercial`): el comercial agrega un producto nuevo a
  mano, como ítem suelto o como componente de **materiales varios**. El
  pendiente se genera **al aprobar** la gestión comercial.

Un producto nuevo del técnico puede cotizarse como ítem suelto o dentro de
materiales varios, pero en **una sola línea** de la proforma.

Con el pendiente, bodega puede entregar el producto aunque no esté en el
catálogo y darlo de alta después sin perder la trazabilidad de lo entregado.

### Tabla

`internal_management.pending_material` (modelo `PendingMaterial`,
`swagger_server/models/db/pending_material.py`)

| Campo | Descripción |
|---|---|
| `inspection_id` | Ticket (inspección) al que pertenece. Siempre presente |
| `material_tech_ticket_id` | Material del registro técnico que lo originó. **Único**. `NULL` si lo originó la proforma |
| `quote_id` | Proforma aprobada. `NULL` hasta que se aprueba: es lo que indica si el pendiente ya está **vinculado** |
| `quotation_item_id` / `additional_material_id` | Línea aprobada: un ítem o un componente de materiales varios (uno de los dos). Ambos **únicos** |
| `name_material`, `description`, `model`, `quantity`, `base_price`, `profit_margin`, `profit_margin_dollar` | Datos sugeridos. Vienen del técnico y se actualizan con los de la proforma al aprobarse |
| `status` | `Pendiente`, `Creado` o `Eliminado de proforma` |
| `material_id` | Producto creado en el catálogo; `NULL` mientras está pendiente |
| `created_at/by`, `resolved_at/by` | Auditoría |

`sale_quotation_item` y `sale_additional_materials` tienen
`material_tech_ticket_id`, que guarda de qué material del técnico proviene la
línea nueva. Es lo que permite vincular el pendiente en lugar de duplicarlo.
Los componentes además tienen `is_new`, `model` y `description` (un componente
nuevo no tiene `material_id`).

Las migraciones están al final de `scripts.sql` (secciones *PENDIENTES DESDE EL
REGISTRO TÉCNICO* y *PRODUCTOS NUEVOS EN MATERIALES VARIOS*).

### Estados

| Desde | Evento | Hacia |
|---|---|---|
| — | El técnico guarda un producto nuevo, o se aprueba una proforma con un producto nuevo agregado por el comercial | `Pendiente` |
| `Pendiente` | El comercial guarda la proforma sin ese producto del técnico | `Eliminado de proforma` |
| `Eliminado de proforma` | El comercial vuelve a incluirlo en la proforma | `Pendiente` |
| `Pendiente` | Logística lo crea en el catálogo (desde el modal de entrega o desde la lista de pendientes) | `Creado` |

- `Eliminado de proforma`: el comercial guardó la proforma sin ese producto del
  técnico. Es reversible: si lo vuelve a incluir, el pendiente regresa a
  `Pendiente`. No se puede crear en el catálogo en este estado.
- `Creado` es final.

### 1.1 Registro técnico

Función: `_save_technical_materials` (la usan `post_ticket_technical` y
`update_ticket_technical`).

- En la edición, los materiales que llegan con `id_material` **se actualizan**
  en lugar de recrearse, para conservar el vínculo con su pendiente. Los que no
  llegan se eliminan.
- `_sync_technical_pendings`: un pendiente por cada material con
  `material_id = NULL`. Usa `name_material = other` (o `material_description` si
  no hay `other`) y `description = material_description`.
  - Mientras el pendiente no esté en una proforma aprobada ni en el catálogo,
    sigue los cambios del técnico (nombre, descripción, cantidad).
  - Si el técnico cambia el producto nuevo por uno del catálogo, el pendiente
    se elimina.
- `_release_technical_pendings` (material quitado por el técnico): si el
  pendiente todavía no llegó a la proforma aprobada ni al catálogo, se elimina.
  Si ya llegó, se conserva y solo se desvincula del técnico.

### 1.2 Proforma

Función: `save_sale_quotation`.

- Los ítems y los componentes pueden enviar `material_tech_ticket_id`.
  `_validate_quotation_technical_materials` valida que pertenezca a la misma
  inspección y que no se repita en la proforma; si no, error 400.
- Un componente de materiales varios sin `material_id` debe ser un producto
  nuevo (`is_new` con descripción); si no, error 400
  (`_validate_quotation_quantities`).
- `_sync_quotation_pendings`: los pendientes del técnico que la proforma no
  incluye pasan a `Eliminado de proforma`, y los que vuelve a incluir regresan a
  `Pendiente`. Solo afecta a los pendientes sin vincular y que no están en
  `Creado`.

### 1.3 Aprobación de la gestión comercial

Función: `_generate_pending_materials(session, quote_id, user)`. Es
**idempotente**.

Se procesan las líneas nuevas de la proforma con `material_id IS NULL`: los
ítems con `is_new = True` (sin mano de obra) y los componentes de materiales
varios con `is_new = True`.

- Si la línea trae `material_tech_ticket_id` y ese pendiente está libre, **se
  vincula**: se le asignan `quote_id` y `quotation_item_id` o
  `additional_material_id`, se actualizan
  cantidad, modelo y precios con los de la proforma, y si estaba en
  `Eliminado de proforma` vuelve a `Pendiente`.
- Si no, se crea un pendiente nuevo con origen proforma.

| Disparador | Endpoint | Condición |
|---|---|---|
| `post_ticket_commercial` | `POST /register-commercial` | Viene `sale_quotation` y `status_id == 5` (Aprobada) |
| `update_ticket_commercial` | `PUT /register-commercial` | La gestión queda en Aprobada |
| `get_project_materials` | `GET /project-materials/{id_task}` | Respaldo para proformas aprobadas antes de existir los pendientes |
| `post_material_delivery` | `POST /material-delivery` | Mismo respaldo |

### 1.4 Entrega de un producto pendiente

En `post_material_delivery`, si el ítem o el componente de la proforma no tiene
`material_id`:

- Se busca su pendiente; si no existe, error 400.
- El detalle se guarda con `pending_material_id` y
  `material_id = pending.material_id`.
- Si el pendiente aún no se creó en el catálogo, **no se descuenta stock**.
  Si ya se creó (por ejemplo, desde el técnico antes de la proforma), se
  descuenta del producto creado.
- Siempre se valida que no se entregue más de lo aprobado en la proforma.

### 1.5 Resolución (alta en el catálogo)

Endpoint: `POST /pending-material/{id_pending_material}/resolve`
Función: `resolve_pending_material`

1. Bloquea el pendiente. Debe estar en `Pendiente`: si está en
   `Eliminado de proforma` o en `Creado`, error 400.
2. Valida el stock:
   - Con proforma aprobada (`quote_id` presente): stock ≥ cantidad de la
     proforma.
   - Sin proforma aprobada: stock ≥ 0.
3. Crea el `TechnicalEquipment` con `stock = stock ingresado − ya entregado`.
4. Enlaza las entregas previas al producto creado.
5. Si el pendiente viene del técnico:
   - Actualiza `material_tech_ticket.material_id`. Así, cuando el comercial arme
     la proforma, lo verá como producto del catálogo, con su precio.
   - Si la proforma todavía no está aprobada, los ítems y componentes que lo
     referencian pasan a `material_id = producto` y `is_new = False`.
6. Marca el pendiente como `Creado`.

### 1.6 Consulta

`GET /pending-material` (`get_pending_materials`) admite los filtros opcionales
`quote_id`, `inspection_id` y `status`. Usa *outer join* con la proforma porque
los pendientes del técnico pueden no tener una. Devuelve `origin` (`Técnico` o
`Proforma`), los datos del ticket (`inspection_code`, `title_ticket`,
`client_name`), `quote_number` y `additional_material_id`.

### Front (pw-tickets)

- `register-ticket-technical`: envía `id_material` al editar.
- `register-ticket-commercial`: conserva y envía `material_tech_ticket_id` en
  los ítems nuevos que vienen del técnico. El modal de materiales varios permite
  agregar "Material existente", "Producto nuevo" o uno "Del registro técnico";
  si este ya estaba como ítem suelto, al aplicar se mueve al grupo.
- `components/modals/pending-product-dialog`: diálogo reutilizable para crear el
  producto. Lo usan el modal de entrega de materiales y la página de pendientes.
- `pages/tables/pending-materials`: ruta `/productos-pendientes`, en el menú
  "Productos pendientes" (permiso `LOGISTICA`).

### Invariantes y riesgos

- Solo se puede editar una gestión comercial en estado Pendiente
  (`update_ticket_commercial`). Una vez aprobada, la proforma no cambia.
- `save_sale_quotation` **borra y recrea** los ítems y componentes de la
  proforma. No es un problema porque los pendientes solo se vinculan a sus
  líneas al aprobar, y una gestión aprobada ya no se edita.
- `checked_item` es opcional en `POST` y `PUT /register-commercial`. Si un ítem
  no lo envía, `save_sale_quotation` conserva el valor anterior buscando la línea
  por `material_id`, luego por `material_tech_ticket_id` y por último por
  `item_number` (mano de obra, materiales varios y productos nuevos a mano); sin
  coincidencia queda en `false`. Si se reordenan esas últimas líneas, el valor
  puede quedar en otra línea, y dos líneas con el mismo `material_id` comparten
  el mismo valor anterior.
- El técnico debe enviar `id_material` al editar. Si no lo envía, sus
  materiales se recrean y los pendientes sin vincular se eliminan y se vuelven
  a generar.

### Tests

`swagger_server/test/test_material_delivery.py`, clases
`TestMaterialDeliveryRepository`, `TestTechnicalPendingMaterials` y
`TestBundleNewProducts`.

---

## 2. Documentos de la inspección

### Propósito

Los archivos adjuntos se guardan **por inspección** (no por gestión), en
`internal_management.inspection_documents`, y se ven juntos en el detalle del
ticket.

### Cómo se reciben

| Endpoint | Formato | Comportamiento |
|---|---|---|
| `POST /inspection`, `POST /register-technical`, `POST /register-commercial`, `POST /register-financial` | `multipart/form-data` (`data` en JSON como texto + `files`) | Guarda la gestión y sus documentos |
| `PUT /register-technical`, `PUT /register-commercial`, `PUT /register-financial` | `application/json` o `multipart/form-data` (mismos campos) | Actualiza la gestión y **agrega** los documentos recibidos; los existentes no se modifican ni eliminan |

- En el controlador, el POST usa `_post_with_documents` y el PUT usa
  `_update_ticket_management`. Los dos leen el multipart con
  `_parse_multipart_request`.
- En Connexion 2, `application/json` debe declararse **primero** en el
  `requestBody` de los PUT. Si no, las peticiones JSON fallan.
- `validate_documents` rechaza las extensiones no permitidas (400) antes de
  escribir nada.
- `_save_inspection_documents` escribe los archivos dentro de la misma
  transacción. Si la transacción falla, `remove_documents` borra los archivos
  ya escritos.

### Front (pw-tickets)

`glpi.service.ts`: `save*` y `updateTicket*` envían `buildMultipart(data, files)`.
Los formularios técnico, comercial y financiero muestran `app-document-upload`
también al editar.

### Tests

`swagger_server/test/test_financial_update.py`, clase `TestUpdateTicketDocuments`.

---

## 3. Tipo de inspección (Soporte)

### Propósito

`inspection_technical.type` distingue una **Inspección** (flujo completo:
Técnica → Comercial → Proyectos → Financiera) de un **Soporte**, que solo se
registra en `inspection_technical` y no continúa a las siguientes áreas.
Valores: `Inspección` | `Soporte`. `NULL` (inspecciones antiguas) se trata
como Inspección; por eso los filtros usan `_not_support()`
(`type IS DISTINCT FROM 'Soporte'`) y no `type != 'Soporte'`, que descartaría
los `NULL`.

### Reglas

- `post_inspection_technical`: `type` se valida con `_inspection_type`
  (vacío → Inspección; otro valor → 400). Un Soporte queda en
  `management_area = 'Técnica'` con `next_area = NULL`, aunque llegue con
  estado "Listo para cotizar" (el estado se guarda, el área no cambia).
- Un Soporte usa `start_date` y `end_date` en lugar de `commitment_date`:
  ambas obligatorias y `end_date >= start_date` (`_validate_support_dates`,
  en POST y PUT, sobre el registro resultante). Las fechas ISO con zona se
  guardan en UTC sin zona (`_parse_datetime`), igual que `commitment_date`
  al editar.
- `update_inspection_technical`: acepta `type`. "Listo para cotizar" no mueve
  un Soporte a Comercial. Pasar a Soporte da 400 si la inspección ya avanzó
  (`_inspection_started_flow`: salió de Técnica o tiene registro técnico o
  comercial). Pasar de Soporte a Inspección se permite y restaura
  `next_area = 'Comercial'`.
- `post_ticket_technical` y `post_ticket_commercial` rechazan un Soporte con
  400 (`_ensure_not_support`).
- `GET /inspection`: `pending_technical=true` y `pending_commercial=true`
  excluyen Soporte (también `pending_commercial` de `GET /register-technical`).
  Filtro opcional `type=Inspección|Soporte`.
- Dashboard: `_dashboard_inspection_conditions` (fechas + `_not_support()`) lo
  usan `get_dashboard_counts` y `get_dashboard_area_times`, así que los
  Soportes no cuentan en pendientes, finalizados, cotizaciones, facturas, SLA
  ni tiempos por área.

### Front (pw-tickets)

`inspection-form`: dropdown "Tipo" (`Inspección` por defecto). Al editar se carga el
`type` guardado; si no, el formulario reenviaría `Inspección` y convertiría un Soporte.
Con Soporte se ocultan "Fecha compromiso" y se muestran "Fecha inicio" y "Fecha fin"
(obligatorias); al guardar se envía en `null` la fecha que no corresponde al tipo.

### Tests

`swagger_server/test/test_inspection_type.py`.
