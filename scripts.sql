CREATE TABLE internal_management.technical_ticket_management
(
    id_management_technical integer NOT NULL,
    code_management text,
    case_type text,
    management_status text,
    next_action text,
    commitment_date timestamp without time zone,
    observations text,
    requires_material boolean,
    requires_monitoring boolean,
    status text,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    created_by text,
    updated_by text,
    PRIMARY KEY (id_management_technical)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.technical_ticket_management
    OWNER to telearseg;



CREATE SEQUENCE internal_management.technical_ticket_management_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.technical_ticket_management_id_seq
    OWNED BY internal_management.technical_ticket_management.id_management_technical;

ALTER SEQUENCE internal_management.technical_ticket_management_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.technical_ticket_management
    ALTER COLUMN id_management_technical SET DEFAULT nextval('internal_management.technical_ticket_management_id_seq'::regclass);


---------------------------------------------------------------------------------------------------------

-- Table: internal_management.tickets_management

-- DROP TABLE IF EXISTS internal_management.tickets_management;

CREATE TABLE IF NOT EXISTS internal_management.inspection_technical
(
    id_inspection integer NOT NULL DEFAULT nextval('internal_management.tickets_management_id_seq'::regclass),
    management_area text COLLATE pg_catalog."default",
    status text COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT now(),
    created_by text COLLATE pg_catalog."default",
    updated_at timestamp without time zone DEFAULT now(),
    updated_by text COLLATE pg_catalog."default",
    priority text COLLATE pg_catalog."default",
    client_id integer,
    ubication_id integer,
    contact text COLLATE pg_catalog."default",
    code text COLLATE pg_catalog."default",
    next_area text COLLATE pg_catalog."default",
    title_ticket text COLLATE pg_catalog."default",
    client_name text COLLATE pg_catalog."default",
    ubication_name text COLLATE pg_catalog."default",
    responsible_id uuid,
    responsible_name text COLLATE pg_catalog."default",
    case_type text COLLATE pg_catalog."default",
    management_status text COLLATE pg_catalog."default",
    commitment_date timestamp without time zone,
    CONSTRAINT tickets_management_pkey PRIMARY KEY (id_inspection)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.inspection_technical
    OWNER to telearseg;




CREATE SEQUENCE internal_management.tickets_management_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.tickets_management_id_seq
    OWNED BY internal_management.inspection_technical.id_inspection;

ALTER SEQUENCE internal_management.tickets_management_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.inspection_technical
    ALTER COLUMN id_ticket SET DEFAULT nextval('internal_management.tickets_management_id_seq'::regclass);



------------------------------------------------------------------------------------------------------------------------------------

ALTER TABLE IF EXISTS internal_management.technical_ticket_management DROP COLUMN IF EXISTS ticket_glpi;

ALTER TABLE IF EXISTS internal_management.technical_ticket_management
    ADD COLUMN ticket_id integer;
ALTER TABLE IF EXISTS internal_management.technical_ticket_management
    ADD CONSTRAINT tech_ticket_fkey FOREIGN KEY (ticket_id)
    REFERENCES internal_management.tickets_management (id_ticket) MATCH SIMPLE
    ON UPDATE NO ACTION
    ON DELETE NO ACTION;
CREATE INDEX IF NOT EXISTS fki_tech_ticket_fkey
    ON internal_management.technical_ticket_management(ticket_id);

-------------------------------------------------------------------------------------------------------------------------------------


CREATE TABLE internal_management.history_area_ticket
(
    id_history integer NOT NULL,
    ticket_id integer,
    previous_area text,
    current_area text,
    created_at timestamp without time zone DEFAULT now(),
    created_by text,
    CONSTRAINT history_area_pkey PRIMARY KEY (id_history),
    CONSTRAINT ticket_fkey FOREIGN KEY (ticket_id)
        REFERENCES internal_management.tickets_management (id_ticket) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.history_area_ticket
    OWNER to telearseg;


CREATE SEQUENCE internal_management.history_area_ticket_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.history_area_ticket_id_seq
    OWNED BY internal_management.history_area_ticket.id_history;

ALTER SEQUENCE internal_management.history_area_ticket_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.history_area_ticket
    ALTER COLUMN id_history SET DEFAULT nextval('internal_management.history_area_ticket_id_seq'::regclass);


-----------------------------------------------------------------------------------------------------------------------------------------

-- Table: internal_management.commercial_origin

-- DROP TABLE IF EXISTS internal_management.commercial_origin;

CREATE TABLE IF NOT EXISTS internal_management.commercial_origin
(
    id_origin integer NOT NULL,
    name text COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT now(),
    created_by text COLLATE pg_catalog."default",
    CONSTRAINT commercial_origin_pkey PRIMARY KEY (id_origin)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.commercial_origin
    OWNER to telearseg;


CREATE SEQUENCE internal_management.commercial_origin_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.commercial_origin_id_seq
    OWNED BY internal_management.commercial_origin.id_origin;

ALTER SEQUENCE internal_management.commercial_origin_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.commercial_origin
    ALTER COLUMN id_origin SET DEFAULT nextval('internal_management.commercial_origin_id_seq'::regclass);



-----------------------------------------------------------------------------------------------------------------------------------------

-- Table: internal_management.commercial_type_solution

-- DROP TABLE IF EXISTS internal_management.commercial_type_solution;

CREATE TABLE IF NOT EXISTS internal_management.commercial_type_solution
(
    id_solution integer NOT NULL,
    name text COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT now(),
    created_by text COLLATE pg_catalog."default",
    CONSTRAINT commercial_type_solution_pkey PRIMARY KEY (id_solution)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.commercial_type_solution
    OWNER to telearseg;


CREATE SEQUENCE internal_management.commercial_type_solution_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.commercial_type_solution_id_seq
    OWNED BY internal_management.commercial_type_solution.id_solution;

ALTER SEQUENCE internal_management.commercial_type_solution_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.commercial_type_solution
    ALTER COLUMN id_solution SET DEFAULT nextval('internal_management.commercial_type_solution_id_seq'::regclass);

-----------------------------------------------------------------------------------------------------------------------------------------
-- Table: internal_management.commmercial_ticket_status

-- DROP TABLE IF EXISTS internal_management.commmercial_ticket_status;

CREATE TABLE IF NOT EXISTS internal_management.commmercial_ticket_status
(
    id_status integer NOT NULL,
    name text COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT now(),
    created_by text COLLATE pg_catalog."default",
    CONSTRAINT commmercial_ticket_status_pkey PRIMARY KEY (id_status)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.commmercial_ticket_status
    OWNER to telearseg;


CREATE SEQUENCE internal_management.commmercial_ticket_status_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.commmercial_ticket_status_id_seq
    OWNED BY internal_management.commmercial_ticket_status.id_status;

ALTER SEQUENCE internal_management.commmercial_ticket_status_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.commmercial_ticket_status
    ALTER COLUMN id_status SET DEFAULT nextval('internal_management.commmercial_ticket_status_id_seq'::regclass);



-----------------------------------------------------------------------------------------------------------------------------------------


CREATE TABLE internal_management.commercial_ticket_management
(
    id_management_commercial integer NOT NULL,
    assigned_user text,
    code_management text,
    origin_id integer,
    type_solution_id integer,
    quoted_amount numeric(12, 2),
    probability_closing integer,
    closing_date timestamp without time zone,
    next_action text,
    responsible_next_action text,
    requires_technical boolean,
    requires_material boolean,
    -- scheduled_start_date timestamp without time zone,
    contract_received boolean,
    date_finish timestamp without time zone,
    reason_loss text,
    observations text,
    status_id integer,
    created_at timestamp without time zone DEFAULT now(),
    created_by text,
    updated_at timestamp without time zone DEFAULT now(),
    updated_by text,
    CONSTRAINT commercial_ticket_pkey PRIMARY KEY (id_management_commercial),
    CONSTRAINT origin_fkey FOREIGN KEY (origin_id)
        REFERENCES internal_management.commercial_origin (id_origin) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,
    CONSTRAINT type_solution_fkey FOREIGN KEY (type_solution_id)
        REFERENCES internal_management.commercial_type_solution (id_solution) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,
    CONSTRAINT status_fkey FOREIGN KEY (status_id)
        REFERENCES internal_management.commmercial_ticket_status (id_status) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.commercial_ticket_management
    OWNER to telearseg;


CREATE SEQUENCE internal_management.commercial_ticket_management_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.commercial_ticket_management_id_seq
    OWNED BY internal_management.commercial_ticket_management.id_management_commercial;

ALTER SEQUENCE internal_management.commercial_ticket_management_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.commercial_ticket_management
    ALTER COLUMN id_management_commercial SET DEFAULT nextval('internal_management.commercial_ticket_management_id_seq'::regclass);


--------------------------------------------------------------------------------------------------------------------------------------


ALTER TABLE IF EXISTS internal_management.commercial_ticket_management
    ADD COLUMN ticket_id integer;
ALTER TABLE IF EXISTS internal_management.commercial_ticket_management
    ADD CONSTRAINT ticket_fkey FOREIGN KEY (ticket_id)
    REFERENCES internal_management.tickets_management (id_ticket) MATCH SIMPLE
    ON UPDATE NO ACTION
    ON DELETE NO ACTION;
CREATE INDEX IF NOT EXISTS fki_ticket_fkey
    ON internal_management.commercial_ticket_management(ticket_id);

--------------------------------------------------------------------------------------------------------------------------------------


CREATE TABLE internal_management.commercial_followup
(
    id_followup integer NOT NULL,
    management_commercial_id integer,
    observations text,
    created_at timestamp without time zone DEFAULT now(),
    created_by text,
    CONSTRAINT commercial_followup_pkey PRIMARY KEY (id_followup),
    CONSTRAINT management_commercial_fkey FOREIGN KEY (management_commercial_id)
        REFERENCES internal_management.commercial_ticket_management (id_management_commercial) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.commercial_followup
    OWNER to telearseg;


CREATE SEQUENCE internal_management.commercial_followup_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.commercial_followup_id_seq
    OWNED BY internal_management.commercial_followup.id_followup;

ALTER SEQUENCE internal_management.commercial_followup_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.commercial_followup
    ALTER COLUMN id_followup SET DEFAULT nextval('internal_management.commercial_followup_id_seq'::regclass);

---------------------------------------------------------------------------------------------------------------------------------

CREATE TABLE internal_management.history_commercial_alerts
(
    id_alert integer NOT NULL,
    management_commercial_id integer,
    alert text,
    created_at timestamp without time zone DEFAULT now(),
    created_by text,
    PRIMARY KEY (id_alert)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.history_commercial_alerts
    OWNER to telearseg;



CREATE SEQUENCE internal_management.history_commercial_alerts_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.history_commercial_alerts_id_seq
    OWNED BY internal_management.history_commercial_alerts.id_alert;

ALTER SEQUENCE internal_management.history_commercial_alerts_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.history_commercial_alerts
    ALTER COLUMN id_alert SET DEFAULT nextval('internal_management.history_commercial_alerts_id_seq'::regclass);


--------------------------------------------------------------------------------------------------------------------------

-- Paginación / ordenamiento para tabla technical_ticket_management
CREATE INDEX IF NOT EXISTS idx_technical_ticket_management_pagination
ON internal_management.technical_ticket_management
(created_at DESC, id_management_technical DESC);


CREATE EXTENSION IF NOT EXISTS pg_trgm;


CREATE INDEX IF NOT EXISTS idx_technical_ticket_management_code_trgm
ON internal_management.technical_ticket_management
USING gin (code_management gin_trgm_ops);


CREATE INDEX IF NOT EXISTS idx_technical_ticket_management_case_type_trgm
ON internal_management.technical_ticket_management
USING gin (case_type gin_trgm_ops);


-------------------------------------------------------------------------------------------------------------------------------------

CREATE TABLE internal_management.financial_ticket_management
(
    id_management_financial integer NOT NULL,
    ticket_id integer,
    code_management text,
    number_document text,
    type_management text,
    amount_pending numeric(12, 2),
    amount_paid numeric(12, 2),
    invoice_price numeric(12, 2),
    observations text,
    status text,
    date_document timestamp without time zone,
    created_at timestamp without time zone DEFAULT now(),
    created_by text,
    updated_at timestamp without time zone DEFAULT now(),
    updated_by text,
    CONSTRAINT financial_pkey PRIMARY KEY (id_management_financial),
    CONSTRAINT ticket_financial_fkey FOREIGN KEY (ticket_id)
        REFERENCES internal_management.tickets_management (id_ticket) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.financial_ticket_management
    OWNER to telearseg;


CREATE SEQUENCE internal_management.financial_ticket_management_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.financial_ticket_management_id_seq
    OWNED BY internal_management.financial_ticket_management.id_management_financial;

ALTER SEQUENCE internal_management.financial_ticket_management_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.financial_ticket_management
    ALTER COLUMN id_management_financial SET DEFAULT nextval('internal_management.financial_ticket_management_id_seq'::regclass);

---------------------------------------------------------------------------------------------------------------------------------


CREATE TABLE internal_management.material_tech_ticket
(
    id_material integer NOT NULL,
    tech_ticket integer,
    material_id integer,
    other text,
    material_description text,
    quantity integer,
    created_at timestamp without time zone DEFAULT now(),
    PRIMARY KEY (id_material),
    CONSTRAINT tech_material_fkey FOREIGN KEY (tech_ticket)
        REFERENCES internal_management.technical_ticket_management (id_management_technical) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,
    CONSTRAINT material_fkey FOREIGN KEY (material_id)
        REFERENCES technical.technical_equipment (id_equipment) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.material_tech_ticket
    OWNER to telearseg;


CREATE SEQUENCE internal_management.material_tech_ticket_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.material_tech_ticket_id_seq
    OWNED BY internal_management.material_tech_ticket.id_material;

ALTER SEQUENCE internal_management.material_tech_ticket_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.material_tech_ticket
    ALTER COLUMN id_material SET DEFAULT nextval('internal_management.material_tech_ticket_id_seq'::regclass);

-------------------------------------------------------------------------------------------------------------------------------------

-- Solo un registro técnico por inspección
ALTER TABLE IF EXISTS internal_management.technical_ticket_management
    ADD CONSTRAINT technical_ticket_inspection_unique UNIQUE (inspection_id);

-------------------------------------------------------------------------------------------------------------------------------------

CREATE TABLE internal_management.providers_products
(
    id_provider integer NOT NULL,
    ruc text,
    provider text,
    address text,
    seller text,
    number_contact text,
    email text,
    status text,
    created_by text,
    created_at timestamp without time zone DEFAULT now(),
    PRIMARY KEY (id_provider)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.providers_products
    OWNER to telearseg;

CREATE SEQUENCE internal_management.providers_products_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.providers_products_id_seq
    OWNED BY internal_management.providers_products.id_provider;

ALTER SEQUENCE internal_management.providers_products_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.providers_products
ALTER COLUMN id_provider SET DEFAULT nextval('internal_management.providers_products_id_seq'::regclass);


-----------------------------------------------------------------------------------------------------------------------------

ALTER TABLE IF EXISTS technical.technical_equipment
    ADD COLUMN provider_id integer;
ALTER TABLE IF EXISTS technical.technical_equipment
    ADD CONSTRAINT provider_fkey FOREIGN KEY (provider_id)
    REFERENCES internal_management.providers_products (id_provider) MATCH SIMPLE
    ON UPDATE NO ACTION
    ON DELETE NO ACTION;
CREATE INDEX IF NOT EXISTS fki_provider_fkey
    ON technical.technical_equipment(provider_id);


----------------------------------------------------------------------------------------------------------------------------


CREATE TABLE internal_management.equipment_images
(
    id_image integer NOT NULL,
    equipment_tech_id integer,
    image_path text,
    created_at timestamp without time zone DEFAULT now(),
    PRIMARY KEY (id_image),
    CONSTRAINT equipment_id_fkey FOREIGN KEY (equipment_tech_id)
        REFERENCES technical.technical_equipment (id_equipment) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.equipment_images
    OWNER to telearseg;


CREATE SEQUENCE internal_management.equipment_images_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.equipment_images_id_seq
    OWNED BY internal_management.equipment_images.id_image;

ALTER SEQUENCE internal_management.equipment_images_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.equipment_images
ALTER COLUMN id_image SET DEFAULT nextval('internal_management.equipment_images_id_seq'::regclass);

----------------------------------------------------------------------------------------------------------------------------------------

CREATE TABLE internal_management.inspection_documents
(
    id_document integer NOT NULL,
    inspection_id integer,
    document_path text,
    name_document text,
    type_document text,
    created_at timestamp without time zone DEFAULT now(),
    PRIMARY KEY (id_document),
    CONSTRAINT inspection_doc_fkey FOREIGN KEY (inspection_id)
        REFERENCES internal_management.inspection_technical (id_inspection) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.inspection_documents
    OWNER to telearseg;


CREATE SEQUENCE internal_management.inspection_documents_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.inspection_documents_id_seq
    OWNED BY internal_management.inspection_documents.id_document;

ALTER SEQUENCE internal_management.inspection_documents_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.inspection_documents
    ALTER COLUMN id_document SET DEFAULT nextval('internal_management.inspection_documents_id_seq'::regclass);


-------------------------------------------------------------------------------------------------------------------------------


ALTER TABLE IF EXISTS internal_management.inspection_technical
    ADD CONSTRAINT client_inspection_fkey FOREIGN KEY (client_id)
    REFERENCES technical.clients (id_client) MATCH SIMPLE
    ON UPDATE NO ACTION
    ON DELETE NO ACTION;
CREATE INDEX IF NOT EXISTS fki_client_inspection_fkey
    ON internal_management.inspection_technical(client_id);

ALTER TABLE IF EXISTS internal_management.inspection_technical
    ADD CONSTRAINT location_inspection_fkey FOREIGN KEY (ubication_id)
    REFERENCES technical.clients_location (id_location) MATCH SIMPLE
    ON UPDATE NO ACTION
    ON DELETE NO ACTION;
CREATE INDEX IF NOT EXISTS fki_location_inspection_fkey
    ON internal_management.inspection_technical(ubication_id);


------------------------------------------------------------------------------------------------------------------------------

CREATE TABLE internal_management.sale_quotation
(
    id_quote integer NOT NULL,
    inspection_id integer,
    client_company integer,
    iva numeric(15, 2),
    iva_rate numeric(15, 2),
    subtotal numeric(15, 2),
    total numeric(15, 2),
    quote_number text,
    delivery_time text,
    payment_terms text,
    validity_days integer,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    created_by text,
    updated_by text,
    PRIMARY KEY (id_quote),
    CONSTRAINT client_company_quote_fkey FOREIGN KEY (client_company)
        REFERENCES technical.client_companies (id_company) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,
    CONSTRAINT inspection_quote_fkey FOREIGN KEY (inspection_id)
        REFERENCES internal_management.inspection_technical (id_inspection) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.sale_quotation
    OWNER to telearseg;


CREATE SEQUENCE internal_management.sale_quotation_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.sale_quotation_id_seq
    OWNED BY internal_management.sale_quotation.id_quote;

ALTER SEQUENCE internal_management.sale_quotation_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.sale_quotation
    ALTER COLUMN id_quote SET DEFAULT nextval('internal_management.sale_quotation_id_seq'::regclass);


---------------------------------------------------------------------------------------------------------------------------------

CREATE TABLE internal_management.sale_quotation_item
(
    id_item integer NOT NULL,
    sale_quote_id integer,
    material_id integer,
    item_number integer,
    is_labor boolean,
    is_bundle boolean,
    base_price numeric(15, 2),
    profit_margin numeric(15, 2),
    profit_margin_dollar numeric(15, 2),
    quantity numeric(15, 2),
    total numeric(15, 2),
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    created_by text,
    updated_by text,
    PRIMARY KEY (id_item),
    CONSTRAINT sale_quote_fkey FOREIGN KEY (sale_quote_id)
        REFERENCES internal_management.sale_quotation (id_quote) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,
    CONSTRAINT material_quote_fkey FOREIGN KEY (material_id)
        REFERENCES technical.technical_equipment (id_equipment) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.sale_quotation_item
    OWNER to telearseg;


CREATE SEQUENCE internal_management.sales_quotation_item_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.sales_quotation_item_id_seq
    OWNED BY internal_management.sale_quotation_item.id_item;

ALTER SEQUENCE internal_management.sales_quotation_item_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.sale_quotation_item
    ALTER COLUMN id_item SET DEFAULT nextval('internal_management.sales_quotation_item_id_seq'::regclass);


----------------------------------------------------------------------------------------------------------------------------

CREATE TABLE internal_management.sale_additional_materials
(
    id_extra integer NOT NULL,
    sale_quote_id integer,
    material_id integer,
    base_price numeric(15, 2),
    profit_margin numeric(15, 2),
    profit_margin_dollar numeric(15, 2),
    quantity numeric(15, 2),
    total numeric(15, 2),
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    created_by text,
    updated_by text,
    PRIMARY KEY (id_extra),
    CONSTRAINT sale_quote_fkey FOREIGN KEY (sale_quote_id)
        REFERENCES internal_management.sale_quotation (id_quote) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,
    CONSTRAINT material_fkey FOREIGN KEY (material_id)
        REFERENCES technical.technical_equipment (id_equipment) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS internal_management.sale_additional_materials
    OWNER to telearseg;


CREATE SEQUENCE internal_management.sale_additional_materials_id_seq
    INCREMENT 1
    START 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

ALTER SEQUENCE internal_management.sale_additional_materials_id_seq
    OWNED BY internal_management.sale_additional_materials.id_extra;

ALTER SEQUENCE internal_management.sale_additional_materials_id_seq
    OWNER TO telearseg;

ALTER TABLE IF EXISTS internal_management.sale_additional_materials
    ALTER COLUMN id_extra SET DEFAULT nextval('internal_management.sale_additional_materials_id_seq'::regclass);


--------------------------------------------------------------------------------------------------------------------------------

ALTER TABLE IF EXISTS internal_management.sale_quotation_item
    ADD COLUMN description text;

ALTER TABLE IF EXISTS internal_management.sale_quotation_item
    ADD COLUMN model text;

ALTER TABLE IF EXISTS internal_management.sale_quotation_item
    ADD COLUMN is_new boolean;

ALTER TABLE IF EXISTS internal_management.sale_additional_materials
    ADD COLUMN quotation_item_id integer;

ALTER TABLE IF EXISTS internal_management.sale_additional_materials
    ADD CONSTRAINT quotation_item_fkey FOREIGN KEY (quotation_item_id)
        REFERENCES internal_management.sale_quotation_item (id_item) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION;
