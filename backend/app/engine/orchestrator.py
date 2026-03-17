from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Agent, WAgent, Workflow, Todo
from app.services.llm_client import llm_client
from loguru import logger
import json
import re


class Orchestrator:
    async def orchestrate(self, db: AsyncSession, todo_ids: list[str]) -> dict:
        """Analyze todos and create orchestration plan using LLM"""
        # 1. Get todos
        result = await db.execute(select(Todo).where(Todo.id.in_(todo_ids)))
        todos = result.scalars().all()
        if not todos:
            return {"error": "No todos found"}

        # 2. Get available agents and wagents
        agents_result = await db.execute(select(Agent).where(Agent.is_enabled == True))
        agents = agents_result.scalars().all()
        wagents_result = await db.execute(select(WAgent).where(WAgent.is_enabled == True))
        wagents = wagents_result.scalars().all()
        workflows_result = await db.execute(select(Workflow).where(Workflow.is_enabled == True))
        workflows = workflows_result.scalars().all()

        # 3. Get LLM config for orchestration
        from app.models.llm_config import LLMConfig
        llm_result = await db.execute(select(LLMConfig).where(LLMConfig.purpose == "orchestration"))
        llm_config = llm_result.scalar_one_or_none()

        if not llm_config:
            # Return a mock plan when no LLM configured
            return self._create_mock_plan(todos, agents, wagents, workflows)

        # 4. Build prompt
        current_time = datetime.now(UTC).replace(tzinfo=None, microsecond=0).isoformat()
        todo_desc = "\n".join([
            f"- ID={t.id}; 标题={t.title}; 描述={t.description or ''}; 优先级={t.priority or 'medium'}; 截止时间={t.due_date.isoformat() if t.due_date else '无'}; 标签={json.dumps(t.tags or [], ensure_ascii=False)}; 项目={t.project or '无'}"
            for t in todos
        ])
        agent_desc = "\n".join([
            f"- ID={a.id}; 名称={a.name}; tags={json.dumps(a.capability_tags or [], ensure_ascii=False)}; 描述={a.description or ''}; input_params={json.dumps(self._filter_prompt_input_params(getattr(a, 'input_params', {})), ensure_ascii=False)}; output_params={json.dumps(a.output_params or {}, ensure_ascii=False)}"
            for a in agents
        ]) or "- 无"
        wagent_desc = "\n".join([
            f"- ID={w.id}; 名称={w.name}; tags={json.dumps(w.capability_tags or [], ensure_ascii=False)}; 描述={w.description or ''}; input_params={json.dumps(self._filter_prompt_input_params(getattr(w, 'input_params', {})), ensure_ascii=False)}; output_params={json.dumps(w.output_params or {}, ensure_ascii=False)}"
            for w in wagents
        ]) or "- 无"
        workflow_desc = "\n".join([
            f"- ID={wf.id}; 名称={wf.name}; tags={json.dumps(wf.capability_tags or [], ensure_ascii=False)}; 描述={wf.description or ''}; input_params={json.dumps(self._filter_prompt_input_params(getattr(wf, 'input_params', {})), ensure_ascii=False)}; output_params={json.dumps(wf.output_params or {}, ensure_ascii=False)}"
            for wf in workflows
        ]) or "- 无"

        default_prompt = f"""
分析以下待办任务，从可用的Agent、W-Agent和Workflow中选择最佳方案来完成任务。

当前时间：
{current_time}

待办任务：
{todo_desc}

可用Agent：
{agent_desc}

可用W-Agent：
{wagent_desc}

可用Workflow：
{workflow_desc}

请严格返回 JSON 对象，不要输出 Markdown 代码块，不要输出 解释文本。
JSON 必须包含以下字段：
{{
  "plan_type": "agent | wagent | new_wagent",
  "recommended_id": "推荐的 agent/wagent id，没有可留空字符串",
  "recommended_name": "推荐名称",
  "reason": "推荐原因",
  "input_params": {{"参数名": "参数值"}},
  "priority": "high | medium | low",
  "estimated_duration_minutes": 30,
  "start_time": "ISO8601 时间，例如 2026-03-09T09:00:00，必须结合当前时间判断，无法判断可用 null",
  "deadline": "ISO8601 时间，例如 2026-03-09T18:00:00，需结合当前时间、预计时长和待办截止时间判断，无法判断可用 null",
  "steps": [{{"order": 1, "workflow_name": "步骤名"}}]
}}

要求：
1. 结合任务描述和候选 input_params 自动补全最合适的 input_params。
2. 必须结合上方“当前时间”为每个任务生成 start_time 与 deadline；若任务没有明确开始时间，start_time 应不早于当前时间。
3. deadline 不能晚于任务中最早的 due_date；如没有 due_date，请结合当前时间与 estimated_duration_minutes 给出合理 deadline。
4. 若选择 new_wagent，请给出 steps；否则 steps 可为空数组。
5. recommended_name 必须与 recommended_id 对应。
"""
        template = llm_config.prompt_template or ""
        required_placeholders = ["{current_time}", "{todo_desc}", "{agent_desc}", "{wagent_desc}", "{workflow_desc}"]
        prompt_context = {
            "current_time": current_time,
            "todo_desc": todo_desc,
            "agent_desc": agent_desc,
            "wagent_desc": wagent_desc,
            "workflow_desc": workflow_desc,
        }
        if all(token in template for token in required_placeholders):
            prompt = self._render_prompt_template(template, prompt_context)
        else:
            prompt = default_prompt

        # 5. Call LLM
        try:
            # logger.info("{}",llm_config.prompt_template)
            logger.info("Orchestration LLM prompt for todo_ids={}:\n{}", todo_ids, prompt)
            response = await llm_client.chat(llm_config, [
                {"role": "system", "content": "你是一个智能任务编排助手，擅长为任务选择执行器并补全 workflow/agent 参数与调度时间。"},
                {"role": "user", "content": prompt}
            ])
            logger.info(
                "Orchestration LLM response for todo_ids={}:\n{}",
                todo_ids,
                json.dumps(response, ensure_ascii=False, default=str),
            )
            await llm_client.log_usage(db, "orchestration", llm_config.model_name, response.get("usage", {}))

            content = response.get("content", "")
            plan = self._parse_plan_response(content)
            plan = self._normalize_plan(plan, todos, agents, wagents, workflows)

            return {
                "status": "pending_confirm",
                "plan": plan,
                "todo_ids": todo_ids,
                "llm_reason": plan.get("reason", content),
            }
        except Exception as e:
            logger.error(f"Orchestration LLM call failed: {e}")
            return self._create_mock_plan(todos, agents, wagents, workflows)

    def _render_prompt_template(self, template: str, values: dict[str, str]) -> str:
        rendered = template
        # Replace known placeholders directly so extra braces in user prompt (for JSON examples)
        # do not trigger str.format parsing errors.
        for key, value in values.items():
            rendered = rendered.replace(f"{{{key}}}", value)
        return rendered

    def _parse_plan_response(self, content: str) -> dict:
        text = (content or "").strip()
        if not text:
            return {}
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        return {"plan_type": "agent", "reason": text}

    def _normalize_plan(self, plan: dict, todos, agents, wagents, workflows) -> dict:
        normalized = dict(plan or {})
        normalized.setdefault("plan_type", "agent")
        normalized["input_params"] = self._coerce_params_map(normalized.get("input_params"))
        normalized.setdefault("priority", "medium")
        normalized.setdefault("estimated_duration_minutes", 30)
        normalized.setdefault("steps", [])
        normalized.setdefault("editable_input_keys", [])

        recommended_id = normalized.get("recommended_id")
        if recommended_id:
            by_id = {item.id: item for item in [*agents, *wagents]}
            target = by_id.get(recommended_id)
            if target:
                normalized.setdefault("recommended_name", getattr(target, "name", ""))
                raw_schema = getattr(target, "input_params", {}) or {}
                candidate_params = self._coerce_params_map(raw_schema)
                editable_keys = self._extract_user_editable_keys(raw_schema)
                normalized["editable_input_keys"] = editable_keys
                normalized["input_params"] = self._merge_input_params(
                    candidate_params,
                    normalized.get("input_params") or {},
                    todos,
                    editable_keys,
                )
        elif normalized.get("plan_type") == "new_wagent":
            normalized.setdefault("recommended_name", "新建W-Agent工作流")
            normalized["steps"] = self._build_new_wagent_steps(workflows, normalized.get("steps"))

        if normalized.get("plan_type") == "new_wagent" and not normalized.get("steps"):
            normalized["steps"] = self._build_new_wagent_steps(workflows, [])

        start_time, deadline = self._normalize_times(
            normalized.get("start_time"),
            normalized.get("deadline"),
            normalized.get("estimated_duration_minutes") or 30,
            todos,
        )
        normalized["start_time"] = start_time
        normalized["deadline"] = deadline
        return normalized

    def _merge_input_params(self, schema_params: dict, llm_params: dict, todos, editable_keys: list[str] | None = None) -> dict:
        schema_map = self._coerce_params_map(schema_params)
        merged = self._coerce_params_map(llm_params)
        if editable_keys is not None:
            editable_set = set(editable_keys)
            schema_map = {k: v for k, v in schema_map.items() if k in editable_set}
            merged = {k: v for k, v in merged.items() if k in editable_set}
        title = todos[0].title if todos else ""
        description = todos[0].description if todos and todos[0].description else ""
        due_date = todos[0].due_date.isoformat() if todos and todos[0].due_date else None
        for key, value in schema_map.items():
            if key in merged and merged[key] not in (None, ""):
                continue
            lowered = str(key).lower()
            if "title" in lowered or "任务" in str(key):
                merged[key] = title
            elif "description" in lowered or "描述" in str(key):
                merged[key] = description
            elif "deadline" in lowered or "due" in lowered or "截止" in str(key):
                merged[key] = due_date
            elif isinstance(value, dict) and "default" in value:
                merged[key] = value.get("default")
            elif value not in (None, "") and not isinstance(value, (dict, list)):
                merged[key] = value
        return merged

    def _extract_user_editable_keys(self, raw_params) -> list[str]:
        if not isinstance(raw_params, list):
            if isinstance(raw_params, dict):
                return list(raw_params.keys())
            return []
        has_explicit_flag = any(isinstance(item, dict) and "user_fill_enabled" in item for item in raw_params)
        keys: list[str] = []
        for item in raw_params:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("key") or item.get("field")
            if not name:
                continue
            if has_explicit_flag:
                if item.get("user_fill_enabled"):
                    keys.append(str(name))
            else:
                keys.append(str(name))
        return keys

    def _filter_prompt_input_params(self, raw_params):
        if isinstance(raw_params, list):
            has_explicit_flag = any(isinstance(item, dict) and "user_fill_enabled" in item for item in raw_params)
            filtered = []
            for item in raw_params:
                if hasattr(item, "model_dump"):
                    item = item.model_dump()
                if not isinstance(item, dict):
                    continue
                # Prompt only includes params for model filling; user_fill_enabled=True means user fills manually.
                if has_explicit_flag and item.get("user_fill_enabled"):
                    continue
                filtered.append(item)
            return filtered
        return raw_params or {}

    def _coerce_params_map(self, raw_params) -> dict:
        if raw_params is None:
            return {}
        if isinstance(raw_params, dict):
            return dict(raw_params)
        if isinstance(raw_params, list):
            normalized: dict = {}
            for item in raw_params:
                if hasattr(item, "model_dump"):
                    item = item.model_dump()
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("key") or item.get("field")
                if not name:
                    continue
                if "default" in item:
                    normalized[name] = item.get("default")
                elif "value" in item:
                    normalized[name] = item.get("value")
                else:
                    normalized[name] = item
            return normalized
        return {}

    def _build_new_wagent_steps(self, workflows, raw_steps) -> list[dict]:
        workflow_by_id = {wf.id: wf for wf in workflows}
        workflow_by_name = {wf.name: wf for wf in workflows}
        normalized_steps: list[dict] = []

        for idx, step in enumerate(raw_steps or []):
            if hasattr(step, "model_dump"):
                step = step.model_dump()
            if not isinstance(step, dict):
                continue
            workflow = None
            if step.get("workflow_id"):
                workflow = workflow_by_id.get(step.get("workflow_id"))
            if workflow is None and step.get("workflow_name"):
                workflow = workflow_by_name.get(step.get("workflow_name"))
            if workflow is None:
                continue

            normalized_steps.append({
                "order": step.get("order", idx + 1),
                "workflow_id": workflow.id,
                "workflow_name": workflow.name,
                "execution_mode": step.get("execution_mode", "serial"),
                "param_mapping": step.get("param_mapping", {}),
            })

        if normalized_steps:
            return normalized_steps

        return [
            {
                "order": idx + 1,
                "workflow_id": wf.id,
                "workflow_name": wf.name,
                "execution_mode": "serial",
                "param_mapping": {},
            }
            for idx, wf in enumerate(workflows[: min(3, len(workflows))])
        ]

    def _normalize_times(self, start_time, deadline, estimated_duration_minutes, todos):
        now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
        parsed_start = self._parse_iso_datetime(start_time) or now
        due_dates = [t.due_date for t in todos if getattr(t, "due_date", None)]
        earliest_due = min(due_dates) if due_dates else None
        parsed_deadline = self._parse_iso_datetime(deadline)
        if parsed_deadline is None:
            parsed_deadline = earliest_due or (parsed_start + timedelta(minutes=max(int(estimated_duration_minutes or 30), 30)))
        if earliest_due and parsed_deadline > earliest_due:
            parsed_deadline = earliest_due
        if parsed_deadline < parsed_start:
            parsed_start = parsed_deadline - timedelta(minutes=max(int(estimated_duration_minutes or 30), 30))
        return parsed_start.isoformat(), parsed_deadline.isoformat()

    def _parse_iso_datetime(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value.replace(microsecond=0)
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None, microsecond=0)
        except ValueError:
            return None

    def _create_mock_plan(self, todos, agents, wagents, workflows):
        """Create a simple mock plan when LLM is not available"""
        recommended = agents[0] if agents else (wagents[0] if wagents else None)
        if not recommended and workflows:
            start_time, deadline = self._normalize_times(None, None, 30, todos)
            return {
                "status": "pending_confirm",
                "plan": {
                    "plan_type": "new_wagent",
                    "recommended_id": "",
                    "recommended_name": "新建W-Agent工作流",
                    "reason": "基于可用 Workflow 组合新的 W-Agent 来完成任务",
                    "input_params": {},
                    "priority": "medium",
                    "estimated_duration_minutes": 30,
                    "start_time": start_time,
                    "deadline": deadline,
                    "steps": self._build_new_wagent_steps(workflows, []),
                },
                "todo_ids": [t.id for t in todos],
                "llm_reason": "基于可用 Workflow 组合新的 W-Agent 来完成任务",
            }
        if not recommended:
            return {"status": "failed", "error": "No agents, W-Agents, or Workflows available"}

        is_agent = isinstance(recommended, Agent) if hasattr(recommended, '__class__') else True
        start_time, deadline = self._normalize_times(None, None, 30, todos)
        return {
            "status": "pending_confirm",
            "plan": {
                "plan_type": "agent" if is_agent else "wagent",
                "recommended_id": recommended.id,
                "recommended_name": recommended.name,
                "reason": f"推荐使用 {recommended.name} 处理此任务",
                "input_params": self._merge_input_params(
                    getattr(recommended, 'input_params', {}) or {},
                    {},
                    todos,
                    self._extract_user_editable_keys(getattr(recommended, 'input_params', {}) or {}),
                ),
                "editable_input_keys": self._extract_user_editable_keys(getattr(recommended, 'input_params', {}) or {}),
                "priority": "medium",
                "estimated_duration_minutes": 30,
                "start_time": start_time,
                "deadline": deadline,
                "steps": [
                    {
                        "order": idx + 1,
                        "workflow_id": wf.id,
                        "workflow_name": wf.name,
                        "execution_mode": "serial",
                        "param_mapping": {},
                    }
                    for idx, wf in enumerate(workflows[: min(3, len(workflows))])
                ] if not is_agent and workflows else [],
            },
            "todo_ids": [t.id for t in todos],
            "llm_reason": f"推荐使用 {recommended.name} 处理此任务",
        }


orchestrator = Orchestrator()
