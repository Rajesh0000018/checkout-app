FROM python:3.12-slim

WORKDIR /app

# psycopg2-binary needs libpq
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_ENV=production
ENV PORT=5001

EXPOSE 5001

# run.py handles schema init before starting gunicorn
CMD ["sh", "-c", "python -c 'from app import ensure_schema; ensure_schema()' && gunicorn --bind 0.0.0.0:5001 --workers 2 --timeout 30 app:app"]
