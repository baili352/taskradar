"""任务生成与管理接口。"""

import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.db.matters import get_matter
from app.db.tasks import (
    create_task,
    delete_task,
    get_task,
    list_tasks,
    try_create_generated_task,
    update_task,
)
from app.schemas.task import (
    TaskCreate,
    TaskDeadlineSuggestion,
    TaskGenerationResult,
    TaskPriority,
    TaskRecord,
    TaskUpdate,
)
from app.services.tasks.generator import build_tasks_from_matter

router = APIRouter(tags=["任务管理"])

TaskStatusQuery = Literal["pending", "in_progress", "done"]


def _task_not_found(task_id: int) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "task_not_found",
            "message": f"任务 {task_id} 不存在，可能已被删除或编号有误。",
        },
    )


def _matter_not_found(matter_id: int) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "matter_not_found",
            "message": f"事项 {matter_id} 不存在，无法生成或挂载任务。",
        },
    )


@router.post(
    "/matters/{matter_id}/tasks",
    response_model=TaskGenerationResult,
    status_code=status.HTTP_201_CREATED,
    summary="按事项办理流程生成任务",
)
def generate_tasks(matter_id: int) -> TaskGenerationResult:
    if matter_id <= 0:
        raise _matter_not_found(matter_id)

    try:
        matter = get_matter(matter_id)
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=500,
            detail={"code": "database_error", "message": f"读取事项失败：{error}"},
        ) from error

    if matter is None:
        raise _matter_not_found(matter_id)

    candidates = build_tasks_from_matter(matter)
    created: list[TaskRecord] = []
    skipped = 0

    try:
        for candidate in candidates:
            task = try_create_generated_task(
                matter_id=matter.id,
                title=candidate.title,
                description=candidate.description,
                priority=candidate.priority,
                deadline=candidate.deadline,
                step_key=candidate.step_key,
                evidence=candidate.evidence,
            )
            if task is None:
                skipped += 1
            else:
                created.append(task)
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=500,
            detail={"code": "database_error", "message": f"写入任务失败：{error}"},
        ) from error

    total_steps = len(matter.process)
    if total_steps == 0:
        message = "该事项没有可执行的办理流程，暂无任务可生成。"
    elif not candidates:
        message = "办理流程中没有识别到可执行的操作步骤，未生成任务。"
    elif not created:
        message = f"该事项的 {len(candidates)} 个流程步骤都已生成过任务，未重复创建。"
    else:
        message = f"已生成 {len(created)} 个任务"
        message += f"，跳过 {skipped} 个重复步骤。" if skipped else "。"

    suggestion = None
    # 只对“没有原文截止时间”的任务给出建议，避免覆盖原文中已明确的时间。
    suggested_ids = [task.id for task in created if task.deadline is None]
    if suggested_ids and matter.deadline:
        suggestion = TaskDeadlineSuggestion(
            deadline=matter.deadline,
            note="系统建议：依据事项总截止日期推断，仅作用于未设置截止时间的任务，确认后才会保存。",
            task_ids=suggested_ids,
        )

    return TaskGenerationResult(
        matter_id=matter.id,
        created=len(created),
        skipped=skipped,
        total_process_steps=total_steps,
        message=message,
        tasks=created,
        suggestion=suggestion,
    )


@router.post(
    "/tasks",
    response_model=TaskRecord,
    status_code=status.HTTP_201_CREATED,
    summary="手动新增任务",
)
def create_manual_task(payload: TaskCreate) -> TaskRecord:
    try:
        matter = get_matter(payload.matter_id)
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=500,
            detail={"code": "database_error", "message": f"读取事项失败：{error}"},
        ) from error

    if matter is None:
        raise _matter_not_found(payload.matter_id)

    try:
        return create_task(payload)
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=500,
            detail={"code": "database_error", "message": f"创建任务失败：{error}"},
        ) from error


@router.get("/tasks", response_model=list[TaskRecord], summary="查询任务列表")
def query_tasks(
    matter_id: int | None = Query(default=None, ge=1),
    status: TaskStatusQuery | None = None,
    priority: TaskPriority | None = None,
    limit: Annotated[int | None, Query(ge=1, le=500, description="分页大小，不传返回全部")] = None,
    offset: Annotated[int, Query(ge=0, description="分页偏移")] = 0,
) -> list[TaskRecord]:
    try:
        return list_tasks(
            matter_id=matter_id,
            status=status,
            priority=priority,
            limit=limit,
            offset=offset,
        )
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=500,
            detail={"code": "database_error", "message": f"读取任务列表失败：{error}"},
        ) from error


@router.get("/tasks/{task_id}", response_model=TaskRecord, summary="查询任务详情")
def query_task(task_id: int) -> TaskRecord:
    if task_id <= 0:
        raise _task_not_found(task_id)
    try:
        task = get_task(task_id)
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=500,
            detail={"code": "database_error", "message": f"读取任务失败：{error}"},
        ) from error
    if task is None:
        raise _task_not_found(task_id)
    return task


@router.patch("/tasks/{task_id}", response_model=TaskRecord, summary="修改任务")
def modify_task(task_id: int, payload: TaskUpdate) -> TaskRecord:
    if task_id <= 0:
        raise _task_not_found(task_id)
    try:
        task = update_task(task_id, payload)
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=500,
            detail={"code": "database_error", "message": f"更新任务失败：{error}"},
        ) from error
    if task is None:
        raise _task_not_found(task_id)
    return task


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除任务",
)
def remove_task(task_id: int) -> Response:
    if task_id <= 0:
        raise _task_not_found(task_id)
    try:
        deleted = delete_task(task_id)
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=500,
            detail={"code": "database_error", "message": f"删除任务失败：{error}"},
        ) from error
    if not deleted:
        raise _task_not_found(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
