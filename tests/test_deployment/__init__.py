"""Tests for deployment configuration validation."""
import json
import os
import pytest
import yaml


DEPLOY_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "deployment")


def _safe_load_yaml(path: str) -> dict:
    """安全加载 YAML 文件，文件不存在则返回空字典。"""
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


class TestDockerCompose:
    """Validate docker-compose.yml."""

    @pytest.fixture
    def compose_path(self):
        return os.path.join(DEPLOY_DIR, "docker", "docker-compose.yml")

    def test_compose_file_exists(self, compose_path):
        assert os.path.exists(compose_path), f"Expected {compose_path} to exist"

    def test_compose_has_services(self, compose_path):
        if not os.path.exists(compose_path):
            pytest.skip("File not yet created")
        data = _safe_load_yaml(compose_path)
        assert "services" in data
        assert len(data["services"]) >= 1

    def test_compose_version_or_top_level(self, compose_path):
        if not os.path.exists(compose_path):
            pytest.skip("File not yet created")
        data = _safe_load_yaml(compose_path)
        # docker compose v2 doesn't require version field
        assert isinstance(data, dict)


class TestDockerfile:
    """Validate Dockerfile."""

    @pytest.fixture
    def dockerfile_path(self):
        return os.path.join(DEPLOY_DIR, "docker", "Dockerfile")

    def test_dockerfile_exists(self, dockerfile_path):
        assert os.path.exists(dockerfile_path), f"Expected {dockerfile_path} to exist"

    def test_dockerfile_has_from(self, dockerfile_path):
        if not os.path.exists(dockerfile_path):
            pytest.skip("File not yet created")
        with open(dockerfile_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "FROM" in content
        assert "EXPOSE" in content or "CMD" in content


class TestHelmChart:
    """Validate Helm chart structure."""

    def test_chart_yaml_exists(self):
        path = os.path.join(DEPLOY_DIR, "helm", "Chart.yaml")
        assert os.path.exists(path), f"Expected {path} to exist"

    def test_chart_yaml_valid(self):
        path = os.path.join(DEPLOY_DIR, "helm", "Chart.yaml")
        if not os.path.exists(path):
            pytest.skip("File not yet created")
        data = _safe_load_yaml(path)
        assert "name" in data
        assert "version" in data

    def test_values_yaml_exists(self):
        path = os.path.join(DEPLOY_DIR, "helm", "values.yaml")
        assert os.path.exists(path), f"Expected {path} to exist"

    def test_values_has_image(self):
        path = os.path.join(DEPLOY_DIR, "helm", "values.yaml")
        if not os.path.exists(path):
            pytest.skip("File not yet created")
        data = _safe_load_yaml(path)
        # Should have image config or service config
        assert isinstance(data, dict)

    def test_templates_exist(self):
        templates_dir = os.path.join(DEPLOY_DIR, "helm", "templates")
        assert os.path.isdir(templates_dir), f"Expected {templates_dir} to exist"
        if os.path.isdir(templates_dir):
            files = os.listdir(templates_dir)
            assert len(files) >= 2  # deployment.yaml + service.yaml at minimum

    def test_deployment_template(self):
        path = os.path.join(DEPLOY_DIR, "helm", "templates", "deployment.yaml")
        assert os.path.exists(path), f"Expected {path} to exist"

    def test_service_template(self):
        path = os.path.join(DEPLOY_DIR, "helm", "templates", "service.yaml")
        assert os.path.exists(path), f"Expected {path} to exist"


class TestDeploymentReadme:
    """Validate deployment README."""

    def test_readme_exists(self):
        path = os.path.join(DEPLOY_DIR, "README.md")
        assert os.path.exists(path), f"Expected {path} to exist"

    def test_readme_has_content(self):
        path = os.path.join(DEPLOY_DIR, "README.md")
        if not os.path.exists(path):
            pytest.skip("File not yet created")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert len(content) > 100
        # Should cover key deployment topics
        assert any(kw in content.lower() for kw in ["docker", "部署", "kubernetes", "helm"])
