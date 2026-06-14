# Sandbox v2 Benchmark Report: sbxbench_9f6e8ee82dfb4a46

- Profile: `smoke`
- Scope: synthetic fixture only; no user code, external network, containers, or MicroVMs

| Target | Status | Ops | Success | Failure | p50 ms | p95 ms | p99 ms | ops/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| alerts | completed | 3 | 3 | 0 | 3.364 | 3.591 | 3.591 | 300.0 |
| metrics | completed | 3 | 3 | 0 | 8.194 | 8.387 | 8.387 | 136.364 |
| queue | completed | 3 | 3 | 0 | 0.579 | 0.751 | 0.751 | 3000.0 |
| jobs | completed | 3 | 3 | 0 | 0.238 | 0.248 | 0.248 | 3000.0 |

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
