CREATE TABLE app.bridge_state (
  id text PRIMARY KEY,
  data jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE app.pending_asks (
  tool_use_id text PRIMARY KEY,
  n integer NOT NULL,
  session_id text NOT NULL,
  name text,
  server text,
  input jsonb NOT NULL,
  thread_id text,
  thread_name text,
  seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX pending_asks_n_idx ON app.pending_asks (n);
CREATE TABLE app.decisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  n integer NOT NULL,
  tool text,
  result text NOT NULL,
  reason text,
  decided_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE app.webhook_events (
  webhook_id text PRIMARY KEY,
  event_type text NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now()
);