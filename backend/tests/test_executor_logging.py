import json

from app.engine.executor import Executor


class DummyTask:
    def __init__(self):
        self.id = "task-log-1"
        self.input_params = {"message": "hello"}


def test_build_execution_log_contains_target_and_result():
    executor = Executor()
    task = DummyTask()

    log_text = executor._build_execution_log(
        task=task,
        target_type="agent",
        target_name="发送消息Agent",
        status="completed",
        payload={"result": "ok"},
    )
    data = json.loads(log_text)

    assert data["task_id"] == "task-log-1"
    assert data["target_type"] == "agent"
    assert data["target_name"] == "发送消息Agent"
    assert data["status"] == "completed"
    assert data["output_result"] == {"result": "ok"}

