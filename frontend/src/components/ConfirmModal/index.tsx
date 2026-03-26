import { Modal, Typography, Button, Space, InputNumber } from 'antd';
import { useState, useEffect } from 'react';

export interface ConfirmTaskInfo {
  id: string;
  name: string;
  agentName: string;
  estimatedDuration: number;
  paramsSummary: string;
}

interface ConfirmModalProps {
  visible: boolean;
  task: ConfirmTaskInfo | null;
  onConfirm: (taskId: string) => void;
  onDelay: (taskId: string, minutes: number) => void;
  onCancel: (taskId: string) => void;
  onClose: () => void;
}

export default function ConfirmModal({
  visible,
  task,
  onConfirm,
  onDelay,
  onCancel,
  onClose,
}: ConfirmModalProps) {
  const [delayMinutes, setDelayMinutes] = useState(30);

  useEffect(() => {
    if (task) {
      setDelayMinutes(30);
    }
  }, [task]);

  if (!task) return null;

  const handleConfirm = () => {
    onConfirm(task.id);
    onClose();
  };

  const handleDelay = () => {
    onDelay(task.id, delayMinutes);
    onClose();
  };

  const handleCancel = () => {
    onCancel(task.id);
    onClose();
  };

  return (
    <Modal
      title="执行确认"
      open={visible}
      onCancel={onClose}
      footer={null}
      width={480}
      destroyOnClose
    >
      <div style={{ marginBottom: 16 }}>
        <Typography.Paragraph strong>任务：{task.name}</Typography.Paragraph>
        <Typography.Paragraph type="secondary">Agent/W-Agent：{task.agentName}</Typography.Paragraph>
        {task.estimatedDuration > 0 && (
          <Typography.Paragraph type="secondary">
            预计耗时：约 {task.estimatedDuration} 分钟
          </Typography.Paragraph>
        )}
        {task.paramsSummary && (
          <Typography.Paragraph type="secondary" ellipsis={{ rows: 3 }}>
            参数摘要：{task.paramsSummary}
          </Typography.Paragraph>
        )}
      </div>
      <Space wrap>
        <Button type="primary" onClick={handleConfirm}>
          立即执行
        </Button>
        <Space>
          <InputNumber
            min={1}
            max={1440}
            value={delayMinutes}
            onChange={(v) => setDelayMinutes(v ?? 30)}
            addonBefore="延后"
            addonAfter="分钟"
          />
          <Button onClick={handleDelay}>延后执行</Button>
        </Space>
        <Button onClick={handleCancel}>取消</Button>
      </Space>
    </Modal>
  );
}
