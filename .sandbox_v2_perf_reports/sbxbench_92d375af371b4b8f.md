# Sandbox v2 Benchmark Report: sbxbench_92d375af371b4b8f

- Profile: `smoke`
- Scope: synthetic fixture only; no user code, external network, containers, or MicroVMs

| Target | Status | Ops | Success | Failure | p50 ms | p95 ms | p99 ms | ops/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| alerts | completed | 3 | 3 | 0 | 0.875 | 1.194 | 1.194 | 1500.0 |
| metrics | completed | 3 | 3 | 0 | 4.093 | 4.191 | 4.191 | 250.0 |
| queue | completed | 3 | 3 | 0 | 0.337 | 0.357 | 0.357 | 3000.0 |
| jobs | completed | 3 | 3 | 0 | 0.092 | 0.129 | 0.129 | 3000.0 |

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
