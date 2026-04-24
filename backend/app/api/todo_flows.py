from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import Message, OrgUnit, Todo, TodoCollaborationRequest, TodoFlowLog, User
from app.schemas.message import MessageResponse
from app.schemas.todo import TodoResponse
from app.utils.timezone import utc_now_naive

router = APIRouter(prefix="/todo-flows", tags=["todo-flows"])


class BatchTodoFlowBody(BaseModel):
    todo_ids: list[str] = []
    target_user_id: str
    action: str
    request_message: str | None = None


class RejectBody(BaseModel):
    reason: str | None = None


DISPATCH_MESSAGE_TYPES = {"dispatch_success", "dispatch_received"}
COLLAB_MESSAGE_TYPES = {
    "collaboration_request",
    "collaboration_accepted",
    "collaboration_rejected",
}


def _is_department_user(user: User) -> bool:
    return bool(user.org_unit and user.org_unit.unit_type == "department")


def _is_section_user(user: User) -> bool:
    return bool(user.org_unit and user.org_unit.unit_type == "section")


def _is_target_in_department_scope(current_user: User, target: User) -> bool:
    if not current_user.org_unit_id or not target.org_unit_id:
        return False
    if target.org_unit_id == current_user.org_unit_id:
        return True
    if target.org_unit and target.org_unit.unit_type == "section" and target.org_unit.parent_id == current_user.org_unit_id:
        return True
    cur = target
    seen: set[str] = set()
    while cur and cur.id not in seen:
        seen.add(cur.id)
        if cur.manager_id == current_user.id:
            return True
        if not cur.manager_id:
            break
        cur = None
    return False


def _can_collaborate_with(current_user: User, target: User) -> bool:
    if current_user.id == target.id:
        return False
    if not current_user.org_unit_id or not target.org_unit_id:
        return False
    if _is_department_user(current_user):
        return _is_target_in_department_scope(current_user, target)
    if _is_section_user(current_user):
        if current_user.org_unit is None:
            return False
        if target.org_unit_id == current_user.org_unit.parent_id:
            return True
        return target.org_unit_id == current_user.org_unit_id
    return False


def _resolve_target_execution_mode(todo: Todo) -> str:
    return "system_execution" if todo.execution_mode == "system" else "user_execution"


async def _append_flow_log(
    db: AsyncSession,
    *,
    todo: Todo,
    action_type: str,
    from_user_id: str | None,
    to_user_id: str | None,
    status_before: str | None,
    status_after: str | None,
    flow_state_before: str | None,
    flow_state_after: str | None,
    remark: str | None = None,
) -> None:
    db.add(
        TodoFlowLog(
            todo_id=todo.id,
            action_type=action_type,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            status_before=status_before,
            status_after=status_after,
            flow_state_before=flow_state_before,
            flow_state_after=flow_state_after,
            remark=remark,
        )
    )


async def _create_message(
    db: AsyncSession,
    *,
    type_: str,
    title: str,
    content: str,
    related_id: str | None,
    related_request_id: str | None,
    recipient_user_id: str | None,
    sender_user_id: str | None,
) -> None:
    db.add(
        Message(
            type=type_,
            title=title,
            content=content,
            status="unread",
            related_type="todo",
            related_id=related_id,
            related_request_id=related_request_id,
            recipient_user_id=recipient_user_id,
            sender_user_id=sender_user_id,
            action_url=None,
        )
    )


@router.get("/eligible-target-users")
async def eligible_target_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    action: str = Query("collaboration"),
):
    if action not in {"dispatch", "collaboration"}:
        raise HTTPException(status_code=400, detail="无效操作类型")
    if action == "dispatch" and not _is_department_user(current_user):
        return {"code": 200, "message": "success", "data": []}
    if not current_user.org_unit_id:
        return {"code": 200, "message": "success", "data": []}

    candidates = (
        await db.execute(
            select(User)
            .options(selectinload(User.org_unit))
            .join(OrgUnit, OrgUnit.id == User.org_unit_id)
            .where(User.is_active.is_(True))
            .order_by(User.created_at.desc())
        )
    ).scalars().all()
    if action == "dispatch":
        users = [u for u in candidates if _is_target_in_department_scope(current_user, u)]
    else:
        users = [u for u in candidates if _can_collaborate_with(current_user, u)]
    return {
        "code": 200,
        "message": "success",
        "data": [
            {
                "id": u.id,
                "label": u.full_name or u.username,
                "org_unit_id": u.org_unit_id,
                "manager_id": u.manager_id,
            }
            for u in users
        ],
    }


@router.get("/dispatchable")
async def dispatchable_todos(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    offset = (page - 1) * size
    q = (
        select(Todo)
        .where(Todo.status == "pending_confirm", Todo.creator_id == current_user.id)
        .order_by(Todo.created_at.desc())
    )
    count_q = select(func.count()).select_from(Todo).where(Todo.status == "pending_confirm", Todo.creator_id == current_user.id)
    total = (await db.execute(count_q)).scalar() or 0
    items = (await db.execute(q.offset(offset).limit(size))).scalars().all()
    return {
        "code": 200,
        "message": "success",
        "data": {"items": [TodoResponse.model_validate(i) for i in items], "total": total, "page": page, "size": size},
    }


@router.get("/managed")
async def managed_flow_todos(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    offset = (page - 1) * size
    q = (
        select(Todo)
        .where(
            Todo.original_owner_id == current_user.id,
            Todo.owner_id != current_user.id,
            Todo.last_flow_state.is_not(None),
        )
        .order_by(Todo.updated_at.desc())
    )
    count_q = select(func.count()).select_from(Todo).where(
        Todo.original_owner_id == current_user.id,
        Todo.owner_id != current_user.id,
        Todo.last_flow_state.is_not(None),
    )
    total = (await db.execute(count_q)).scalar() or 0
    items = (await db.execute(q.offset(offset).limit(size))).scalars().all()
    return {
        "code": 200,
        "message": "success",
        "data": {"items": [TodoResponse.model_validate(i) for i in items], "total": total, "page": page, "size": size},
    }


@router.post("/batch-action")
async def batch_action(body: BatchTodoFlowBody, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if body.action not in {"dispatch", "collaboration"}:
        raise HTTPException(status_code=400, detail="无效操作类型")
    if body.action == "dispatch" and not _is_department_user(current_user):
        raise HTTPException(status_code=403, detail="仅 department 用户可派发")
    if body.action == "collaboration" and not (_is_department_user(current_user) or _is_section_user(current_user)):
        raise HTTPException(status_code=403, detail="当前账户不支持协作")
    if not body.todo_ids:
        raise HTTPException(status_code=400, detail="请选择任务")
    if not body.target_user_id:
        raise HTTPException(status_code=400, detail="请选择目标成员")

    todos = (await db.execute(select(Todo).where(Todo.id.in_(body.todo_ids)))).scalars().all()
    if len(todos) != len(body.todo_ids):
        raise HTTPException(status_code=400, detail="存在无效任务")
    if any(t.status != "pending_confirm" for t in todos):
        raise HTTPException(status_code=400, detail="仅待确认任务支持操作")
    if any((t.creator_id or t.owner_id) != current_user.id for t in todos):
        raise HTTPException(status_code=403, detail="仅支持操作当前账户名下任务")

    target = (await db.execute(select(User).where(User.id == body.target_user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="目标成员不存在")
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="不允许选择自己")

    if body.action == "dispatch":
        if not _is_target_in_department_scope(current_user, target):
            raise HTTPException(status_code=400, detail="目标成员不在允许范围内")
    else:
        if not _can_collaborate_with(current_user, target):
            raise HTTPException(status_code=400, detail="目标成员不在允许范围内")

    for todo in todos:
        status_before = todo.status
        flow_before = todo.last_flow_state
        todo.original_owner_id = todo.original_owner_id or current_user.id
        todo.target_user_id = target.id
        todo.task_flow_type = "dispatch_collaboration"
        todo.last_flow_type = body.action
        todo.review_reason = None

        if body.action == "dispatch":
            todo.source = "dispatched"
            todo.owner_id = target.id
            todo.status = "pending_confirm"
            todo.execution_mode = todo.execution_mode
            todo.last_flow_state = "transferred"
            await _create_message(
                db,
                type_="dispatch_success",
                title=todo.title,
                content=f"任务已派发成功：{todo.title}",
                related_id=todo.id,
                related_request_id=None,
                recipient_user_id=current_user.id,
                sender_user_id=current_user.id,
            )
            await _create_message(
                db,
                type_="dispatch_received",
                title=todo.title,
                content=f"收到派发任务：{todo.title}",
                related_id=todo.id,
                related_request_id=None,
                recipient_user_id=target.id,
                sender_user_id=current_user.id,
            )
            await _append_flow_log(
                db,
                todo=todo,
                action_type="dispatch",
                from_user_id=current_user.id,
                to_user_id=target.id,
                status_before=status_before,
                status_after=todo.status,
                flow_state_before=flow_before,
                flow_state_after=todo.last_flow_state,
                remark="任务已派发至目标账户",
            )
        else:
            todo.source = "collaboration"
            todo.status = "pending_confirm"
            todo.last_flow_state = "requesting"
            request = TodoCollaborationRequest(
                todo_id=todo.id,
                source_user_id=current_user.id,
                target_user_id=target.id,
                request_status="pending",
                request_message=body.request_message,
            )
            db.add(request)
            await db.flush()
            await _create_message(
                db,
                type_="collaboration_request",
                title=todo.title,
                content=f"收到协作请求：{todo.title}",
                related_id=todo.id,
                related_request_id=request.id,
                recipient_user_id=target.id,
                sender_user_id=current_user.id,
            )
            await _append_flow_log(
                db,
                todo=todo,
                action_type="collaboration_request",
                from_user_id=current_user.id,
                to_user_id=target.id,
                status_before=status_before,
                status_after=todo.status,
                flow_state_before=flow_before,
                flow_state_after=todo.last_flow_state,
                remark=body.request_message or "发起协作请求",
            )

    await db.flush()
    return {"code": 200, "message": "success", "data": {"updated": len(todos)}}


@router.get("/dispatch-messages")
async def dispatch_messages(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    offset = (page - 1) * size
    q = (
        select(Message)
        .where(Message.type.in_(DISPATCH_MESSAGE_TYPES), Message.recipient_user_id == current_user.id)
        .order_by(Message.created_at.desc())
    )
    count_q = select(func.count()).select_from(Message).where(
        Message.type.in_(DISPATCH_MESSAGE_TYPES),
        Message.recipient_user_id == current_user.id,
    )
    total = (await db.execute(count_q)).scalar() or 0
    items = (await db.execute(q.offset(offset).limit(size))).scalars().all()
    return {
        "code": 200,
        "message": "success",
        "data": {"items": [MessageResponse.model_validate(m) for m in items], "total": total, "page": page, "size": size},
    }


@router.get("/collaboration-requests")
async def collaboration_requests(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    offset = (page - 1) * size
    q = (
        select(Message)
        .where(Message.type.in_(COLLAB_MESSAGE_TYPES), Message.recipient_user_id == current_user.id)
        .order_by(Message.created_at.desc())
    )
    count_q = select(func.count()).select_from(Message).where(
        Message.type.in_(COLLAB_MESSAGE_TYPES),
        Message.recipient_user_id == current_user.id,
    )
    total = (await db.execute(count_q)).scalar() or 0
    items = (await db.execute(q.offset(offset).limit(size))).scalars().all()
    return {
        "code": 200,
        "message": "success",
        "data": {"items": [MessageResponse.model_validate(m) for m in items], "total": total, "page": page, "size": size},
    }


@router.post("/collaboration-requests/{request_id}/accept")
async def accept_collaboration(request_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    request = (
        await db.execute(select(TodoCollaborationRequest).where(TodoCollaborationRequest.id == request_id))
    ).scalar_one_or_none()
    if not request:
        raise HTTPException(status_code=404, detail="协作请求不存在")
    if request.target_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权处理该协作请求")
    if request.request_status != "pending":
        raise HTTPException(status_code=400, detail="该协作请求已处理")

    todo = (await db.execute(select(Todo).where(Todo.id == request.todo_id))).scalar_one_or_none()
    if not todo:
        raise HTTPException(status_code=404, detail="关联任务不存在")

    request.request_status = "accepted"
    request.accepted_at = utc_now_naive()

    status_before = todo.status
    flow_before = todo.last_flow_state
    todo.owner_id = current_user.id
    todo.target_user_id = current_user.id
    todo.task_flow_type = _resolve_target_execution_mode(todo)
    todo.last_flow_state = "transferred"
    todo.last_flow_type = "collaboration_accept"
    todo.status = "pending_confirm"

    related_messages = (
        await db.execute(select(Message).where(Message.related_request_id == request.id))
    ).scalars().all()
    for msg in related_messages:
        if msg.recipient_user_id == current_user.id:
            msg.status = "processed"
            msg.type = "collaboration_accepted"
            msg.content = f"协作请求已接受：{todo.title}"

    await _create_message(
        db,
        type_="collaboration_accepted",
        title=todo.title,
        content=f"协作请求已接受：{todo.title}",
        related_id=todo.id,
        related_request_id=request.id,
        recipient_user_id=current_user.id,
        sender_user_id=request.source_user_id,
    )
    await _create_message(
        db,
        type_="collaboration_accepted",
        title=todo.title,
        content=f"对方已接受协作请求：{todo.title}",
        related_id=todo.id,
        related_request_id=request.id,
        recipient_user_id=request.source_user_id,
        sender_user_id=current_user.id,
    )
    await _append_flow_log(
        db,
        todo=todo,
        action_type="collaboration_accept",
        from_user_id=request.source_user_id,
        to_user_id=current_user.id,
        status_before=status_before,
        status_after=todo.status,
        flow_state_before=flow_before,
        flow_state_after=todo.last_flow_state,
        remark="协作请求已接受，任务已转入目标账户执行模块",
    )
    await db.flush()
    return {"code": 200, "message": "success", "data": None}


@router.post("/collaboration-requests/{request_id}/reject")
async def reject_collaboration(
    request_id: str,
    body: RejectBody | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = (
        await db.execute(select(TodoCollaborationRequest).where(TodoCollaborationRequest.id == request_id))
    ).scalar_one_or_none()
    if not request:
        raise HTTPException(status_code=404, detail="协作请求不存在")
    if request.target_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权处理该协作请求")
    if request.request_status != "pending":
        raise HTTPException(status_code=400, detail="该协作请求已处理")

    todo = (await db.execute(select(Todo).where(Todo.id == request.todo_id))).scalar_one_or_none()
    if not todo:
        raise HTTPException(status_code=404, detail="关联任务不存在")

    original_task_flow_type = todo.task_flow_type
    request.request_status = "rejected"
    request.rejected_at = utc_now_naive()
    request.rejected_reason = body.reason if body else None

    status_before = todo.status
    flow_before = todo.last_flow_state
    original_task_flow_type = "system_execution" if todo.execution_mode == "system" else "user_execution"
    todo.owner_id = todo.original_owner_id or request.source_user_id
    todo.target_user_id = None
    todo.task_flow_type = original_task_flow_type
    todo.last_flow_state = None
    todo.last_flow_type = "collaboration_reject"
    todo.review_status = "rejected"
    todo.review_reason = request.rejected_reason or "协作请求被拒绝"
    todo.status = "pending_confirm"

    related_messages = (
        await db.execute(select(Message).where(Message.related_request_id == request.id))
    ).scalars().all()
    for msg in related_messages:
        if msg.recipient_user_id == current_user.id:
            msg.status = "processed"
            msg.type = "collaboration_rejected"
            msg.content = f"协作请求已拒绝：{todo.title}"

    await _create_message(
        db,
        type_="collaboration_rejected",
        title=todo.title,
        content=f"协作请求已拒绝：{todo.title}",
        related_id=todo.id,
        related_request_id=request.id,
        recipient_user_id=current_user.id,
        sender_user_id=request.source_user_id,
    )
    await _create_message(
        db,
        type_="collaboration_rejected",
        title=todo.title,
        content=f"协作请求被拒绝：{todo.title}",
        related_id=todo.id,
        related_request_id=request.id,
        recipient_user_id=request.source_user_id,
        sender_user_id=current_user.id,
    )
    await _append_flow_log(
        db,
        todo=todo,
        action_type="collaboration_reject",
        from_user_id=request.source_user_id,
        to_user_id=current_user.id,
        status_before=status_before,
        status_after=todo.status,
        flow_state_before=flow_before,
        flow_state_after=todo.last_flow_state,
        remark=request.rejected_reason or "协作请求被拒绝，任务已回退原账户",
    )
    await db.flush()
    return {"code": 200, "message": "success", "data": None}
