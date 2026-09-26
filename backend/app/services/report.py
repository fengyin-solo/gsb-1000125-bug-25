"""检测报告业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from threading import Lock
from typing import Any

from app.store import store

MODULE = "report"
REQUIRED_FIELDS = ["报告编号", "委托单位", "样品名称"]
OPTIONAL_FIELDS = ["报告类型", "编制人", "批准人", "签发日期"]
FILTER_FIELDS = ["报告编号", "委托单位", "样品名称", "报告类型"]
STATUS_ORDER = ["待编制", "编制中", "待批准", "已签发", "已撤回"]
ACTION_RULES = {"编制报告": "编制中", "提交批准": "待批准", "签发报告": "已签发", "撤回报告": "已撤回"}
NEXT_ACTIONS: dict[str, tuple[str, ...]] = {
    "待编制": ("编制报告",),
    "编制中": ("提交批准",),
    "待批准": ("签发报告",),
    "已签发": ("撤回报告",),
    "已撤回": (),
}
NEGATIVE_ACTIONS: set[str] = set()

_action_lock = Lock()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """统一内部状态与列表展示的报告状态，避免列表、详情、动作结果各说各话。"""
    status = _clean(entry.get("status"))
    if status not in STATUS_ORDER:
        status = STATUS_ORDER[0]
    entry["status"] = status
    entry["报告状态"] = status
    entry["pending"] = status in {"待编制", "编制中", "待批准"}
    entry["abnormal"] = bool(entry.get("abnormal")) and status in NEGATIVE_ACTIONS
    return entry


def _matches(entry: dict[str, Any], filters: dict[str, str]) -> bool:
    for field, keyword in filters.items():
        if keyword and keyword.casefold() not in _clean(entry.get(field)).casefold():
            return False
    return True


class ReportService:
    def list_entries(
        self,
        *,
        filters: dict[str, str] | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int, int, int, dict[str, int]]:
        normalized_filters = {
            field: _clean(value)
            for field, value in (filters or {}).items()
            if field in FILTER_FIELDS and _clean(value)
        }
        normalized_status = _clean(status)
        rows: list[dict[str, Any]] = []
        if not normalized_status or normalized_status in STATUS_ORDER:
            rows = [_normalize_entry(dict(row)) for row in store.rows(MODULE)]
            if normalized_status:
                rows = [row for row in rows if row["status"] == normalized_status]
            rows = [row for row in rows if _matches(row, normalized_filters)]

        total = len(rows)
        page = max(page, 1)
        size = max(size, 1)
        total_pages = max((total + size - 1) // size, 1)
        if page > total_pages:
            page = total_pages
        start = (page - 1) * size
        stats = self._build_stats(rows)
        return rows[start:start + size], total, page, size, stats

    @staticmethod
    def _build_stats(rows: list[dict[str, Any]]) -> dict[str, int]:
        month = date.today().strftime("%Y-%m")
        return {
            "待编制报告": sum(1 for row in rows if row["status"] == "待编制"),
            "待批准报告": sum(1 for row in rows if row["status"] == "待批准"),
            "本月签发": sum(
                1
                for row in rows
                if row["status"] == "已签发" and _clean(row.get("签发日期")).startswith(month)
            ),
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _normalize_entry(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not _clean(values.get(field))]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in [*REQUIRED_FIELDS, *OPTIONAL_FIELDS]:
            entry[field] = _clean(values.get(field))
        entry["status"] = STATUS_ORDER[0]
        entry["报告状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        action = _clean(action)
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于检测报告可执行范围"

        with _action_lock:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                return None, f"检测报告 {entry_id} 不存在或已归档"
            _normalize_entry(entry)
            current_status = entry["status"]
            if action not in NEXT_ACTIONS[current_status]:
                allowed = "、".join(NEXT_ACTIONS[current_status]) or "无"
                return None, f"当前状态为「{current_status}」，仅可执行：{allowed}"

            target = ACTION_RULES[action]
            entry["status"] = target
            entry["报告状态"] = target
            entry["pending"] = target in {"待编制", "编制中", "待批准"}
            entry["abnormal"] = action in NEGATIVE_ACTIONS
            if action == "签发报告":
                entry["签发日期"] = date.today().isoformat()
            return entry, f"检测报告已{action}"
