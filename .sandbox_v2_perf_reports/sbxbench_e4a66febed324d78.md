# Sandbox v2 Benchmark Report: sbxbench_e4a66febed324d78

- Profile: `smoke`
- Scope: synthetic fixture only; no user code, external network, containers, or MicroVMs

| Target | Status | Ops | Success | Failure | p50 ms | p95 ms | p99 ms | ops/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| alerts | completed | 3 | 3 | 0 | 1.74 | 2.873 | 2.873 | 600.0 |
| metrics | completed | 3 | 3 | 0 | 5.462 | 6.333 | 6.333 | 187.5 |
| queue | completed | 3 | 3 | 0 | 0.55 | 0.711 | 0.711 | 3000.0 |
| jobs | completed | 3 | 3 | 0 | 0.162 | 0.22 | 0.22 | 3000.0 |

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
