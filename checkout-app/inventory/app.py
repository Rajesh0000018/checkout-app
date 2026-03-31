"""
Inventory Service — reserves stock for a given SKU and quantity.
POST /reserve  → {"sku": "SKU-001", "quantity": 2}
GET  /health   → {"status": "ok", "service": "inventory"}

Stock is held in memory. SKU-999 is permanently out-of-stock for testing.
All other known SKUs have generous stock; unknown SKUs get a small fallback.
"""

import os
import uuid
import json
import logging
import time

from flask import Flask, request, jsonify, g

# ── Logging ───────────────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log = {
            "timestamp": self.formatTime(record),
            "service": "inventory",
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra"):
            log.update(record.extra)
        return json.dumps(log)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("inventory")

# ── Config ────────────────────────────────────────────────────────────────────

PORT = int(os.environ.get("PORT", "5003"))

# ── In-memory stock ───────────────────────────────────────────────────────────
# stock[sku] = available units. SKU-999 = 0 (always out-of-stock for testing).

STOCK = {
    "SKU-001": 500,
    "SKU-002": 200,
    "SKU-003": 50,
    "SKU-004": 1000,
    "SKU-005": 25,
    "SKU-999": 0,   # intentionally out-of-stock
}
DEFAULT_STOCK = 10  # fallback for unknown SKUs

# ── App ───────────────────────────────────────────────────────────────────────

app = Flask(__name__)

# ── Middleware ────────────────────────────────────────────────────────────────

@app.before_request
def attach_request_id():
    g.request_id = request.headers.get("X-Request-Id") or f"inv-{uuid.uuid4().hex[:12]}"
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

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "inventory"})

@app.route("/reserve", methods=["POST"])
def reserve():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "invalid_request", "message": "body must be JSON"}), 400

    sku = body.get("sku", "").strip()
    if not sku:
        return jsonify({"error": "invalid_request", "message": "sku is required"}), 400

    try:
        quantity = int(body.get("quantity", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_request", "message": "quantity must be an integer"}), 400

    if quantity <= 0:
        return jsonify({"error": "invalid_request", "message": "quantity must be greater than zero"}), 400

    available_stock = STOCK.get(sku, DEFAULT_STOCK)

    if available_stock < quantity:
        logger.info(
            "out of stock",
            extra={
                "extra": {
                    "request_id":       g.request_id,
                    "sku":              sku,
                    "quantity":         quantity,
                    "available_stock":  available_stock,
                }
            },
        )
        return jsonify({
            "available":  False,
            "sku":        sku,
            "quantity":   quantity,
            "reason":     "out_of_stock",
            "message":    f"Only {available_stock} units available, {quantity} requested",
        }), 200  # 200: the request succeeded; the *business outcome* is out-of-stock

    # Deduct stock (in-memory; not durable — fine for a demo)
    STOCK[sku] = available_stock - quantity
    reservation_id = f"res-{uuid.uuid4().hex[:10]}"

    logger.info(
        "reservation created",
        extra={
            "extra": {
                "request_id":      g.request_id,
                "sku":             sku,
                "quantity":        quantity,
                "reservation_id":  reservation_id,
                "remaining_stock": STOCK[sku],
            }
        },
    )

    return jsonify({
        "available":      True,
        "sku":            sku,
        "quantity":       quantity,
        "reservationId":  reservation_id,
    }), 200

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
