FROM python:3.11-slim

# Non-root user — never run app code as root
RUN useradd --create-home app

WORKDIR /app

# Copy requirements first so this layer is cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/        ./src/
COPY migrations/ ./migrations/

USER app

EXPOSE 8000

# Docker will mark the container unhealthy if /health stops returning 200
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

CMD ["python3", "src/server.py", "--sse"]
