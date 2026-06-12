"""Manifest example builders — return dict, no file I/O unless explicitly saved."""

from typing import Any


def build_minimal_manifest() -> dict[str, Any]:
    return {
        "name": "hello-world-agent",
        "display_name": "Hello World Agent",
        "description": "A minimal valid developer agent manifest for testing and quick-start.",
        "version": "0.1.0",
        "capabilities": ["knowledge_search"],
        "required_permissions": ["agent:execute", "memory:read"],
        "supported_workflows": [],
        "runtime_type": "manifest_only",
        "entrypoint": None,
        "config_schema": {},
        "usage_limits": {},
        "security_profile": {
            "sandbox_level": "no_execution",
            "requires_network": False,
            "reads_user_data": False,
            "writes_user_data": False,
        },
        "metadata": {
            "no_remote_code_execution": True,
            "simulation_only": True,
        },
    }


def build_package_metadata_manifest() -> dict[str, Any]:
    return {
        "name": "knowledge-assistant",
        "display_name": "Knowledge Assistant",
        "description": "Demonstrates package metadata: checksum, signature, license, dependencies. Package URL is NOT downloaded.",
        "version": "1.0.0",
        "capabilities": ["knowledge_search", "knowledge_recommend"],
        "required_permissions": ["agent:execute", "memory:read", "kg:query"],
        "supported_workflows": [],
        "runtime_type": "manifest_only",
        "entrypoint": None,
        "config_schema": {},
        "usage_limits": {},
        "security_profile": {
            "sandbox_level": "simulation_only",
            "requires_network": False,
            "allowed_domains": [],
            "reads_user_data": False,
            "writes_user_data": False,
            "requires_secrets": False,
            "allowed_secret_names": [],
            "data_access_scope": [],
            "max_timeout_ms": 5000,
            "max_memory_mb": 64,
        },
        "metadata": {
            "package_url": "https://github.com/example/knowledge-assistant/releases/download/v1.0.0/knowledge-assistant-1.0.0.zip",
            "repository_url": "https://github.com/example/knowledge-assistant",
            "package_name": "knowledge-assistant",
            "package_version": "1.0.0",
            "package_checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "package_checksum_algorithm": "sha256",
            "package_signature": "untrusted comment: minisign signature",
            "package_signature_algorithm": "minisign",
            "signing_key_id": "example-key-2026",
            "license": "MIT",
            "security_contact": "security@example.com",
            "dependencies": ["python>=3.10", "requests>=2.28"],
            "no_remote_code_execution": True,
            "simulation_only": True,
            "documentation_url": "https://docs.example.com/knowledge-assistant",
            "support_url": "https://github.com/example/knowledge-assistant/issues",
        },
    }


def build_invalid_network_manifest() -> dict[str, Any]:
    return {
        "name": "invalid-network-agent",
        "display_name": "Invalid Network Agent",
        "description": "This manifest requests network access — not allowed in Step 23 MVP.",
        "version": "0.1.0",
        "capabilities": ["external_api_call"],
        "required_permissions": ["agent:execute", "memory:read"],
        "supported_workflows": [],
        "runtime_type": "manifest_only",
        "entrypoint": None,
        "config_schema": {},
        "usage_limits": {},
        "security_profile": {
            "sandbox_level": "no_execution",
            "requires_network": True,
            "allowed_domains": ["api.example.com"],
            "reads_user_data": True,
            "writes_user_data": False,
        },
        "metadata": {
            "no_remote_code_execution": True,
            "simulation_only": True,
            "license": "MIT",
        },
    }
