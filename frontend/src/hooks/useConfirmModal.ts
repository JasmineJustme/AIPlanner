import { useState, useEffect, useCallback } from 'react';
import { sseManager } from '@/api/sse';
import { confirmExecute, delayTask, cancelTask } from '@/api/scheduling';
import type { ConfirmTaskInfo } from '@/components/ConfirmModal';

export function useConfirmModal() {
  const [visible, setVisible] = useState(false);
  const [task, setTask] = useState<ConfirmTaskInfo | null>(null);

  useEffect(() => {
    sseManager.connect();
    const handler = (data: unknown) => {
      const d = data as { task_id?: string; task_name?: string };
      if (d?.task_id) {
        setTask({
          id: d.task_id,
          name: d.task_name ?? `Task ${d.task_id?.slice(0, 8) ?? ''}`,
          agentName: '',
          estimatedDuration: 0,
          paramsSummary: '',
        });
        setVisible(true);
      }
    };
    sseManager.on('task.confirm_required', handler);
    return () => sseManager.off('task.confirm_required', handler);
  }, []);

  const handleConfirm = useCallback(async (taskId: string) => {
    await confirmExecute(taskId);
  }, []);

  const handleDelay = useCallback(async (taskId: string, minutes: number) => {
    await delayTask(taskId, { minutes });
  }, []);

  const handleCancel = useCallback(async (taskId: string) => {
    await cancelTask(taskId);
  }, []);

  const handleClose = useCallback(() => {
    setVisible(false);
    setTask(null);
  }, []);

  return {
    visible,
    task,
    onConfirm: handleConfirm,
    onDelay: handleDelay,
    onCancel: handleCancel,
    onClose: handleClose,
  };
}
