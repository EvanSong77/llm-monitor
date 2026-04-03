#!/bin/bash

echo "Installing dependencies..."
pip install -e .

echo ""
echo "Starting vLLM Monitor..."
echo "Dashboard will be available at http://localhost:8000"
echo "API docs available at http://localhost:8000/docs"
echo ""

uvicorn llm_monitor.main:app --reload --host 0.0.0.0 --port 8000
