# CheckoutOS — Microservices Checkout Platform

A five-service Python/Flask application demonstrating gateway routing,
inter-service HTTP orchestration, inventory reservation, deterministic pricing,
and PostgreSQL audit persistence.

---

## Architecture

```
                        ┌─────────────────────────────┐
      Browser / curl    │         GATEWAY :5000        │  ← public entrypoint
         ───────────►   │  GET /   POST /api/checkout  │
                        │  GET /api/ping  /api/arch    │
                        └──────────────┬──────────────┘
                                       │ HTTP
                        ┌──────────────▼──────────────┐
                        │       CHECKOUT :5001         │
                        │  validates → prices → reserves│
                        │  → writes Postgres audit row  │
                        └──────┬─────────────┬─────────┘
                               │             │
               ┌───────────────▼──┐   ┌──────▼──────────┐
               │  PRICING :5002   │   │ INVENTORY :5003  │
               │  POST /price     │   │  POST /reserve   │
               └──────────────────┘   └─────────────────┘

                        ┌─────────────────────────────┐
                        │       QUOTE :5004            │  ← independent
                        │  GET /quote (preview only)   │
                        └─────────────────────────────┘

                        ┌─────────────────────────────┐
                        │      PostgreSQL :5432        │
                        │  table: checkout_audit       │
                        └─────────────────────────────┘
```

---

## Quick start — Docker Compose (recommended)

```bash
# 1. Clone / unzip the project
cd checkout-app

# 2. Build and start all services
docker compose up --build

# 3. Open the UI
open http://localhost:5000

# 4. Tear down (add -v to also remove the Postgres volume)
docker compose down
docker compose down -v
```

All services start in dependency order. Postgres health-check ensures the
checkout service only starts once the DB is ready.

---

## Quick start — Local processes (no Docker)

### Prerequisites

- Python 3.11+
- A running PostgreSQL instance
- (optional) `virtualenv` or `pyenv`

### 1. Create the database

```sql
CREATE DATABASE checkoutdb;
CREATE USER checkoutuser WITH PASSWORD 'checkoutpass';
GRANT ALL PRIVILEGES ON DATABASE checkoutdb TO checkoutuser;
-- also grant schema privileges (Postgres 15+)
\c checkoutdb
GRANT ALL ON SCHEMA public TO checkoutuser;
```

Apply the schema:
```bash
psql -U checkoutuser -d checkoutdb -f db/init.sql
```

### 2. Install dependencies per service

```bash
for svc in gateway checkout pricing inventory quote; do
  python -m venv $svc/.venv
  source $svc/.venv/bin/activate
  pip install -r $svc/requirements.txt
  deactivate
done
```

Or share a single venv (install all requirements):
```bash
python -m venv .venv && source .venv/bin/activate
pip install flask requests psycopg2-binary gunicorn
```

### 3. Set environment variables

```bash
cp .env.example .env
# edit .env if your Postgres credentials differ
export $(grep -v '^#' .env | xargs)
```

### 4. Start each service in a separate terminal

**Terminal 1 — Pricing**
```bash
cd pricing
PORT=5002 python app.py
```

**Terminal 2 — Inventory**
```bash
cd inventory
PORT=5003 python app.py
```

**Terminal 3 — Quote**
```bash
cd quote
PORT=5004 python app.py
```

**Terminal 4 — Checkout**
```bash
cd checkout
PORT=5001 \
PRICING_URL=http://localhost:5002 \
INVENTORY_URL=http://localhost:5003 \
DB_HOST=localhost DB_PORT=5432 DB_NAME=checkoutdb \
DB_USER=checkoutuser DB_PASSWORD=checkoutpass \
python run.py
```

**Terminal 5 — Gateway**
```bash
cd gateway
PORT=5000 \
CHECKOUT_URL=http://localhost:5001 \
QUOTE_URL=http://localhost:5004 \
python app.py
```

Open **http://localhost:5000** in your browser.

---

## Sample requests (curl)

### 1. Happy path checkout

```bash
curl -s -X POST http://localhost:5000/api/checkout \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: req-happy-001" \
  -d '{"customerId": "cust-101", "sku": "SKU-001", "quantity": 2}' \
  | python3 -m json.tool
```

Expected: HTTP 200
```json
{
  "requestId": "req-happy-001",
  "status": "success",
  "sku": "SKU-001",
  "quantity": 2,
  "totalPrice": 50.0,
  "currency": "GBP",
  "inventoryReserved": true,
  "reservationId": "res-xxxxxxxxxx",
  "message": "checkout completed successfully"
}
```

---

### 2. Invalid input — missing SKU

```bash
curl -s -X POST http://localhost:5000/api/checkout \
  -H "Content-Type: application/json" \
  -d '{"customerId": "cust-101", "quantity": 2}' \
  | python3 -m json.tool
```

Expected: HTTP 400
```json
{
  "error": "invalid_request",
  "message": "sku is required"
}
```

---

### 3. Invalid input — bad quantity

```bash
curl -s -X POST http://localhost:5000/api/checkout \
  -H "Content-Type: application/json" \
  -d '{"sku": "SKU-001", "quantity": -1}' \
  | python3 -m json.tool
```

Expected: HTTP 400
```json
{
  "error": "invalid_request",
  "message": "quantity must be greater than zero"
}
```

---

### 4. Out-of-stock (SKU-999 always has 0 stock)

```bash
curl -s -X POST http://localhost:5000/api/checkout \
  -H "Content-Type: application/json" \
  -d '{"customerId": "cust-202", "sku": "SKU-999", "quantity": 1}' \
  | python3 -m json.tool
```

Expected: HTTP 409
```json
{
  "requestId": "...",
  "status": "failed",
  "error": "out_of_stock",
  "message": "Requested quantity is not available (out_of_stock)"
}
```

---

### 5. Simulate dependency timeout / failure

Stop the pricing service (Ctrl-C in its terminal), then:

```bash
curl -s -X POST http://localhost:5000/api/checkout \
  -H "Content-Type: application/json" \
  -d '{"customerId": "cust-303", "sku": "SKU-001", "quantity": 1}' \
  | python3 -m json.tool
```

Expected: HTTP 503
```json
{
  "requestId": "...",
  "status": "failed",
  "error": "dependency_failure",
  "message": "pricing service returned an error or is unavailable"
}
```

---

### 6. Quote preview (no stock reservation)

```bash
curl -s "http://localhost:5000/api/quote?sku=SKU-003&quantity=5" \
  | python3 -m json.tool
```

Expected: HTTP 200
```json
{
  "requestId": "...",
  "sku": "SKU-003",
  "quantity": 5,
  "unitPrice": 49.95,
  "totalPrice": 249.75,
  "currency": "GBP",
  "note": "This is a price preview only. No stock has been reserved."
}
```

---

### 7. Ping

```bash
curl -s http://localhost:5000/api/ping | python3 -m json.tool
```

---

### 8. Architecture summary

```bash
curl -s http://localhost:5000/api/arch | python3 -m json.tool
```

---

### 9. Individual service health checks

```bash
curl -s http://localhost:5001/health   # checkout
curl -s http://localhost:5002/health   # pricing
curl -s http://localhost:5003/health   # inventory
curl -s http://localhost:5004/health   # quote
```

---

### 10. Query audit records directly

```bash
psql -U checkoutuser -d checkoutdb \
  -c "SELECT id, request_id, customer_id, sku, quantity, total_price, created_at FROM checkout_audit ORDER BY created_at DESC LIMIT 10;"
```

---

## SKU reference

| SKU     | Unit Price | Notes                         |
|---------|------------|-------------------------------|
| SKU-001 | £25.00     | Standard item                 |
| SKU-002 | £14.99     | Budget item                   |
| SKU-003 | £49.95     | Mid-range item                |
| SKU-004 | £9.99      | Low-cost item                 |
| SKU-005 | £199.00    | Premium item (only 25 units)  |
| SKU-999 | £0.01      | Always out-of-stock (testing) |
| (other) | £19.99     | Default fallback price        |

---

## Project structure

```
checkout-app/
├── docker-compose.yml
├── .env.example
├── README.md
├── db/
│   └── init.sql
├── gateway/
│   ├── app.py
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── templates/
│   │   └── index.html
│   └── static/
│       └── css/
│           └── style.css
├── checkout/
│   ├── app.py
│   ├── run.py
│   ├── requirements.txt
│   └── Dockerfile
├── pricing/
│   ├── app.py
│   ├── requirements.txt
│   └── Dockerfile
├── inventory/
│   ├── app.py
│   ├── requirements.txt
│   └── Dockerfile
└── quote/
    ├── app.py
    ├── requirements.txt
    └── Dockerfile
```

---

## Environment variables reference

| Variable             | Default                   | Used by              |
|----------------------|---------------------------|----------------------|
| `PORT`               | per-service               | all services         |
| `FLASK_ENV`          | `development`             | all services         |
| `CHECKOUT_URL`       | `http://localhost:5001`   | gateway              |
| `QUOTE_URL`          | `http://localhost:5004`   | gateway              |
| `PRICING_URL`        | `http://localhost:5002`   | checkout             |
| `INVENTORY_URL`      | `http://localhost:5003`   | checkout             |
| `REQUEST_TIMEOUT_MS` | `800`                     | gateway, checkout    |
| `DB_HOST`            | `localhost`               | checkout             |
| `DB_PORT`            | `5432`                    | checkout             |
| `DB_NAME`            | `checkoutdb`              | checkout             |
| `DB_USER`            | `checkoutuser`            | checkout             |
| `DB_PASSWORD`        | `checkoutpass`            | checkout             |
| `CURRENCY`           | `GBP`                     | pricing, quote       |
