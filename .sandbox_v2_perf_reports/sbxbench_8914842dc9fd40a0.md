# Sandbox v2 Benchmark Report: sbxbench_8914842dc9fd40a0

- Profile: `smoke`
- Scope: synthetic fixture only; no user code, external network, containers, or MicroVMs

| Target | Status | Ops | Success | Failure | p50 ms | p95 ms | p99 ms | ops/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| alerts | completed | 3 | 3 | 0 | 1.15 | 1.255 | 1.255 | 1000.0 |
| metrics | completed | 3 | 3 | 0 | 4.605 | 5.264 | 5.264 | 214.286 |
| queue | completed | 3 | 3 | 0 | 0.228 | 0.384 | 0.384 | 3000.0 |
| jobs | completed | 3 | 3 | 0 | 0.068 | 0.174 | 0.174 | 3000.0 |

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
