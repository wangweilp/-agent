from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.import_router import create_import_router
from src.adapters.config import Settings


class _History:
    def list_jobs(self):
        return []

    def get_job(self, job_id):
        return None


class _Worker:
    def __init__(self):
        self._history = _History()
        self._progress = {}
        self.pending = 0
        self.alerts = []
        self.stats = {
            "worker": {"alive": False},
            "jobs": {"completed": 0, "failed": 0, "in_progress": 0, "pending": 0},
            "dead_letter": {"count": 0},
        }

    def enqueue(self, job):
        self.pending += 1


def test_imports_canonical_and_import_alias_list_endpoint():
    app = FastAPI()
    app.include_router(
        create_import_router(
            Settings(deepseek_api_key="sk-test"),
            llm=object(),
            writer=object(),
            import_worker=_Worker(),
            agent=None,
        )
    )
    client = TestClient(app)

    canonical = client.get("/imports")
    alias = client.get("/import")

    assert canonical.status_code == 200
    assert alias.status_code == 200
    assert canonical.json()["jobs"] == []
    assert alias.json()["jobs"] == []
