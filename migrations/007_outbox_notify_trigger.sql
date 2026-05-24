-- S-I: trigger AFTER INSERT em shared.outbox -> pg_notify('outbox_new', NEW.id::text)
-- Aditivo: polling continua funcionando se NOTIFY for ignorado.
-- Idempotente: CREATE OR REPLACE + DROP IF EXISTS.

CREATE OR REPLACE FUNCTION shared.notify_outbox_new() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  PERFORM pg_notify('outbox_new', NEW.id::text);
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_outbox_notify ON shared.outbox;
CREATE TRIGGER trg_outbox_notify
  AFTER INSERT ON shared.outbox
  FOR EACH ROW
  EXECUTE FUNCTION shared.notify_outbox_new();

-- Comentário documentação
COMMENT ON FUNCTION shared.notify_outbox_new() IS
  'S-I (v4 sprint plan): emite NOTIFY para que cdc_worker acorde imediatamente. Aditivo ao polling.';
