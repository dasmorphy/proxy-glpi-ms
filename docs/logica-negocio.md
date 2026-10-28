# Lógica de negocio

Documento vivo con los flujos de negocio de la API. Cada sección describe un
flujo: qué lo dispara, qué tablas toca y qué reglas aplica. Al cambiar un flujo,
actualizar su sección; al agregar uno nuevo, añadirlo al índice.

Las referencias a código apuntan a funciones (no a números de línea, que
cambian). Salvo que se indique otra cosa, están en
`swagger_server/repository/internal_management_repository.py`.

## Índice

1. [Materiales pendientes de creación](#1-materiales-pendientes-de-creación)

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
  mano. El pendiente se genera **al aprobar** la gestión comercial.

Con el pendiente, bodega puede entregar el producto aunque no esté en el
catálogo y darlo de alta después sin perder la trazabilidad de lo entregado.

### Tabla

`internal_management.pending_material` (modelo `PendingMaterial`,
`swagger_server/models/db/pending_material.py`)

| Campo | Descripción |
|---|---|
| `inspection_id` | Ticket (inspección) al que pertenece. Siempre presente |
| `material_tech_ticket_id` | Material del registro técnico que lo originó. **Único**. `NULL` si lo originó la proforma |
| `quote_id`, `quotation_item_id` | Proforma e ítem aprobados. `NULL` hasta que la proforma se aprueba. `quotation_item_id` es **único** |
| `name_material`, `description`, `model`, `quantity`, `base_price`, `profit_margin`, `profit_margin_dollar` | Datos sugeridos. Vienen del técnico y se actualizan con los de la proforma al aprobarse |
| `status` | `Pendiente`, `Creado` o `Eliminado de proforma` |
| `material_id` | Producto creado en el catálogo; `NULL` mientras está pendiente |
| `created_at/by`, `resolved_at/by` | Auditoría |

También `sale_quotation_item.material_tech_ticket_id` guarda de qué material del
técnico proviene un ítem nuevo de la proforma. Es lo que permite vincular el
pendiente en lugar de duplicarlo.

La migración está al final de `scripts.sql` (sección *PENDIENTES DESDE EL
REGISTRO TÉCNICO*).

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

- Los ítems pueden enviar `material_tech_ticket_id`. Se valida que pertenezca a
  la misma inspección (`_validate_quotation_technical_materials`); si no, error
  400.
- `_sync_quotation_pendings`: los pendientes del técnico que la proforma no
  incluye pasan a `Eliminado de proforma`, y los que vuelve a incluir regresan a
  `Pendiente`. Solo afecta a los pendientes sin vincular y que no están en
  `Creado`.

### 1.3 Aprobación de la gestión comercial

Función: `_generate_pending_materials(session, quote_id, user)`. Es
**idempotente**.

Se procesan los ítems de la proforma con `is_new = True`, `is_labor` distinto de
`True` y `material_id IS NULL`:

- Si el ítem trae `material_tech_ticket_id` y ese pendiente está libre, **se
  vincula**: se le asignan `quote_id` y `quotation_item_id`, se actualizan
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

En `post_material_delivery`, si el ítem de la proforma no tiene `material_id`:

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
   - Con proforma aprobada (`quotation_item_id` presente): stock ≥ cantidad de
     la proforma.
   - Sin proforma aprobada: stock ≥ 0.
3. Crea el `TechnicalEquipment` con `stock = stock ingresado − ya entregado`.
4. Enlaza las entregas previas al producto creado.
5. Si el pendiente viene del técnico:
   - Actualiza `material_tech_ticket.material_id`. Así, cuando el comercial arme
     la proforma, lo verá como producto del catálogo, con su precio.
   - Si la proforma todavía no está aprobada, los ítems que lo referencian pasan
     a `material_id = producto` y `is_new = False`.
6. Marca el pendiente como `Creado`.

### 1.6 Consulta

`GET /pending-material` (`get_pending_materials`) admite los filtros opcionales
`quote_id`, `inspection_id` y `status`. Usa *outer join* con la proforma porque
los pendientes del técnico pueden no tener una. Devuelve `origin` (`Técnico` o
`Proforma`), los datos del ticket (`inspection_code`, `title_ticket`,
`client_name`) y `quote_number`.

### Front (pw-tickets)

- `register-ticket-technical`: envía `id_material` al editar.
- `register-ticket-commercial`: conserva y envía `material_tech_ticket_id` en
  los ítems nuevos que vienen del técnico.
- `components/modals/pending-product-dialog`: diálogo reutilizable para crear el
  producto. Lo usan el modal de entrega de materiales y la página de pendientes.
- `pages/tables/pending-materials`: ruta `/productos-pendientes`, en el menú
  "Productos pendientes" (permiso `LOGISTICA`).

### Invariantes y riesgos

- Solo se puede editar una gestión comercial en estado Pendiente
  (`update_ticket_commercial`). Una vez aprobada, la proforma no cambia.
- `save_sale_quotation` **borra y recrea** los ítems de la proforma. No es un
  problema porque los pendientes solo se vinculan a `quotation_item_id` al
  aprobar, y una gestión aprobada ya no se edita.
- El técnico debe enviar `id_material` al editar. Si no lo envía, sus
  materiales se recrean y los pendientes sin vincular se eliminan y se vuelven
  a generar.

### Tests

`swagger_server/test/test_material_delivery.py`, clases
`TestMaterialDeliveryRepository` y `TestTechnicalPendingMaterials`.
