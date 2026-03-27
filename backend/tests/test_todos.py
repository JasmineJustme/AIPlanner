import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.orchestration as orchestration_api
from app.api.orchestration import SubmitPayload, submit_orchestration
from app.api.todos import (
    cancel_user_todo,
    complete_todo,
    confirm_user_todo,
    create_todo,
    delete_todo,
    list_todos,
    rerun_todo,
    smart_discover_todos,
    update_todo,
)
from app.models.base import Base
from app.models.orchestration import Orchestration
from app.models.todo import Todo
from app.schemas.todo import TodoCreate, TodoUpdate
from app.services.llm_client import LLMServiceError


@pytest.mark.asyncio
async def test_list_todos_can_filter_by_execution_mode():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Todo.__table__])

    try:
        async with session_factory() as db:
            await create_todo(
                TodoCreate(title="用户执行任务", source="manual", execution_mode="user"),
                db,
            )
            await create_todo(
                TodoCreate(title="系统执行任务", source="manual", execution_mode="system"),
                db,
            )
            await db.commit()

            result = await list_todos(
                page=1,
                size=20,
                status=None,
                priority=None,
                source=None,
                execution_mode="user",
                db=db,
            )

        items = result["data"]["items"]
        assert len(items) == 1
        assert items[0].title == "用户执行任务"
        assert items[0].execution_mode == "user"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_update_todo_switch_to_user_execution_resets_system_state():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Todo.__table__])

    try:
        async with session_factory() as db:
            todo = Todo(
                id="todo-switch-user",
                title="切换执行方式",
                source="manual",
                execution_mode="system",
                status="scheduling",
                orchestration_id="orch-switch-user",
            )
            db.add(todo)
            await db.commit()

            await update_todo(todo.id, TodoUpdate(execution_mode="user"), db)
            await db.commit()

            reloaded = await db.get(Todo, todo.id)

        assert reloaded is not None
        assert reloaded.execution_mode == "user"
        assert reloaded.status == "pending"
        assert reloaded.orchestration_id is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_complete_todo_marks_user_execution_task_completed():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Todo.__table__])

    try:
        async with session_factory() as db:
            todo = Todo(
                id="todo-user-complete",
                title="手动完成任务",
                source="manual",
                execution_mode="user",
                status="pending",
            )
            db.add(todo)
            await db.commit()

            await complete_todo(todo.id, db)
            await db.commit()

            reloaded = await db.get(Todo, todo.id)

        assert reloaded is not None
        assert reloaded.status == "completed"
        assert reloaded.completed_at is not None
        assert reloaded.orchestration_id is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_user_todo_moves_pending_confirm_to_pending():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Todo.__table__])

    try:
        async with session_factory() as db:
            todo = Todo(
                id="todo-user-confirm",
                title="用户确认任务",
                source="manual",
                execution_mode="user",
                status="pending_confirm",
            )
            db.add(todo)
            await db.commit()

            await confirm_user_todo(todo.id, db)
            await db.commit()

            reloaded = await db.get(Todo, todo.id)

        assert reloaded is not None
        assert reloaded.status == "pending"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cancel_user_todo_moves_pending_to_pending_confirm():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Todo.__table__])

    try:
        async with session_factory() as db:
            todo = Todo(
                id="todo-user-cancel",
                title="用户取消任务",
                source="manual",
                execution_mode="user",
                status="pending",
            )
            db.add(todo)
            await db.commit()

            await cancel_user_todo(todo.id, db)
            await db.commit()

            reloaded = await db.get(Todo, todo.id)

        assert reloaded is not None
        assert reloaded.status == "pending_confirm"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_user_todo_rejects_invalid_status():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Todo.__table__])

    try:
        async with session_factory() as db:
            todo = Todo(
                id="todo-user-confirm-invalid",
                title="状态不允许确认",
                source="manual",
                execution_mode="user",
                status="pending",
            )
            db.add(todo)
            await db.commit()

            with pytest.raises(HTTPException) as exc_info:
                await confirm_user_todo(todo.id, db)

        assert exc_info.value.status_code == 400
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_generated_relation_todo_keeps_related_originals():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Todo.__table__])

    try:
        async with session_factory() as db:
            db.add_all(
                [
                    Todo(
                        id="todo-origin-a",
                        title="原任务A",
                        source="manual",
                        execution_mode="user",
                        status="pending_confirm",
                    ),
                    Todo(
                        id="todo-origin-b",
                        title="原任务B",
                        source="system",
                        execution_mode="system",
                        status="pending_confirm",
                    ),
                    Todo(
                        id="todo-generated",
                        title="生成任务",
                        source="system",
                        execution_mode="user",
                        status="pending_confirm",
                        duplicate_of="todo-origin-a",
                    ),
                ]
            )
            await db.commit()

            await confirm_user_todo("todo-generated", db)
            await db.commit()

            origin_a = await db.get(Todo, "todo-origin-a")
            origin_b = await db.get(Todo, "todo-origin-b")
            generated = await db.get(Todo, "todo-generated")

        assert origin_a is not None
        assert origin_b is not None
        assert generated is not None
        assert generated.status == "pending"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_original_relation_todo_keeps_generated_todo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Todo.__table__])

    try:
        async with session_factory() as db:
            db.add_all(
                [
                    Todo(
                        id="todo-origin-c",
                        title="原任务C",
                        source="manual",
                        execution_mode="user",
                        status="pending_confirm",
                    ),
                    Todo(
                        id="todo-generated-c",
                        title="生成任务C",
                        source="system",
                        execution_mode="system",
                        status="pending_confirm",
                        duplicate_of="todo-origin-c",
                    ),
                ]
            )
            await db.commit()

            await confirm_user_todo("todo-origin-c", db)
            await db.commit()

            origin = await db.get(Todo, "todo-origin-c")
            generated = await db.get(Todo, "todo-generated-c")

        assert origin is not None
        assert origin.status == "pending"
        assert generated is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_delete_todo_only_removes_target_todo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Todo.__table__])

    try:
        async with session_factory() as db:
            db.add_all(
                [
                    Todo(
                        id="todo-same-a",
                        title="重复任务A",
                        source="manual",
                        execution_mode="user",
                        status="pending_confirm",
                    ),
                    Todo(
                        id="todo-same-b",
                        title="重复任务B",
                        source="manual",
                        execution_mode="user",
                        status="pending_confirm",
                        duplicate_of="todo-same-a",
                    ),
                    Todo(
                        id="todo-same-c",
                        title="重复任务C",
                        source="manual",
                        execution_mode="user",
                        status="pending_confirm",
                        duplicate_of="todo-same-a",
                    ),
                ]
            )
            await db.commit()

            await delete_todo("todo-same-a", db)
            await db.commit()

            todo_a = await db.get(Todo, "todo-same-a")
            todo_b = await db.get(Todo, "todo-same-b")
            todo_c = await db.get(Todo, "todo-same-c")

        assert todo_a is None
        assert todo_b is not None
        assert todo_c is not None
        assert todo_b.duplicate_of == "todo-same-a"
        assert todo_c.duplicate_of == "todo-same-a"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_complete_todo_rejects_system_execution_task():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Todo.__table__])

    try:
        async with session_factory() as db:
            todo = Todo(
                id="todo-system-complete",
                title="系统任务不能手动完成",
                source="manual",
                execution_mode="system",
                status="pending",
            )
            db.add(todo)
            await db.commit()

            with pytest.raises(HTTPException) as exc_info:
                await complete_todo(todo.id, db)

        assert exc_info.value.status_code == 400
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_submit_orchestration_rejects_user_execution_task():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Todo.__table__])

    try:
        async with session_factory() as db:
            todo = Todo(
                id="todo-user-orchestration",
                title="用户执行任务不能走编排",
                source="manual",
                execution_mode="user",
                status="pending",
            )
            db.add(todo)
            await db.commit()

            with pytest.raises(HTTPException) as exc_info:
                await submit_orchestration(SubmitPayload(todo_ids=[todo.id]), db)

        assert exc_info.value.status_code == 400
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rerun_todo_clones_completed_task_with_pending_confirm_status():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Todo.__table__])

    try:
        async with session_factory() as db:
            todo = Todo(
                id="todo-rerun-source",
                title="已完成任务",
                description="原任务描述",
                source="manual",
                execution_mode="system",
                status="completed",
                priority="high",
                source_ref="email-001",
                tags=["审计", "复核"],
                responsibility_ids=["resp-1", "resp-2"],
                responsibility_titles=["凭证审计", "风险复核"],
                project="年度审计",
            )
            db.add(todo)
            await db.commit()

            result = await rerun_todo(todo.id, db)
            await db.commit()

            created = result["data"]
            original = await db.get(Todo, todo.id)
            all_todos = (await db.execute(__import__("sqlalchemy").select(Todo).order_by(Todo.created_at.asc()))).scalars().all()

        assert original is not None
        assert created.id != todo.id
        assert created.title == todo.title
        assert created.description == todo.description
        assert created.priority == todo.priority
        assert created.source == todo.source
        assert created.execution_mode == todo.execution_mode
        assert created.source_ref == todo.source_ref
        assert created.tags == todo.tags
        assert created.responsibility_ids == todo.responsibility_ids
        assert created.responsibility_titles == todo.responsibility_titles
        assert created.project == todo.project
        assert created.status == "pending_confirm"
        assert len(all_todos) == 2
        assert all_todos[0].id == todo.id
        assert all_todos[1].status == "pending_confirm"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rerun_todo_rejects_non_completed_task():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Todo.__table__])

    try:
        async with session_factory() as db:
            todo = Todo(
                id="todo-rerun-pending",
                title="未完成任务",
                source="manual",
                execution_mode="user",
                status="pending_confirm",
            )
            db.add(todo)
            await db.commit()

            with pytest.raises(HTTPException) as exc_info:
                await rerun_todo(todo.id, db)

        assert exc_info.value.status_code == 400
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_submit_orchestration_rejects_completed_system_task():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Todo.__table__])

    try:
        async with session_factory() as db:
            todo = Todo(
                id="todo-completed-system-orchestration",
                title="已完成系统任务",
                source="manual",
                execution_mode="system",
                status="completed",
            )
            db.add(todo)
            await db.commit()

            with pytest.raises(HTTPException) as exc_info:
                await submit_orchestration(SubmitPayload(todo_ids=[todo.id]), db)

        assert exc_info.value.status_code == 400
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_submit_orchestration_marks_system_todo_orchestrating(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Todo.__table__, Orchestration.__table__],
        )

    async def fake_orchestrate(db, todo_ids):
        return {
            "status": "pending_confirm",
            "plan": {
                "plan_type": "agent",
                "recommended_id": "agent-1",
                "recommended_name": "测试Agent",
                "reason": "测试提交后立即进入编排",
                "input_params": {},
                "priority": "medium",
                "estimated_duration_minutes": 30,
                "start_time": None,
                "deadline": None,
                "steps": [],
            },
            "llm_reason": "测试提交后立即进入编排",
        }

    monkeypatch.setattr(orchestration_api.orchestrator, "orchestrate", fake_orchestrate)
    monkeypatch.setattr(orchestration_api, "_launch_analysis", lambda *a: None)

    try:
        async with session_factory() as db:
            todo = Todo(
                id="todo-system-submit",
                title="待提交系统任务",
                source="manual",
                execution_mode="system",
                status="pending_confirm",
            )
            db.add(todo)
            await db.commit()

            result = await submit_orchestration(SubmitPayload(todo_ids=[todo.id]), db)

            orch_id = result["data"]["orch_id"]
            assert result["data"]["status"] == "analyzing"

            event_status, _ = await orchestration_api._process_analysis(
                db, orch_id, [todo.id], {}
            )
            await db.flush()

            reloaded = await db.get(Todo, todo.id)
            orch = await db.get(Orchestration, orch_id)

        assert orch.status == "pending_confirm"
        assert event_status == "pending_confirm"
        assert reloaded is not None
        assert reloaded.status == "orchestrating"
        assert reloaded.orchestration_id == orch_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_submit_orchestration_error_keeps_analyzing_status_and_broadcasts_failed(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Todo.__table__, Orchestration.__table__],
        )

    async def fake_orchestrate(_db, _todo_ids):
        return {"error": "mock llm failure"}

    monkeypatch.setattr(orchestration_api.orchestrator, "orchestrate", fake_orchestrate)
    monkeypatch.setattr(orchestration_api, "_launch_analysis", lambda *a: None)

    try:
        async with session_factory() as db:
            todo = Todo(
                id="todo-system-submit-failed",
                title="失败后仍分析中",
                source="manual",
                execution_mode="system",
                status="pending_confirm",
            )
            db.add(todo)
            await db.commit()

            result = await submit_orchestration(SubmitPayload(todo_ids=[todo.id]), db)

            orch_id = result["data"]["orch_id"]
            assert result["data"]["status"] == "analyzing"

            event_status, error_msg = await orchestration_api._process_analysis(
                db, orch_id, [todo.id], {}
            )
            await db.flush()

            reloaded = await db.get(Todo, todo.id)
            orch = await db.get(Orchestration, orch_id)

        assert event_status == "pending_confirm"
        assert error_msg == "mock llm failure"
        assert orch.status == "pending_confirm"
        assert orch.error == "mock llm failure"
        assert reloaded is not None
        assert reloaded.status == "orchestrating"
        assert reloaded.orchestration_id == orch_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_smart_discover_todos_delegates_to_engine(monkeypatch):
    async def fake_smart_discover(_db):
        return {
            "synced_datasource_count": 2,
            "created_count": 3,
            "dedup_count": 1,
            "created_todo_ids": ["a", "b", "c"],
            "duplicates": [{"source_id": "a", "target_id": "b"}],
        }

    monkeypatch.setattr("app.api.todos.todo_discovery_engine.smart_discover", fake_smart_discover)

    result = await smart_discover_todos(db=None)

    assert result["code"] == 200
    assert result["data"]["created_count"] == 3
    assert result["data"]["dedup_count"] == 1


@pytest.mark.asyncio
async def test_smart_discover_todos_maps_llm_service_error_to_gateway_error(monkeypatch):
    async def fake_smart_discover(_db):
        raise LLMServiceError("LLM call failed (openai/glm-4-flash): Server disconnected")

    monkeypatch.setattr("app.api.todos.todo_discovery_engine.smart_discover", fake_smart_discover)

    with pytest.raises(HTTPException) as exc_info:
        await smart_discover_todos(db=None)

    assert exc_info.value.status_code == 502
    assert "LLM call failed" in str(exc_info.value.detail)
