# DevFlowFix

> Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

## What It Does

DevFlowFix automatically fixes 75% of deployment failures in under 8 minutes by:
- Receiving webhooks from GitHub Actions, ArgoCD, and Kubernetes
- Analyzing failures using AI (NVIDIA NIM) and RAG
- Executing safe remediation actions (workflow reruns, pod restarts, sync operations)
- Learning from outcomes to improve confidence scoring

## Tech Stack

- **Runtime**: AWS Lambda (Docker)
- **AI**: NVIDIA NIM API (Llama 3.1 + embeddings)
- **Database**: PostgreSQL with pgvector
- **Framework**: FastAPI + SQLModel
- **Package Manager**: uv

## Quick Start

```bash
# Install dependencies
uv sync

# Start local development stack
docker-compose up

# Run tests
uv run pytest

# Deploy to AWS
cd infrastructure/terraform
terraform apply
```

## Cost

~$26/month for 100 incidents (Lambda + RDS + NVIDIA free tier)

## Architecture

```
Webhook → Lambda → AI Analysis → RAG Retrieval → Decision Engine → Remediation
                                                                      ↓
                                                           PostgreSQL (pgvector)
```

## Key Features

- ✅ **Autonomous**: 75% auto-resolution rate
- ✅ **Safe**: Confidence scoring + blast radius limits + rollback
- ✅ **Observable**: CloudWatch metrics + X-Ray tracing
- ✅ **Extensible**: Pluggable remediators and strategies

## Documentation

- [Architecture Overview](docs/architecture/overview.md)
- [Deployment Guide](docs/deployment/lambda-deployment.md)
- [Development Setup](docs/development/setup.md)

## License

GNU 3 
