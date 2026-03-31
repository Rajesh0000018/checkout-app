"""
Quote Preview Service — lightweight price preview with no stock reservation or DB writes.
GET /quote?sku=SKU-001&quantity=2
GET /health
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
            "service": "quote",
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra"):
            log.update(record.extra)
        return json.dumps(log)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("quote")

# ── Config ────────────────────────────────────────────────────────────────────

PORT     = int(os.environ.get("PORT", "5004"))
CURRENCY = os.environ.get("CURRENCY", "GBP")

# ── Shared price catalogue (same as pricing service) ──────────────────────────
# Quote is intentionally decoupled from the pricing service to be independent.
# In a real system these would share a data source.

PRICE_CATALOGUE = {
    "SKU-001": 25.00,
    "SKU-002": 14.99,
    "SKU-003": 49.95,
    "SKU-004": 9.99,
    "SKU-005": 199.00,
    "SKU-999": 0.01,
}
DEFAULT_PRICE = 19.99

# ── App ───────────────────────────────────────────────────────────────────────

app = Flask(__name__)

# ── Middleware ────────────────────────────────────────────────────────────────

@app.before_request
def attach_request_id():
    g.request_id = request.headers.get("X-Request-Id") or f"qt-{uuid.uuid4().hex[:12]}"
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
    return jsonify({"status": "ok", "service": "quote"})

@app.route("/quote")
def quote():
    sku = request.args.get("sku", "").strip()
    if not sku:
        return jsonify({"error": "invalid_request", "message": "sku query param is required"}), 400

    try:
        quantity = int(request.args.get("quantity", "1"))
    except ValueError:
        return jsonify({"error": "invalid_request", "message": "quantity must be an integer"}), 400

    if quantity <= 0:
        return jsonify({"error": "invalid_request", "message": "quantity must be greater than zero"}), 400

    unit_price  = PRICE_CATALOGUE.get(sku, DEFAULT_PRICE)
    total_price = round(unit_price * quantity, 2)

    logger.info(
        "quote generated",
        extra={
            "extra": {
                "request_id": g.request_id,
                "sku":         sku,
                "quantity":    quantity,
                "total_price": total_price,
            }
        },
    )

    return jsonify({
        "requestId":   g.request_id,
        "sku":         sku,
        "quantity":    quantity,
        "unitPrice":   unit_price,
        "totalPrice":  total_price,
        "currency":    CURRENCY,
        "note":        "This is a price preview only. No stock has been reserved.",
    }), 200

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
