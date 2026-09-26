"""检测报告接口：维护检测报告，覆盖编制报告、提交批准、签发报告、撤回报告等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.report import FILTER_FIELDS, STATUS_ORDER, ReportService

router = APIRouter(prefix="/api/report", tags=["检测报告"])

service = ReportService()

LIST_FIELDS = ["报告编号", "委托单位", "样品名称", "报告类型", "编制人", "批准人", "签发日期", "报告状态"]
STATUSES = STATUS_ORDER
FILTER_ALIASES = {
    "报告编号": ("keyword", "report_no", "reportNo"),
    "委托单位": ("client",),
    "样品名称": ("sample_name", "sampleName"),
    "报告类型": ("report_type", "reportType"),
}


def _first_param(request: Request, names: tuple[str, ...]) -> str | None:
    for name in names:
        value = request.query_params.get(name)
        if value and value.strip():
            return value.strip()
    return None


def _read_filters(request: Request) -> tuple[dict[str, str], str | None]:
    filters: dict[str, str] = {}
    for field in FILTER_FIELDS:
        value = request.query_params.get(field)
        if value and value.strip():
            filters[field] = value.strip()
            continue
        aliases = FILTER_ALIASES[field]
        alias_value = _first_param(request, aliases)
        if alias_value:
            filters[field] = alias_value
    status = _first_param(request, ("status", "报告状态"))
    return filters, status


def _read_page(request: Request) -> tuple[int, int]:
    try:
        page = int(request.query_params.get("page", "1"))
        size = int(request.query_params.get("size", "20"))
    except ValueError:
        raise HTTPException(status_code=400, detail="页码和每页条数必须是整数") from None
    if page < 1:
        raise HTTPException(status_code=400, detail="页码必须从 1 开始")
    if size < 1:
        raise HTTPException(status_code=400, detail="每页条数至少为 1")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    return page, size


@router.get("", response_model=PageResult[dict])
def list_entries(request: Request) -> PageResult[dict]:
    """按报告编号、委托单位、样品名称、报告类型与状态过滤；空条件和无结果都返回稳定分页。"""
    filters, status = _read_filters(request)
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail="报告状态不在允许范围内")
    page, size = _read_page(request)
    items, total, page, size, stats = service.list_entries(filters=filters, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size, stats=stats)


@router.get("/export")
def export_entries(request: Request) -> dict[str, Any]:
    """导出当前筛选条件下的全量数据，口径与列表完全一致。"""
    filters, status = _read_filters(request)
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail="报告状态不在允许范围内")
    items, total, _, _, _ = service.list_entries(filters=filters, status=status, page=1, size=10000)
    return {"module": "report", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict[str, Any]:
    """读取单条检测报告明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"检测报告 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条检测报告，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="检测报告已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条检测报告执行允许的状态动作；互斥或非法动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
