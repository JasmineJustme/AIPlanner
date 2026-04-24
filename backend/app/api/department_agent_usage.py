from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import Agent, OrgUnit, Orchestration, ScheduleTask, User

router = APIRouter(prefix="/department-agent-usage", tags=["department-agent-usage"])


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d")


async def _get_department_and_users(db: AsyncSession, current_user: User) -> tuple[OrgUnit, list[User]]:
    if not current_user.org_unit_id:
        raise HTTPException(status_code=403, detail="仅 department 账户可访问")

    dept_result = await db.execute(
        select(OrgUnit).where(
            OrgUnit.id == current_user.org_unit_id,
            OrgUnit.unit_type == "department",
            OrgUnit.is_active.is_(True),
        )
    )
    department = dept_result.scalar_one_or_none()
    if not department:
        raise HTTPException(status_code=403, detail="仅 department 账户可访问")

    users_result = await db.execute(
        select(User)
        .where(User.is_active.is_(True))
        .where(
            (User.org_unit_id == department.id)
            | (User.org_unit_id.in_(select(OrgUnit.id).where(OrgUnit.parent_id == department.id)))
        )
    )
    return department, users_result.scalars().all()


@router.get("")
async def get_department_agent_usage(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    top_n: int = Query(10, ge=3, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    department, users = await _get_department_and_users(db, current_user)
    user_map = {user.id: user for user in users}
    user_ids = list(user_map.keys())

    start_dt = _parse_date(start_date)
    end_dt = _parse_date(end_date)
    if end_dt is not None:
        end_dt = end_dt + timedelta(days=1)

    if not user_ids:
        return {
            "code": 200,
            "message": "success",
            "data": {
                "department": {"id": department.id, "name": department.name},
                "summary": {"total_usage_count": 0, "employee_count": 0, "agent_count": 0, "avg_usage_per_employee": 0},
                "employees": [],
                "agents": [],
                "matrix": {"employees": [], "agents": [], "rows": []},
                "links": [],
            },
        }

    task_filters = [ScheduleTask.status == "completed", ScheduleTask.agent_id.is_not(None)]
    if start_dt is not None:
        task_filters.append(ScheduleTask.completed_at >= start_dt)
    if end_dt is not None:
        task_filters.append(ScheduleTask.completed_at < end_dt)

    tasks_result = await db.execute(
        select(
            ScheduleTask.agent_id,
            ScheduleTask.orchestration_id,
            ScheduleTask.completed_at,
            Agent.name.label("agent_name"),
            Agent.dify_api_key.label("agent_api_key"),
            Orchestration.user_id.label("employee_id"),
        )
        .join(Agent, Agent.id == ScheduleTask.agent_id, isouter=True)
        .join(Orchestration, Orchestration.id == ScheduleTask.orchestration_id, isouter=True)
        .where(*task_filters)
        .where(Orchestration.user_id.in_(user_ids))
    )

    rows = tasks_result.all()

    employee_agent_counts: dict[tuple[str, str], int] = defaultdict(int)
    employee_map: dict[str, dict] = {}
    agent_map: dict[str, dict] = {}
    matrix_map: dict[tuple[str, str], int] = defaultdict(int)
    agent_users: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        employee_id = row.employee_id
        agent_api_key = row.agent_api_key or "unknown"
        if not employee_id or employee_id not in user_map:
            continue

        usage_count = 1
        user = user_map[employee_id]
        employee_agent_counts[(employee_id, agent_api_key)] += usage_count
        matrix_map[(employee_id, agent_api_key)] += usage_count
        agent_users[agent_api_key].add(employee_id)

        employee = employee_map.setdefault(
            employee_id,
            {
                "employee_id": employee_id,
                "employee_name": user.full_name or user.username,
                "section_name": user.org_unit.name if getattr(user, "org_unit", None) else "未知部门",
                "usage_count": 0,
                "agent_count": 0,
                "top_agents": [],
                "last_used_at": None,
            },
        )
        employee["usage_count"] += usage_count
        if row.completed_at and (employee["last_used_at"] is None or row.completed_at > employee["last_used_at"]):
            employee["last_used_at"] = row.completed_at

        agent = agent_map.setdefault(
            agent_api_key,
            {
                "agent_api_key": agent_api_key,
                "agent_name": row.agent_name or "未知 Agent",
                "usage_count": 0,
                "employee_count": 0,
            },
        )
        agent["usage_count"] += usage_count

    for (employee_id, agent_api_key), count in employee_agent_counts.items():
        employee = employee_map.get(employee_id)
        if not employee:
            continue
        employee.setdefault("agent_usage", []).append(
            {
                "agent_api_key": agent_api_key,
                "agent_name": agent_map.get(agent_api_key, {}).get("agent_name", "未知 Agent"),
                "usage_count": count,
            }
        )

    for employee in employee_map.values():
        agent_usage = sorted(employee.get("agent_usage", []), key=lambda x: x["usage_count"], reverse=True)
        employee["top_agents"] = agent_usage[:3]
        employee["agent_count"] = len(agent_usage)
        employee.pop("agent_usage", None)

    for agent_api_key, users_set in agent_users.items():
        if agent_api_key in agent_map:
            agent_map[agent_api_key]["employee_count"] = len(users_set)

    employees = sorted(employee_map.values(), key=lambda x: x["usage_count"], reverse=True)
    agents = sorted(agent_map.values(), key=lambda x: x["usage_count"], reverse=True)
    employee_top = employees[:top_n]
    agent_top = agents[:top_n]
    employee_ids_order = [item["employee_id"] for item in employee_top]
    agent_keys_order = [item["agent_api_key"] for item in agent_top]

    matrix_rows = []
    links = []
    for employee_id in employee_ids_order:
        row_values = []
        employee_name = next((x["employee_name"] for x in employee_top if x["employee_id"] == employee_id), employee_id)
        for agent_api_key in agent_keys_order:
            value = matrix_map.get((employee_id, agent_api_key), 0)
            row_values.append(value)
            if value:
                links.append({"employee_id": employee_id, "agent_api_key": agent_api_key, "value": value})
        matrix_rows.append({"employee_id": employee_id, "employee_name": employee_name, "values": row_values})

    return {
        "code": 200,
        "message": "success",
        "data": {
            "department": {"id": department.id, "name": department.name},
            "summary": {
                "total_usage_count": sum(1 for _ in rows),
                "employee_count": len(employees),
                "agent_count": len(agents),
                "avg_usage_per_employee": round(len(rows) / len(employees), 2) if employees else 0,
            },
            "employees": employees,
            "agents": agents,
            "matrix": {"employees": employee_top, "agents": agent_top, "rows": matrix_rows},
            "links": links,
        },
    }
