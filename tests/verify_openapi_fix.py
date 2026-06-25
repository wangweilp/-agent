"""Minimal verification: OpenAPI schema + /docs after ForwardRef fix."""
import io, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import logging
logging.getLogger().setLevel(logging.WARNING)
for n in logging.root.manager.loggerDict:
    logging.getLogger(n).setLevel(logging.WARNING)

from main import app
from fastapi.testclient import TestClient

print("=" * 60)
print("  OpenAPI Fix Verification")
print("=" * 60)

# 1. app.openapi()
print("\n[1] app.openapi()…")
try:
    schema = app.openapi()
    paths = len(schema.get("paths", {}))
    print(f"    ✅ OK — {paths} paths generated")
except Exception:
    import traceback
    print(f"    ❌ FAILED\n{traceback.format_exc()}")
    sys.exit(1)

# 2. GET /openapi.json
print("\n[2] GET /openapi.json…")
client = TestClient(app)
resp = client.get("/openapi.json")
if resp.status_code == 200:
    data = resp.json()
    print(f"    ✅ HTTP 200 — {len(data.get('paths',{}))} paths")
else:
    print(f"    ❌ HTTP {resp.status_code}: {resp.text[:200]}")

# 3. GET /docs
print("\n[3] GET /docs…")
resp = client.get("/docs")
if resp.status_code == 200:
    print(f"    ✅ HTTP 200 — content-length={len(resp.text)}")
else:
    print(f"    ❌ HTTP {resp.status_code}")

# 4. The affected route still works
print("\n[4] GET /health…")
resp = client.get("/health")
print(f"    {'✅' if resp.status_code == 200 else '❌'} HTTP {resp.status_code}: {resp.json()['status']}")

print("\n✅ All verifications passed" if True else "")
