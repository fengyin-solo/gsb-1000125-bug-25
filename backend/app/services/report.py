"""检测报告业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "report"
REQUIRED_FIELDS = ["报告编号", "委托单位", "样品名称"]
FILTER_FIELDS = ["报告编号", "委托单位", "样品名称", "报告类型"]
STATUS_FIELD = "报告状态"
STATUS_ORDER = ["待编制", "编制中", "待批准", "已签发", "已撤回"]
ACTION_RULES = {"编制报告": "编制中", "提交批准": "待批准", "撤回报告": "已撤回"}
NEGATIVE_ACTIONS = []


class ReportService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        filters: dict[str, str] | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """按同一口径过滤并分页：所有条件取交集，顺序保持录入顺序不变。"""
        rows = store.rows(MODULE)
        if keyword and keyword.strip():
            rows = [row for row in rows if keyword.strip() in str(row.get("报告编号", ""))]
        if status and status.strip():
            rows = [row for row in rows if row.get("status") == status.strip()]
        for field in FILTER_FIELDS:
            value = str((filters or {}).get(field) or "").strip()
            if value:
                rows = [row for row in rows if value in str(row.get(field, ""))]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def stats(self) -> list[dict[str, Any]]:
        """模块级数量指标：与列表同源统计，保证指标和记录对得上。"""
        rows = store.rows(MODULE)
        month = date.today().strftime("%Y-%m")
        issued = sum(
            1
            for row in rows
            if row.get("status") == "已签发" and str(row.get("签发日期", "")).startswith(month)
        )
        return [
            {"label": "待编制报告", "value": sum(1 for row in rows if row.get("status") == "待编制")},
            {"label": "待批准报告", "value": sum(1 for row in rows if row.get("status") == "待批准")},
            {"label": "本月签发", "value": issued},
        ]

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry[STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测报告 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于检测报告可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry[STATUS_FIELD] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"检测报告已{action}"
