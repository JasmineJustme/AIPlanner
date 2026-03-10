export const TaskStatus = {
  PendingConfirm: 'pending_confirm',
  Pending: 'pending',
  Confirming: 'confirming',
  Running: 'running',
  Completed: 'completed',
  Failed: 'failed',
  Skipped: 'skipped',
  Blocked: 'blocked',
  Paused: 'paused',
  Delayed: 'delayed',
  Retrying: 'retrying',
  Archived: 'archived',
} as const;
export type TaskStatus = (typeof TaskStatus)[keyof typeof TaskStatus];

export const STATUS_TAG_MAP: Record<string, { color: string; text: string }> = {
  [TaskStatus.PendingConfirm]: { color: 'blue', text: '待确认' },
  [TaskStatus.Pending]: { color: 'default', text: '待执行' },
  [TaskStatus.Confirming]: { color: 'blue', text: '待确认执行' },
  [TaskStatus.Running]: { color: 'orange', text: '执行中' },
  [TaskStatus.Completed]: { color: 'success', text: '已完成' },
  [TaskStatus.Failed]: { color: 'error', text: '失败' },
  [TaskStatus.Skipped]: { color: 'default', text: '已跳过' },
  [TaskStatus.Blocked]: { color: 'purple', text: '已阻塞' },
  [TaskStatus.Paused]: { color: 'warning', text: '已暂停' },
  [TaskStatus.Delayed]: { color: 'warning', text: '已延后' },
  [TaskStatus.Retrying]: { color: 'orange', text: '重试中' },
  [TaskStatus.Archived]: { color: 'default', text: '已归档' },
};

export const TodoStatus = {
  PendingConfirm: 'pending_confirm',
  Orchestrating: 'orchestrating',
  Scheduling: 'scheduling',
  Completed: 'completed',
  Pending: 'pending',
} as const;
export type TodoStatus = (typeof TodoStatus)[keyof typeof TodoStatus];

export const TODO_STATUS_MAP: Record<string, { color: string; text: string }> = {
  [TodoStatus.PendingConfirm]: { color: 'blue', text: '待确认' },
  [TodoStatus.Orchestrating]: { color: 'cyan', text: '编排中' },
  [TodoStatus.Scheduling]: { color: 'orange', text: '调度中' },
  [TodoStatus.Completed]: { color: 'success', text: '已完成' },
  [TodoStatus.Pending]: { color: 'default', text: '待处理' },
};

export const Priority = {
  High: 'high',
  Medium: 'medium',
  Low: 'low',
} as const;
export type Priority = (typeof Priority)[keyof typeof Priority];

export const PRIORITY_MAP: Record<string, { color: string; text: string }> = {
  [Priority.High]: { color: '#ff4d4f', text: '高' },
  [Priority.Medium]: { color: '#faad14', text: '中' },
  [Priority.Low]: { color: '#52c41a', text: '低' },
};

export const TodoSource = {
  Manual: 'manual',
  Email: 'email',
  Calendar: 'calendar',
  Project: 'project',
} as const;
export type TodoSource = (typeof TodoSource)[keyof typeof TodoSource];

export const SOURCE_MAP: Record<string, { color: string; text: string; icon: string }> = {
  [TodoSource.Manual]: { color: '#8c8c8c', text: '手动', icon: 'EditOutlined' },
  [TodoSource.Email]: { color: '#1890ff', text: '邮件', icon: 'MailOutlined' },
  [TodoSource.Calendar]: { color: '#52c41a', text: '日程', icon: 'CalendarOutlined' },
  [TodoSource.Project]: { color: '#fa8c16', text: '项目', icon: 'ProjectOutlined' },
};

export const ReviewStatus = {
  PendingReview: 'pending_review',
  Confirmed: 'confirmed',
  Rejected: 'rejected',
} as const;
export type ReviewStatus = (typeof ReviewStatus)[keyof typeof ReviewStatus];

export const OrchestrationStatus = {
  Analyzing: 'analyzing',
  PendingConfirm: 'pending_confirm',
  Confirmed: 'confirmed',
  Cancelled: 'cancelled',
  Failed: 'failed',
} as const;
export type OrchestrationStatus = (typeof OrchestrationStatus)[keyof typeof OrchestrationStatus];

export const SchedulePlanStatus = {
  Active: 'active',
  Paused: 'paused',
  Completed: 'completed',
  Cancelled: 'cancelled',
} as const;
export type SchedulePlanStatus = (typeof SchedulePlanStatus)[keyof typeof SchedulePlanStatus];

export const MessageType = {
  ReviewNew: 'review_new',
  OrchestrationConfirm: 'orchestration_confirm',
  TaskConfirm: 'task_confirm',
  TaskCompleted: 'task_completed',
  TaskFailed: 'task_failed',
  PlanChanged: 'plan_changed',
  SyncCompleted: 'sync_completed',
  SyncFailed: 'sync_failed',
  DeadlineWarning: 'deadline_warning',
  RecurringTrigger: 'recurring_trigger',
  CircuitBreaker: 'circuit_breaker',
  SystemAlert: 'system_alert',
} as const;
export type MessageType = (typeof MessageType)[keyof typeof MessageType];

export const MessageStatus = {
  Unread: 'unread',
  Read: 'read',
  Processed: 'processed',
} as const;
export type MessageStatus = (typeof MessageStatus)[keyof typeof MessageStatus];

export const TodoExecutionMode = {
  User: 'user',
  System: 'system',
} as const;
export type TodoExecutionMode = (typeof TodoExecutionMode)[keyof typeof TodoExecutionMode];

export const TODO_EXECUTION_MODE_MAP: Record<string, { color: string; text: string }> = {
  [TodoExecutionMode.User]: { color: 'purple', text: '用户执行' },
  [TodoExecutionMode.System]: { color: 'geekblue', text: '系统执行' },
};
