"""Package Registry Service — Package 生命周期管理。

约束：
- metadata-only
- 审核流水线: draft → review → approved → published
- 不执行、不联网、不写文件
"""

from __future__ import annotations

import logging
from typing import Any

from src.open_platform.package_registry import (
    Package,
    PackageNotFoundError,
    PackageStateError,
    PackageStatus,
    PackageValidationError,
)

logger = logging.getLogger(__name__)


class PackageService:
    """Package 生命周期管理服务。"""

    def __init__(self, package_store) -> None:
        self._store = package_store

    def create_package(
        self,
        workspace_id: str,
        name: str,
        description: str = "",
        artifact_ids: list[str] | None = None,
        version: str = "0.1.0",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Package:
        package = Package(
            workspace_id=workspace_id,
            name=name,
            description=description,
            artifact_ids=artifact_ids or [],
            version=version,
            status=PackageStatus.DRAFT,
            metadata_only=True,
            tags=tags or [],
            metadata=metadata or {},
        )
        errors = package.validate()
        if errors:
            raise PackageValidationError(
                f"Package 校验失败: {'; '.join(errors)}", errors)
        created = self._store.create(package)
        logger.info("package_created", extra={"package_id": created.id, "package_name": name})
        return created

    def submit_review(self, package_id: str) -> Package:
        pkg = self._store.get(package_id)
        if pkg is None:
            raise PackageNotFoundError(f"Package 不存在: {package_id}")
        if pkg.status != PackageStatus.DRAFT:
            raise PackageStateError(
                f"只有 draft 状态可提交审核，当前: {pkg.status}")
        self._store.update_status(package_id, PackageStatus.REVIEW)
        logger.info("package_review_submitted", extra={"package_id": package_id})
        return self._store.get(package_id)  # type: ignore[return-value]

    def approve(self, package_id: str, reviewer_id: str,
                comment: str = "") -> Package:
        pkg = self._store.get(package_id)
        if pkg is None:
            raise PackageNotFoundError(f"Package 不存在: {package_id}")
        if pkg.status != PackageStatus.REVIEW:
            raise PackageStateError(
                f"只有 review 状态可 approve，当前: {pkg.status}")
        self._store.update_status(
            package_id, PackageStatus.APPROVED,
            reviewed_by=reviewer_id, review_comment=comment)
        logger.info("package_approved", extra={"package_id": package_id})
        return self._store.get(package_id)  # type: ignore[return-value]

    def reject(self, package_id: str, reviewer_id: str,
               comment: str = "") -> Package:
        pkg = self._store.get(package_id)
        if pkg is None:
            raise PackageNotFoundError(f"Package 不存在: {package_id}")
        if pkg.status != PackageStatus.REVIEW:
            raise PackageStateError(
                f"只有 review 状态可 reject，当前: {pkg.status}")
        self._store.update_status(
            package_id, PackageStatus.REJECTED,
            reviewed_by=reviewer_id, review_comment=comment)
        logger.info("package_rejected", extra={"package_id": package_id})
        return self._store.get(package_id)  # type: ignore[return-value]

    def publish(self, package_id: str, publisher_id: str) -> Package:
        pkg = self._store.get(package_id)
        if pkg is None:
            raise PackageNotFoundError(f"Package 不存在: {package_id}")
        if pkg.status != PackageStatus.APPROVED:
            raise PackageStateError(
                f"只有 approved 状态可 publish，当前: {pkg.status}")
        self._store.update_status(
            package_id, PackageStatus.PUBLISHED, published_by=publisher_id)
        logger.info("package_published", extra={"package_id": package_id})
        return self._store.get(package_id)  # type: ignore[return-value]

    def get(self, package_id: str) -> Package | None:
        return self._store.get(package_id)

    def list(self, *, workspace_id: str = "", status: str = "",
             limit: int = 50, offset: int = 0) -> list[Package]:
        return self._store.list(
            workspace_id=workspace_id, status=status,
            limit=limit, offset=offset)

    def delete(self, package_id: str) -> None:
        return self._store.delete(package_id)
