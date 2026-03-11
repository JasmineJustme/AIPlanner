import { useEffect, useState, useRef, useCallback } from 'react';
import {
  Typography,
  Tabs,
  Table,
  Button,
  Space,
  Select,
  message,
  Popconfirm,
} from 'antd';
import {
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  CloseOutlined,
  ForwardOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { gantt } from 'dhtmlx-gantt';
import 'dhtmlx-gantt/codebase/dhtmlxgantt.css';
import {
  getScheduleTasks,
  getGanttData,
  getSchedulePlans,
  retryTask,
  skipTask,
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

const { Title } = Typography;

/* Gantt bar colors by status */
const ganttStatusStyles = `
  .gantt_completed .gantt_task_progress { background: #52c41a !important; }
  .gantt_failed .gantt_task_progress,
  .gantt_failed .gantt_task_content { background: #ff4d4f !important; }
  .gantt_running .gantt_task_progress,
  .gantt_running .gantt_task_content { background: #fa8c16 !important; }
`;

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

function GanttView({ tasks }: { tasks: Array<{ id: string; name: string; start: string; end: string; status: string }> }) {
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

    const ganttTasks = tasks.map((t) => {
      const start = t.start ? new Date(t.start) : new Date();
      const end = t.end ? new Date(t.end) : new Date(start.getTime() + 3600000);
      const duration = Math.max(1, Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)));
      return {
        id: t.id,
        text: t.name,
        start_date: start,
        duration,
        progress: t.status === 'completed' ? 100 : 0,
        status: t.status,
      };
    });
    gantt.clearAll();
    gantt.parse({ data: ganttTasks, links: [] });
  }, [tasks]);

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
  const [tasks, setTasks] = useState<ScheduleTask[]>([]);
  const [plans, setPlans] = useState<SchedulePlan[]>([]);
  const [ganttTasks, setGanttTasks] = useState<Array<{ id: string; name: string; start: string; end: string; status: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [planFilter, setPlanFilter] = useState<string>('');

  const getTaskDisplayName = useCallback((task: Pick<ScheduleTask, 'task_title' | 'plan_name' | 'agent_name' | 'agent_id' | 'wagent_id' | 'id'>) => {
    return task.task_title
      || task.plan_name
      || task.agent_name
      || (task.agent_id ? `Agent ${task.agent_id.slice(0, 8)}` : task.wagent_id ? `W-Agent ${task.wagent_id.slice(0, 8)}` : `Task ${task.id.slice(0, 8)}`);
  }, []);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const params: { status?: string; plan_id?: string } = {};
      if (statusFilter) params.status = statusFilter;
      if (planFilter) params.plan_id = planFilter;
      const res = await getScheduleTasks(params);
      const body = res.data as APIResponse<ScheduleTask[]>;
      const data = body?.data ?? (res.data as unknown);
      setTasks(Array.isArray(data) ? data : []);
    } catch {
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, planFilter]);

  const loadGantt = useCallback(async () => {
    try {
      const params = planFilter ? { plan_id: planFilter } : undefined;
      const res = await getGanttData(params);
      const body = res.data as APIResponse<{ tasks: Array<{ id: string; name: string; start: string; end: string; status: string }> }>;
      const data = body?.data ?? (res.data as unknown);
      const taskList = (data as { tasks?: Array<{ id: string; name: string; start: string; end: string; status: string }> })?.tasks ?? [];
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

  const handleSkipTask = async (taskId: string) => {
    try {
      await skipTask(taskId);
      message.success('已跳过');
      loadTasks();
      loadGantt();
    } catch {
      message.error('操作失败');
    }
  };

  const handleCancelTask = async (taskId: string) => {
    try {
      await cancelTask(taskId);
      message.success('已取消，任务已返回待确认列表');
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

  const columns = [
    {
      title: '任务名称',
      key: 'name',
      render: (_: unknown, r: ScheduleTask) => getTaskDisplayName(r),
    },
    {
      title: 'Agent/W-Agent',
      dataIndex: 'agent_name',
      key: 'agent_name',
      render: (v: string, r: ScheduleTask) => v || (r.wagent_id ? 'W-Agent' : '-'),
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
      width: 220,
      render: (_: unknown, r: ScheduleTask) => {
        const isTerminalFailed = r.status === 'failed' && (r.retry_count ?? 0) >= (r.max_retries ?? 3);
        return (
          <Space size="small">
            {r.status === 'failed' && (
              <Button type="link" size="small" icon={<ReloadOutlined />} onClick={() => handleRetryTask(r.id)}>
                重试
              </Button>
            )}
            {isTerminalFailed && (
              <Popconfirm title="确定取消？" onConfirm={() => handleCancelTask(r.id)}>
                <Button type="link" size="small" danger icon={<CloseOutlined />}>
                  取消
                </Button>
              </Popconfirm>
            )}
            {(r.status === 'pending' || r.status === 'confirming') && (
              <>
                <Button type="link" size="small" icon={<ForwardOutlined />} onClick={() => handleSkipTask(r.id)}>
                  跳过
                </Button>
                <Popconfirm title="确定取消？" onConfirm={() => handleCancelTask(r.id)}>
                  <Button type="link" size="small" danger icon={<CloseOutlined />}>
                    取消
                  </Button>
                </Popconfirm>
              </>
            )}
            {r.status === 'running' && (
              <Button type="link" size="small" icon={<PauseCircleOutlined />} onClick={() => handlePauseTask(r.id)}>
                暂停
              </Button>
            )}
            {r.status === 'paused' && (
              <Button type="link" size="small" icon={<PlayCircleOutlined />} onClick={() => handleResumeTask(r.id)}>
                恢复
              </Button>
            )}
            {r.status !== 'completed' && r.status !== 'failed' && (
              <Button type="link" size="small" icon={<ClockCircleOutlined />} onClick={() => handleDelayTask(r.id)}>
                延后
              </Button>
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
                <GanttView tasks={ganttTasks} />
              </div>
            ),
          },
          {
            key: 'list',
            label: '列表',
            children: (
              <Table
                rowKey="id"
                loading={loading}
                dataSource={tasks}
                columns={columns}
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
            ),
          },
        ]}
      />
    </div>
  );
}
