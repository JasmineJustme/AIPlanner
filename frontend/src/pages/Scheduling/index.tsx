import { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import {
  Typography,
  Tabs,
  Table,
  Card,
  Tag,
  Button,
  Space,
  Select,
  Segmented,
  message,
  Popconfirm,
} from 'antd';
import {
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  CloseOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { gantt } from 'dhtmlx-gantt';
import 'dhtmlx-gantt/codebase/dhtmlxgantt.css';
import {
  getScheduleTasks,
  getGanttData,
  getSchedulePlans,
  retryTask,
  runNowTask,
  cancelTask,
  pauseTask,
  resumeTask,
  delayTask,
} from '@/api/scheduling';
import type { ScheduleTask, SchedulePlan } from '@/types/schedule';
import type { APIResponse } from '@/api/client';
import StatusTag from '@/components/StatusTag';
import PriorityTag from '@/components/PriorityTag';
import JsonViewer from '@/components/JsonViewer';
import { sseManager } from '@/api/sse';
import dayjs from 'dayjs';
import { useLocation } from 'react-router-dom';

const { Title } = Typography;

/* Gantt bar colors by status */
const ganttStatusStyles = `
  .gantt_completed .gantt_task_progress { background: #52c41a !important; }
  .gantt_failed .gantt_task_progress,
  .gantt_failed .gantt_task_content { background: #ff4d4f !important; }
  .gantt_running .gantt_task_progress,
  .gantt_running .gantt_task_content { background: #fa8c16 !important; }
`;

const parentCardStyles = {
  marginBottom: 12,
  borderRadius: 8,
  border: '1px solid #e5f5d9',
} as const;

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '待执行' },
  { value: 'running', label: '执行中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'skipped', label: '已跳过' },
  { value: 'blocked', label: '已阻塞' },
  { value: 'confirming', label: '待确认' },
];

const GANTT_WINDOW_OPTIONS = [
  { label: '7天', value: 7 },
  { label: '14天', value: 14 },
  { label: '30天', value: 30 },
];

function parseStatusFilterFromSearch(search: string): string {
  const status = new URLSearchParams(search).get('status') || '';
  const allowed = STATUS_OPTIONS.map((item) => item.value);
  return allowed.includes(status) ? status : '';
}

function GanttView({ tasks, windowDays }: { tasks: Array<{ id: string; name: string; start?: string | null; end?: string | null; status: string }>; windowDays: number }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const initialized = useRef(false);

  useEffect(() => {
    if (!containerRef.current) return;

    if (!initialized.current) {
      gantt.config.readonly = true;
      gantt.config.drag_move = false;
      gantt.config.drag_progress = false;
      gantt.config.drag_resize = false;
      gantt.config.drag_links = false;
      gantt.config.columns = [
        { name: 'text', label: '任务', width: 200, tree: true },
        { name: 'status', label: '状态', width: 80 },
      ];
      gantt.templates.task_class = (_start: Date, _end: Date, task: unknown) => {
        const status = (task as { status?: string })?.status || '';
        if (status === 'completed') return 'gantt_completed';
        if (status === 'failed') return 'gantt_failed';
        if (status === 'running') return 'gantt_running';
        return '';
      };
      gantt.init(containerRef.current);
      initialized.current = true;
    }

    const dayMs = 24 * 60 * 60 * 1000;
    const windowSpanMs = Math.max(windowDays - 1, 0) * dayMs;
    const now = new Date();
    let windowStart = now;
    let windowEnd = new Date(now.getTime() + windowSpanMs);

    const parsedRanges = tasks
      .map((t) => {
        const parsedStart = t.start ? new Date(t.start) : null;
        const parsedEnd = t.end ? new Date(t.end) : null;
        if (parsedStart && Number.isNaN(parsedStart.getTime())) return null;
        if (parsedEnd && Number.isNaN(parsedEnd.getTime())) return null;
        const start = parsedStart || parsedEnd;
        const end = parsedEnd || parsedStart;
        if (!start || !end) return null;
        return { start, end };
      })
      .filter((item): item is { start: Date; end: Date } => !!item);

    if (parsedRanges.length > 0) {
      const latestTaskTime = new Date(Math.max(...parsedRanges.map((range) => range.end.getTime())));
      windowEnd = latestTaskTime;
      windowStart = new Date(windowEnd.getTime() - windowSpanMs);

      const tasksInBackwardWindow = parsedRanges
        .filter((range) => range.end >= windowStart && range.start <= windowEnd)
        .sort((a, b) => a.start.getTime() - b.start.getTime());

      if (tasksInBackwardWindow.length > 0) {
        const firstTaskStart = tasksInBackwardWindow[0].start;
        if (firstTaskStart.getTime() > windowStart.getTime()) {
          windowStart = firstTaskStart;
          windowEnd = new Date(windowStart.getTime() + windowSpanMs);
        }
      }
    }

    gantt.config.start_date = windowStart;
    gantt.config.end_date = windowEnd;

    const ganttTasks = tasks.map((t) => {
      const start = t.start ? new Date(t.start) : new Date();
      const end = t.end ? new Date(t.end) : new Date(start.getTime() + 3600000);
      const duration = Math.max(1, Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)));
      return {
        id: t.id,
        text: t.name,
        start_date: start,
        duration,
        progress: t.status === 'completed' ? 1 : 0,
        status: t.status,
      };
    });
    gantt.clearAll();
    gantt.parse({ data: ganttTasks, links: [] });
  }, [tasks, windowDays]);

  return (
    <>
      <style>{ganttStatusStyles}</style>
      <div
        ref={containerRef}
        style={{ width: '100%', height: 400, minHeight: 400 }}
      />
    </>
  );
}

export default function SchedulingPage() {
  const location = useLocation();
  const [tasks, setTasks] = useState<ScheduleTask[]>([]);
  const [plans, setPlans] = useState<SchedulePlan[]>([]);
  const [ganttTasks, setGanttTasks] = useState<Array<{ id: string; name: string; start?: string | null; end?: string | null; status: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>(() => parseStatusFilterFromSearch(location.search));
  const [planFilter, setPlanFilter] = useState<string>('');
  const [ganttWindowDays, setGanttWindowDays] = useState<number>(7);

  const getTaskDisplayName = useCallback((task: Pick<ScheduleTask, 'task_title' | 'plan_name' | 'agent_name' | 'agent_id' | 'wagent_id' | 'id'>) => {
    return task.task_title
      || task.plan_name
      || task.agent_name
      || (task.agent_id ? `Agent ${task.agent_id.slice(0, 8)}` : task.wagent_id ? `W-Agent ${task.wagent_id.slice(0, 8)}` : `Task ${task.id.slice(0, 8)}`);
  }, []);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getScheduleTasks();
      const body = res.data as APIResponse<ScheduleTask[]>;
      const data = body?.data ?? (res.data as unknown);
      setTasks(Array.isArray(data) ? data : []);
    } catch {
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadGantt = useCallback(async () => {
    try {
      const params = planFilter ? { plan_id: planFilter } : undefined;
      const res = await getGanttData(params);
      const body = res.data as APIResponse<{ tasks: Array<{ id: string; name: string; start?: string | null; end?: string | null; status: string }> }>;
      const data = body?.data ?? (res.data as unknown);
      const taskList = (data as { tasks?: Array<{ id: string; name: string; start?: string | null; end?: string | null; status: string }> })?.tasks ?? [];
      setGanttTasks(Array.isArray(taskList) ? taskList : []);
    } catch {
      setGanttTasks([]);
    }
  }, [planFilter]);

  const loadPlans = useCallback(async () => {
    try {
      const res = await getSchedulePlans();
      const body = res.data as APIResponse<SchedulePlan[]>;
      const data = body?.data ?? (res.data as unknown);
      setPlans(Array.isArray(data) ? data : []);
    } catch {
      setPlans([]);
    }
  }, []);

  useEffect(() => {
    loadTasks();
    loadGantt();
    loadPlans();
  }, [loadTasks, loadGantt, loadPlans]);

  useEffect(() => {
    const next = parseStatusFilterFromSearch(location.search);
    setStatusFilter((prev) => (prev === next ? prev : next));
  }, [location.search]);

  useEffect(() => {
    sseManager.connect();
    const handler = () => {
      loadTasks();
      loadGantt();
    };
    sseManager.on('task.status_changed', handler);
    return () => sseManager.off('task.status_changed', handler);
  }, [loadTasks, loadGantt]);

  const handleRetryTask = async (taskId: string) => {
    try {
      await retryTask(taskId);
      message.success('已加入重试队列');
      loadTasks();
      loadGantt();
    } catch {
      message.error('重试失败');
    }
  };

  const handleRunNowTask = async (taskId: string) => {
    try {
      await runNowTask(taskId);
      message.success('已加入立即执行队列');
      loadTasks();
      loadGantt();
    } catch {
      message.error('操作失败');
    }
  };

  const handleCancelTask = async (task: ScheduleTask) => {
    try {
      await cancelTask(task.id);
      if (task.is_parent) {
        message.success('已取消总任务及其全部子任务，任务已返回智能编排界面');
      } else if (task.parent_task_id) {
        message.success('已取消子任务，并恢复父任务到下一次循环时间');
      } else {
        message.success('已取消非循环任务，任务已返回智能编排界面');
      }
      loadTasks();
      loadGantt();
    } catch {
      message.error('操作失败');
    }
  };

  const handlePauseTask = async (taskId: string) => {
    try {
      await pauseTask(taskId);
      message.success('已暂停');
      loadTasks();
      loadGantt();
    } catch {
      message.error('操作失败');
    }
  };

  const handleResumeTask = async (taskId: string) => {
    try {
      await resumeTask(taskId);
      message.success('已恢复');
      loadTasks();
      loadGantt();
    } catch {
      message.error('操作失败');
    }
  };

  const handleDelayTask = async (taskId: string) => {
    try {
      await delayTask(taskId, { minutes: 30 });
      message.success('已延后 30 分钟');
      loadTasks();
      loadGantt();
    } catch {
      message.error('操作失败');
    }
  };

  const activePlan = planFilter || (plans.length > 0 ? plans[0].id : null);

  const displayData = useMemo(() => {
    const parentTasks = tasks.filter((t) => !!t.is_parent);
    const children = tasks.filter((t) => !t.is_parent);
    const childrenByParent: Record<string, ScheduleTask[]> = {};

    children.forEach((t) => {
      const pid = t.parent_task_id;
      if (!pid) return;
      childrenByParent[pid] = childrenByParent[pid] || [];
      childrenByParent[pid].push(t);
    });

    const recurringGroups = parentTasks.map((p) => {
      const childList = (childrenByParent[p.id] || []).sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));
      return { parent: p, children: childList };
    });

    const nonRecurringTasks = tasks.filter((t) => !t.is_parent && !t.parent_task_id);
    const orphanChildren = children.filter((t) => t.parent_task_id && !parentTasks.some((p) => p.id === t.parent_task_id));

    return {
      recurringGroups,
      nonRecurringTasks: [...nonRecurringTasks, ...orphanChildren],
    };
  }, [tasks]);

  const matchTaskFilter = useCallback((task: ScheduleTask) => {
    if (statusFilter && task.status !== statusFilter) return false;
    if (planFilter && task.plan_id !== planFilter) return false;
    if (task.status === 'cancelled') return false;
    return true;
  }, [statusFilter, planFilter]);

  const filteredRecurringGroups = useMemo(() => {
    return displayData.recurringGroups
      .map((g) => ({ ...g, children: g.children.filter(matchTaskFilter) }))
      .filter((g) => {
        if (!statusFilter && !planFilter) return true;
        if (planFilter && g.parent.plan_id === planFilter) return true;
        return g.children.length > 0;
      });
  }, [displayData.recurringGroups, matchTaskFilter, statusFilter, planFilter]);

  const filteredNonRecurringTasks = useMemo(
    () => displayData.nonRecurringTasks.filter(matchTaskFilter),
    [displayData.nonRecurringTasks, matchTaskFilter],
  );

  const fallbackUngroupedTasks = useMemo(() => {
    const visibleIds = new Set<string>();
    filteredRecurringGroups.forEach((g) => {
      visibleIds.add(g.parent.id);
      g.children.forEach((c) => visibleIds.add(c.id));
    });
    filteredNonRecurringTasks.forEach((t) => visibleIds.add(t.id));

    return tasks.filter((t) => matchTaskFilter(t) && !visibleIds.has(t.id));
  }, [tasks, matchTaskFilter, filteredRecurringGroups, filteredNonRecurringTasks]);

  const renderParentActions = (r: ScheduleTask) => (
    <Space size="small">
      {(r.status === 'recurring' || r.status === 'pending' || r.status === 'running' || r.status === 'confirming') && (
        <Popconfirm title="确定立即执行？" onConfirm={() => handleRunNowTask(r.id)}>
          <Button type="link" size="small" icon={<ThunderboltOutlined />}>立即执行</Button>
        </Popconfirm>
      )}
      {(r.status === 'recurring' || r.status === 'pending' || r.status === 'running' || r.status === 'confirming') && (
        <Popconfirm title="确定取消总任务并回到编排？" onConfirm={() => handleCancelTask(r)}>
          <Button type="link" size="small" danger icon={<CloseOutlined />}>取消</Button>
        </Popconfirm>
      )}
      {r.status !== 'completed' && r.status !== 'failed' && r.status !== 'cancelled' && (
        <Button type="link" size="small" icon={<ClockCircleOutlined />} onClick={() => handleDelayTask(r.id)}>延后</Button>
      )}
    </Space>
  );

  const childTaskColumns = [
    {
      title: '任务名称',
      key: 'name',
      render: (_: unknown, r: ScheduleTask) => getTaskDisplayName(r),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <StatusTag status={s} />,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      render: (p: string) => <PriorityTag priority={p || 'medium'} />,
    },
    {
      title: '计划时间',
      dataIndex: 'scheduled_at',
      key: 'scheduled_at',
      render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '完成时间',
      dataIndex: 'completed_at',
      key: 'completed_at',
      render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '重试次数',
      key: 'retry',
      render: (_: unknown, r: ScheduleTask) => `${r.retry_count ?? 0} / ${r.max_retries ?? 3}`,
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_: unknown, r: ScheduleTask) => {
        const isTerminalFailed = r.status === 'failed' && (r.retry_count ?? 0) >= (r.max_retries ?? 3);
        return (
          <Space size="small">
            {r.status === 'failed' && (
              <Button type="link" size="small" icon={<ReloadOutlined />} onClick={() => handleRetryTask(r.id)}>重试</Button>
            )}
            {isTerminalFailed && (
              <Popconfirm title="确定取消？" onConfirm={() => handleCancelTask(r)}>
                <Button type="link" size="small" danger icon={<CloseOutlined />}>取消</Button>
              </Popconfirm>
            )}
            {(r.status === 'pending' || r.status === 'confirming') && (
              <>
                <Popconfirm title="确定立即执行？" onConfirm={() => handleRunNowTask(r.id)}>
                  <Button type="link" size="small" icon={<ThunderboltOutlined />}>立即执行</Button>
                </Popconfirm>
                <Popconfirm title="确定取消？" onConfirm={() => handleCancelTask(r)}>
                  <Button type="link" size="small" danger icon={<CloseOutlined />}>取消</Button>
                </Popconfirm>
              </>
            )}
            {r.status === 'running' && (
              <Button type="link" size="small" icon={<PauseCircleOutlined />} onClick={() => handlePauseTask(r.id)}>暂停</Button>
            )}
            {r.status === 'paused' && (
              <Button type="link" size="small" icon={<PlayCircleOutlined />} onClick={() => handleResumeTask(r.id)}>恢复</Button>
            )}
            {r.status !== 'completed' && r.status !== 'failed' && (
              <Button type="link" size="small" icon={<ClockCircleOutlined />} onClick={() => handleDelayTask(r.id)}>延后</Button>
            )}
          </Space>
        );
      },
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          调度监控
        </Title>
        <Space>
          <Select
            placeholder="状态筛选"
            value={statusFilter || undefined}
            onChange={(v) => setStatusFilter(v || '')}
            style={{ width: 120 }}
            options={STATUS_OPTIONS}
          />
          <Select
            placeholder="计划筛选"
            value={planFilter || undefined}
            onChange={(v) => setPlanFilter(v || '')}
            style={{ width: 160 }}
            options={[{ value: '', label: '全部计划' }, ...plans.map((p) => ({ value: p.id, label: p.name }))]}
          />
          <Segmented
            options={GANTT_WINDOW_OPTIONS}
            value={ganttWindowDays}
            onChange={(value) => setGanttWindowDays(Number(value))}
          />
        </Space>
      </div>

      {activePlan && (
        <Space style={{ marginBottom: 16 }}>
           <Typography.Text type="secondary">Plan ID: {activePlan}</Typography.Text>
        </Space>
      )}

      <Tabs
        defaultActiveKey="gantt"
        items={[
          {
            key: 'gantt',
            label: '甘特图',
            children: (
              <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
                <GanttView tasks={ganttTasks} windowDays={ganttWindowDays} />
              </div>
            ),
          },
          {
            key: 'list',
            label: '列表',
            children: (
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                {filteredRecurringGroups.map((group) => {
                  const done = group.parent.recurrence_done ?? 0;
                  const limit = group.parent.recurrence_limit ?? 0;
                  const cycleText = limit > 0 ? `${done} / ${limit}` : `${done} / ∞`;
                  return (
                    <Card
                      key={group.parent.id}
                      style={parentCardStyles}
                      title={
                        <Space size={10} wrap>
                          <Typography.Text strong>{getTaskDisplayName(group.parent)}</Typography.Text>
                          <Tag color="green">循环总任务</Tag>
                          <Tag color="green">循环中</Tag>
                          <Tag color="processing">已循环 {cycleText}</Tag>
                        </Space>
                      }
                      extra={renderParentActions(group.parent)}
                    >
                      <Table
                        rowKey="id"
                        loading={loading}
                        dataSource={group.children}
                        columns={childTaskColumns}
                        pagination={false}
                        locale={{ emptyText: '暂无子任务（到点后将自动生成）' }}
                        expandable={{
                          expandedRowRender: (record) => (
                            <div style={{ padding: '8px 24px' }}>
                              <div style={{ marginBottom: 12 }}>
                                <strong>输入参数：</strong>
                                <JsonViewer data={record.input_params ?? {}} />
                              </div>
                              <div style={{ marginBottom: 12 }}>
                                <strong>输出结果：</strong>
                                <JsonViewer data={record.output_result ?? {}} />
                              </div>
                              {record.execution_log && (
                                <div style={{ marginBottom: 12 }}>
                                  <strong>执行日志：</strong>
                                  <JsonViewer data={record.execution_log} />
                                </div>
                              )}
                              {record.error_message && (
                                <div>
                                  <strong>错误信息：</strong>
                                  <pre
                                    style={{
                                      background: '#fff2f0',
                                      padding: 12,
                                      borderRadius: 4,
                                      fontSize: 12,
                                      color: '#cf1322',
                                      margin: 0,
                                      whiteSpace: 'pre-wrap',
                                      wordBreak: 'break-word',
                                      overflowWrap: 'anywhere',
                                    }}
                                  >
                                    {record.error_message}
                                  </pre>
                                </div>
                              )}
                            </div>
                          ),
                        }}
                      />
                    </Card>
                  );
                })}

                {(filteredNonRecurringTasks.length > 0 || fallbackUngroupedTasks.length > 0) && (
                  <Card title="非循环任务" style={{ borderRadius: 8 }}>
                    <Table
                      rowKey="id"
                      loading={loading}
                      dataSource={[...filteredNonRecurringTasks, ...fallbackUngroupedTasks]}
                      columns={childTaskColumns}
                      pagination={false}
                      expandable={{
                        expandedRowRender: (record) => (
                          <div style={{ padding: '8px 24px' }}>
                            <div style={{ marginBottom: 12 }}>
                              <strong>输入参数：</strong>
                              <JsonViewer data={record.input_params ?? {}} />
                            </div>
                            <div style={{ marginBottom: 12 }}>
                              <strong>输出结果：</strong>
                              <JsonViewer data={record.output_result ?? {}} />
                            </div>
                            {record.execution_log && (
                              <div style={{ marginBottom: 12 }}>
                                <strong>执行日志：</strong>
                                <JsonViewer data={record.execution_log} />
                              </div>
                            )}
                            {record.error_message && (
                              <div>
                                <strong>错误信息：</strong>
                                <pre
                                  style={{
                                    background: '#fff2f0',
                                    padding: 12,
                                    borderRadius: 4,
                                    fontSize: 12,
                                    color: '#cf1322',
                                    margin: 0,
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                    overflowWrap: 'anywhere',
                                  }}
                                >
                                  {record.error_message}
                                </pre>
                              </div>
                            )}
                          </div>
                        ),
                      }}
                    />
                  </Card>
                )}
              </Space>
            ),
          },
        ]}
      />
    </div>
  );
}
