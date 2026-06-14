"""Smoke check key API routes against a running FastAPI server.

Usage:
    python scripts/check_api_routes.py --base-url http://127.0.0.1:8000

The script treats 401/403 as connected-but-auth-required. It fails on 404 so
route drift is visible without requiring admin credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class RouteCheck:
    method: str
    path: str
    note: str
    allow_resource_404: bool = False


ROUTES: tuple[RouteCheck, ...] = (
    RouteCheck("GET", "/health", "public health"),
    RouteCheck("GET", "/imports", "canonical import route"),
    RouteCheck("GET", "/import", "legacy import alias"),
    RouteCheck("GET", "/api/rbac/users", "RBAC through FastAPI"),
    RouteCheck("GET", "/api/admin/config", "admin config"),
    RouteCheck("GET", "/api/admin/production-backends", "production backend readiness"),
    RouteCheck("GET", "/admin/runtime/adapters", "runtime adapters"),
    RouteCheck("GET", "/admin/runtime/governance/summary", "runtime governance summary"),
    RouteCheck("GET", "/admin/sandbox-policies", "sandbox policies"),
    RouteCheck("GET", "/developers/me", "developer console", allow_resource_404=True),
    RouteCheck("GET", "/agent-marketplace/categories", "marketplace categories"),
)


def check_route(base_url: str, route: RouteCheck, token: str = "") -> dict[str, object]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(f"{base_url.rstrip('/')}{route.path}", method=route.method, headers=headers)
    try:
        with urlopen(req, timeout=5) as res:
            body = res.read(200).decode("utf-8", errors="replace")
            return {"path": route.path, "status": res.status, "ok": res.status != 404, "note": route.note, "sample": body}
    except HTTPError as exc:
        sample = exc.read(200).decode("utf-8", errors="replace")
        resource_missing = route.allow_resource_404 and exc.code == 404 and "not found" in sample.lower()
        return {"path": route.path, "status": exc.code, "ok": exc.code != 404 or resource_missing, "note": route.note, "sample": sample}
    except URLError as exc:
        return {"path": route.path, "status": "connect_error", "ok": False, "note": route.note, "sample": str(exc)}


def run_checks(base_url: str, routes: Iterable[RouteCheck], token: str = "") -> list[dict[str, object]]:
    return [check_route(base_url, route, token) for route in routes]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default="", help="Optional bearer token for protected routes")
    args = parser.parse_args()

    results = run_checks(args.base_url, ROUTES, args.token)
    print(json.dumps({"base_url": args.base_url, "results": results}, ensure_ascii=False, indent=2))
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
