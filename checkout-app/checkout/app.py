"""
Checkout Service — orchestrates pricing, inventory, and Postgres persistence.
POST /checkout  → validate → call pricing → call inventory → write DB → respond
GET  /health    → simple liveness check
"""

import os
import uuid
import json
import logging
import time

import requests
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, g

# ── Logging ───────────────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log = {
            "timestamp": self.formatTime(record),
            "service": "checkout",
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra"):
            log.update(record.extra)
        return json.dumps(log)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("checkout")

# ── Config ────────────────────────────────────────────────────────────────────

PRICING_URL   = os.environ.get("PRICING_URL",   "http://localhost:5002")
INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://localhost:5003")
TIMEOUT_MS    = int(os.environ.get("REQUEST_TIMEOUT_MS", "800"))
TIMEOUT_S     = TIMEOUT_MS / 1000.0
PORT          = int(os.environ.get("PORT", "5001"))

DB_HOST     = os.environ.get("DB_HOST",     "localhost")
DB_PORT     = int(os.environ.get("DB_PORT", "5432"))
DB_NAME     = os.environ.get("DB_NAME",     "checkoutdb")
DB_USER     = os.environ.get("DB_USER",     "checkoutuser")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "checkoutpass")

# ── App ───────────────────────────────────────────────────────────────────────

app = Flask(__name__)

# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db_conn():
    """Open a fresh Postgres connection. Called once per successful checkout."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=5,
    )

def ensure_schema():
    """Create the checkout_audit table if it does not exist."""
    sql = """
    CREATE TABLE IF NOT EXISTS checkout_audit (
        id          SERIAL PRIMARY KEY,
        request_id  TEXT         NOT NULL,
        customer_id TEXT,
        sku         TEXT         NOT NULL,
        quantity    INT          NOT NULL,
        total_price NUMERIC(10,2) NOT NULL,
        created_at  TIMESTAMP    DEFAULT NOW()
    );
    """
    try:
        conn = get_db_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        conn.close()
        logger.info("schema ready — checkout_audit table exists")
    except Exception as exc:
        logger.error(f"schema init failed: {exc}")

def insert_audit(request_id, customer_id, sku, quantity, total_price):
    """Insert one audit row for a successful checkout."""
    sql = """
    INSERT INTO checkout_audit (request_id, customer_id, sku, quantity, total_price)
    VALUES (%s, %s, %s, %s, %s)
    """
    conn = get_db_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql, (request_id, customer_id, sku, quantity, total_price))
    conn.close()

# ── Middleware ────────────────────────────────────────────────────────────────

@app.before_request
def attach_request_id():
    g.request_id = request.headers.get("X-Request-Id") or f"co-{uuid.uuid4().hex[:12]}"
    g.start_time = time.time()

@app.after_request
def log_request(response):
    duration_ms = round((time.time() - g.start_time) * 1000, 2)
    logger.info(
        "request completed",
        extra={
            "extra": {
                "request_id": g.request_id,
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            }
        },
    )
    response.headers["X-Request-Id"] = g.request_id
    return response

def _headers():
    return {
        "X-Request-Id": g.request_id,
        "Content-Type": "application/json",
    }

# ── Validation ────────────────────────────────────────────────────────────────

def validate_body(body):
    """Return (error_message | None)."""
    if not body:
        return "request body is missing or not JSON"
    sku = body.get("sku")
    if sku is None:
        return "sku is required"
    if not isinstance(sku, str) or sku.strip() == "":
        return "sku must be a non-empty string"
    qty = body.get("quantity")
    if qty is None:
        return "quantity is required"
    if not isinstance(qty, int):
        return "quantity must be an integer"
    if qty <= 0:
        return "quantity must be greater than zero"
    return None

# ── Service calls ─────────────────────────────────────────────────────────────

def call_pricing(sku, quantity):
    """
    Call pricing service.
    Returns (data_dict, None) on success or (None, error_response_tuple) on failure.
    """
    try:
        resp = requests.post(
            f"{PRICING_URL}/price",
            json={"sku": sku, "quantity": quantity},
            headers=_headers(),
            timeout=TIMEOUT_S,
        )
        resp.raise_for_status()
        return resp.json(), None
    except requests.Timeout:
        logger.error("pricing timeout", extra={"extra": {"request_id": g.request_id}})
        return None, (
            {
                "requestId": g.request_id,
                "status": "failed",
                "error": "dependency_timeout",
                "message": "pricing service did not respond within timeout",
            },
            503,
        )
    except (requests.ConnectionError, requests.HTTPError) as exc:
        logger.error(f"pricing error: {exc}", extra={"extra": {"request_id": g.request_id}})
        return None, (
            {
                "requestId": g.request_id,
                "status": "failed",
                "error": "dependency_failure",
                "message": "pricing service returned an error or is unavailable",
            },
            503,
        )

def call_inventory(sku, quantity):
    """
    Call inventory service.
    Returns (data_dict, None) on success or (None, error_response_tuple) on failure.
    """
    try:
        resp = requests.post(
            f"{INVENTORY_URL}/reserve",
            json={"sku": sku, "quantity": quantity},
            headers=_headers(),
            timeout=TIMEOUT_S,
        )
        resp.raise_for_status()
        return resp.json(), None
    except requests.Timeout:
        logger.error("inventory timeout", extra={"extra": {"request_id": g.request_id}})
        return None, (
            {
                "requestId": g.request_id,
                "status": "failed",
                "error": "dependency_timeout",
                "message": "inventory service did not respond within timeout",
            },
            503,
        )
    except (requests.ConnectionError, requests.HTTPError) as exc:
        logger.error(f"inventory error: {exc}", extra={"extra": {"request_id": g.request_id}})
        return None, (
            {
                "requestId": g.request_id,
                "status": "failed",
                "error": "dependency_failure",
                "message": "inventory service returned an error or is unavailable",
            },
            503,
        )

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "checkout"})

@app.route("/checkout", methods=["POST"])
def checkout():
    body = request.get_json(silent=True)

    # 1. Validate input
    err = validate_body(body)
    if err:
        return jsonify({"error": "invalid_request", "message": err}), 400

    sku         = body["sku"].strip()
    quantity    = body["quantity"]
    customer_id = body.get("customerId", "")

    logger.info(
        "checkout started",
        extra={"extra": {"request_id": g.request_id, "sku": sku, "quantity": quantity}},
    )

    # 2. Call pricing
    pricing_data, pricing_err = call_pricing(sku, quantity)
    if pricing_err:
        return jsonify(pricing_err[0]), pricing_err[1]

    total_price = pricing_data.get("totalPrice", 0.0)
    currency    = pricing_data.get("currency", "GBP")

    # 3. Call inventory
    inv_data, inv_err = call_inventory(sku, quantity)
    if inv_err:
        return jsonify(inv_err[0]), inv_err[1]

    # 4. Check stock availability
    if not inv_data.get("available", False):
        reason = inv_data.get("reason", "out_of_stock")
        return jsonify({
            "requestId":  g.request_id,
            "status":     "failed",
            "error":      "out_of_stock",
            "message":    f"Requested quantity is not available ({reason})",
        }), 409

    reservation_id = inv_data.get("reservationId", "")

    # 5. Persist audit record — hard failure: do not silently swallow DB errors
    try:
        insert_audit(g.request_id, customer_id, sku, quantity, total_price)
    except Exception as exc:
        logger.error(
            f"DB write failed: {exc}",
            extra={"extra": {"request_id": g.request_id, "sku": sku, "quantity": quantity}},
        )
        return jsonify({
            "requestId": g.request_id,
            "status":    "failed",
            "error":     "database_error",
            "message":   "failed to persist checkout audit record",
        }), 500

    # 6. Return success
    logger.info(
        "checkout succeeded",
        extra={
            "extra": {
                "request_id":     g.request_id,
                "sku":            sku,
                "quantity":       quantity,
                "total_price":    total_price,
                "reservation_id": reservation_id,
            }
        },
    )
    return jsonify({
        "requestId":         g.request_id,
        "status":            "success",
        "sku":               sku,
        "quantity":          quantity,
        "totalPrice":        total_price,
        "currency":          currency,
        "inventoryReserved": True,
        "reservationId":     reservation_id,
        "message":           "checkout completed successfully",
    }), 200

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ensure_schema()
    app.run(host="0.0.0.0", port=PORT)
