# Use the specified Python base image
FROM harbor-ai.dahuatech.com/base/python:3.11

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies using the specified pip mirror
RUN pip install --no-cache-dir -r requirements.txt \
    -i http://yumserver.dahuatech.com/pypi/simple/ \
    --trusted-host yumserver.dahuatech.com

# Copy application code
COPY llm_monitor/ ./llm_monitor/
COPY docker-entrypoint.sh .

# Create non-root user and set permissions
RUN useradd -m -u 1000 appuser && \
    chmod +x docker-entrypoint.sh && \
    chown -R appuser:appuser /app

# Create config directory for mounting
RUN mkdir -p /app/config && chown appuser:appuser /app/config

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application via entrypoint script
ENTRYPOINT ["./docker-entrypoint.sh"]
