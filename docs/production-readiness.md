# Production Readiness

This project still defaults to a local demonstration mode:

- Database: SQLite
- Vector store: ChromaDB
- Cache: in-memory process state
- Object storage: local filesystem paths
- Task queue: inline/local worker behavior

The new production backend settings make the migration path explicit without
breaking the current demo:

- `DATABASE_BACKEND=sqlite/postgres`
- `CACHE_BACKEND=memory/redis`
- `OBJECT_STORAGE_BACKEND=local/s3/minio`
- `QUEUE_BACKEND=inline/redis/celery/rq`

## What Is Implemented

- A unified Settings entry for the production backend switches.
- Metadata-only readiness adapters for PostgreSQL, Redis, object storage, and task queues.
- A backend health payload at `GET /api/admin/production-backends`.
- Documentation and a compose example for PostgreSQL, Redis, and MinIO.

## What Is Not Claimed

This is not a complete production cluster deployment. PostgreSQL, Redis,
S3/MinIO, and a real task queue are not enabled by default and are not opened by
the readiness checks. The current work is adapter foundation, configuration,
health visibility, and migration planning.

## Recommended Migration Path

1. Keep local demo on SQLite + ChromaDB until production credentials are ready.
2. Generate SQLAlchemy/Alembic migrations for PostgreSQL.
3. Run SQLite to PostgreSQL data migration in a staging environment.
4. Add Redis cache client, cache invalidation tests, and fallback behavior.
5. Move uploads/imports/artifacts to S3 or MinIO with signed access and lifecycle rules.
6. Add Celery/RQ/Redis queue with idempotency keys, dead-letter handling, and worker probes.
7. Run the full backend and frontend smoke suite against the production-like stack.

## Health Check

Use:

```bash
python scripts/check_api_routes.py --base-url http://127.0.0.1:8000
```

Authenticated admin users can inspect:

```text
GET /api/admin/production-backends
```
