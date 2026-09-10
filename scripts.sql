CREATE TABLE internal_management.technical_ticket_management
(
    id_management_technical integer NOT NULL,
    ticket_glpi text,
    code_management text,
    client_id integer,
    ubication_client_id integer,
    contact text,
    case_type text,
    priority text,
    responsible text,
    management_status text,
    next_action text,
    commitment_date timestamp without time zone,
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














