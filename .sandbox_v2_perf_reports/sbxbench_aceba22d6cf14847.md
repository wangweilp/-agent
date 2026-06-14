# Sandbox v2 Benchmark Report: sbxbench_aceba22d6cf14847

- Profile: `smoke`
- Scope: synthetic fixture only; no user code, external network, containers, or MicroVMs

| Target | Status | Ops | Success | Failure | p50 ms | p95 ms | p99 ms | ops/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| alerts | completed | 3 | 3 | 0 | 1.05 | 1.229 | 1.229 | 1000.0 |
| metrics | completed | 3 | 3 | 0 | 4.094 | 7.632 | 7.632 | 200.0 |
| queue | completed | 3 | 3 | 0 | 0.536 | 0.675 | 0.675 | 3000.0 |
| jobs | completed | 3 | 3 | 0 | 0.136 | 0.316 | 0.316 | 3000.0 |

## Capacity Estimate
- Jobs/min: 180000.0
- Queue items/min: 180000.0
- Artifact metadata/min: 0.0
- Network preflight/min: 0.0

## Recommendations
- Keep ordinary pytest on smoke/small limits; never run large benchmarks by default.
- Move sustained job/metadata benchmarks to PostgreSQL before production capacity claims.
- Move distributed queue lease benchmarks to Redis before multi-worker rollout.
- Use MinIO/S3 for artifact-heavy capacity validation.
