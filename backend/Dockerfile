FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_PYTHON=/opt/agentdesk-mcp/bin/python

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --requirement requirements.txt

# The SDK requires a different httpx2 version; keep backend pins isolated.
COPY mcp-server/requirements.txt /tmp/mcp-requirements.txt
RUN python -m venv /opt/agentdesk-mcp \
    && /opt/agentdesk-mcp/bin/python -m pip install --no-cache-dir --requirement /tmp/mcp-requirements.txt

COPY mcp-server/client.py mcp-server/server.py mcp-server/orders.py mcp-server/fixtures.json /mcp-server/
COPY mcp-server/tracking.py mcp-server/tracking-fixtures.json /mcp-server/
COPY backend/app ./app

RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
