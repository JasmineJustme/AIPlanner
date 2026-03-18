from datetime import UTC, datetime
import json
import re

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DataSource, LLMConfig, Responsibility, Todo
from app.services.datasource_sync import sync_all_datasources
from app.services.llm_client import llm_client


class TodoDiscoveryEngine:
    def _normalize_responsibility_titles(self, value: object) -> list[str]:
        if isinstance(value, str):
            candidates = re.split(r"[,，;；/、\n]+", value)
        elif isinstance(value, list):
            candidates = []
            for item in value:
                if isinstance(item, dict):
                    title = item.get("title") or item.get("name") or item.get("职责")
                    if title:
                        candidates.append(str(title))
                elif item is not None:
                    candidates.append(str(item))
        else:
            return []

        seen: set[str] = set()
        normalized: list[str] = []
        for raw in candidates:
            title = str(raw or "").strip()
            if not title:
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(title)
        return normalized

    async def _build_responsibility_lookup(self, db: AsyncSession) -> dict[str, str]:
        result = await db.execute(select(Responsibility))
        items = result.scalars().all()
        lookup: dict[str, str] = {}
        for item in items:
            key = (item.title or "").strip().lower()
            if key and key not in lookup:
                lookup[key] = item.id
        return lookup

    def _resolve_responsibility_ids(self, titles: list[str], lookup: dict[str, str]) -> list[str]:
        ids: list[str] = []
        for title in titles:
            matched = lookup.get(title.strip().lower())
            if matched and matched not in ids:
                ids.append(matched)
        return ids

    def _render_prompt_template(self, template: str, values: dict[str, str]) -> str:
        rendered = template or ""
        for key, value in values.items():
            rendered = rendered.replace(f"{{{key}}}", value)
        return rendered

    def _extract_json_payload(self, content: str) -> dict | list | None:
        text = (content or "").strip()
        if not text:
            return None
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
            if not match:
                return None
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

    def _normalize_priority(self, value: str | None) -> str:
        if value in {"high", "medium", "low"}:
            return value
        return "medium"

    def _parse_due_date(self, value: object) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    def _normalize_execution_mode(self, value: object) -> str:
        text = str(value or "").strip().lower()
        if text in {"user", "manual", "human", "用户", "人工"}:
            return "user"
        return "system"

    def _normalize_bool(self, value: object) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "y", "on", "是", "需要", "需"}

    def _pick_first(self, item: dict, keys: list[str]) -> object:
        for key in keys:
            if key in item and item.get(key) not in (None, ""):
                return item.get(key)
        return None

    def _extract_discovered_todos(self, payload: dict | list | None) -> list[dict]:
        if payload is None:
            return []
        items: list = []
        if isinstance(payload, dict):
            for key in ("todos", "items", "tasks"):
                if isinstance(payload.get(key), list):
                    items = payload.get(key) or []
                    break
            if not items and (
                payload.get("title")
                or payload.get("summary")
                or payload.get("todo_summary")
                or payload.get("待办摘要")
            ):
                items = [payload]
        elif isinstance(payload, list):
            items = payload

        discovered: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(
                self._pick_first(item, ["todo_summary", "summary", "title", "待办摘要", "任务标题"]) or ""
            ).strip()
            if not title:
                continue

            description = self._pick_first(item, ["task_description", "description", "detail", "任务描述", "描述"])
            urgency_reason = self._pick_first(item, ["urgency_reason", "紧急性原因", "priority_reason", "reason"])
            confirm_time = self._pick_first(item, ["confirm_by", "confirm_time", "need_confirm_before", "确认时间", "需要用户确认时间", "due_date", "deadline"])
            execution_mode = self._pick_first(item, ["executor", "execution_mode", "执行方", "执行人"])
            recurring = self._pick_first(item, ["start_recurring", "is_recurring", "need_recurring", "是否开始循环", "是否需要开始循环"])
            responsibilities = self._pick_first(
                item,
                [
                    "responsibilities",
                    "responsibility_titles",
                    "responsibility_sources",
                    "work_responsibilities",
                    "来源职责",
                    "工作职责",
                    "职责",
                ],
            )

            raw_tags = item.get("tags")
            tags = raw_tags if isinstance(raw_tags, list) else []
            if urgency_reason:
                tags = [*tags, f"urgency_reason:{str(urgency_reason).strip()}"]

            discovered.append(
                {
                    "title": title,
                    "description": str(description or "").strip() or None,
                    "priority": self._normalize_priority(item.get("priority") if isinstance(item.get("priority"), str) else None),
                    "due_date": self._parse_due_date(confirm_time),
                    "tags": tags,
                    "responsibility_titles": self._normalize_responsibility_titles(responsibilities),
                    "project": str(item.get("project") or item.get("项目") or "").strip() or None,
                    "review_reason": str(urgency_reason or "").strip() or None,
                    "is_recurring": self._normalize_bool(recurring),
                    "execution_mode": self._normalize_execution_mode(execution_mode),
                }
            )
        return discovered

    def _flatten_responsibility_tree(self, by_parent: dict[str | None, list[Responsibility]], parent_id: str | None = None, depth: int = 0) -> list[str]:
        lines: list[str] = []
        children = by_parent.get(parent_id, [])
        children.sort(key=lambda x: (x.sort_order, x.created_at))
        for node in children:
            indent = "  " * depth
            title = (node.title or "").strip()
            desc = (node.description or "").strip()
            if title:
                lines.append(f"{indent}- {title}{f'：{desc}' if desc else ''}")
            lines.extend(self._flatten_responsibility_tree(by_parent, node.id, depth + 1))
        return lines

    async def _build_responsibility_text(self, db: AsyncSession) -> str:
        result = await db.execute(select(Responsibility))
        items = result.scalars().all()
        by_parent: dict[str | None, list[Responsibility]] = {}
        for item in items:
            by_parent.setdefault(item.parent_id, []).append(item)
        lines = self._flatten_responsibility_tree(by_parent)
        return "\n".join(lines) if lines else "- 无"

    async def _run_todo_dedup(self, db: AsyncSession) -> list[dict]:
        cfg_result = await db.execute(select(LLMConfig).where(LLMConfig.purpose == "todo_dedup"))
        llm_cfg = cfg_result.scalar_one_or_none()
        if not llm_cfg:
            return []

        result = await db.execute(
            select(Todo).where(
                Todo.source == "system",
                Todo.status != "completed",
            )
        )
        todos = result.scalars().all()
        if len(todos) < 2:
            return []

        for todo in todos:
            todo.duplicate_of = None

        todo_desc = "\n".join(
            [
                f"- id={t.id}; title={t.title}; description={t.description or ''}; priority={t.priority}; project={t.project or ''}"
                for t in todos
            ]
        )
        default_prompt = (
            "请识别以下待办中语义重复的任务。\n"
            "当前时间:\n{current_time}\n\n"
            "待办列表:\n{todo_desc}\n\n"
            "仅返回 JSON：{\"duplicates\":[{\"source_id\":\"...\",\"target_id\":\"...\",\"reason\":\"...\"}]}"
        )
        prompt = self._render_prompt_template(
            llm_cfg.prompt_template or default_prompt,
            {
                "current_time": datetime.now(UTC).replace(tzinfo=None, microsecond=0).isoformat(),
                "todo_desc": todo_desc,
            },
        )
        if "duplicates" not in prompt:
            prompt = f"{prompt}\n\n仅返回 JSON：{{\"duplicates\":[{{\"source_id\":\"...\",\"target_id\":\"...\",\"reason\":\"...\"}}]}}"

        logger.info("Todo dedup LLM prompt:\n{}", prompt)
        response = await llm_client.chat(
            llm_cfg,
            [
                {"role": "system", "content": "你是待办任务去重助手。"},
                {"role": "user", "content": prompt},
            ],
        )
        logger.info("Todo dedup LLM response:\n{}", json.dumps(response, ensure_ascii=False, default=str))
        await llm_client.log_usage(db, "todo_dedup", llm_cfg.model_name or "", response.get("usage", {}))

        payload = self._extract_json_payload(response.get("content", ""))
        duplicates_raw = payload.get("duplicates") if isinstance(payload, dict) else None
        if not isinstance(duplicates_raw, list):
            await db.flush()
            return []

        by_id = {todo.id: todo for todo in todos}
        dedup_links: list[dict] = []
        for rel in duplicates_raw:
            if not isinstance(rel, dict):
                continue
            source_id = str(rel.get("source_id") or "").strip()
            target_id = str(rel.get("target_id") or "").strip()
            if not source_id or not target_id or source_id == target_id:
                continue
            source_todo = by_id.get(source_id)
            target_todo = by_id.get(target_id)
            if not source_todo or not target_todo:
                continue
            source_todo.duplicate_of = target_id
            dedup_links.append(
                {
                    "source_id": source_id,
                    "source_title": source_todo.title,
                    "target_id": target_id,
                    "target_title": target_todo.title,
                    "reason": str(rel.get("reason") or ""),
                }
            )

        await db.flush()
        return dedup_links

    async def smart_discover(self, db: AsyncSession) -> dict:
        # Always sync datasources first, then analyze synced context.
        synced_data = await sync_all_datasources(db)

        enabled_ds_result = await db.execute(select(DataSource).where(DataSource.is_enabled == True))
        enabled_ds = enabled_ds_result.scalars().all()
        ds_lines = []
        for ds in enabled_ds:
            ds_lines.append(
                f"- {ds.type}: status={ds.last_sync_status or 'unknown'}; error={ds.last_sync_error or 'none'}; data={json.dumps((synced_data or {}).get(ds.type, ds.sync_data_cache or {}), ensure_ascii=False)}"
            )
        datasource_text = "\n".join(ds_lines) if ds_lines else "- 无可用数据源"
        responsibility_text = await self._build_responsibility_text(db)
        responsibility_lookup = await self._build_responsibility_lookup(db)

        llm_result = await db.execute(select(LLMConfig).where(LLMConfig.purpose == "todo_analysis"))
        llm_cfg = llm_result.scalar_one_or_none()
        if not llm_cfg:
            raise ValueError("待办梳理 LLM 未配置")

        current_time = datetime.now(UTC).replace(tzinfo=None, microsecond=0).isoformat()
        default_prompt = (
            "请根据数据源同步信息和工作职责，识别可执行待办。\n\n"
            "当前时间:\n{current_time}\n\n"
            "数据源信息:\n{datasource_info}\n\n"
            "工作职责:\n{responsibilities}\n\n"
            "仅返回 JSON，字段必须完整："
            "{\"todos\":[{\"todo_summary\":\"\",\"task_description\":\"\",\"priority\":\"high|medium|low\",\"urgency_reason\":\"\",\"start_recurring\":false,\"confirm_by\":null,\"executor\":\"user|system\",\"tags\":[],\"project\":\"\",\"responsibilities\":[]}]}"
        )
        prompt = self._render_prompt_template(
            llm_cfg.prompt_template or default_prompt,
            {
                "current_time": current_time,
                "datasource_info": datasource_text,
                "responsibilities": responsibility_text,
            },
        )
        if '"todos"' not in prompt:
            prompt = (
                f"{prompt}\n\n"
                "仅返回 JSON：{\"todos\":[{\"todo_summary\":\"\",\"task_description\":\"\",\"priority\":\"high|medium|low\",\"urgency_reason\":\"\",\"start_recurring\":false,\"confirm_by\":null,\"executor\":\"user|system\",\"tags\":[],\"project\":\"\",\"responsibilities\":[]}]}"
            )

        logger.info("Todo analysis LLM prompt:\n{}", prompt)
        response = await llm_client.chat(
            llm_cfg,
            [
                {"role": "system", "content": "你是待办任务梳理助手。"},
                {"role": "user", "content": prompt},
            ],
        )
        logger.info("Todo analysis LLM response:\n{}", json.dumps(response, ensure_ascii=False, default=str))
        await llm_client.log_usage(db, "todo_analysis", llm_cfg.model_name or "", response.get("usage", {}))

        payload = self._extract_json_payload(response.get("content", ""))
        discovered = self._extract_discovered_todos(payload)

        created_items: list[Todo] = []
        for item in discovered:
            responsibility_titles = item.get("responsibility_titles") or []
            responsibility_ids = self._resolve_responsibility_ids(responsibility_titles, responsibility_lookup)
            todo = Todo(
                title=item["title"],
                description=item.get("description"),
                status="pending_confirm",
                priority=item.get("priority") or "medium",
                source="system",
                execution_mode=item.get("execution_mode") or "system",
                due_date=item.get("due_date"),
                tags=item.get("tags") or [],
                responsibility_ids=responsibility_ids,
                responsibility_titles=responsibility_titles,
                project=item.get("project"),
                review_reason=item.get("review_reason"),
                is_recurring=bool(item.get("is_recurring")),
            )
            db.add(todo)
            created_items.append(todo)

        await db.flush()
        for todo in created_items:
            await db.refresh(todo)

        dedup_links = await self._run_todo_dedup(db)

        return {
            "synced_datasource_count": len(enabled_ds),
            "created_count": len(created_items),
            "dedup_count": len(dedup_links),
            "created_todo_ids": [todo.id for todo in created_items],
            "duplicates": dedup_links,
        }


todo_discovery_engine = TodoDiscoveryEngine()

