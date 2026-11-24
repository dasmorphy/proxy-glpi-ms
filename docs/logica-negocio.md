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
3. [Tipo de inspección (Soporte / Asistencia)](#3-tipo-de-inspección-soporte--asistencia)
4. [Registro de proveedores](#4-registro-de-proveedores)
5. [Devolver un registro a Comercial](#5-devolver-un-registro-a-comercial)
6. [Devolver un registro a Técnica](#6-devolver-un-registro-a-técnica)
7. [Documentos de la proforma (PDF / Excel)](#7-documentos-de-la-proforma-pdf--excel)

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
| `Pendiente` | Al editar una proforma ya aprobada, el comercial quita un producto nuevo que agregó él | `Eliminado de proforma` (y se desvincula de la proforma) |
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
- La **Asistencia** no pasa por esta entrega: al aprobarse la proforma se
  registra una entrega automática con el mismo modelo (`task_id` y
  `delivered_to` en `NULL`). Sus productos nuevos quedan igual, con su
  pendiente y sin descontar stock (sección 3).

### 1.5 Resolución (alta en el catálogo)

Endpoint: `POST /pending-material/{id_pending_material}/resolve`
Función: `resolve_pending_material`

Hay dos modos:
- **Crear producto** (sin `material_id`): crea un `TechnicalEquipment` nuevo.
- **Usar producto existente** (con `material_id`): vincula el pendiente a ese
  producto del catálogo, sin crear otro. Sirve cuando varios pendientes de
  distintas inspecciones o proformas son el mismo producto: el primero se crea
  y los demás se vinculan a él. Los datos del producto (nombre, precio,
  proveedor) no cambian; `stock` son las unidades recibidas y se suman al
  stock actual.

No se resuelven otros pendientes automáticamente por nombre: cada uno conserva
su línea de proforma, su material técnico, su cantidad y sus entregas, y una
persona elige qué producto le corresponde.

1. Bloquea el pendiente. Debe estar en `Pendiente`: si está en
   `Eliminado de proforma` o en `Creado`, error 400. Con `material_id`, también
   bloquea el producto; si no existe, error 404.
2. Valida el stock:
   - Con proforma aprobada (`quote_id` presente): stock ≥ cantidad de la
     proforma. Con un producto existente, se compara stock actual + recibido.
   - Sin proforma aprobada: stock ≥ 0.
3. Producto nuevo: `stock = stock ingresado − ya entregado`. Producto
   existente: `stock = stock actual + recibido − ya entregado`.
4. Enlaza las entregas previas al producto.
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
  si este ya estaba como ítem suelto, al aplicar se mueve al grupo. Los ítems de
  la proforma tienen el mismo selector "Del registro técnico", con los productos
  del técnico que todavía no están en ninguna línea (ni como ítem ni en
  materiales varios). Así, si se quitó el ítem o se edita una proforma guardada,
  se puede volver a vincular al pendiente del técnico en lugar de crear un
  "Producto nuevo" suelto que al aprobar generaría otro pendiente.
- `register-ticket-commercial`, al editar una proforma guardada
  (`mergeTechnicalMaterials`): agrega como líneas los materiales del técnico
  creados **después del último guardado de la proforma**
  (`created_at` de `/inspection-materials` > `sale_quotation.updated_at` de
  `GET /register-commercial`) que no están en ella. Los del catálogo se agregan
  con sus precios y los nuevos con `material_tech_ticket_id` y sin precio. Se
  identifican por `material_tech_ticket_id` (nuevos) o `material_id` (catálogo,
  como ítem o en materiales varios). Los anteriores al guardado no se agregan,
  porque Comercial pudo excluirlos a propósito. Además, avisa sin tocar la
  proforma cuando el técnico quitó un producto nuevo o cuando la cantidad
  difiere (catálogo: solo si hay una única línea de ese producto).
- `components/modals/pending-product-dialog`: diálogo reutilizable para crear el
  producto o, con "Usar producto existente", vincularlo a uno del catálogo
  (`tech-materials` del servicio técnico). Las opciones del catálogo se ordenan
  poniendo primero las que comparten palabras con el nombre o modelo del
  pendiente. Lo usan el modal de entrega de materiales y la página de pendientes.
- `pages/tables/pending-materials`: ruta `/productos-pendientes`, en el menú
  "Productos pendientes" (permiso `LOGISTICA`).

### Invariantes y riesgos

- Solo se puede editar una gestión comercial en estado Pendiente
  (`update_ticket_commercial`). Una vez aprobada, la proforma no cambia.
- `save_sale_quotation` **borra y recrea** los ítems y componentes de la
  proforma. Desde el commit `71dba1e`, una gestión ya aprobada se puede editar
  (por ejemplo, cuando se devuelve a Comercial), y sus pendientes ya están
  vinculados a las líneas. Por eso, antes de borrarlas,
  `_unlink_quotation_pendings` desvincula los pendientes de la proforma, y
  después `_relink_quotation_pendings` vuelve a vincular cada uno a la línea
  recreada con la misma clave (`_pending_line_key`): el material del técnico o,
  si no tiene, descripción + modelo. No se usa `item_number`, para que reordenar
  no los cruce. El pendiente toma la cantidad y los precios de la nueva línea.
  Si no hay coincidencia, queda con `quote_id = NULL` y, si estaba `Pendiente`,
  pasa a `Eliminado de proforma` (`Creado` no cambia). Si alguna línea ya tiene
  entregas (`material_delivery_detail`), se responde 400: el detalle de la
  entrega referencia la línea y no se puede recrear.
- `checked_item` es opcional en `POST` y `PUT /register-commercial`. Si un ítem
  no lo envía, `save_sale_quotation` conserva el valor anterior buscando la línea
  por `material_id`, luego por `material_tech_ticket_id` y por último por
  `item_number` (mano de obra, materiales varios y productos nuevos a mano); sin
  coincidencia queda en `false`. Si se reordenan esas últimas líneas, el valor
  puede quedar en otra línea, y dos líneas con el mismo `material_id` comparten
  el mismo valor anterior.
- Al devolver la proforma (`sale_quotation.items` en `GET /register-commercial`),
  los ítems con `is_labor = true` van al final; el resto mantiene el orden que
  trae la consulta. Solo cambia la respuesta: `item_number` y la BD no se tocan.
- El técnico debe enviar `id_material` al editar. Si no lo envía, sus
  materiales se recrean y los pendientes sin vincular se eliminan y se vuelven
  a generar.

### Tests

`swagger_server/test/test_material_delivery.py`, clases
`TestMaterialDeliveryRepository`, `TestTechnicalPendingMaterials`,
`TestBundleNewProducts` y `TestEditApprovedQuotation`.

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

## 3. Tipo de inspección (Soporte / Asistencia)

### Propósito

`inspection_technical.type` distingue:

- **Inspección**: flujo completo Técnica → Comercial → Proyectos → Financiera.
- **Asistencia**: Técnica → Comercial → **Financiera** (sin Proyectos). En
  Técnica y Comercial sigue el flujo de la Inspección (registro técnico con
  materiales, aprobación técnica, proforma). Usa fecha inicio y fin, en el front
  se aprueba desde la bandeja "Soportes / Asistencias", y al aprobarse su
  gestión comercial pasa directo a Financiera descontando el stock (ver
  "Aprobación comercial de la Asistencia").
- **Soporte**: solo se registra en `inspection_technical` y no continúa a las
  siguientes áreas.

`NULL` (inspecciones antiguas) se trata como Inspección; por eso `_in_flow()` usa
`type IS DISTINCT FROM 'Soporte'` y no `type != 'Soporte'`, que descartaría los
`NULL`. `SUPPORT_TYPES` (Soporte y Asistencia) solo se usa para las fechas.

### Reglas

- `post_inspection_technical`: `type` se valida con `_inspection_type`
  (vacío → Inspección; otro valor → 400). Un Soporte queda en
  `management_area = 'Técnica'` con `next_area = NULL`, aunque llegue con
  estado "Listo para cotizar" (el estado se guarda, el área no cambia). La
  Asistencia toma las áreas igual que una Inspección.
- Soporte y Asistencia usan `start_date` y `end_date` en lugar de
  `commitment_date`: ambas obligatorias y `end_date >= start_date`
  (`_validate_support_dates`, en POST y PUT, sobre el registro resultante). Las
  fechas ISO con zona se guardan en UTC sin zona (`_parse_datetime`), igual que
  `commitment_date` al editar.
- `update_inspection_technical`: acepta `type`. "Listo para cotizar" no mueve
  un Soporte a Comercial. Pasar a Soporte da 400 si la inspección ya avanzó
  (`_inspection_started_flow`: salió de Técnica o tiene registro técnico o
  comercial) y deja `approve_support = false`, `next_area = NULL`. Pasar de
  Soporte a Inspección/Asistencia estando en Técnica restaura
  `next_area = 'Comercial'` y `approve_support = false`.
- `post_ticket_technical`, `post_ticket_commercial` y
  `approve_technical_inspection` rechazan un Soporte con 400
  (`_ensure_not_support`). La Asistencia los acepta.
- Aprobación:
  - Soporte: `POST /approve-support` → `approve_support = true`; se queda en
    Técnica. Una Asistencia ahí responde 400.
  - Asistencia: `approve_technical_inspection` (igual que una Inspección: registro
    técnico `Aprobado`, inspección "Listo para cotizar" → Comercial) y además
    `approve_support = true`, para que el front la muestre aprobada.
- **Asistencias antiguas**: antes se aprobaban con `/approve-support` y pasaban a
  Comercial sin registro técnico. Siguen en su área;
  `_legacy_approved_assistance()` (Asistencia con `approve_support = true`) las
  excluye de `pending_technical` cuando no tienen registro técnico.
- `GET /register-technical`:
  - `type` (uno o varios, `_type_condition`).
  - `responsible` (lo envía el front para el rol técnico): `responsible_id =
    responsible` y las **Asistencias solo salen si `management_status` no es
    `Completado`** (incluye `NULL`). Las Inspecciones no se filtran por
    `management_status`. Sin `responsible` (otros roles) sale todo.
  - `pending_commercial` excluye el Soporte.
- `GET /inspection`: `pending_technical=true` y `pending_commercial=true`
  excluyen el Soporte (`_in_flow()`). Filtro opcional
  `type=Inspección|Soporte|Asistencia`; `pending_approve_support=true` →
  `approve_support` no es `true` (el front lo usa solo con `type=Soporte`). Con
  `responsible_id` o `responsible` (consulta de un técnico) se aplica la misma regla
  que en `/register-technical`: las Asistencias en `management_status = 'Completado'`
  no salen (`_not_completed_assistance()`).
- Dashboard: `_dashboard_inspection_conditions` (fechas + `_in_flow()`) lo
  usan `get_dashboard_counts` y `get_dashboard_area_times`, así que los
  Soportes no cuentan en pendientes, finalizados, cotizaciones, facturas, SLA
  ni tiempos por área. Las Asistencias cuentan como una Inspección.
- Dashboard `pending_technical` y `GET /inspection?pending_technical=true`: en el
  flujo y sin registro técnico (salvo Asistencias antiguas aprobadas) **o** con
  el registro técnico en `Devuelto` (sección 6).
- Dashboard `pending_commercial`: mismo conteo que
  `GET /inspection?pending_commercial=true` (en el flujo, `status = 'Listo para
  cotizar'` y sin registro comercial). Las que siguen en Técnica no cuentan.

### Personal técnico y registros técnicos

Un Soporte o una Asistencia tiene su propio **personal técnico**, como un
proyecto. Una Inspección lo asigna al crear el proyecto.

- Tabla `internal_management.inspection_technical_assignments`
  (`InspectionTechnicalAssignment`): `inspection_id` + `user_id`
  (`public.users.id_user`, sin FK porque `public.users` es una tabla foránea; la
  existencia la valida la API), única por par. Equivale a
  `technical.task_technical_assignments`.
- `assigned_technicians` (lista de `id_user`), en `data`:
  - `POST /inspection`: obligatoria con al menos uno para Soporte y Asistencia
    (`_save_technicians`); se ignora en una Inspección. Se quitan los repetidos.
  - `PUT /inspection/{id}`: si llega, **reemplaza** la guardada (vacía → 400); si
    no llega, se conserva. Así los Soportes / Asistencias anteriores a este cambio
    (sin personal) se siguen editando. Al pasar a Inspección se elimina.
  - Un id que no es UUID o no existe en `public.users` → 400.
- `technical.technical_record.inspection_id` (nullable): registro técnico hecho
  sobre un Soporte / Asistencia con el **flujo anterior** (technical-control-ms).
  Los de proyecto lo dejan en `NULL`. Solo se lee: los registros nuevos van a
  `/register-technical` (ver "Registros técnicos de campo").
- `GET /inspection` y `GET /register-technical` (`_support_staff`) devuelven en
  cada Soporte / Asistencia:
  - `assigned_technicians`: `[{id_user, user, fullname}]`.
  - `record_technical`: los registros de los dos flujos, más recientes primero.
    `source` indica el origen:
    - `technical_record` (anterior): `id_record`, `resume`, `vehicle`, `status`,
      `created_by`, `created_at`, … e `images` (rutas de
      `technical.tech_record_image`, modelo de solo lectura `TechRecordImage`).
    - `register_technical` (nuevo, `_add_field_records`): `id_management_technical`,
      `code_management`, `resume` (= `description`), `vehicle`, `status`
      (= `record_status`), `approval_status` (= `status` del flujo),
      `technical_staff`, `materials` e `images` (rutas de `inspection_documents`
      del registro; se sirven desde `TECHNICAL_BASE_URL`).

### Registros técnicos de campo (app)

Los técnicos registran su trabajo en un Soporte / Asistencia desde la app con
`POST /register-technical` y `field_record = true`. Conviven en
`internal_management.technical_ticket_management` con la gestión técnica de la
web y se distinguen por `is_field_record`:

| | Gestión técnica (web) | Registro de campo (app) |
|---|---|---|
| `is_field_record` | `false` | `true` |
| Por caso | Una (409 si ya existe) | Varias |
| Tipos | Inspección y Asistencia (Soporte → 400) | Soporte y Asistencia (Inspección → 400) |
| `vehicle`, `record_status` | `NULL` | Del registro (`record_status`: `Completado` / `Incompleto`) |
| Personal | — | `technical.tech_staff_record` (`inspection_id` + `management_technical_id`) |
| Imágenes / documentos | `inspection_documents` (`management_technical_id NULL`) | `inspection_documents` con su `management_technical_id` |

- Se quitó el `UNIQUE (inspection_id)` de `technical_ticket_management`; la regla
  "una gestión por inspección" la valida la API solo para `is_field_record = false`.
- Bloqueos (`_ensure_field_record_allowed`, en el POST y el PUT): 400 si el caso
  tiene `approve_support = true` o si `management_area` no es `NULL` ni `Técnica`
  (el Soporte nunca sale de Técnica).
- `technical_staff` (lista de `id_user`) se guarda **solo si llega**; en el PUT,
  si llega reemplaza el personal del registro. Un id que no es UUID → 400.
- `PUT /register-technical`: con `id_management_technical` de un registro de campo
  actualiza `description`, `vehicle`, `record_status`, `materials`,
  `technical_staff` y agrega sus imágenes, sin tocar el flujo. **Sin**
  `id_management_technical` se edita la gestión de la web, nunca un registro de campo.
- Todas las consultas del flujo usan solo la gestión (`is_field_record = false`):
  `GET /register-technical`, el join de `GET /inspection` (`technical_id`,
  `description_technical`, `pending_technical`), contadores del dashboard,
  `_inspection_started_flow`, devolver a Técnica y los materiales de la proforma
  (`get_inspection_materials` y su validación). Los materiales de los registros
  de campo **no** pasan a la proforma.
- Aprobación (`_approve_technical_records`): `approve-support` (Soporte) y
  `approve-technical-inspection` (Asistencia) marcan `Aprobado` la gestión y todos
  los registros de campo del caso. La Asistencia se puede aprobar aunque no tenga
  gestión ni registros; la Inspección sigue exigiendo su gestión (404).
- Registros recientes del técnico: technical-control-ms (`GET /technical_record`)
  une `technical_record` y los registros de campo (`source`).

  En una Inspección ambos son `[]`. El filtro del técnico (`responsible` /
  `responsible_id`) **no** cambia: sigue siendo el responsable, no el personal
  técnico.
- `GET /inspection?technical=<id_user>` (UUID; otro valor → 400): registros
  donde ese usuario es el responsable (`responsible_id`) **o** está en el
  personal técnico (`inspection_technical_assignments`), vía
  `_technical_condition`. Se combina con los demás filtros (p. ej. `type`). No
  aplica la regla de Asistencias completadas de `responsible` / `responsible_id`.

### Aprobación comercial de la Asistencia

Cuando la gestión comercial de una Asistencia pasa a Aprobada (`status_id = 5`):
en `post_ticket_commercial`, o en `update_ticket_commercial` estando en Comercial.
Todo va en la misma transacción que la aprobación:

1. `_move_on_commercial_approval`: `management_area = next_area = 'Financiera'` e
   historial `Comercial → Financiera` (una Inspección va a Proyectos, como siempre).
   Así sale en `GET /register-commercial?pending_financial=true` y en el contador
   `pending_financial` del dashboard sin cambiar esas consultas.
2. `_generate_pending_materials` (sección 1.3).
3. `_discount_assistance_materials`: entrega automática en
   `material_delivery_history` con `task_id = NULL`, `delivered_to = NULL`,
   `created_by` = usuario que guarda la proforma y `observation = 'Descuento
   automático por asistencia'`. Un detalle por línea con la **cantidad de la
   proforma aprobada**:
   - Entran los ítems de material y los componentes de materiales varios; no la
     mano de obra (`is_labor`) ni la línea agrupadora (`is_bundle`).
   - Producto del catálogo: se descuenta su stock (`SELECT … FOR UPDATE` de todos
     los productos en una consulta). Si un producto se repite en varias líneas se
     valida la suma. Si no alcanza: 400 `Stock insuficiente de "<producto>":
     disponible X, requerido Y` y no se guarda nada (ni la aprobación).
   - Producto nuevo: el detalle va con su pendiente y no descuenta. Al crearlo,
     `resolve_pending_material` resta lo entregado, así que su stock inicial ya
     descuenta lo usado en la Asistencia (sección 1.5).
   - Proforma sin materiales: no se crea entrega.

Antes de aprobar nunca se descuenta (guardar la proforma en Pendiente no toca el
stock). Después de aprobada:

- `_assistance_sent_to_financial` (Asistencia con historial `Comercial →
  Financiera`): `POST /register-commercial`, y `PUT` con `sale_quotation` o con
  un `status_id` distinto de 5, responden 400. El `PUT` de otros campos
  (observaciones, etc.) sí se permite.
- No se puede devolver a Comercial desde Financiera (sección 5).
- `approve-ticket-commercial` (Proyectos → Financiera) responde 400.
- `ready_for_project` es `false` (flag de `GET /inspection` y filtro
  `ready_for_project=true`): no se crea proyecto.
- Estas entregas no salen en las consultas de entregas por proyecto (logística
  no las ve). `finished_projects` del dashboard no las cuenta (exige
  `Proyectos → Financiera`) y en tiempos por área no hay tramo de Proyectos.

**Asistencias antiguas** aprobadas antes de este cambio (en Proyectos): siguen el
flujo anterior (proyecto, entregas, `approve-ticket-commercial`) y no descuentan
stock al aprobarse. La migración de `scripts.sql` deja `task_id` y `delivered_to`
de `material_delivery_history` como nullable.

### Front (pw-tickets)

- `inspection-form`: dropdown "Tipo" (`Inspección` por defecto). Al editar se carga
  el `type` guardado; si no, el formulario reenviaría `Inspección` y convertiría un
  Soporte. Con Soporte o Asistencia se ocultan "Fecha compromiso" y se muestran
  "Fecha inicio" y "Fecha fin" (obligatorias); al guardar se envía en `null` la
  fecha que no corresponde al tipo. Con Soporte o Asistencia también muestra el
  multiselect obligatorio "Personal técnico" (`assigned_technicians`); con una
  Inspección se envía `[]`. Al editar se carga desde `assigned_technicians`.
- `components/support-records`: contenido de la fila expandida de un Soporte /
  Asistencia (chips del personal técnico + tabla de `record_technical`, como en
  Proyectos técnicos) con las mismas acciones: ver detalle (modal con imágenes),
  descargar el PDF y eliminar (permiso `ELIMINAR_REGISTRO_TECNICO`). El PDF y el
  borrado usan los endpoints de technical-control-api por `id_record`
  (`/technical_record/pdf`, `DELETE /technical_record/{id}`), que no requieren
  proyecto; al eliminar emite `recordDeleted` y la página vuelve a consultar. Lo usan `inspections-technical` en la ruta
  `/soportes-asistencias` (columna para expandir y "N. registros"; `dataKey` es
  `id_inspection`) y la pestaña Soportes / Asistencias de `inspections-approval`.
- `tickets-technical`: la Asistencia aparece en pendientes para "Registro" (formulario
  de materiales). El técnico consulta `/register-technical` con `responsible`.
- `inspections-approval` ("Por aprobar"):
  - Pestaña Inspecciones: `/register-technical` con `type=Inspección`.
  - Pestaña Soportes / Asistencias: Soportes y Asistencias de `/inspection`
    (`type=Soporte&type=Asistencia&pending_approve_support=true`), con o sin
    registros técnicos.
  - Asistencia: "Editar" abre `/registro-inspeccion-tecnica/:id` (materiales) y
    "Aprobar" usa `approve-technical-inspection`. Soporte: "Editar" abre el
    formulario de la inspección y "Aprobar" usa `approve-support`.

### Tests

`swagger_server/test/test_inspection_type.py` (personal técnico:
`TestSupportTechnicians`), `swagger_server/test/test_field_record.py` (registros
de campo) y `swagger_server/test/test_assistance_financial.py`
(aprobación comercial).

---

## 4. Registro de proveedores

### Propósito

Alta de proveedores en `internal_management.providers_products`. El listado
(`GET /providers`, `get_providers`) se usa como catálogo.

### Reglas

`POST /providers` (`post_provider`). Body: `{"data": {...}, "channel", "externalTransactionId"}`.

- Solo `provider` es obligatorio; vacío o solo espacios responde 400.
- `ruc`, `address`, `seller`, `number_contact`, `email` y `status` son opcionales.
  Los textos se recortan y los vacíos se guardan como `NULL`. `status` no tiene
  valor por defecto.
- `data.user` se guarda en `created_by`; `created_at` lo pone la BD.
- No valida duplicados (mismo `ruc` o nombre).
- Responde `data.id_provider` con el id creado.

### Tests

`swagger_server/test/test_providers.py`.

---

## 5. Devolver un registro a Comercial

### Propósito

Un registro aprobado (gestión comercial con `status_id = 5`) que ya está en
Proyectos o Financiera vuelve a Comercial para que se edite la proforma. Antes
se hacía con cambios manuales en la base.

### Disparador

`POST /return-to-commercial` (`return_to_commercial`). Body:
`{"data": {"inspection_id", "reason", "user"}, "channel", "externalTransactionId"}`.

### Validaciones (en orden)

| Regla | Respuesta |
|---|---|
| `inspection_id` entero, `reason` con texto (use case) | 400 |
| La inspección existe | 404 `Inspección no encontrada` |
| `management_area` en `Proyectos` o `Financiera` | 400 (`ya está en Comercial` / `Solo se pueden devolver registros de Proyectos o Financiera`) |
| `status` de la inspección distinto de `Finalizado` | 400 |
| No es una Asistencia en Financiera | 400 `Las asistencias no se pueden devolver a Comercial` (ya descontaron stock; sección 3) |
| Última gestión comercial existe y está aprobada (5) | 404 / 400 |
| Ninguna proforma de la inspección tiene entregas (`material_delivery_history`) | 400: el detalle de la entrega referencia las líneas, que no se podrían recrear al editar |
| No hay gestiones financieras (`Cobrada` tiene su propio mensaje) | 400: hay que eliminarlas antes |

### Efectos (una transacción)

- Gestión comercial → `status_id = 7` (Pendiente), `updated_by = user`.
- Inspección → `management_area = 'Comercial'`, `next_area = 'Proyectos'`.
- `history_area_ticket`: `previous_area` (Proyectos/Financiera) → `Comercial`, con
  el motivo en `reason`.
- `commercial_followup` con `"Devuelto a Comercial desde <área>: <motivo>"`.
- **No se tocan** la proforma, los pendientes ni el proyecto (`task_technical`).
  Al editar la proforma, `save_sale_quotation` re-vincula los pendientes (sección 1).
  Al aprobar otra vez, `update_ticket_commercial` mueve el registro a Proyectos y
  `_generate_pending_materials` no duplica pendientes. El proyecto se conserva y
  sigue vinculado, porque no se elimina un registro del dominio técnico.

Responde `data`: `{inspection_id, previous_area, management_area, commercial_status_id}`.

### Tests

`swagger_server/test/test_return_to_commercial.py`.

---

## 6. Devolver un registro a Técnica

### Propósito

Un registro que está en Comercial, con una gestión comercial **no aprobada**, vuelve
a Técnica para corregir el registro técnico (materiales, descripción). No se borra
nada: la gestión comercial, la proforma, los pendientes y los documentos se
conservan, y la gestión comercial queda **congelada** hasta que Técnica la vuelva a
aprobar.

### Disparador

`POST /return-to-technical` (`return_to_technical`). Body:
`{"data": {"inspection_id", "reason", "user"}, "channel", "externalTransactionId"}`.

### Validaciones (en orden)

| Regla | Respuesta |
|---|---|
| `inspection_id` entero, `reason` con texto (use case, `_return_payload`) | 400 |
| La inspección existe | 404 |
| `status` distinto de `Finalizado` | 400 |
| `management_area = 'Comercial'` | 400 (`ya está en Técnica` / `Solo se pueden devolver a Técnica registros de Comercial`) |
| Tiene registro técnico (las Asistencias aprobadas con el flujo anterior no tienen) | 400 |
| Última gestión comercial existe, no está Aprobada (5) ni ya devuelta (9) | 404 / 400 |
| No hay proyecto (`task_technical`): se armó con una proforma aprobada antes | 400 |
| Sin entregas ni gestiones financieras (`_ensure_returnable`, compartida con la sección 5) | 400 |

### Efectos (una transacción)

- Registro técnico → `status = 'Devuelto'`. Se ve en `GET /register-technical`.
- Gestión comercial → `status_id = 9` (`Devuelto a Técnica`, migración al final de
  `scripts.sql`).
- Inspección → `status = 'Devuelto a Técnica'`, `management_area = 'Técnica'`,
  `next_area = 'Comercial'`.
- `history_area_ticket`: Comercial → Técnica, con el motivo en `reason` (columna
  agregada al final de `scripts.sql`; `NULL` en los avances normales).
- `commercial_followup` con `"Devuelto a Técnica: <motivo>"`.

El motivo se consulta con `GET /history-area-ticket/{id_inspection}` (incluye
`reason`): el front toma el último registro Comercial → Técnica. No hay un endpoint
propio para esto.

### Mientras está devuelto

- `PUT /register-commercial` responde 400 (gestión en 9 o inspección en Técnica).
- `POST /register-commercial` responde 400 si la última gestión está en 9.
- `approve-commercial-ticket` y `return-to-commercial` ya lo rechazan (exigen
  Aprobada / Proyectos-Financiera).
- Cuenta en `pending_technical` del dashboard y de `GET /inspection`.

### Corrección y nueva aprobación

`Devuelto` → (`PUT /register-technical` sin `status`) → `Pendiente aprobación` →
(`approve_technical_inspection`) → `Aprobado`. Al aprobar, la inspección vuelve a
Comercial con "Listo para cotizar" y `_resume_returned_commercial` pasa la gestión
comercial de 9 a Pendiente (7), con el seguimiento "Aprobado nuevamente por Técnica;
revisar la proforma". Lo mismo ocurre si el registro pasa a Comercial por
`update_ticket_technical` o `update_inspection_technical` con "Listo para cotizar".
No aparece en `pending_commercial` (exige no tener gestión comercial): se ve en
`/register-commercial` como Pendiente.

### Impacto de los cambios del técnico en los materiales

Como la gestión no está aprobada, no hay proyecto, entregas ni facturas. Los
pendientes siguen las reglas de la sección 1:

- Producto del catálogo agregado o editado: la proforma no cambia hasta que
  Comercial la edite. Al editarla, el front agrega los materiales nuevos del
  técnico y avisa las cantidades distintas (sección 1, Front).
- Producto nuevo agregado: crea un pendiente `Pendiente` sin proforma. Al editar,
  el front lo agrega a la proforma; si Comercial lo quita antes de guardar, pasa a
  `Eliminado de proforma`.
- Producto nuevo editado: el pendiente (sin `quote_id` y no `Creado`) toma los
  cambios. La línea de la proforma conserva los datos anteriores hasta que se edite.
- Producto nuevo quitado, o cambiado por uno del catálogo: la línea de la proforma
  pierde `material_tech_ticket_id` y el pendiente se elimina, salvo que ya esté
  `Creado`; en ese caso solo se desvincula y el stock ingresado no se revierte.
  **Riesgo:** si Comercial aprueba sin editar la proforma, la línea suelta genera un
  pendiente nuevo. Por eso la gestión vuelve a Pendiente con un seguimiento que pide
  revisar la proforma.

### Tests

`swagger_server/test/test_return_to_technical.py`.

## 7. Documentos de la proforma (PDF / Excel)

### Propósito

Descargar la proforma (`internal_management.sale_quotation`) para el cliente (PDF)
o para uso interno con el detalle de costos (Excel).

### Endpoints

- `GET /sale-quotation/{id_quote}/pdf` (`inline=true` para verla en el navegador):
  cotización para el cliente, sin costos ni ganancias.
- `GET /sale-quotation/{id_quote}/excel`: `.xlsx` con cliente, RUC, proyecto,
  solicitante, asesor y fecha; por ítem: modelo, descripción, tipo, cantidad, costo,
  ganancia %, ganancia $, PVP y total; luego subtotal, IVA, total y condiciones.

### Reglas

Ambos salen de `InternalManagementUseCase._build_sale_quotation_document`:

- Asesor (header del PDF y fila "Asesor" del Excel): `attributes.fullname` de
  `public.users` del asesor asignado a la inspección (`inspection_technical.sales_user`);
  si no hay asesor asignado, del usuario que creó la proforma (`sale_quotation.created_by`).
  Sin `fullname`, se muestra el login.
- Ítem del catálogo: modelo y descripción se toman de `technical_equipment`.
- Materiales varios: modelo `M/V` por defecto y descripción armada con sus
  componentes (`sale_additional_materials`).
- Mano de obra: modelo `M/V` por defecto.
- Nombre del archivo (`sale_quotation_file_name`): `<quote_number> - <proyecto>.pdf|xlsx`,
  p. ej. `JPEREZ-0042 - Instalación cámaras bodega norte.pdf`. `quote_number` es
  `<código del asesor>-<id_quote 4 dígitos>`; proyecto = `inspection_technical.title_ticket`
  sin caracteres inválidos en nombres de archivo y recortado a 80 caracteres. Sin
  proyecto: `<quote_number>.pdf`; sin `quote_number` se usa `id_quote`. Va en
  `Content-Disposition` (`filename*` UTF-8 conserva tildes); CORS expone ese header.
- PVP = `total / quantity`. Ganancia % = `profit_margin`; en materiales varios es
  `profit_margin_dollar / (base_price + profit_margin_dollar)` (ponderado sobre la venta).

### Fórmula del precio de venta (margen sobre la venta)

El % de ganancia es margen sobre el precio de venta, no markup sobre el costo:

```
PVP        = costo / (1 - margen)      # 34,61 al 30 % => 49,44
ganancia $ = PVP - costo               # 14,83 = 30 % de 49,44
```

- La calcula el front (`pw-tickets/src/app/utils/pricing.ts`, `priceFromMargin`) en la
  proforma, en materiales varios, en el catálogo de bodega y al crear un producto
  pendiente. El margen debe ser menor a 100 %.
- Al cargar un producto del catálogo en la proforma, el PVP se recalcula con
  `base_price` y `profit_margin`; no se usa el `price` guardado.
- Hasta el 13/11/2026 se usaba `PVP = costo × (1 + margen)`. `scripts.sql` recalcula
  `technical.technical_equipment` con la fórmula nueva. Las proformas ya guardadas
  conservan sus precios; si se edita el costo o el % de una línea, se recalcula con la
  fórmula nueva.
- 404 si la proforma no existe.

### Front (pw-tickets)

`ticket-detail-sidebar`: botones ver/descargar PDF y descargar Excel
(`GlpiService.downloadSaleQuote` / `downloadSaleQuoteExcel`, con `observe: 'response'`).
El nombre de la descarga se toma de `Content-Disposition` con
`UtilsService.fileNameFromHeaders`; `cotizacion-<id>.pdf` / `proforma-<id>.xlsx` solo
si el header no llega.

### Tests

`swagger_server/test/test_sale_quotation_pdf.py`,
`swagger_server/test/test_sale_quotation_excel.py`.
