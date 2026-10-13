FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY orders.py server.py client.py check.py fixtures.json ./
COPY tracking.py tracking-fixtures.json ./
COPY tickets.py ./
COPY tests ./tests

CMD ["python", "check.py"]
