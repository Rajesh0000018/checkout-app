FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_ENV=production
ENV PORT=5004

EXPOSE 5004

CMD ["gunicorn", "--bind", "0.0.0.0:5004", "--workers", "2", "--timeout", "30", "app:app"]
