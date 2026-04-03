#!/bin/bash
set -e

echo "========================================"
echo "LLM Monitor Container Starting..."
echo "========================================"

# Wait for Elasticsearch to be ready
echo ""
echo "Waiting for Elasticsearch to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s -f "${ELASTICSEARCH_URL}/_cluster/health" > /dev/null 2>&1; then
        echo "✓ Elasticsearch is ready!"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "  Attempt $RETRY_COUNT/$MAX_RETRIES - Elasticsearch not ready yet, waiting..."
    sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "⚠ Warning: Elasticsearch not available after $MAX_RETRIES attempts"
    echo "  Starting application anyway (will retry connection in background)"
fi

echo ""

echo ""
echo "========================================"
echo "Starting LLM Monitor Application..."
echo "========================================"
echo ""

# Start the application
exec uvicorn llm_monitor.main:app --host 0.0.0.0 --port 8000
