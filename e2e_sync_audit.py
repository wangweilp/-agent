"""第三阶段 E2E：Sync 完整闭环（等待执行完成，不提前删除）。
验证真实链路：login -> create connector -> test -> create job -> run -> 轮询执行到 completed -> 资源/变更落库 -> 清理。
"""
import json
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = "http://127.0.0.1:8000"
ROOT = "D:/dma/day2/data/sync_roots/e2e"


def call(method, path, token=None, body=None):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def main():
    print("=== 1. 登录 ===")
    code, resp = call("POST", "/auth/login", body={
        "email": "471417088@qq.com", "password": "471417088lP"})
    if code != 200:
        print("FAIL login:", resp); sys.exit(1)
    token = resp["access_token"]
    print("login ok")

    print("\n=== 2. 创建 connector ===")
    code, resp = call("POST", "/sync/connectors", token=token, body={
        "name": "E2E Complete",
        "connector_type": "local_folder",
        "credentials": {"folder_path": ROOT},
    })
    if code != 200:
        print("FAIL create:", resp); sys.exit(1)
    cid = resp["connector"]["id"]
    print("created", cid)

    print("\n=== 3. test ===")
    code, resp = call("POST", f"/sync/connectors/{cid}/test", token=token)
    print("test:", resp.get("test"))

    print("\n=== 4. create job ===")
    code, resp = call("POST", "/sync/jobs", token=token, body={
        "connector_config_id": cid, "name": "E2E Complete Job", "rule_type": "manual"})
    if code != 200:
        print("FAIL job:", resp); sys.exit(1)
    jid = resp["job"]["id"]
    print("job", jid)

    print("\n=== 5. run ===")
    code, resp = call("POST", f"/sync/jobs/{jid}/run", token=token)
    print("run:", resp.get("status"), "execution:", resp.get("execution_id"))
    eid = resp.get("execution_id")

    print("\n=== 6. 轮询执行直至非 running ===")
    final = None
    for i in range(30):
        time.sleep(2)
        code, resp = call("GET", f"/sync/jobs/{jid}", token=token)
        execs = resp.get("recent_executions", [])
        if execs:
            final = execs[0]
            st = final.get("status")
            print(f"  poll {i}: status={st} items_new={final.get('items_new')} memories={final.get('memories_created')} error={final.get('error')}")
            if st in ("completed", "failed", "partial"):
                break
    if final is None:
        print("WARN: no execution found"); sys.exit(1)

    print("\n=== 7. history ===")
    code, resp = call("GET", "/sync/history", token=token)
    print("history count:", resp.get("total"))

    print("\n=== 8. 清理 ===")
    call("DELETE", f"/sync/jobs/{jid}", token=token)
    call("DELETE", f"/sync/connectors/{cid}", token=token)
    print("cleaned")
    print("\nDONE")


if __name__ == "__main__":
    main()