#!/bin/bash

# LLM Monitor Docker Image Build Script
# Usage: ./image_build.sh [image_tag] [push]

set -e

# Configuration
IMAGE_NAME="harbor-ai.dahuatech.com/llms/llm-monitor"
IMAGE_TAG="${1:-latest}"
PUSH_IMAGE="${2:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}LLM Monitor Image Build Script${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo -e "${YELLOW}Image: ${IMAGE_NAME}:${IMAGE_TAG}${NC}"
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed or not in PATH${NC}"
    exit 1
fi

# Build the Docker image
echo -e "${YELLOW}Building Docker image...${NC}"
docker build \
    --no-cache \
    --tag ${IMAGE_NAME}:${IMAGE_TAG} \
    --tag ${IMAGE_NAME}:latest \
    -f Dockerfile \
    .

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Image built successfully${NC}"
    echo ""
    
    # Show image details
    echo -e "${YELLOW}Image details:${NC}"
    docker images ${IMAGE_NAME}:${IMAGE_TAG}
    echo ""
    
    # Push image if requested
    if [ "$PUSH_IMAGE" = "push" ]; then
        echo -e "${YELLOW}Pushing image to registry...${NC}"
        docker push ${IMAGE_NAME}:${IMAGE_TAG}
        docker push ${IMAGE_NAME}:latest
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Image pushed successfully${NC}"
        else
            echo -e "${RED}✗ Failed to push image${NC}"
            exit 1
        fi
    else
        echo -e "${YELLOW}Note: To push the image, run: ./image_build.sh ${IMAGE_TAG} push${NC}"
    fi
else
    echo -e "${RED}✗ Failed to build image${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}Build completed!${NC}"
echo -e "${GREEN}======================================${NC}"
