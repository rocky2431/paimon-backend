# ADR-001: Technology Stack Selection

**Status**: Accepted
**Date**: 2024-12-13
**Deciders**: Architecture Team

## Context

Paimon Prime Fund backend system requires a technology stack that supports:
- High-performance async API
- Blockchain (BSC) integration
- Real-time event processing
- Time-series data storage
- Distributed task execution

## Decision

We will use the following technology stack:

| Component | Technology | Version |
|-----------|------------|---------|
| Language | Python | 3.11+ |
| Web Framework | FastAPI | 0.100+ |
| ORM | SQLAlchemy | 2.x |
| Migration | Alembic | 1.x |
| Chain Client | web3.py | 6.x |
| Main Database | PostgreSQL | 16 |
| Time-Series | TimescaleDB | 2.x |
| Cache | Redis | 7.x |
| Task Queue | Celery | 5.x |
| Scheduler | APScheduler | 3.x |
| Logging | structlog | 23.x |

## Rationale

### Python + FastAPI
- **Async Support**: Native async/await for high concurrency
- **Auto Documentation**: OpenAPI/Swagger auto-generated
- **Type Hints**: Better code quality and IDE support
- **Web3 Ecosystem**: web3.py is mature and well-documented

### PostgreSQL + TimescaleDB
- **Reliability**: Industry-proven ACID compliance
- **TimescaleDB**: Native time-series support as PostgreSQL extension
- **Single Deployment**: Both in same database cluster

### Celery + Redis
- **Distributed Tasks**: Battle-tested distributed task queue
- **Scheduling**: APScheduler for cron-like scheduling
- **Caching**: Redis for high-performance caching

## Consequences

### Positive
- Mature, well-documented ecosystem
- Strong async support
- Good blockchain integration
- Single database technology (PostgreSQL family)

### Negative
- Python GIL may limit CPU-bound operations
- Multiple services to manage (API, workers, scheduler)

### Mitigation
- Use process-based parallelism for CPU-bound tasks
- Kubernetes for service orchestration

## References

- `docs/backend/00-overview.md` - Technology rationale
- FastAPI documentation: https://fastapi.tiangolo.com/
- web3.py documentation: https://web3py.readthedocs.io/
