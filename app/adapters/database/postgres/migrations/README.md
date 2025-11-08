# Alembic Database Migrations

This directory contains Alembic migrations for the DevFlowFix application.

## Setup Complete ✓

The following has been configured:

1. **Alembic initialized** at `app/adapters/database/postgres/migrations/`
2. **Configuration files updated**:
   - `alembic.ini` - Database URL set to PostgreSQL
   - `env.py` - Configured to import Base metadata from `app.main`

3. **Migrations created**:
   - `001_initial.py` - Core database schema
   - `002_enable_pgvector.py` - pgvector extension and vector tables

4. **Database tables created**:
   - `incidents` - Store incident information
   - `analyses` - Store analysis results  
   - `remediations` - Store remediation actions
   - `feedback` - Store user feedback for learning
   - `incident_embeddings` - Vector embeddings for incidents (with vector(1536))
   - `knowledge_base` - Vector-based knowledge storage (with vector(1536))

## Usage

### Run migrations (WSL)

```bash
# Activate virtual environment
source .venv/bin/activate

# Upgrade to latest
alembic upgrade head

# Check current version
alembic current

# View migration history
alembic history --verbose
```

### Create new migration

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "description of changes"

# Create empty migration
alembic revision -m "description of changes"
```

### Rollback migrations

```bash
# Downgrade one version
alembic downgrade -1

# Downgrade to specific version
alembic downgrade <revision_id>

# Downgrade all
alembic downgrade base
```

## Database Info

- **Database**: PostgreSQL with pgvector extension
- **Connection**: postgresql://postgres:postgres@localhost:5432/vector_db
- **Vector Dimensions**: 1536 (OpenAI embeddings)
- **Vector Index Type**: IVFFlat with cosine similarity

## Extensions Enabled

- ✓ pgvector 0.8.1 - Vector similarity search

## Notes

- All timestamps use timezone-aware datetime
- Vector embeddings use cosine similarity (vector_cosine_ops)
- Foreign keys cascade on delete where appropriate
- Migrations must be run from WSL environment with activated venv
