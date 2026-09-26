"""检测报告接口：维护检测报告，覆盖编制报告、提交批准、撤回报告等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.report import FILTER_FIELDS, ReportService

router = APIRouter(prefix="/api/report", tags=["检测报告"])

service = ReportService()

LIST_FIELDS = ["报告编号", "委托单位", "样品名称", "报告类型", "编制人", "批准人", "签发日期", "报告状态"]
STATUSES = ["待编制", "编制中", "待批准", "已签发", "已撤回"]


def collect_filters(
    report_no: str | None,
    client: str | None,
    sample_name: str | None,
    report_type: str | None,
) -> dict[str, str]:
    """把四个字段级筛选条件收拢成字典，空白条件视为未填写。"""
    raw = {
        "报告编号": report_no,
        "委托单位": client,
        "样品名称": sample_name,
        "报告类型": report_type,
    }
    return {field: str(raw[field]).strip() for field in FILTER_FIELDS if str(raw[field] or "").strip()}


def check_pagination(page: int, size: int) -> None:
    """翻页口径统一校验：页码从 1 开始，每页 1~200 条，越界直接说明原因。"""
    if page < 1:
        raise HTTPException(status_code=400, detail="页码从 1 开始，请调整翻页参数")
    if size < 1:
        raise HTTPException(status_code=400, detail="每页至少 1 条，请调整分页参数")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按报告编号检索"),
    status: str | None = Query(default=None, description="待编制、编制中、待批准、已签发、已撤回"),
    report_no: str | None = Query(default=None, alias="报告编号", description="按报告编号过滤"),
    client: str | None = Query(default=None, alias="委托单位", description="按委托单位过滤"),
    sample_name: str | None = Query(default=None, alias="样品名称", description="按样品名称过滤"),
    report_type: str | None = Query(default=None, alias="报告类型", description="按报告类型过滤"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按报告编号、委托单位、样品名称、报告类型与状态过滤检测报告列表；没有数据时返回空页，不报错。"""
    check_pagination(page, size)
    filters = collect_filters(report_no, client, sample_name, report_type)
    items, total = service.list_entries(
        keyword=keyword, status=status, filters=filters, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats() -> dict[str, Any]:
    """检测报告数量指标：与列表同源统计，卡片数字和记录保持一致。"""
    return {"module": "report", "cards": service.stats()}


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按报告编号检索"),
    status: str | None = Query(default=None, description="待编制、编制中、待批准、已签发、已撤回"),
    report_no: str | None = Query(default=None, alias="报告编号", description="按报告编号过滤"),
    client: str | None = Query(default=None, alias="委托单位", description="按委托单位过滤"),
    sample_name: str | None = Query(default=None, alias="样品名称", description="按样品名称过滤"),
    report_type: str | None = Query(default=None, alias="报告类型", description="按报告类型过滤"),
) -> dict[str, Any]:
    """导出检测报告清单：返回当前过滤条件下的全量数据，口径与列表页一致。"""
    filters = collect_filters(report_no, client, sample_name, report_type)
    items, total = service.list_entries(
        keyword=keyword, status=status, filters=filters, page=1, size=10000
    )
    return {"module": "report", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
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
    """对单条检测报告执行编制报告、提交批准、撤回报告；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
