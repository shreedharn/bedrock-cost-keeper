#!/bin/bash
# Test runner script for Bedrock Metering API

set -e

echo "Running Bedrock Metering API Tests"
echo "==================================="
echo ""

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# Install test dependencies
echo "Installing test dependencies..."
pip install -q -r requirements-dev.txt

# Run tests
echo ""
echo "Running tests..."
pytest "$@"

# Generate coverage report
echo ""
echo "Coverage report generated in htmlcov/index.html"
