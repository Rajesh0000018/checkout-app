"""
Gateway Service — public entrypoint.
Serves the HTML UI, proxies API calls to internal services,
and propagates X-Request-Id across the call chain.
"""

import os
import uuid
import json
import logging
import time

import requests
from flask import Flask, request, jsonify, render_template, g

# ── Logging ──────────────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log = {
            "timestamp": self.formatTime(record),
            "service": "gateway",
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra"):
            log.update(record.extra)
        return json.dumps(log)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("gateway")

# ── Config ────────────────────────────────────────────────────────────────────

CHECKOUT_URL     = os.environ.get("CHECKOUT_URL",  "http://localhost:5001")
QUOTE_URL        = os.environ.get("QUOTE_URL",     "http://localhost:5004")
TIMEOUT_MS       = int(os.environ.get("REQUEST_TIMEOUT_MS", "2000"))
TIMEOUT_S        = TIMEOUT_MS / 1000.0
PORT             = int(os.environ.get("PORT", "5000"))

# ── App ───────────────────────────────────────────────────────────────────────

app = Flask(__name__, template_folder="templates", static_folder="static")

# ── Middleware: request ID ────────────────────────────────────────────────────

@app.before_request
def attach_request_id():
    g.request_id = request.headers.get("X-Request-Id") or f"gw-{uuid.uuid4().hex[:12]}"
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
    """Build forwarding headers with request correlation."""
    return {
        "X-Request-Id": g.request_id,
        "Content-Type": "application/json",
    }

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/ping")
def ping():
    return jsonify({"status": "ok", "service": "gateway", "request_id": g.request_id})

@app.route("/api/arch")
def arch():
    return jsonify({
        "service": "gateway",
        "version": "1.0.0",
        "request_id": g.request_id,
        "architecture": {
            "gateway":   "public entrypoint — routes, UI, correlation",
            "checkout":  "orchestrates pricing + inventory, writes to Postgres",
            "pricing":   "returns unit/total price for a SKU",
            "inventory": "reserves stock for a SKU/quantity",
            "quote":     "lightweight price preview (no reservation)",
        },
        "public_routes": [
            "GET  /",
            "GET  /api/ping",
            "GET  /api/arch",
            "POST /api/checkout",
            "GET  /api/quote?sku=SKU-001&quantity=2",
        ],
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "gateway"})

@app.route("/api/checkout", methods=["POST"])
def checkout():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "invalid_request", "message": "request body must be JSON"}), 400

    try:
        resp = requests.post(
            f"{CHECKOUT_URL}/checkout",
            json=payload,
            headers=_headers(),
            timeout=TIMEOUT_S,
        )
        return jsonify(resp.json()), resp.status_code

    except requests.Timeout:
        logger.error("checkout service timeout", extra={"extra": {"request_id": g.request_id}})
        return jsonify({
            "requestId": g.request_id,
            "status": "failed",
            "error": "dependency_timeout",
            "message": "checkout service did not respond within timeout",
        }), 503

    except requests.ConnectionError:
        logger.error("checkout service unavailable", extra={"extra": {"request_id": g.request_id}})
        return jsonify({
            "requestId": g.request_id,
            "status": "failed",
            "error": "service_unavailable",
            "message": "checkout service is not reachable",
        }), 503

@app.route("/api/quote")
def quote_proxy():
    sku = request.args.get("sku", "")
    quantity = request.args.get("quantity", "1")
    try:
        resp = requests.get(
            f"{QUOTE_URL}/quote",
            params={"sku": sku, "quantity": quantity},
            headers=_headers(),
            timeout=TIMEOUT_S,
        )
        return jsonify(resp.json()), resp.status_code
    except requests.Timeout:
        return jsonify({"error": "dependency_timeout", "message": "quote service timed out"}), 503
    except requests.ConnectionError:
        return jsonify({"error": "service_unavailable", "message": "quote service not reachable"}), 503

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
