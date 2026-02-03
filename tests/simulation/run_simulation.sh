#!/bin/bash
# Pricing Simulation Test Runner
#
# Runs comprehensive pricing simulation tests and displays results

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         Bedrock Cost Keeper - Pricing Simulation Tests           ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if DynamoDB Local is running
echo -e "${YELLOW}[1/3] Checking prerequisites...${NC}"
if ! nc -z localhost 8000 2>/dev/null; then
    echo -e "${RED}❌ DynamoDB Local is not running on port 8000${NC}"
    echo -e "${YELLOW}Start it with: finch run -d -p 8000:8000 amazon/dynamodb-local${NC}"
    exit 1
fi
echo -e "${GREEN}✅ DynamoDB Local is running${NC}"
echo ""

# Check if tables exist
echo -e "${YELLOW}[2/3] Verifying database setup...${NC}"
if ! aws dynamodb describe-table --table-name bedrock-cost-keeper-config --endpoint-url http://localhost:8000 --region us-east-1 >/dev/null 2>&1; then
    echo -e "${RED}❌ Tables not found. Run: python scripts/init_local_dynamodb.py init && python scripts/init_local_dynamodb.py seed${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Database tables exist${NC}"
echo ""

# Run the simulation tests
echo -e "${YELLOW}[3/3] Running pricing simulation tests...${NC}"
echo ""

pytest tests/simulation/test_pricing_simulation.py -v -s --tb=short \
    --color=yes \
    -m integration \
    | tee /tmp/simulation_results.log

# Check exit code
if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                    ✅ ALL TESTS PASSED                            ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${GREEN}✅ Cost calculations verified${NC}"
    echo -e "${GREEN}✅ Aggregation working correctly${NC}"
    echo -e "${GREEN}✅ All model tiers accurate${NC}"
    echo -e "${GREEN}✅ Edge cases handled${NC}"
    echo ""
    exit 0
else
    echo ""
    echo -e "${RED}╔═══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║                    ❌ TESTS FAILED                                ║${NC}"
    echo -e "${RED}╚═══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${RED}Review the output above for details${NC}"
    exit 1
fi
