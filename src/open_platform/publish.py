"""Open Platform Publish — Manifest → MarketplaceAgent 映射。

安全边界：
- 不执行 package_url
- 不注册 AgentRuntime
- 不创建 TenantAgentInstallation
- 不接入真实支付
- Developer Agent 默认 visibility=beta, pricing_model=free
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.agents.marketplace import MarketplaceAgent
from src.open_platform.developer import DeveloperAccount
from src.open_platform.submission import AgentSubmission


def build_marketplace_agent_from_submission(
    submission: AgentSubmission,
    developer: DeveloperAccount | None,
) -> MarketplaceAgent:
    """将 approved AgentSubmission 映射为 MarketplaceAgent。

    映射后的 Agent 仍需经过 Marketplace install/permissions 流程才能使用。
    """

    manifest = submission.agent_manifest
    if manifest is None:
        raise ValueError("Cannot publish submission without agent_manifest")

    # Reuse existing marketplace_agent_id if set
    marketplace_agent_id = submission.marketplace_agent_id
    if not marketplace_agent_id:
        marketplace_agent_id = f"mkp_dev_{manifest.name}_{submission.submission_id[-8:]}"

    # agent_id: developer_<submission_id>
    agent_id = f"developer_{submission.submission_id}"

    publisher_name = "Developer"
    if developer:
        publisher_name = developer.organization_name or developer.display_name or "Developer"

    # Metadata
    metadata: dict[str, Any] = {
        "developer_id": submission.developer_id,
        "developer_user_id": developer.user_id if developer else "",
        "developer_tenant_id": developer.tenant_id if developer else "",
        "submission_id": submission.submission_id,
        "review_status": "published",
        "source_type": submission.source_type,
        "runtime_type": manifest.runtime_type,
        "sandbox_level": manifest.security_profile.sandbox_level if manifest.security_profile else "no_execution",
        "verified_publisher": developer.verified if developer else False,
        "package_url_present": bool(submission.package_url),
        "no_remote_code_execution": True,
        "published_from_open_platform": True,
    }

    return MarketplaceAgent(
        marketplace_agent_id=marketplace_agent_id,
        agent_id=agent_id,
        name=manifest.name,
        display_name=manifest.display_name,
        description=manifest.description,
        long_description=manifest.metadata.get("long_description") if isinstance(manifest.metadata.get("long_description"), str) else manifest.description,
        category=manifest.metadata.get("category") if isinstance(manifest.metadata.get("category"), str) else "assistant",
        department=manifest.metadata.get("department") if isinstance(manifest.metadata.get("department"), str) else "developer",
        capabilities=list(manifest.capabilities),
        required_permissions=list(manifest.required_permissions),
        supported_workflows=list(manifest.supported_workflows),
        version=manifest.version,
        publisher_type="developer",
        publisher_name=publisher_name,
        icon=manifest.metadata.get("icon") if isinstance(manifest.metadata.get("icon"), str) else None,
        visibility="beta",          # MVP: 默认 beta，不自动 public
        pricing_model="free",       # MVP: 不做真实支付
        usage_limits=dict(manifest.usage_limits),
        install_count=0,
        rating=0.0,
        status="beta",             # MVP: beta
        metadata=metadata,
    )
