#!/bin/bash
# Quick install script for Contradiction Service

echo "Installing Contradiction Service dependencies..."

# Install from requirements.txt
pip install -r "$(dirname "$0")/requirements.txt"

echo ""
echo "Installation complete!"
echo ""
echo "To run the service:"
echo "  cd $(dirname "$0")/.."
echo "  python -m backend_lite.run"
echo ""
echo "Or with uvicorn directly:"
echo "  uvicorn backend_lite.api:app --port 8000"
