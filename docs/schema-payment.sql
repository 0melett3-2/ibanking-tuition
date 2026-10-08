--
-- PostgreSQL database dump
--

\restrict gWwGHhreb6SOuUDmxYjWTUiP9g0AZiXCvvedRU3JWIK96sCMeP8atiojnFgWDsx

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: accounts; Type: TABLE; Schema: public; Owner: ibanking
--

CREATE TABLE public.accounts (
    id integer NOT NULL,
    user_id integer NOT NULL,
    balance numeric(15,2) NOT NULL,
    CONSTRAINT ck_accounts_balance CHECK ((balance >= (0)::numeric))
);


ALTER TABLE public.accounts OWNER TO ibanking;

--
-- Name: accounts_id_seq; Type: SEQUENCE; Schema: public; Owner: ibanking
--

CREATE SEQUENCE public.accounts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.accounts_id_seq OWNER TO ibanking;

--
-- Name: accounts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ibanking
--

ALTER SEQUENCE public.accounts_id_seq OWNED BY public.accounts.id;


--
-- Name: email_logs; Type: TABLE; Schema: public; Owner: ibanking
--

CREATE TABLE public.email_logs (
    id integer NOT NULL,
    transaction_id integer NOT NULL,
    email_type character varying(20) NOT NULL,
    recipient character varying(100) NOT NULL,
    status character varying(10) NOT NULL,
    attempts integer NOT NULL,
    sent_at timestamp with time zone,
    CONSTRAINT ck_email_logs_status CHECK (((status)::text = ANY ((ARRAY['PENDING'::character varying, 'SENT'::character varying, 'FAILED'::character varying])::text[]))),
    CONSTRAINT ck_email_logs_type CHECK (((email_type)::text = ANY ((ARRAY['OTP'::character varying, 'CONFIRMATION'::character varying])::text[])))
);


ALTER TABLE public.email_logs OWNER TO ibanking;

--
-- Name: email_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: ibanking
--

CREATE SEQUENCE public.email_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.email_logs_id_seq OWNER TO ibanking;

--
-- Name: email_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ibanking
--

ALTER SEQUENCE public.email_logs_id_seq OWNED BY public.email_logs.id;


--
-- Name: otps; Type: TABLE; Schema: public; Owner: ibanking
--

CREATE TABLE public.otps (
    id integer NOT NULL,
    transaction_id integer NOT NULL,
    code_hash character varying(64) NOT NULL,
    status character varying(10) NOT NULL,
    attempts integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_otps_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'USED'::character varying, 'REVOKED'::character varying, 'EXPIRED'::character varying])::text[])))
);


ALTER TABLE public.otps OWNER TO ibanking;

--
-- Name: otps_id_seq; Type: SEQUENCE; Schema: public; Owner: ibanking
--

CREATE SEQUENCE public.otps_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.otps_id_seq OWNER TO ibanking;

--
-- Name: otps_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ibanking
--

ALTER SEQUENCE public.otps_id_seq OWNED BY public.otps.id;


--
-- Name: transactions; Type: TABLE; Schema: public; Owner: ibanking
--

CREATE TABLE public.transactions (
    id integer NOT NULL,
    account_id integer NOT NULL,
    tuition_id integer NOT NULL,
    student_code character varying(20) NOT NULL,
    student_name character varying(100) NOT NULL,
    amount numeric(15,2) NOT NULL,
    status character varying(10) NOT NULL,
    fail_reason character varying(50),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT ck_transactions_amount CHECK ((amount > (0)::numeric)),
    CONSTRAINT ck_transactions_status CHECK (((status)::text = ANY ((ARRAY['PENDING'::character varying, 'DEBITED'::character varying, 'SUCCESS'::character varying, 'FAILED'::character varying, 'EXPIRED'::character varying])::text[])))
);


ALTER TABLE public.transactions OWNER TO ibanking;

--
-- Name: transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: ibanking
--

CREATE SEQUENCE public.transactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.transactions_id_seq OWNER TO ibanking;

--
-- Name: transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ibanking
--

ALTER SEQUENCE public.transactions_id_seq OWNED BY public.transactions.id;


--
-- Name: accounts id; Type: DEFAULT; Schema: public; Owner: ibanking
--

ALTER TABLE ONLY public.accounts ALTER COLUMN id SET DEFAULT nextval('public.accounts_id_seq'::regclass);


--
-- Name: email_logs id; Type: DEFAULT; Schema: public; Owner: ibanking
--

ALTER TABLE ONLY public.email_logs ALTER COLUMN id SET DEFAULT nextval('public.email_logs_id_seq'::regclass);


--
-- Name: otps id; Type: DEFAULT; Schema: public; Owner: ibanking
--

ALTER TABLE ONLY public.otps ALTER COLUMN id SET DEFAULT nextval('public.otps_id_seq'::regclass);


--
-- Name: transactions id; Type: DEFAULT; Schema: public; Owner: ibanking
--

ALTER TABLE ONLY public.transactions ALTER COLUMN id SET DEFAULT nextval('public.transactions_id_seq'::regclass);


--
-- Name: accounts accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: ibanking
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_pkey PRIMARY KEY (id);


--
-- Name: accounts accounts_user_id_key; Type: CONSTRAINT; Schema: public; Owner: ibanking
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_user_id_key UNIQUE (user_id);


--
-- Name: email_logs email_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: ibanking
--

ALTER TABLE ONLY public.email_logs
    ADD CONSTRAINT email_logs_pkey PRIMARY KEY (id);


--
-- Name: otps otps_pkey; Type: CONSTRAINT; Schema: public; Owner: ibanking
--

ALTER TABLE ONLY public.otps
    ADD CONSTRAINT otps_pkey PRIMARY KEY (id);


--
-- Name: transactions transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: ibanking
--

ALTER TABLE ONLY public.transactions
    ADD CONSTRAINT transactions_pkey PRIMARY KEY (id);


--
-- Name: uq_otps_code_active; Type: INDEX; Schema: public; Owner: ibanking
--

CREATE UNIQUE INDEX uq_otps_code_active ON public.otps USING btree (code_hash) WHERE ((status)::text = 'ACTIVE'::text);


--
-- Name: uq_otps_transaction_active; Type: INDEX; Schema: public; Owner: ibanking
--

CREATE UNIQUE INDEX uq_otps_transaction_active ON public.otps USING btree (transaction_id) WHERE ((status)::text = 'ACTIVE'::text);


--
-- Name: uq_transactions_pending; Type: INDEX; Schema: public; Owner: ibanking
--

CREATE UNIQUE INDEX uq_transactions_pending ON public.transactions USING btree (account_id, tuition_id) WHERE ((status)::text = 'PENDING'::text);


--
-- Name: uq_transactions_tuition_paid; Type: INDEX; Schema: public; Owner: ibanking
--

CREATE UNIQUE INDEX uq_transactions_tuition_paid ON public.transactions USING btree (tuition_id) WHERE ((status)::text = ANY ((ARRAY['DEBITED'::character varying, 'SUCCESS'::character varying])::text[]));


--
-- Name: email_logs email_logs_transaction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ibanking
--

ALTER TABLE ONLY public.email_logs
    ADD CONSTRAINT email_logs_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);


--
-- Name: otps otps_transaction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ibanking
--

ALTER TABLE ONLY public.otps
    ADD CONSTRAINT otps_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);


--
-- Name: transactions transactions_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: ibanking
--

ALTER TABLE ONLY public.transactions
    ADD CONSTRAINT transactions_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id);


--
-- PostgreSQL database dump complete
--

\unrestrict gWwGHhreb6SOuUDmxYjWTUiP9g0AZiXCvvedRU3JWIK96sCMeP8atiojnFgWDsx

