-- Estructura del schema public de la plataforma, copiada de la RDS (wiseerp).
-- NO se edita a mano: la maneja el servicio de plataforma con su propio Alembic.
-- Para actualizarla: make db-sync-cloud (requiere .env.aws)

--
-- PostgreSQL database dump
--


-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6 (Debian 18.6-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: pg_database_owner
--



ALTER SCHEMA public OWNER TO pg_database_owner;

--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: pg_database_owner
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: app_crear_organizacion(text, text, uuid); Type: FUNCTION; Schema: public; Owner: wiseadmin
--

CREATE FUNCTION public.app_crear_organizacion(p_slug text, p_nombre text, p_admin uuid) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
        DECLARE
            v_tenant uuid;
            v_membresia uuid;
            v_rol uuid;
        BEGIN
            SELECT id INTO v_rol FROM roles
            WHERE code = 'administrador' AND tenant_id IS NULL;
            IF v_rol IS NULL THEN
                RAISE EXCEPTION 'no existe el rol administrador';
            END IF;

            INSERT INTO tenants (id, slug, name, kind, status)
            VALUES (gen_random_uuid(), lower(p_slug), p_nombre, 'client', 'active')
            RETURNING id INTO v_tenant;

            INSERT INTO memberships (id, user_id, tenant_id, status)
            VALUES (gen_random_uuid(), p_admin, v_tenant, 'invited')
            RETURNING id INTO v_membresia;

            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (v_membresia, v_rol);

            RETURN v_tenant;
        END $$;


ALTER FUNCTION public.app_crear_organizacion(p_slug text, p_nombre text, p_admin uuid) OWNER TO wiseadmin;

--
-- Name: app_crear_usuario(text, text, text); Type: FUNCTION; Schema: public; Owner: wiseadmin
--

CREATE FUNCTION public.app_crear_usuario(p_email text, p_nombre text, p_sub text) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
        DECLARE v_id uuid;
        BEGIN
            INSERT INTO users (id, email, full_name, cognito_sub, is_active)
            VALUES (gen_random_uuid(), lower(p_email), p_nombre, p_sub, true)
            RETURNING id INTO v_id;
            RETURN v_id;
        END $$;


ALTER FUNCTION public.app_crear_usuario(p_email text, p_nombre text, p_sub text) OWNER TO wiseadmin;

--
-- Name: app_es_miembro(uuid); Type: FUNCTION; Schema: public; Owner: wiseadmin
--

CREATE FUNCTION public.app_es_miembro(p_tenant uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
            SELECT EXISTS (
                SELECT 1 FROM memberships m
                WHERE m.tenant_id = p_tenant
                  AND m.user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
                  AND m.status IN ('active', 'invited')
            )
        $$;


ALTER FUNCTION public.app_es_miembro(p_tenant uuid) OWNER TO wiseadmin;

--
-- Name: app_rol_no_pisa_al_sistema(); Type: FUNCTION; Schema: public; Owner: wiseadmin
--

CREATE FUNCTION public.app_rol_no_pisa_al_sistema() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            IF NEW.tenant_id IS NOT NULL AND EXISTS (
                SELECT 1 FROM roles WHERE tenant_id IS NULL AND code = NEW.code
            ) THEN
                RAISE EXCEPTION 'el codigo % pertenece a un rol del sistema', NEW.code
                    USING ERRCODE = 'unique_violation';
            END IF;
            RETURN NEW;
        END $$;


ALTER FUNCTION public.app_rol_no_pisa_al_sistema() OWNER TO wiseadmin;

--
-- Name: app_usuario_por_sub(text); Type: FUNCTION; Schema: public; Owner: wiseadmin
--

CREATE FUNCTION public.app_usuario_por_sub(p_sub text) RETURNS uuid
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
            SELECT id FROM users WHERE cognito_sub = p_sub AND is_active
        $$;


ALTER FUNCTION public.app_usuario_por_sub(p_sub text) OWNER TO wiseadmin;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: wiseadmin
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO wiseadmin;

--
-- Name: alembic_version_extraccion; Type: TABLE; Schema: public; Owner: wiseadmin
--

CREATE TABLE public.alembic_version_extraccion (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version_extraccion OWNER TO wiseadmin;

--
-- Name: auditoria; Type: TABLE; Schema: public; Owner: wiseadmin
--

CREATE TABLE public.auditoria (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    ocurrido_en timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid,
    rol character varying(50),
    origen character varying(20) DEFAULT 'usuario'::character varying NOT NULL,
    modulo character varying(50) NOT NULL,
    accion character varying(100) NOT NULL,
    resultado character varying(20) DEFAULT 'exito'::character varying NOT NULL,
    detalle text,
    objeto_tipo character varying(50),
    objeto_id uuid,
    cliente_id uuid,
    compromiso_id uuid,
    formato character varying(20),
    ip inet,
    sesion character varying(100),
    metodo_ingreso character varying(50),
    contingencia boolean DEFAULT false NOT NULL,
    valor_anterior jsonb,
    valor_nuevo jsonb,
    CONSTRAINT ck_auditoria_origen CHECK (((origen)::text = ANY ((ARRAY['usuario'::character varying, 'sistema'::character varying])::text[]))),
    CONSTRAINT ck_auditoria_resultado CHECK (((resultado)::text = ANY ((ARRAY['exito'::character varying, 'error'::character varying, 'denegado'::character varying])::text[])))
);


ALTER TABLE public.auditoria OWNER TO wiseadmin;

--
-- Name: consentimientos; Type: TABLE; Schema: public; Owner: wiseadmin
--

CREATE TABLE public.consentimientos (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    politica_version integer NOT NULL,
    aceptado_en timestamp with time zone DEFAULT now() NOT NULL,
    ip inet,
    agente character varying(500)
);


ALTER TABLE public.consentimientos OWNER TO wiseadmin;

--
-- Name: extracciones; Type: TABLE; Schema: public; Owner: wiseadmin
--

CREATE TABLE public.extracciones (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    tipo character varying(40) NOT NULL,
    estado character varying(20) NOT NULL,
    archivo_nombre character varying(255),
    archivo_tipo character varying(100) NOT NULL,
    archivo_bytes integer NOT NULL,
    archivo_sha256 character varying(64) NOT NULL,
    modelo character varying(80) NOT NULL,
    duracion_ms integer,
    datos jsonb,
    advertencias jsonb DEFAULT '[]'::jsonb NOT NULL,
    error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_extracciones_estado CHECK (((estado)::text = ANY ((ARRAY['ok'::character varying, 'error'::character varying])::text[])))
);


ALTER TABLE public.extracciones OWNER TO wiseadmin;

--
-- Name: membership_roles; Type: TABLE; Schema: public; Owner: wiseadmin
--

CREATE TABLE public.membership_roles (
    membership_id uuid NOT NULL,
    role_id uuid NOT NULL
);


ALTER TABLE public.membership_roles OWNER TO wiseadmin;

--
-- Name: memberships; Type: TABLE; Schema: public; Owner: wiseadmin
--

CREATE TABLE public.memberships (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_memberships_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'invited'::character varying, 'revoked'::character varying])::text[])))
);


ALTER TABLE public.memberships OWNER TO wiseadmin;

--
-- Name: permissions; Type: TABLE; Schema: public; Owner: wiseadmin
--

CREATE TABLE public.permissions (
    code character varying(100) NOT NULL,
    description character varying(300)
);


ALTER TABLE public.permissions OWNER TO wiseadmin;

--
-- Name: politicas_privacidad; Type: TABLE; Schema: public; Owner: wiseadmin
--

CREATE TABLE public.politicas_privacidad (
    version integer NOT NULL,
    resumen text NOT NULL,
    url character varying(500),
    vigente_desde timestamp with time zone DEFAULT now() NOT NULL,
    vigente boolean DEFAULT true NOT NULL
);


ALTER TABLE public.politicas_privacidad OWNER TO wiseadmin;

--
-- Name: politicas_privacidad_version_seq; Type: SEQUENCE; Schema: public; Owner: wiseadmin
--

CREATE SEQUENCE public.politicas_privacidad_version_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.politicas_privacidad_version_seq OWNER TO wiseadmin;

--
-- Name: politicas_privacidad_version_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: wiseadmin
--

ALTER SEQUENCE public.politicas_privacidad_version_seq OWNED BY public.politicas_privacidad.version;


--
-- Name: role_permissions; Type: TABLE; Schema: public; Owner: wiseadmin
--

CREATE TABLE public.role_permissions (
    role_id uuid NOT NULL,
    permission_code character varying(100) NOT NULL
);


ALTER TABLE public.role_permissions OWNER TO wiseadmin;

--
-- Name: roles; Type: TABLE; Schema: public; Owner: wiseadmin
--

CREATE TABLE public.roles (
    id uuid NOT NULL,
    tenant_id uuid,
    code character varying(50) NOT NULL,
    name character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.roles OWNER TO wiseadmin;

--
-- Name: tenants; Type: TABLE; Schema: public; Owner: wiseadmin
--

CREATE TABLE public.tenants (
    id uuid NOT NULL,
    slug character varying(63) NOT NULL,
    name character varying(200) NOT NULL,
    kind character varying(20) DEFAULT 'client'::character varying NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_tenants_kind CHECK (((kind)::text = ANY ((ARRAY['internal'::character varying, 'client'::character varying])::text[]))),
    CONSTRAINT ck_tenants_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'suspended'::character varying])::text[])))
);


ALTER TABLE public.tenants OWNER TO wiseadmin;

--
-- Name: users; Type: TABLE; Schema: public; Owner: wiseadmin
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    cognito_sub character varying(64),
    email character varying(320) NOT NULL,
    full_name character varying(200),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.users OWNER TO wiseadmin;

--
-- Name: politicas_privacidad version; Type: DEFAULT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.politicas_privacidad ALTER COLUMN version SET DEFAULT nextval('public.politicas_privacidad_version_seq'::regclass);


--
-- Name: alembic_version_extraccion alembic_version_extraccion_pkc; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.alembic_version_extraccion
    ADD CONSTRAINT alembic_version_extraccion_pkc PRIMARY KEY (version_num);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: auditoria auditoria_pkey; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.auditoria
    ADD CONSTRAINT auditoria_pkey PRIMARY KEY (id);


--
-- Name: consentimientos consentimientos_pkey; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.consentimientos
    ADD CONSTRAINT consentimientos_pkey PRIMARY KEY (id);


--
-- Name: extracciones extracciones_pkey; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.extracciones
    ADD CONSTRAINT extracciones_pkey PRIMARY KEY (id);


--
-- Name: membership_roles membership_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.membership_roles
    ADD CONSTRAINT membership_roles_pkey PRIMARY KEY (membership_id, role_id);


--
-- Name: memberships memberships_pkey; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_pkey PRIMARY KEY (id);


--
-- Name: permissions permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_pkey PRIMARY KEY (code);


--
-- Name: politicas_privacidad politicas_privacidad_pkey; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.politicas_privacidad
    ADD CONSTRAINT politicas_privacidad_pkey PRIMARY KEY (version);


--
-- Name: role_permissions role_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_pkey PRIMARY KEY (role_id, permission_code);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--
-- Name: tenants tenants_pkey; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);


--
-- Name: tenants tenants_slug_key; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_slug_key UNIQUE (slug);


--
-- Name: consentimientos uq_consentimiento; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.consentimientos
    ADD CONSTRAINT uq_consentimiento UNIQUE (user_id, politica_version);


--
-- Name: memberships uq_memberships_user_tenant; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT uq_memberships_user_tenant UNIQUE (user_id, tenant_id);


--
-- Name: roles uq_roles_tenant_code; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT uq_roles_tenant_code UNIQUE (tenant_id, code);


--
-- Name: users users_cognito_sub_key; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_cognito_sub_key UNIQUE (cognito_sub);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_auditoria_objeto; Type: INDEX; Schema: public; Owner: wiseadmin
--

CREATE INDEX ix_auditoria_objeto ON public.auditoria USING btree (objeto_tipo, objeto_id);


--
-- Name: ix_auditoria_tenant_fecha; Type: INDEX; Schema: public; Owner: wiseadmin
--

CREATE INDEX ix_auditoria_tenant_fecha ON public.auditoria USING btree (tenant_id, ocurrido_en DESC);


--
-- Name: ix_auditoria_usuario; Type: INDEX; Schema: public; Owner: wiseadmin
--

CREATE INDEX ix_auditoria_usuario ON public.auditoria USING btree (user_id, ocurrido_en DESC);


--
-- Name: ix_extracciones_tenant_fecha; Type: INDEX; Schema: public; Owner: wiseadmin
--

CREATE INDEX ix_extracciones_tenant_fecha ON public.extracciones USING btree (tenant_id, created_at DESC);


--
-- Name: ix_extracciones_tenant_sha; Type: INDEX; Schema: public; Owner: wiseadmin
--

CREATE INDEX ix_extracciones_tenant_sha ON public.extracciones USING btree (tenant_id, archivo_sha256);


--
-- Name: ix_politica_vigente; Type: INDEX; Schema: public; Owner: wiseadmin
--

CREATE UNIQUE INDEX ix_politica_vigente ON public.politicas_privacidad USING btree (vigente) WHERE vigente;


--
-- Name: ix_users_cognito_sub; Type: INDEX; Schema: public; Owner: wiseadmin
--

CREATE INDEX ix_users_cognito_sub ON public.users USING btree (cognito_sub);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: wiseadmin
--

CREATE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: roles tg_rol_no_pisa_al_sistema; Type: TRIGGER; Schema: public; Owner: wiseadmin
--

CREATE TRIGGER tg_rol_no_pisa_al_sistema BEFORE INSERT OR UPDATE OF code, tenant_id ON public.roles FOR EACH ROW EXECUTE FUNCTION public.app_rol_no_pisa_al_sistema();


--
-- Name: consentimientos consentimientos_politica_version_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.consentimientos
    ADD CONSTRAINT consentimientos_politica_version_fkey FOREIGN KEY (politica_version) REFERENCES public.politicas_privacidad(version);


--
-- Name: consentimientos consentimientos_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.consentimientos
    ADD CONSTRAINT consentimientos_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: extracciones extracciones_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.extracciones
    ADD CONSTRAINT extracciones_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: extracciones extracciones_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.extracciones
    ADD CONSTRAINT extracciones_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: membership_roles membership_roles_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.membership_roles
    ADD CONSTRAINT membership_roles_membership_id_fkey FOREIGN KEY (membership_id) REFERENCES public.memberships(id) ON DELETE CASCADE;


--
-- Name: membership_roles membership_roles_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.membership_roles
    ADD CONSTRAINT membership_roles_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: memberships memberships_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: memberships memberships_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: role_permissions role_permissions_permission_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_permission_code_fkey FOREIGN KEY (permission_code) REFERENCES public.permissions(code) ON DELETE CASCADE;


--
-- Name: role_permissions role_permissions_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: roles roles_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wiseadmin
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: auditoria; Type: ROW SECURITY; Schema: public; Owner: wiseadmin
--

ALTER TABLE public.auditoria ENABLE ROW LEVEL SECURITY;

--
-- Name: auditoria auditoria_aislamiento; Type: POLICY; Schema: public; Owner: wiseadmin
--

CREATE POLICY auditoria_aislamiento ON public.auditoria USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


--
-- Name: consentimientos; Type: ROW SECURITY; Schema: public; Owner: wiseadmin
--

ALTER TABLE public.consentimientos ENABLE ROW LEVEL SECURITY;

--
-- Name: consentimientos consentimientos_aislamiento; Type: POLICY; Schema: public; Owner: wiseadmin
--

CREATE POLICY consentimientos_aislamiento ON public.consentimientos USING (((user_id = (NULLIF(current_setting('app.user_id'::text, true), ''::text))::uuid) OR (EXISTS ( SELECT 1
   FROM public.memberships m
  WHERE ((m.user_id = consentimientos.user_id) AND (m.tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))))));


--
-- Name: extracciones; Type: ROW SECURITY; Schema: public; Owner: wiseadmin
--

ALTER TABLE public.extracciones ENABLE ROW LEVEL SECURITY;

--
-- Name: extracciones extracciones_aislamiento; Type: POLICY; Schema: public; Owner: wiseadmin
--

CREATE POLICY extracciones_aislamiento ON public.extracciones USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


--
-- Name: membership_roles; Type: ROW SECURITY; Schema: public; Owner: wiseadmin
--

ALTER TABLE public.membership_roles ENABLE ROW LEVEL SECURITY;

--
-- Name: membership_roles membership_roles_aislamiento; Type: POLICY; Schema: public; Owner: wiseadmin
--

CREATE POLICY membership_roles_aislamiento ON public.membership_roles USING ((EXISTS ( SELECT 1
   FROM public.memberships m
  WHERE ((m.id = membership_roles.membership_id) AND ((m.user_id = (NULLIF(current_setting('app.user_id'::text, true), ''::text))::uuid) OR (m.tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))))));


--
-- Name: memberships; Type: ROW SECURITY; Schema: public; Owner: wiseadmin
--

ALTER TABLE public.memberships ENABLE ROW LEVEL SECURITY;

--
-- Name: memberships memberships_aislamiento; Type: POLICY; Schema: public; Owner: wiseadmin
--

CREATE POLICY memberships_aislamiento ON public.memberships USING (((user_id = (NULLIF(current_setting('app.user_id'::text, true), ''::text))::uuid) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: roles; Type: ROW SECURITY; Schema: public; Owner: wiseadmin
--

ALTER TABLE public.roles ENABLE ROW LEVEL SECURITY;

--
-- Name: roles roles_aislamiento; Type: POLICY; Schema: public; Owner: wiseadmin
--

CREATE POLICY roles_aislamiento ON public.roles USING (((tenant_id IS NULL) OR (tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)));


--
-- Name: tenants; Type: ROW SECURITY; Schema: public; Owner: wiseadmin
--

ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;

--
-- Name: tenants tenants_aislamiento; Type: POLICY; Schema: public; Owner: wiseadmin
--

CREATE POLICY tenants_aislamiento ON public.tenants USING (((id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid) OR public.app_es_miembro(id)));


--
-- Name: users; Type: ROW SECURITY; Schema: public; Owner: wiseadmin
--

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

--
-- Name: users users_aislamiento; Type: POLICY; Schema: public; Owner: wiseadmin
--

CREATE POLICY users_aislamiento ON public.users USING (((id = (NULLIF(current_setting('app.user_id'::text, true), ''::text))::uuid) OR (EXISTS ( SELECT 1
   FROM public.memberships m
  WHERE ((m.user_id = users.id) AND (m.tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))))));


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: pg_database_owner
--

GRANT USAGE ON SCHEMA public TO wiseerp_ro;
GRANT ALL ON SCHEMA public TO wiseerp_rw;
GRANT USAGE ON SCHEMA public TO wiseerp_app;


--
-- Name: FUNCTION app_crear_organizacion(p_slug text, p_nombre text, p_admin uuid); Type: ACL; Schema: public; Owner: wiseadmin
--

REVOKE ALL ON FUNCTION public.app_crear_organizacion(p_slug text, p_nombre text, p_admin uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION public.app_crear_organizacion(p_slug text, p_nombre text, p_admin uuid) TO wiseerp_app;


--
-- Name: FUNCTION app_crear_usuario(p_email text, p_nombre text, p_sub text); Type: ACL; Schema: public; Owner: wiseadmin
--

REVOKE ALL ON FUNCTION public.app_crear_usuario(p_email text, p_nombre text, p_sub text) FROM PUBLIC;
GRANT ALL ON FUNCTION public.app_crear_usuario(p_email text, p_nombre text, p_sub text) TO wiseerp_app;


--
-- Name: FUNCTION app_es_miembro(p_tenant uuid); Type: ACL; Schema: public; Owner: wiseadmin
--

REVOKE ALL ON FUNCTION public.app_es_miembro(p_tenant uuid) FROM PUBLIC;
GRANT ALL ON FUNCTION public.app_es_miembro(p_tenant uuid) TO wiseerp_app;


--
-- Name: FUNCTION app_usuario_por_sub(p_sub text); Type: ACL; Schema: public; Owner: wiseadmin
--

REVOKE ALL ON FUNCTION public.app_usuario_por_sub(p_sub text) FROM PUBLIC;
GRANT ALL ON FUNCTION public.app_usuario_por_sub(p_sub text) TO wiseerp_app;


--
-- Name: TABLE alembic_version; Type: ACL; Schema: public; Owner: wiseadmin
--

GRANT SELECT ON TABLE public.alembic_version TO wiseerp_ro;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.alembic_version TO wiseerp_rw;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.alembic_version TO wiseerp_app;


--
-- Name: TABLE alembic_version_extraccion; Type: ACL; Schema: public; Owner: wiseadmin
--

GRANT SELECT ON TABLE public.alembic_version_extraccion TO wiseerp_ro;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.alembic_version_extraccion TO wiseerp_rw;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.alembic_version_extraccion TO wiseerp_app;


--
-- Name: TABLE auditoria; Type: ACL; Schema: public; Owner: wiseadmin
--

GRANT SELECT ON TABLE public.auditoria TO wiseerp_ro;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.auditoria TO wiseerp_rw;
GRANT SELECT,INSERT ON TABLE public.auditoria TO wiseerp_app;


--
-- Name: TABLE consentimientos; Type: ACL; Schema: public; Owner: wiseadmin
--

GRANT SELECT ON TABLE public.consentimientos TO wiseerp_ro;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.consentimientos TO wiseerp_rw;
GRANT SELECT,INSERT ON TABLE public.consentimientos TO wiseerp_app;


--
-- Name: TABLE extracciones; Type: ACL; Schema: public; Owner: wiseadmin
--

GRANT SELECT ON TABLE public.extracciones TO wiseerp_ro;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.extracciones TO wiseerp_rw;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.extracciones TO wiseerp_app;


--
-- Name: TABLE membership_roles; Type: ACL; Schema: public; Owner: wiseadmin
--

GRANT SELECT ON TABLE public.membership_roles TO wiseerp_ro;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.membership_roles TO wiseerp_rw;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.membership_roles TO wiseerp_app;


--
-- Name: TABLE memberships; Type: ACL; Schema: public; Owner: wiseadmin
--

GRANT SELECT ON TABLE public.memberships TO wiseerp_ro;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.memberships TO wiseerp_rw;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.memberships TO wiseerp_app;


--
-- Name: TABLE permissions; Type: ACL; Schema: public; Owner: wiseadmin
--

GRANT SELECT ON TABLE public.permissions TO wiseerp_ro;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.permissions TO wiseerp_rw;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.permissions TO wiseerp_app;


--
-- Name: TABLE politicas_privacidad; Type: ACL; Schema: public; Owner: wiseadmin
--

GRANT SELECT ON TABLE public.politicas_privacidad TO wiseerp_ro;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.politicas_privacidad TO wiseerp_rw;
GRANT SELECT ON TABLE public.politicas_privacidad TO wiseerp_app;


--
-- Name: SEQUENCE politicas_privacidad_version_seq; Type: ACL; Schema: public; Owner: wiseadmin
--

GRANT SELECT,USAGE ON SEQUENCE public.politicas_privacidad_version_seq TO wiseerp_rw;
GRANT SELECT,USAGE ON SEQUENCE public.politicas_privacidad_version_seq TO wiseerp_app;


--
-- Name: TABLE role_permissions; Type: ACL; Schema: public; Owner: wiseadmin
--

GRANT SELECT ON TABLE public.role_permissions TO wiseerp_ro;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.role_permissions TO wiseerp_rw;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.role_permissions TO wiseerp_app;


--
-- Name: TABLE roles; Type: ACL; Schema: public; Owner: wiseadmin
--

GRANT SELECT ON TABLE public.roles TO wiseerp_ro;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.roles TO wiseerp_rw;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.roles TO wiseerp_app;


--
-- Name: TABLE tenants; Type: ACL; Schema: public; Owner: wiseadmin
--

GRANT SELECT ON TABLE public.tenants TO wiseerp_ro;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tenants TO wiseerp_rw;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tenants TO wiseerp_app;


--
-- Name: TABLE users; Type: ACL; Schema: public; Owner: wiseadmin
--

GRANT SELECT ON TABLE public.users TO wiseerp_ro;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.users TO wiseerp_rw;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.users TO wiseerp_app;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: public; Owner: wiseadmin
--

ALTER DEFAULT PRIVILEGES FOR ROLE wiseadmin IN SCHEMA public GRANT SELECT,USAGE ON SEQUENCES TO wiseerp_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE wiseadmin IN SCHEMA public GRANT SELECT,USAGE ON SEQUENCES TO wiseerp_app;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: public; Owner: wiseadmin
--

ALTER DEFAULT PRIVILEGES FOR ROLE wiseadmin IN SCHEMA public GRANT SELECT ON TABLES TO wiseerp_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE wiseadmin IN SCHEMA public GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO wiseerp_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE wiseadmin IN SCHEMA public GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO wiseerp_app;


--
-- PostgreSQL database dump complete
--


