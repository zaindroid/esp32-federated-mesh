FROM python:3.11-slim

# Install curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY python/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY python/bridge.py .
COPY web/ ./web/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV APP_VERSION=${APP_VERSION:-dev}
ENV BUILD_SHA=${BUILD_SHA:-unknown}

# Expose port (will be set by app.yaml)
EXPOSE 8080

# Run the bridge
CMD ["python", "bridge.py"]
