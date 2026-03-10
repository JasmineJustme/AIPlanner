import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, WAgent
from app.models.execution import ExecutionHistory
from app.models.schedule import ScheduleTask
from app.models.wagent import WAgentVersion
from app.services.dify_client import dify_client
from loguru import logger


def _now_local_naive() -> datetime:
    return datetime.now().replace(microsecond=0)


class Executor:
    def _build_execution_log(self, *, task: ScheduleTask, target_type: str, target_name: str | None, status: str, payload=None, error: str | None = None) -> str:
        content = {
            "task_id": task.id,
            "target_type": target_type,
            "target_name": target_name,
            "status": status,
            "input_params": task.input_params or {},
            "output_result": payload,
            "error_message": error,
            "logged_at": _now_local_naive().isoformat(),
        }
        return json.dumps(content, ensure_ascii=False, default=str)

    async def execute_agent(self, db: AsyncSession, task: ScheduleTask) -> ExecutionHistory:
        """Execute a single Agent task"""
        agent = await db.get(Agent, task.agent_id)
        if not agent:
            return await self._record_failure(db, task, "Agent not found")

        started_at = _now_local_naive()
        try:
            result = await dify_client.call_agent(
                agent.dify_endpoint, agent.dify_api_key,
                task.input_params or {}, agent.timeout_seconds
            )
            completed_at = _now_local_naive()
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            execution_log = self._build_execution_log(
                task=task,
                target_type="agent",
                target_name=agent.name,
                status="completed",
                payload=result,
            )

            task.status = "completed"
            task.output_result = result
            task.completed_at = completed_at
            task.execution_log = execution_log

            logger.info("Agent execution completed for task_id={} agent='{}': {}", task.id, agent.name, execution_log)

            agent.call_count += 1
            agent.success_count += 1

            history = ExecutionHistory(
                task_id=task.id, agent_id=agent.id, agent_name=agent.name,
                status="completed", input_params=task.input_params,
                output_result=result, execution_log=execution_log, duration_ms=duration_ms,
                started_at=started_at, completed_at=completed_at,
            )
            db.add(history)
            await db.flush()
            return history
        except Exception as e:
            return await self._record_failure(db, task, str(e), started_at, agent=agent)

    async def execute_wagent(self, db: AsyncSession, task: ScheduleTask) -> ExecutionHistory:
        """Execute a W-Agent task (sequential workflow steps)"""
        wagent = await db.get(WAgent, task.wagent_id)
        if not wagent:
            return await self._record_failure(db, task, "W-Agent not found", wagent=None)

        # Get version steps
        version_q = select(WAgentVersion).where(
            WAgentVersion.wagent_id == wagent.id,
            WAgentVersion.version == (task.wagent_version or wagent.current_version)
        )
        version = (await db.execute(version_q)).scalar_one_or_none()
        if not version or not version.steps:
            return await self._record_failure(db, task, "W-Agent version or steps not found", wagent=wagent)

        started_at = _now_local_naive()
        step_outputs = {}
        try:
            from app.models.workflow import Workflow
            for step in sorted(version.steps, key=lambda s: s.get("order", 0)):
                wf = await db.get(Workflow, step.get("workflow_id"))
                if not wf:
                    raise Exception(f"Workflow {step.get('workflow_id')} not found")

                # Build input params from mapping
                inputs = self._resolve_params(step.get("param_mapping", {}), task.input_params or {}, step_outputs)

                result = await dify_client.call_workflow(
                    wf.dify_endpoint, wf.dify_api_key, inputs, wf.timeout_seconds
                )
                step_outputs[step.get("order", 0)] = result

            completed_at = _now_local_naive()
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            execution_log = self._build_execution_log(
                task=task,
                target_type="wagent",
                target_name=wagent.name,
                status="completed",
                payload=step_outputs,
            )

            task.status = "completed"
            task.output_result = step_outputs
            task.completed_at = completed_at
            task.execution_log = execution_log

            logger.info("W-Agent execution completed for task_id={} wagent='{}': {}", task.id, wagent.name, execution_log)

            wagent.call_count += 1
            wagent.success_count += 1

            history = ExecutionHistory(
                task_id=task.id, wagent_id=wagent.id, agent_name=wagent.name,
                status="completed", input_params=task.input_params,
                output_result=step_outputs, execution_log=execution_log, duration_ms=duration_ms,
                started_at=started_at, completed_at=completed_at,
            )
            db.add(history)
            await db.flush()
            return history
        except Exception as e:
            return await self._record_failure(db, task, str(e), started_at, wagent=wagent)

    def _resolve_params(self, mapping: dict, wagent_input: dict, step_outputs: dict) -> dict:
        """Resolve param mapping for a workflow step"""
        resolved = {}
        for param_name, config in mapping.items():
            source = config.get("source", "fixed_value") if isinstance(config, dict) else "fixed_value"
            if source == "wagent_input":
                upstream_param = config.get("upstream_param", param_name)
                resolved[param_name] = wagent_input.get(upstream_param, "")
            elif source == "upstream_output":
                step_idx = config.get("upstream_step", 0)
                upstream_param = config.get("upstream_param", "")
                step_data = step_outputs.get(step_idx, {})
                resolved[param_name] = step_data.get(upstream_param, "") if isinstance(step_data, dict) else ""
            else:
                resolved[param_name] = config.get("fixed_value", "") if isinstance(config, dict) else str(config)
        return resolved

    async def _record_failure(
        self,
        db: AsyncSession,
        task: ScheduleTask,
        error: str,
        started_at: datetime | None = None,
        agent=None,
        wagent=None,
    ) -> ExecutionHistory:
        if not started_at:
            started_at = _now_local_naive()
        completed_at = _now_local_naive()
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        task.status = "failed"
        task.error_message = error
        task.completed_at = completed_at
        task.execution_log = self._build_execution_log(
            task=task,
            target_type="agent" if task.agent_id else "wagent" if task.wagent_id else "unknown",
            target_name=getattr(agent or wagent, "name", None),
            status="failed",
            error=error,
        )

        logger.error("Execution failed for task_id={}: {}", task.id, task.execution_log)

        entity = agent or wagent
        if entity:
            entity.call_count += 1

        agent_name = None
        if agent:
            agent_name = agent.name
        elif wagent:
            agent_name = wagent.name

        history = ExecutionHistory(
            task_id=task.id,
            agent_id=task.agent_id,
            wagent_id=task.wagent_id,
            agent_name=agent_name,
            status="failed",
            input_params=task.input_params,
            error_message=error,
            execution_log=task.execution_log,
            duration_ms=duration_ms,
            started_at=started_at,
            completed_at=completed_at,
        )
        db.add(history)
        await db.flush()
        return history


executor = Executor()
