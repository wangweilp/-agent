from src.adapters.config import Settings
from src.adapters.production_backends import assess_production_backend_readiness


def test_default_backend_readiness_keeps_local_demo_defaults():
    settings = Settings(deepseek_api_key="sk-test")
    data = assess_production_backend_readiness(settings)

    assert data["status"] == "local_demo_default"
    assert data["production_ready"] is False
    assert data["components"]["database"]["configured_backend"] == "sqlite"
    assert data["components"]["database"]["enabled"] is True
    assert data["components"]["cache"]["configured_backend"] == "memory"


def test_postgres_redis_object_storage_queue_are_metadata_only_until_connected():
    settings = Settings(
        deepseek_api_key="sk-test",
        database_backend="postgres",
        cache_backend="redis",
        object_storage_backend="minio",
        queue_backend="celery",
        postgres_dsn="postgresql://user:pass@localhost:5432/cognitive_os",
        redis_url="redis://localhost:6379/0",
        object_storage_endpoint="http://localhost:9000",
        queue_url="redis://localhost:6379/1",
    )
    data = assess_production_backend_readiness(settings)

    assert data["production_ready"] is False
    assert data["components"]["database"]["status"] == "configured_metadata_only"
    assert data["components"]["database"]["enabled"] is False
    assert data["components"]["cache"]["status"] == "configured_metadata_only"
    assert data["components"]["object_storage"]["configured_backend"] == "minio"
    assert data["components"]["task_queue"]["configured_backend"] == "celery"
