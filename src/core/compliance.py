"""Enterprise Compliance Domain Models — Data Retention / Deletion / PII Detection.

六边形架构核心层：只定义数据类和协议，不引用任何外部库。

支持：
- 数据保留策略（保留期限、归档策略）
- 个人数据导出 / 删除（GDPR/个人信息保护法）
- 敏感信息检测（手机号/邮箱/身份证/银行卡）
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import uuid4


# ── Policy Types ──


class RetentionPeriod(StrEnum):
    """数据保留期限。"""
    DAYS_30 = "30d"
    DAYS_90 = "90d"
    DAYS_180 = "180d"
    YEAR_1 = "1y"
    YEAR_3 = "3y"
    YEAR_7 = "7y"
    FOREVER = "forever"


class ArchiveAction(StrEnum):
    """归档动作。"""
    ARCHIVE = "archive"           # 标记为已归档
    DELETE = "delete"             # 硬删除
    ANONYMIZE = "anonymize"      # 匿名化处理


# ── Data Retention Policy ──


@dataclass
class DataRetentionPolicy:
    """数据保留策略 — 定义某类数据的保留期限和处理方式。"""
    name: str
    resource_type: str                          # "memory" | "audit_log" | "import_job" | "notification"
    retention_period: RetentionPeriod
    archive_action: ArchiveAction = ArchiveAction.ARCHIVE
    organization_id: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))
    description: str = ""
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def retention_days(self) -> int | None:
        """返回保留天数，None 表示永久。"""
        mapping = {
            "30d": 30, "90d": 90, "180d": 180,
            "1y": 365, "3y": 1095, "7y": 2555,
            "forever": None,
        }
        return mapping.get(self.retention_period.value, None)


# ── GDPR / Personal Data Request ──


class DataRequestType(StrEnum):
    """个人数据请求类型。"""
    EXPORT = "export"          # 导出我的数据
    DELETE = "delete"          # 删除我的数据


class DataRequestStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DataRequest:
    """个人数据请求 — 用户提交的导出或删除请求。"""
    user_id: str
    organization_id: str
    request_type: DataRequestType
    id: str = field(default_factory=lambda: str(uuid4()))
    status: DataRequestStatus = DataRequestStatus.PENDING
    result_url: str = ""                        # 导出文件下载链接
    error_message: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


# ── Sensitive Info Detection ──


@dataclass
class SensitiveMatch:
    """敏感信息匹配结果。"""
    entity_type: str                            # "phone" | "email" | "id_card" | "bank_card"
    value_masked: str                           # 脱敏后的值: "138****1234"
    position: int = 0                           # 在文本中的起始位置
    confidence: float = 1.0                     # 置信度 0-1


# ── PII Detection Patterns ──

PII_PATTERNS: dict[str, re.Pattern] = {
    "phone": re.compile(
        r'(?<!\d)(1[3-9]\d)[\- ]?(\d{4})[\- ]?(\d{4})(?!\d)'
    ),
    "email": re.compile(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    ),
    "id_card": re.compile(
        r'(?<!\d)([1-9]\d{5})(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)'
    ),
    "bank_card": re.compile(
        r'(?<!\d)(\d{4})[\- ]?(\d{4})[\- ]?(\d{4})[\- ]?(\d{4,7})(?!\d)'
    ),
}

MASK_PATTERNS: dict[str, str] = {
    "phone": r"\1****\3",
    "email": r"***@***",
    "id_card": r"\1****\2****",
    "bank_card": r"\1 **** **** ****",
}


def detect_sensitive(text: str, entity_types: list[str] | None = None) -> list[SensitiveMatch]:
    """检测文本中的敏感信息，返回匹配列表。

    Args:
        text: 待检测文本
        entity_types: 要检测的类型列表，None = 全部检测

    Returns:
        SensitiveMatch 列表
    """
    results: list[SensitiveMatch] = []
    targets = entity_types or list(PII_PATTERNS.keys())

    for etype in targets:
        pattern = PII_PATTERNS.get(etype)
        if pattern is None:
            continue
        for m in pattern.finditer(text):
            # 脱敏
            mask = MASK_PATTERNS.get(etype, "***")
            masked = text
            try:
                if etype == "phone":
                    masked = pattern.sub(mask, m.group())
                elif etype == "email":
                    masked = "***@***"
                elif etype == "id_card":
                    masked = pattern.sub(mask, m.group())
                elif etype == "bank_card":
                    masked = pattern.sub(mask, m.group())
                else:
                    masked = "***"
            except Exception:
                masked = "***"
            # Validate with checksum if id_card
            confidence = 1.0
            if etype == "id_card" and not _validate_id_checksum(m.group()):
                confidence = 0.5
            if etype == "bank_card" and not _luhn_check(m.group().replace(" ", "").replace("-", "")):
                confidence = 0.7

            results.append(SensitiveMatch(
                entity_type=etype,
                value_masked=masked,
                position=m.start(),
                confidence=confidence,
            ))

    return sorted(results, key=lambda x: x.position)


def mask_sensitive(text: str, entity_types: list[str] | None = None) -> str:
    """检测并脱敏文本中的敏感信息。"""
    matches = detect_sensitive(text, entity_types)
    # 从后往前替换，保持位置正确
    chars: list[str] = list(text)
    for m in reversed(matches):
        if m.entity_type == "email":
            # 简单替换整个 email
            pass  # email needs different handling — mask in place
    # Simple approach: just regex replace
    result = text
    for etype in (entity_types or list(PII_PATTERNS.keys())):
        pattern = PII_PATTERNS.get(etype)
        mask = MASK_PATTERNS.get(etype, "***")
        if pattern and mask:
            try:
                result = pattern.sub(mask, result)
            except Exception:
                pass
    return result


# ── Luhn / ID Checksum Validation ──


def _luhn_check(card_num: str) -> bool:
    """银行卡号 Luhn 校验。"""
    if not card_num.isdigit():
        return False
    total = 0
    reverse_digits = card_num[::-1]
    for i, ch in enumerate(reverse_digits):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _validate_id_checksum(id_str: str) -> bool:
    """中国身份证号校验码验证。"""
    if len(id_str) != 18:
        return False
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_chars = "10X98765432"
    try:
        nums = [int(c) for c in id_str[:17]]
    except ValueError:
        return False
    total = sum(n * w for n, w in zip(nums, weights))
    expected = check_chars[total % 11]
    return id_str[17].upper() == expected


# ── Compliance Report ──


@dataclass
class ComplianceReport:
    """合规报告 — 显示组织的合规状态。"""
    organization_id: str
    total_memories: int = 0
    sensitive_memories: int = 0               # 包含敏感信息的记忆数
    retention_policies: int = 0               # 活跃的保留策略数
    pending_data_requests: int = 0            # 待处理的个人数据请求
    expired_data_count: int = 0               # 超过保留期的数据量
    pii_breakdown: dict[str, int] = field(default_factory=dict)
    # {"phone": 5, "email": 12, "id_card": 3, "bank_card": 1}
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Protocols ──


@runtime_checkable
class ComplianceStore(Protocol):
    """合规存储协议。"""

    # Data Retention
    def create_retention_policy(self, policy: DataRetentionPolicy) -> DataRetentionPolicy: ...
    def get_retention_policy(self, policy_id: str) -> DataRetentionPolicy | None: ...
    def list_retention_policies(self, organization_id: str) -> list[DataRetentionPolicy]: ...
    def update_retention_policy(self, policy: DataRetentionPolicy) -> None: ...
    def delete_retention_policy(self, policy_id: str) -> None: ...
    def enforce_retention(self, organization_id: str) -> dict[str, int]: ...
    # 返回 {"archived": N, "deleted": N, "anonymized": N}

    # Data Requests
    def create_data_request(self, req: DataRequest) -> DataRequest: ...
    def get_data_request(self, request_id: str) -> DataRequest | None: ...
    def list_data_requests(self, organization_id: str,
                           user_id: str = "",
                           status: str = "") -> list[DataRequest]: ...
    def update_data_request(self, req: DataRequest) -> None: ...
    def export_user_data(self, user_id: str, organization_id: str) -> str: ...
    # 返回导出文件路径
    def delete_user_data(self, user_id: str, organization_id: str) -> int: ...
    # 返回删除的记录数

    # Compliance Report
    def generate_compliance_report(self, organization_id: str) -> ComplianceReport: ...

    # Sensitive Info
    def scan_sensitive_content(self, organization_id: str,
                                entity_types: list[str] | None = None) -> list[dict]: ...
    # 返回 [{"memory_id": ..., "matches": [SensitiveMatch, ...]}, ...]
