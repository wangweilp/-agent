# Sandbox v2 Benchmark Report: sbxbench_ae2c72cde6e34d49

- Profile: `smoke`
- Scope: synthetic fixture only; no user code, external network, containers, or MicroVMs

| Target | Status | Ops | Success | Failure | p50 ms | p95 ms | p99 ms | ops/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| alerts | completed | 3 | 3 | 0 | 1.096 | 1.241 | 1.241 | 1000.0 |
| metrics | completed | 3 | 3 | 0 | 4.57 | 11.003 | 11.003 | 157.895 |
| queue | completed | 3 | 3 | 0 | 0.272 | 0.334 | 0.334 | 3000.0 |
| jobs | completed | 3 | 3 | 0 | 0.058 | 0.178 | 0.178 | 3000.0 |

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
