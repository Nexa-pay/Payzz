# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create necessary directories for persistent data
# Railway will mount a volume here, so we ensure the path exists
RUN mkdir -p /app/data /app/logs /app/sessions

# Create a non-root user to run the app
RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 app

# ⚠️ IMPORTANT: Set ownership AFTER creating directories and BEFORE switching user
# This ensures the 'app' user can write to the directories where Railway volumes will be mounted.
RUN chown -R app:app /app

# Expose health check port (optional but recommended for Railway)
EXPOSE 8080

# Switch to non-root user
USER app

# Health check to keep Railway happy (adjust the command if needed)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import socket; socket.socket().connect(('localhost', 8080))" || exit 1

# Command to run the bot
CMD ["python", "main.py"]