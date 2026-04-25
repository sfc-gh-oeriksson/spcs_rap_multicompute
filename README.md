# SPCS Top Clerks Demo

A three-service Snowpark Container Services (SPCS) application that demonstrates role-based row-level security using Snowflake Row Access Policies. Users can switch between two data roles in the UI; the backend opens a fresh Snowflake session with the chosen role, causing the Row Access Policy to filter the underlying data automatically.

**Live app:** `https://bwae3fb-sfseeurope-sto-demo07.snowflakecomputing.app`  
**Account:** `sfseeurope-sto-demo07` (EU North 1, AWS)

---

## What the app does

The app shows the *Top N Clerks by total order value* from the TPCH SF10 sample dataset, filtered by a date range and a Snowflake role:

| Role | Data visible |
|---|---|
| `EAP_ROLE1` | Orders dated **before 1995-01-01** |
| `EAP_ROLE2` | Orders dated **1995-01-01 and later** |

The table displays `O_CLERK`, `CLERK_TOTAL`, `EARLIEST_ORDER`, and `LATEST_ORDER`. The date columns make the role boundary immediately visible: switching roles changes the date range in the results.

---

## Architecture

Three containers, three separate services, two compute pools:

```
Browser
  │
  ▼
┌─────────────────────────────────┐  Snowflake auth proxy (public endpoint)
│  ROUTER service                 │  Compute pool: EAP_FRONTEND_POOL
│  nginx reverse proxy            │
│  /        → frontend:8080       │
│  /api      → backend:8081       │
└─────────┬───────────────────────┘
          │ internal network (same DB/schema)
    ┌─────┴──────┐       ┌──────────────────┐
    │  FRONTEND  │       │  BACKEND         │
    │  Vue 2 +   │       │  Flask +         │
    │  Vuetify 2 │       │  Snowpark Python │
    │  port 8080 │       │  port 8081       │
    │  EAP_FRONTEND_POOL │  EAP_BACKEND_POOL│
    └────────────┘       └──────────────────┘
```

The services are split across two compute pools deliberately:
- **EAP_FRONTEND_POOL** hosts the router and frontend — lightweight, CPU_X64_XS
- **EAP_BACKEND_POOL** hosts the backend — can be scaled or upgraded to a GPU or memory-optimised pool independently

Service-to-service DNS works by lowercase service name within the same database/schema: `http://frontend:8080/`, `http://backend:8081/`.

---

## Snowflake infrastructure

### Compute pools

```sql
CREATE COMPUTE POOL EAP_FRONTEND_POOL
  MIN_NODES = 1 MAX_NODES = 1
  INSTANCE_FAMILY = CPU_X64_XS
  AUTO_RESUME = TRUE;

CREATE COMPUTE POOL EAP_BACKEND_POOL
  MIN_NODES = 1 MAX_NODES = 1
  INSTANCE_FAMILY = CPU_X64_XS
  AUTO_RESUME = TRUE;
```

### Database, schema, image repo, stage

```sql
CREATE DATABASE EAP_DEMO;
CREATE SCHEMA EAP_DEMO.PUBLIC;
CREATE IMAGE REPOSITORY EAP_DEMO.PUBLIC.EAP_IMAGES;
CREATE STAGE EAP_DEMO.PUBLIC.EAP_STAGE;
```

### External Access Integration (for Snowflake Logo in app bar)

```sql
CREATE OR REPLACE NETWORK RULE NR_WIKI
  TYPE = HOST_PORT MODE = EGRESS
  VALUE_LIST = ('upload.wikimedia.org');

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION EAI_WIKI
  ALLOWED_NETWORK_RULES = (NR_WIKI)
  ENABLED = TRUE;
```

### Data layer

The app queries a view over the shared TPCH dataset. You cannot attach a Row Access Policy directly to `SNOWFLAKE_SAMPLE_DATA`, so a view is used as the policy target:

```sql
CREATE VIEW EAP_DEMO.PUBLIC.ORDERS_VIEW AS
  SELECT * FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF10.ORDERS;

CREATE OR REPLACE ROW ACCESS POLICY EAP_DEMO.PUBLIC.RAP_ORDERS_BY_ROLE
  AS (order_date DATE) RETURNS BOOLEAN ->
    CASE
      WHEN CURRENT_ROLE() = 'EAP_ROLE1' THEN order_date < '1995-01-01'
      WHEN CURRENT_ROLE() = 'EAP_ROLE2' THEN order_date >= '1995-01-01'
      WHEN IS_ROLE_IN_SESSION('ACCOUNTADMIN') THEN TRUE
      ELSE FALSE
    END;

ALTER VIEW EAP_DEMO.PUBLIC.ORDERS_VIEW
  ADD ROW ACCESS POLICY EAP_DEMO.PUBLIC.RAP_ORDERS_BY_ROLE ON (O_ORDERDATE);
```

### Roles and users

```sql
-- Roles
CREATE ROLE EAP_ROLE1;
CREATE ROLE EAP_ROLE2;

-- Grant data access to each role
GRANT USAGE ON DATABASE EAP_DEMO TO ROLE EAP_ROLE1;
GRANT USAGE ON SCHEMA EAP_DEMO.PUBLIC TO ROLE EAP_ROLE1;
GRANT SELECT ON VIEW EAP_DEMO.PUBLIC.ORDERS_VIEW TO ROLE EAP_ROLE1;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE EAP_ROLE1;
-- (repeat for EAP_ROLE2)

-- Grant app endpoint access
GRANT USAGE ON SERVICE ROLE EAP_DEMO.PUBLIC.ROUTER.APP TO ROLE EAP_ROLE1;
GRANT USAGE ON SERVICE ROLE EAP_DEMO.PUBLIC.ROUTER.APP TO ROLE EAP_ROLE2;

-- Allow the service (ACCOUNTADMIN) to switch into these roles
GRANT ROLE EAP_ROLE1 TO ROLE ACCOUNTADMIN;
GRANT ROLE EAP_ROLE2 TO ROLE ACCOUNTADMIN;

-- Demo users (secondary roles disabled so only the active role is in session)
CREATE USER EAP_USER1 PASSWORD='...' DEFAULT_ROLE=EAP_ROLE1;
CREATE USER EAP_USER2 PASSWORD='...' DEFAULT_ROLE=EAP_ROLE2;
ALTER USER EAP_USER1 SET DEFAULT_SECONDARY_ROLES = ();
ALTER USER EAP_USER2 SET DEFAULT_SECONDARY_ROLES = ();
GRANT ROLE EAP_ROLE1 TO USER EAP_USER1;
GRANT ROLE EAP_ROLE2 TO USER EAP_USER1;
GRANT ROLE EAP_ROLE1 TO USER EAP_USER2;
GRANT ROLE EAP_ROLE2 TO USER EAP_USER2;
```

---

## Build and deploy

### 1. Authenticate to the image registry

```bash
snow spcs image-registry login --connection <your-connection>
```

### 2. Set the registry URL in the Makefile

Edit the `REPO` variable at the top of `Makefile`:

```makefile
REPO?=<account>.registry.snowflakecomputing.com/eap_demo/public/eap_images
```

### 3. Build and push all images

```bash
make build   # builds eap_backend, eap_frontend, eap_router
make push    # tags and pushes all three to the Snowflake registry
```

> **Important:** The generated service YAML files must include `:latest` on every image path. SPCS will reject an image reference without an explicit tag.

### 4. Upload service specs to stage

```bash
snow sql -q "PUT file://backend.yaml  @EAP_DEMO.PUBLIC.EAP_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"
snow sql -q "PUT file://frontend.yaml @EAP_DEMO.PUBLIC.EAP_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"
snow sql -q "PUT file://router.yaml   @EAP_DEMO.PUBLIC.EAP_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"
```

### 5. Create the services

```sql
CREATE SERVICE EAP_DEMO.PUBLIC.BACKEND
  IN COMPUTE POOL EAP_BACKEND_POOL
  FROM @EAP_DEMO.PUBLIC.EAP_STAGE SPECIFICATION_FILE='backend.yaml';

CREATE SERVICE EAP_DEMO.PUBLIC.FRONTEND
  IN COMPUTE POOL EAP_FRONTEND_POOL
  FROM @EAP_DEMO.PUBLIC.EAP_STAGE SPECIFICATION_FILE='frontend.yaml';

CREATE SERVICE EAP_DEMO.PUBLIC.ROUTER
  IN COMPUTE POOL EAP_FRONTEND_POOL
  FROM @EAP_DEMO.PUBLIC.EAP_STAGE SPECIFICATION_FILE='router.yaml'
  EXTERNAL_ACCESS_INTEGRATIONS = (EAI_WIKI);
```

### Updating a running service

`ALTER SERVICE SUSPEND / RESUME` does **not** re-pull a `:latest` image. To force a fresh pull:

```sql
ALTER SERVICE EAP_DEMO.PUBLIC.BACKEND
  FROM @EAP_DEMO.PUBLIC.EAP_STAGE SPECIFICATION_FILE='backend.yaml';
```

---

## Verifying separate compute pools

### Check which pool each service runs in

```sql
SHOW SERVICES IN SCHEMA EAP_DEMO.PUBLIC;
```

Look at the `compute_pool` column. You should see:

| name | compute_pool |
|---|---|
| BACKEND | EAP_BACKEND_POOL |
| FRONTEND | EAP_FRONTEND_POOL |
| ROUTER | EAP_FRONTEND_POOL |

### Confirm the pools exist and are active

```sql
SHOW COMPUTE POOLS;
```

### Confirm the container is actually running on the pool node

```sql
SELECT PARSE_JSON(SYSTEM$GET_SERVICE_STATUS('EAP_DEMO.PUBLIC.BACKEND'));
SELECT PARSE_JSON(SYSTEM$GET_SERVICE_STATUS('EAP_DEMO.PUBLIC.FRONTEND'));
SELECT PARSE_JSON(SYSTEM$GET_SERVICE_STATUS('EAP_DEMO.PUBLIC.ROUTER'));
```

Each response includes `"status":"READY"`, `"startTime"`, and `"restartCount"`.

### Read container logs

```sql
-- backend
SELECT SYSTEM$GET_SERVICE_LOGS('EAP_DEMO.PUBLIC.BACKEND',  0, 'eap-backend',  50);
-- frontend
SELECT SYSTEM$GET_SERVICE_LOGS('EAP_DEMO.PUBLIC.FRONTEND', 0, 'eap-frontend', 50);
-- router (nginx config + access log)
SELECT SYSTEM$GET_SERVICE_LOGS('EAP_DEMO.PUBLIC.ROUTER',   0, 'router',       50);
```

### Verify the RAP is active and attached

```sql
-- Check policy body
DESCRIBE ROW ACCESS POLICY EAP_DEMO.PUBLIC.RAP_ORDERS_BY_ROLE;

-- Confirm it is attached to the view
SELECT REF_ENTITY_NAME, REF_COLUMN_NAME, POLICY_STATUS
FROM TABLE(EAP_DEMO.INFORMATION_SCHEMA.POLICY_REFERENCES(
  POLICY_NAME => 'EAP_DEMO.PUBLIC.RAP_ORDERS_BY_ROLE'));

-- Test filtering per role (requires the roles to be granted to your user)
USE ROLE EAP_ROLE1;
SELECT CURRENT_ROLE(), MIN(O_ORDERDATE), MAX(O_ORDERDATE), COUNT(*)
FROM EAP_DEMO.PUBLIC.ORDERS_VIEW;
-- Expected: max date = 1994-12-31, count = 6,833,762

USE ROLE EAP_ROLE2;
SELECT CURRENT_ROLE(), MIN(O_ORDERDATE), MAX(O_ORDERDATE), COUNT(*)
FROM EAP_DEMO.PUBLIC.ORDERS_VIEW;
-- Expected: min date = 1995-01-01, count = 8,166,238

USE ROLE ACCOUNTADMIN;
```

---

## Authentication

### How SPCS service authentication works

Every container in SPCS receives a **service OAuth token** at `/snowflake/session/token`. This token is minted by Snowflake at service startup and grants the Snowflake session with the **service owner's role** (ACCOUNTADMIN in this demo). It is refreshed automatically and does not expire during normal service operation.

The backend reads this token at module load time and holds a long-lived `_service_session`:

```python
# connection.py
token = open('/snowflake/session/token', 'r').read()
creds = {
    'authenticator': "oauth",
    'token': token,
    ...
}
conn = snowflake.connector.connect(**creds)
```

Environment variables injected automatically by SPCS (no need to set in the service spec):
- `SNOWFLAKE_HOST` — account hostname
- `SNOWFLAKE_PORT` — 443
- `SNOWFLAKE_ACCOUNT` — account identifier

### Role-switching for Row Access Policy enforcement

The Row Access Policy uses `CURRENT_ROLE()` to decide which rows to expose. For the policy to filter correctly, every data query must run under the role matching the user's selection (`EAP_ROLE1` or `EAP_ROLE2`).

The backend opens a **fresh Snowflake connection per request** when a role is selected, setting the role at connection time (not via `USE ROLE` after connecting, which can be discarded when Snowpark wraps the connection into a Session):

```python
# connection.py — session_for_role()
creds = {
    'authenticator': "oauth",
    'token': open('/snowflake/session/token', 'r').read(),
    'role': role,   # <-- set at connection establishment
    ...
}
conn = snowflake.connector.connect(**creds)
return Session.builder.configs({"connection": conn}).create()
```

This means `CURRENT_ROLE()` returns `EAP_ROLE1` or `EAP_ROLE2` inside the session, and the RAP filters accordingly.

### Why per-user OAuth tokens are not used

SPCS can inject a per-user OAuth token via the `Sf-Context-Current-User-Token` request header, which would allow each query to run as the connecting user's identity (caller's rights). The backend code supports this path:

```python
# snowpark.py
user_token = request.headers.get('Sf-Context-Current-User-Token')
if user_token:
    return session_with_user_token(user_token, role), True   # caller's rights
if role:
    return session_for_role(role), True                      # service token, explicit role
return _service_session, False                               # service token, owner's rights
```

In this deployment the SPCS proxy does not inject the user token header (confirmed via the `token_present=False` diagnostic log). The fallback path (`session_for_role`) is therefore always used. This is transparent to the RAP — the role is still set correctly, so the filtering behaves identically.

**Security implication:** With `session_for_role`, the role is chosen by the client-supplied `role` query parameter. The backend validates it against an explicit allowlist before using it:

```python
ALLOWED_ROLES = {'EAP_ROLE1', 'EAP_ROLE2'}
role = role_param if role_param in ALLOWED_ROLES else None
```

Any value outside the allowlist is silently ignored and the default service session (ACCOUNTADMIN) is used, which sees all data.

### Header forwarding through the nginx router

Because the router and backend are separate services, the nginx reverse proxy must explicitly forward Snowflake's context headers. Without this, the backend never receives them:

```nginx
location /api {
    rewrite /api/(.*) /$1 break;
    proxy_pass http://backend:8081/;
    proxy_set_header Sf-Context-Current-User       $http_sf_context_current_user;
    proxy_set_header Sf-Context-Current-User-Token $http_sf_context_current_user_token;
}
```

This is generated dynamically at container start by `router/src/entrypoint.sh`.

---

## File structure

```
spcs_app_python-main/
├── Makefile                         # build / push targets
├── backend.yaml                     # SPCS service spec — backend
├── frontend.yaml                    # SPCS service spec — frontend
├── router.yaml                      # SPCS service spec — router (public endpoint)
├── backend/
│   ├── Dockerfile
│   └── src/
│       ├── app.py                   # Flask app entry point
│       ├── entrypoint.sh
│       ├── snowpark.py              # /whoami and /top_clerks endpoints
│       └── spcs_helpers/
│           ├── __init__.py
│           └── connection.py        # Snowflake connection factory
└── frontend/
    ├── Dockerfile
    └── vue/
        ├── entrypoint.sh            # npm run serve -- --host 0.0.0.0
        └── src/
            ├── App.vue              # App bar, user chip, role switcher
            └── components/
                └── TopClerks.vue    # Date picker, TopN slider, results table
router/
├── Dockerfile
└── src/
    └── entrypoint.sh                # Generates nginx.conf with proxy_set_header
```
