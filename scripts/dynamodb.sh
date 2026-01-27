#!/bin/bash
# Helper script to manage local DynamoDB for testing
# Supports both Docker and Finch

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

function print_green() {
    echo -e "${GREEN}$1${NC}"
}

function print_yellow() {
    echo -e "${YELLOW}$1${NC}"
}

function print_red() {
    echo -e "${RED}$1${NC}"
}

function print_blue() {
    echo -e "${BLUE}$1${NC}"
}

# Auto-detect container runtime (Finch or Docker)
CONTAINER_RUNTIME=""

function detect_runtime() {
    # Check for Finch first (prefer if both available)
    if command -v finch &> /dev/null; then
        CONTAINER_RUNTIME="finch"
        print_blue "Using Finch as container runtime"
        return 0
    fi

    # Fall back to Docker
    if command -v docker &> /dev/null; then
        CONTAINER_RUNTIME="docker"
        print_blue "Using Docker as container runtime"
        return 0
    fi

    print_red "❌ Neither Finch nor Docker is installed."
    print_yellow "Please install one of:"
    print_yellow "  - Finch: https://github.com/runfinch/finch"
    print_yellow "  - Docker: https://www.docker.com/get-started"
    exit 1
}

function get_compose_cmd() {
    if [ "$CONTAINER_RUNTIME" = "finch" ]; then
        echo "finch compose"
    else
        echo "docker compose"
    fi
}

function get_container_cmd() {
    echo "$CONTAINER_RUNTIME"
}

function check_container_runtime() {
    if [ -z "$CONTAINER_RUNTIME" ]; then
        detect_runtime
    fi
}

function start_dynamodb() {
    check_container_runtime
    print_yellow "Starting DynamoDB Local with $CONTAINER_RUNTIME..."

    cd "$PROJECT_ROOT"

    # Check if container is already running
    if $(get_container_cmd) ps | grep -q bedrock-cost-keeper-dynamodb-local; then
        print_yellow "⚠️  DynamoDB Local is already running"
        return 0
    fi

    # Start with compose
    $(get_compose_cmd) up -d dynamodb-local

    # Wait for DynamoDB to be ready
    print_yellow "Waiting for DynamoDB to be ready..."
    sleep 3

    # Check if it's running
    if $(get_container_cmd) ps | grep -q bedrock-cost-keeper-dynamodb-local; then
        print_green "✅ DynamoDB Local is running on http://localhost:8000"
        print_blue "Container runtime: $CONTAINER_RUNTIME"
    else
        print_red "❌ Failed to start DynamoDB Local"
        exit 1
    fi
}

function stop_dynamodb() {
    check_container_runtime
    print_yellow "Stopping DynamoDB Local..."

    cd "$PROJECT_ROOT"
    $(get_compose_cmd) down

    print_green "✅ DynamoDB Local stopped"
}

function restart_dynamodb() {
    stop_dynamodb
    sleep 1
    start_dynamodb
}

function status_dynamodb() {
    check_container_runtime

    if $(get_container_cmd) ps | grep -q bedrock-cost-keeper-dynamodb-local; then
        print_green "✅ DynamoDB Local is RUNNING"
        print_blue "Container runtime: $CONTAINER_RUNTIME"
        $(get_container_cmd) ps | grep bedrock-cost-keeper-dynamodb-local
    else
        print_yellow "⚠️  DynamoDB Local is NOT running"
    fi
}

function logs_dynamodb() {
    check_container_runtime
    print_yellow "Showing DynamoDB Local logs..."

    $(get_container_cmd) logs bedrock-cost-keeper-dynamodb-local
}

function init_tables() {
    print_yellow "Initializing DynamoDB tables..."

    cd "$PROJECT_ROOT"

    # Make sure DynamoDB is running
    if ! $(get_container_cmd) ps | grep -q bedrock-cost-keeper-dynamodb-local; then
        print_red "❌ DynamoDB Local is not running. Start it first with: ./scripts/dynamodb.sh start"
        exit 1
    fi

    # Run initialization script
    python scripts/init_local_dynamodb.py init

    print_green "✅ Tables initialized"
}

function seed_data() {
    print_yellow "Seeding test data..."

    cd "$PROJECT_ROOT"

    # Make sure DynamoDB is running
    if ! $(get_container_cmd) ps | grep -q bedrock-cost-keeper-dynamodb-local; then
        print_red "❌ DynamoDB Local is not running. Start it first with: ./scripts/dynamodb.sh start"
        exit 1
    fi

    # Run seed script
    python scripts/init_local_dynamodb.py seed

    print_green "✅ Test data seeded"
}

function reset_data() {
    print_yellow "Resetting database (clear + seed)..."

    cd "$PROJECT_ROOT"

    # Make sure DynamoDB is running
    if ! $(get_container_cmd) ps | grep -q bedrock-cost-keeper-dynamodb-local; then
        print_red "❌ DynamoDB Local is not running. Start it first with: ./scripts/dynamodb.sh start"
        exit 1
    fi

    # Run reset script
    python scripts/init_local_dynamodb.py reset

    print_green "✅ Database reset complete"
}

function clear_data() {
    print_yellow "Clearing all table data..."

    cd "$PROJECT_ROOT"

    # Make sure DynamoDB is running
    if ! $(get_container_cmd) ps | grep -q bedrock-cost-keeper-dynamodb-local; then
        print_red "❌ DynamoDB Local is not running. Start it first with: ./scripts/dynamodb.sh start"
        exit 1
    fi

    # Run clear script
    python scripts/init_local_dynamodb.py clear

    print_green "✅ All tables cleared"
}

function list_tables() {
    print_yellow "Listing DynamoDB tables..."

    check_container_runtime

    if ! $(get_container_cmd) ps | grep -q bedrock-cost-keeper-dynamodb-local; then
        print_red "❌ DynamoDB Local is not running"
        exit 1
    fi

    # Check if AWS CLI is available
    if command -v aws &> /dev/null; then
        aws dynamodb list-tables \
            --endpoint-url http://localhost:8000 \
            --region us-east-1 \
            --no-cli-pager
    else
        print_yellow "⚠️  AWS CLI not found. Install it to use table inspection commands."
        print_yellow "Tables should be:"
        print_yellow "  - bedrock-cost-keeper-config"
        print_yellow "  - bedrock-cost-keeper-usage"
        print_yellow "  - bedrock-cost-keeper-aggregates"
        print_yellow "  - bedrock-cost-keeper-tokens"
        print_yellow "  - bedrock-cost-keeper-secrets"
    fi
}

function scan_table() {
    if [ -z "$1" ]; then
        print_red "❌ Please provide a table name"
        echo "Available tables:"
        echo "  - bedrock-cost-keeper-config"
        echo "  - bedrock-cost-keeper-usage"
        echo "  - bedrock-cost-keeper-aggregates"
        echo "  - bedrock-cost-keeper-tokens"
        echo "  - bedrock-cost-keeper-secrets"
        exit 1
    fi

    print_yellow "Scanning table: $1"

    if command -v aws &> /dev/null; then
        aws dynamodb scan \
            --table-name "$1" \
            --endpoint-url http://localhost:8000 \
            --region us-east-1 \
            --no-cli-pager
    else
        print_red "❌ AWS CLI is required for this command"
        print_yellow "Install it with: brew install awscli"
        exit 1
    fi
}

function run_integration_tests() {
    print_yellow "Running integration tests..."

    cd "$PROJECT_ROOT"

    check_container_runtime

    # Make sure DynamoDB is running
    if ! $(get_container_cmd) ps | grep -q bedrock-cost-keeper-dynamodb-local; then
        print_red "❌ DynamoDB Local is not running. Start it first with: ./scripts/dynamodb.sh start"
        exit 1
    fi

    # Run only integration tests
    pytest tests/integration -v -m integration "$@"

    print_green "✅ Integration tests complete"
}

function setup() {
    print_yellow "Setting up local DynamoDB for integration testing..."

    detect_runtime
    print_blue "Using container runtime: $CONTAINER_RUNTIME"

    start_dynamodb
    sleep 2
    init_tables
    seed_data

    print_green "✅ Setup complete! DynamoDB Local is ready for integration tests"
    print_blue "Container runtime: $CONTAINER_RUNTIME"
    print_yellow ""
    print_yellow "Next steps:"
    print_yellow "  - Run integration tests: ./scripts/dynamodb.sh test"
    print_yellow "  - View table data: ./scripts/dynamodb.sh scan bedrock-cost-keeper-usage"
    print_yellow "  - Reset data: ./scripts/dynamodb.sh reset"
}

function show_runtime() {
    detect_runtime
    print_blue "Current container runtime: $CONTAINER_RUNTIME"

    if [ "$CONTAINER_RUNTIME" = "finch" ]; then
        finch version
    else
        docker version --format '{{.Server.Version}}'
    fi
}

function show_help() {
    cat << EOF
DynamoDB Local Management Script
Automatically uses Finch or Docker (prefers Finch if both installed)

Usage: ./scripts/dynamodb.sh [command]

Commands:
    setup       Complete setup (start + init + seed)
    start       Start DynamoDB Local container
    stop        Stop DynamoDB Local container
    restart     Restart DynamoDB Local container
    status      Check if DynamoDB Local is running
    logs        Show DynamoDB Local container logs

    init        Initialize database tables
    seed        Seed test data
    reset       Reset database (clear + seed)
    clear       Clear all table data

    list        List all tables (requires AWS CLI)
    scan TABLE  Scan and display table contents (requires AWS CLI)

    test [ARGS] Run integration tests (pass pytest args)
    runtime     Show detected container runtime

    help        Show this help message

Container Runtime:
    This script auto-detects whether to use Finch or Docker.
    Priority: Finch > Docker
    Current: Run './scripts/dynamodb.sh runtime' to check

Examples:
    # Complete setup (auto-detects Finch/Docker)
    ./scripts/dynamodb.sh setup

    # Check which runtime is being used
    ./scripts/dynamodb.sh runtime

    # Start and initialize
    ./scripts/dynamodb.sh start
    ./scripts/dynamodb.sh init
    ./scripts/dynamodb.sh seed

    # Run tests
    ./scripts/dynamodb.sh test
    ./scripts/dynamodb.sh test -v  # verbose
    ./scripts/dynamodb.sh test -k test_submit_single  # specific test

    # View data (requires AWS CLI)
    ./scripts/dynamodb.sh scan bedrock-cost-keeper-usage

    # Reset for clean test run
    ./scripts/dynamodb.sh reset

    # View logs
    ./scripts/dynamodb.sh logs

Using Finch:
    If you have Finch installed, it will be used automatically.
    Finch is AWS's open-source container development tool.
    Install: https://github.com/runfinch/finch

    On macOS:
      brew install --cask finch
      finch vm init

Using Docker:
    If Finch is not available, Docker will be used.
    Install: https://www.docker.com/get-started

EOF
}

# Main command dispatcher
case "${1:-help}" in
    setup)
        setup
        ;;
    start)
        start_dynamodb
        ;;
    stop)
        stop_dynamodb
        ;;
    restart)
        restart_dynamodb
        ;;
    status)
        status_dynamodb
        ;;
    logs)
        logs_dynamodb
        ;;
    init)
        init_tables
        ;;
    seed)
        seed_data
        ;;
    reset)
        reset_data
        ;;
    clear)
        clear_data
        ;;
    list)
        list_tables
        ;;
    scan)
        scan_table "$2"
        ;;
    test)
        shift
        run_integration_tests "$@"
        ;;
    runtime)
        show_runtime
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_red "❌ Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
