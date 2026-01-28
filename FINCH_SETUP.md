# Running with Finch

This guide explains how to use Finch (AWS's open-source container development tool) for local DynamoDB integration testing.

## What is Finch?

[Finch](https://github.com/runfinch/finch) is an open-source container development tool from AWS that provides:
- ✅ **Docker-compatible** CLI and workflow
- ✅ **Lightweight** - Uses Lima VM on macOS (lighter than Docker Desktop)
- ✅ **Free and open-source** - Apache 2.0 license
- ✅ **Native ARM support** - Optimized for Apple Silicon
- ✅ **No licensing concerns** - Unlike Docker Desktop

## Installation

### macOS (Recommended)

```bash
# Install Finch via Homebrew
brew install --cask finch

# Initialize the VM
finch vm init

# Verify installation
finch version
```

### Linux

```bash
# Download and install
wget https://github.com/runfinch/finch/releases/latest/download/finch-linux-amd64.tar.gz
tar -xzf finch-linux-amd64.tar.gz
sudo install finch /usr/local/bin/

# Initialize
finch vm init
```

## Quick Start with Finch

The `dynamodb.sh` script **automatically detects Finch** and uses it if available:

```bash
# 1. Complete setup (auto-uses Finch)
./scripts/dynamodb.sh setup

# 2. Run integration tests
./scripts/dynamodb.sh test

# 3. Stop when done
./scripts/dynamodb.sh stop
```

## Verify Finch is Being Used

```bash
# Check which runtime is detected
./scripts/dynamodb.sh runtime

# Expected output:
# Using Finch as container runtime
# Current container runtime: finch
# ...finch version details...
```

## All Commands Work with Finch

The script transparently uses Finch for all operations:

```bash
# Container management
./scripts/dynamodb.sh start     # Uses: finch compose up
./scripts/dynamodb.sh stop      # Uses: finch compose down
./scripts/dynamodb.sh status    # Uses: finch ps
./scripts/dynamodb.sh logs      # Uses: finch logs

# Same as Docker - no changes needed!
```

## Manual Finch Commands

If you want to use Finch directly:

```bash
# Start DynamoDB Local
finch compose up -d dynamodb-local

# Check running containers
finch ps

# View logs
finch logs bedrock-cost-keeper-dynamodb-local

# Stop
finch compose down

# Pull images
finch pull amazon/dynamodb-local:latest
```

## Differences from Docker

### What's the Same
- ✅ Same `docker-compose.yml` file
- ✅ Same commands (`finch` instead of `docker`)
- ✅ Same images (pulls from Docker Hub)
- ✅ Same port mappings
- ✅ Same networking

### What's Different
- Uses `finch compose` instead of `docker compose`
- Uses Lima VM instead of Docker Desktop
- Different storage location for images/containers
- Different VM management commands

## VM Management

Finch uses a VM (Lima on macOS). Useful commands:

```bash
# Check VM status
finch vm status

# Start VM
finch vm start

# Stop VM
finch vm stop

# View VM info
finch vm info

# SSH into VM
finch vm ssh
```

## Troubleshooting

### Finch VM Not Running

```bash
# Start the VM
finch vm start

# Or restart it
finch vm stop
finch vm start
```

### Port Already in Use

```bash
# Check what's using port 8000
lsof -i :8000

# Stop the VM and try again
finch vm stop
finch vm start
./scripts/dynamodb.sh start
```

### Container Not Starting

```bash
# View logs
./scripts/dynamodb.sh logs

# Or directly
finch logs bedrock-cost-keeper-dynamodb-local

# Restart everything
finch compose down
finch compose up -d
```

### Image Pull Issues

```bash
# Pull image manually
finch pull amazon/dynamodb-local:latest

# Verify image exists
finch images
```

### Permission Errors

```bash
# Finch might need sudo on some systems
sudo finch vm init
```

## Performance Comparison

### Finch Benefits
- **Faster startup** - Lima VM is lighter than Docker Desktop
- **Lower memory** - More efficient resource usage
- **Better ARM support** - Native on Apple Silicon
- **No Docker Desktop** - Avoid licensing and resource overhead

### Benchmarks (Approximate)
| Metric | Docker Desktop | Finch |
|--------|---------------|-------|
| VM Startup | 10-20s | 5-10s |
| Memory Usage | 2-4 GB | 1-2 GB |
| Container Start | ~same | ~same |
| Image Pull | ~same | ~same |

## Switching Between Docker and Finch

The script auto-detects which tool to use with this priority:

1. **Finch** (if available)
2. **Docker** (fallback)

### Force Docker Even with Finch Installed

If you have both and want to use Docker:

```bash
# Temporarily rename finch
sudo mv /usr/local/bin/finch /usr/local/bin/finch.bak

# Run your commands
./scripts/dynamodb.sh setup

# Restore finch
sudo mv /usr/local/bin/finch.bak /usr/local/bin/finch
```

Or just use Docker commands directly:

```bash
docker compose up -d
docker ps
docker compose down
```

## Integration with CI/CD

Finch works great in CI/CD pipelines:

### GitHub Actions Example

```yaml
name: Integration Tests with Finch

on: [push, pull_request]

jobs:
  test:
    runs-on: macos-latest  # or ubuntu-latest

    steps:
      - uses: actions/checkout@v2

      - name: Install Finch
        run: |
          brew install --cask finch
          finch vm init

      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements-dev.txt

      - name: Start DynamoDB Local
        run: ./scripts/dynamodb.sh setup

      - name: Run integration tests
        run: ./scripts/dynamodb.sh test

      - name: Cleanup
        run: ./scripts/dynamodb.sh stop
```

## Common Finch Commands Cheat Sheet

```bash
# Container Management
finch ps                    # List running containers
finch ps -a                 # List all containers
finch logs CONTAINER        # View container logs
finch exec -it CONTAINER sh # Enter container shell
finch stop CONTAINER        # Stop container
finch rm CONTAINER          # Remove container

# Image Management
finch images                # List images
finch pull IMAGE            # Pull image
finch rmi IMAGE             # Remove image
finch build -t TAG .        # Build image

# Compose
finch compose up -d         # Start services
finch compose down          # Stop services
finch compose ps            # List services
finch compose logs          # View logs

# System
finch system prune          # Clean up
finch version               # Show version
finch info                  # Show system info

# VM Management (macOS/Linux)
finch vm init               # Initialize VM
finch vm start              # Start VM
finch vm stop               # Stop VM
finch vm status             # VM status
finch vm ssh                # SSH into VM
```

## Resources

- **Finch GitHub**: https://github.com/runfinch/finch
- **Finch Docs**: https://runfinch.com/docs/
- **Finch vs Docker**: https://aws.amazon.com/blogs/opensource/finch-open-source-container-development-tool/
- **Lima Project**: https://github.com/lima-vm/lima

## FAQ

### Q: Can I use Finch instead of Docker Desktop?
**A:** Yes! Finch is a complete Docker Desktop alternative for development.

### Q: Will my existing docker-compose.yml work?
**A:** Yes, Finch uses the same Compose specification.

### Q: Is Finch production-ready?
**A:** Finch is for local development. Use ECS, EKS, or Fargate for production.

### Q: Can I use Docker and Finch together?
**A:** Yes, but they use separate VMs and storage. Our script auto-detects which to use.

### Q: Does Finch work on Windows?
**A:** Finch primarily targets macOS and Linux. Windows support is experimental.

### Q: Is Finch faster than Docker?
**A:** Yes, typically faster startup and lower memory usage, especially on macOS.

## Recommended Workflow

```bash
# 1. Install Finch (one time)
brew install --cask finch
finch vm init

# 2. Verify it's detected
./scripts/dynamodb.sh runtime

# 3. Use normally - script handles everything
./scripts/dynamodb.sh setup
./scripts/dynamodb.sh test
./scripts/dynamodb.sh stop

# 4. When done for the day
finch vm stop  # Save resources
```

## Next Steps

1. ✅ Install Finch: `brew install --cask finch`
2. ✅ Initialize VM: `finch vm init`
3. ✅ Verify: `./scripts/dynamodb.sh runtime`
4. ✅ Run tests: `./scripts/dynamodb.sh setup && ./scripts/dynamodb.sh test`

The script will automatically use Finch - no configuration needed! 🚀
