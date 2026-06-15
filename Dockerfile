FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_NO_CACHE_DIR=1 \
	PIP_DEFAULT_TIMEOUT=120 \
	PIP_RETRIES=10

WORKDIR /app

COPY requirements.docker.txt /app/
RUN pip install -r requirements.docker.txt

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY mcp-server /app/mcp-server

RUN pip install --no-deps .

EXPOSE 8766

CMD ["boss-mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "8766"]
