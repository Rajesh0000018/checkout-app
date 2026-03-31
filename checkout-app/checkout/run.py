"""
Entrypoint for checkout service when running directly (not via gunicorn).
Runs schema init then starts Flask dev server.
Used by: python run.py
"""

from app import app, ensure_schema, PORT

if __name__ == "__main__":
    ensure_schema()
    app.run(host="0.0.0.0", port=PORT)
