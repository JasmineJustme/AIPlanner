import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  message,
  Pagination,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import { AppstoreOutlined, PlusOutlined, QuestionCircleOutlined, RedoOutlined, UnorderedListOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { ColumnsType } from 'antd/es/table';
import { useLocation } from 'react-router-dom';
import {
  cancelUserTodo,
  confirmUserTodo,
  completeTodo,
  createTodo,
  deleteTodo,
  getTodos,
  rerunTodo,
  smartDiscoverTodos,
  updateTodo,
} from '@/api/todos';
import { getResponsibilities } from '@/api/config';
import { submitOrchestration } from '@/api/orchestration';
import type { Todo } from '@/types/todo';
import PriorityTag from '@/components/PriorityTag';
import SourceTag from '@/components/SourceTag';
import { formatDate } from '@/utils/format';
import {
  PRIORITY_MAP,
  SOURCE_MAP,
  TODO_EXECUTION_MODE_MAP,
  TODO_STATUS_MAP,
  TodoExecutionMode,
  TodoStatus,
} from '@/constants/status';

const { Title, Text } = Typography;

const STATUS_OPTIONS = Object.entries(TODO_STATUS_MAP).map(([k, v]) => ({
  value: k,
  label: v.text,
}));
const PRIORITY_OPTIONS = Object.entries(PRIORITY_MAP).map(([k, v]) => ({
  value: k,
  label: v.text,
}));
const SOURCE_OPTIONS = Object.entries(SOURCE_MAP).map(([k, v]) => ({
  value: k,
  label: v.text,
}));
const EXECUTION_MODE_OPTIONS = Object.entries(TODO_EXECUTION_MODE_MAP).map(([k, v]) => ({
  value: k,
  label: v.text,
}));

function getStatusFromSearch(search: string): string | undefined {
  const status = new URLSearchParams(search).get('status') || undefined;
  if (!status) return undefined;
  return Object.prototype.hasOwnProperty.call(TODO_STATUS_MAP, status) ? status : undefined;
}

export default function TodosPage() {
  const location = useLocation();
  const [loading, setLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingTodo, setEditingTodo] = useState<Todo | null>(null);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [viewMode, setViewMode] = useState<'list' | 'board'>('list');
  const requestSeqRef = useRef(0);
  const [data, setData] = useState<{ items: Todo[]; total: number; page: number; size: number; pages: number }>({
    items: [],
    total: 0,
    page: 1,
    size: 20,
    pages: 0,
  });
  const [filters, setFilters] = useState<{
    status?: string;
    priority?: string;
    source?: string;
    dateRange?: [string, string] | null;
  }>({
    status: getStatusFromSearch(location.search),
  });
  const [form] = Form.useForm();
  const [responsibilityOptions, setResponsibilityOptions] = useState<Array<{ id: string; title: string }>>([]);
  const [responsibilityIdToTitle, setResponsibilityIdToTitle] = useState<Record<string, string>>({});
  const [responsibilityTitleToIds, setResponsibilityTitleToIds] = useState<Record<string, string[]>>({});

  useEffect(() => {
    let cancelled = false;
    const loadResponsibilities = async () => {
      try {
        const res = await getResponsibilities();
        // getResponsibilities() 返回结构在前端侧可能未完全类型化，这里用安全解包避免 TS 属性错误。
        const body = (res as any)?.data as unknown;
        const payload = typeof body === 'object' && body !== null && 'data' in (body as object) ? (body as any).data : body;
        const roots = Array.isArray(payload) ? payload : [];

        const flat: Array<{ id: string; title: string }> = [];
        const idToTitle: Record<string, string> = {};
        const titleToIds: Record<string, string[]> = {};

        const walk = (nodes: any[]) => {
          nodes.forEach((n) => {
            const id = n?.id;
            const title = n?.title;
            if (typeof id === 'string' && typeof title === 'string') {
              flat.push({ id, title });
              idToTitle[id] = title;
              titleToIds[title] = titleToIds[title] ?? [];
              titleToIds[title].push(id);
            }
            if (Array.isArray(n?.children) && n.children.length > 0) {
              walk(n.children);
            }
          });
        };

        walk(roots);

        if (!cancelled) {
          setResponsibilityOptions(flat);
          setResponsibilityIdToTitle(idToTitle);
          setResponsibilityTitleToIds(titleToIds);
        }
      } catch {
        if (!cancelled) {
          setResponsibilityOptions([]);
          setResponsibilityIdToTitle({});
          setResponsibilityTitleToIds({});
        }
      }
    };

    loadResponsibilities();
    return () => {
      cancelled = true;
    };
  }, []);

  // 如果历史数据只有 responsibility_titles 而没有责任 ids，
  // 等职责配置加载完成后补全 responsibility_ids，避免编辑时误清空。
  useEffect(() => {
    if (!drawerOpen || !editingTodo) return;

    const recordResponsibilityIds = Array.isArray(editingTodo.responsibility_ids) ? editingTodo.responsibility_ids : [];
    const recordResponsibilityTitles = Array.isArray(editingTodo.responsibility_titles) ? editingTodo.responsibility_titles : [];
    if (recordResponsibilityIds.length > 0) return;
    if (recordResponsibilityTitles.length === 0) return;

    const mappedIds = recordResponsibilityTitles
      .map((t) => responsibilityTitleToIds[t]?.[0])
      .filter((id): id is string => typeof id === 'string');

    if (mappedIds.length > 0) {
      form.setFieldsValue({ responsibility_ids: mappedIds });
    }
  }, [drawerOpen, editingTodo, responsibilityTitleToIds, form]);

  const patchTodo = (todoId: string, updater: (todo: Todo) => Todo) => {
    setData((current) => ({
      ...current,
      items: current.items.map((item) => (item.id === todoId ? updater(item) : item)),
    }));
  };

  const loadTodos = useCallback(async () => {
    const requestSeq = ++requestSeqRef.current;
    setLoading(true);
    try {
      const res = await getTodos({
        page: data.page,
        size: data.size,
        status: filters.status || undefined,
        priority: filters.priority || undefined,
        source: filters.source || undefined,
      });
      const body = (res as { data: { data?: typeof data } }).data;
      const payload = body?.data ?? body;
      if (requestSeq !== requestSeqRef.current) {
        return;
      }
      if (payload && typeof payload === 'object' && 'items' in payload) {
        setData({
          items: payload.items ?? [],
          total: payload.total ?? 0,
          page: payload.page ?? 1,
          size: payload.size ?? 20,
          pages: payload.pages ?? 0,
        });
      }
    } catch {
      if (requestSeq === requestSeqRef.current) {
        setData((d) => ({ ...d, items: [] }));
      }
    } finally {
      if (requestSeq === requestSeqRef.current) {
        setLoading(false);
      }
    }
  }, [data.page, data.size, filters.status, filters.priority, filters.source]);

  useEffect(() => {
    loadTodos();
  }, [loadTodos]);

  useEffect(() => {
    const statusFromQuery = getStatusFromSearch(location.search);
    if (!statusFromQuery) {
      return;
    }
    setFilters((prev) => {
      if (prev.status === statusFromQuery) {
        return prev;
      }
      return { ...prev, status: statusFromQuery };
    });
    setData((prev) => ({ ...prev, page: 1 }));
  }, [location.search]);

  const closeDrawer = () => {
    setDrawerOpen(false);
    setEditingTodo(null);
    form.resetFields();
  };

  const openCreateDrawer = () => {
    setEditingTodo(null);
    form.resetFields();
    form.setFieldsValue({
      priority: 'medium',
      tags: [],
      execution_mode: TodoExecutionMode.System,
      is_recurring: false,
      recurrence_count: 0,
      recurrence_cron: undefined,
      responsibility_ids: [],
    });
    setDrawerOpen(true);
  };

  const openEditDrawer = (record: Todo) => {
    setEditingTodo(record);
    form.resetFields();
    const recordResponsibilityIds = Array.isArray(record.responsibility_ids) ? record.responsibility_ids : [];
    const recordResponsibilityTitles = Array.isArray(record.responsibility_titles) ? record.responsibility_titles : [];
    const selectedByTitles =
      recordResponsibilityIds.length > 0
        ? recordResponsibilityIds
        : recordResponsibilityTitles
            .map((t) => responsibilityTitleToIds[t]?.[0])
            .filter((id): id is string => typeof id === 'string');
    form.setFieldsValue({
      title: record.title,
      description: record.description,
      priority: record.priority,
      execution_mode: record.execution_mode || TodoExecutionMode.System,
      due_date: record.due_date ? dayjs(record.due_date) : null,
      tags: record.tags ?? [],
      responsibility_ids: selectedByTitles,
      is_recurring: !!record.is_recurring,
      recurrence_cron: record.recurrence_cron,
      recurrence_count: record.recurrence_count ?? 0,
    });
    setDrawerOpen(true);
  };

  const handleSubmitTodo = async (values: Record<string, unknown>) => {
    setSaving(true);
    try {
      const isRecurring = Boolean(values.is_recurring);
      const selectedResponsibilityIds = Array.isArray(values.responsibility_ids)
        ? (values.responsibility_ids as unknown[]).filter((v): v is string => typeof v === 'string')
        : [];
      const computedResponsibilityTitles = selectedResponsibilityIds
        .map((id) => responsibilityIdToTitle[id])
        .filter((t): t is string => typeof t === 'string');
      const fallbackResponsibilityTitles =
        editingTodo && Array.isArray(editingTodo.responsibility_titles)
          ? editingTodo.responsibility_titles.filter((t): t is string => typeof t === 'string')
          : [];
      const payload = {
        title: values.title,
        description: values.description,
        priority: values.priority ?? 'medium',
        execution_mode: values.execution_mode ?? TodoExecutionMode.System,
        due_date: values.due_date ? (values.due_date as { toISOString?: () => string })?.toISOString?.() : undefined,
        tags: Array.isArray(values.tags) ? values.tags : [],
        responsibility_ids: selectedResponsibilityIds,
        responsibility_titles: computedResponsibilityTitles.length > 0 ? computedResponsibilityTitles : fallbackResponsibilityTitles,
        is_recurring: isRecurring,
        recurrence_cron: isRecurring ? (values.recurrence_cron as string | undefined) : undefined,
        recurrence_count: isRecurring ? Number(values.recurrence_count ?? 0) : 0,
      };
      if (editingTodo) {
        await updateTodo(editingTodo.id, payload);
        message.success('修改成功');
      } else {
        await createTodo(payload);
        message.success('创建成功');
      }
      closeDrawer();
      loadTodos();
    } catch {
      message.error(editingTodo ? '修改失败' : '创建失败');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteTodo(id);
      message.success('已删除');
      loadTodos();
    } catch {
      message.error('删除失败');
    }
  };

  const handleConfirmTask = async (record: Todo) => {
    const previousRecord = { ...record };
    patchTodo(record.id, (item) => ({
      ...item,
      status: TodoStatus.Orchestrating,
    }));
    setSubmitting(record.id);
    try {
      const res = await submitOrchestration({ todo_ids: [record.id] });
      const body = (res as { data: { data?: { orch_id?: string; status?: string; error?: string } } }).data;
      const result = (body?.data ?? body) as { orch_id?: string; status?: string; error?: string } | undefined;

      patchTodo(record.id, (item) => ({
        ...item,
        status: TodoStatus.Orchestrating,
        orchestration_id: result?.orch_id ?? item.orchestration_id,
      }));

      if (result?.error) {
        message.warning(`任务已提交编排，但分析失败: ${result.error}`);
      } else {
        message.success('任务已提交编排');
      }
    } catch (e: unknown) {
      patchTodo(record.id, () => previousRecord);
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      const detail = err?.response?.data?.detail || err?.message || '提交失败';
      message.error(`编排提交失败: ${detail}`);
    } finally {
      setSubmitting(null);
    }
  };

  const handleCompleteTask = async (record: Todo) => {
    setSubmitting(record.id);
    try {
      await completeTodo(record.id);
      message.success('任务已完成');
      loadTodos();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      const detail = err?.response?.data?.detail || err?.message || '完成失败';
      message.error(detail);
    } finally {
      setSubmitting(null);
    }
  };

  const handleUserConfirmTask = async (record: Todo) => {
    setSubmitting(record.id);
    try {
      await confirmUserTodo(record.id);
      message.success('任务已确认，状态更新为待处理');
      loadTodos();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      const detail = err?.response?.data?.detail || err?.message || '确认失败';
      message.error(detail);
    } finally {
      setSubmitting(null);
    }
  };

  const handleUserCancelTask = async (record: Todo) => {
    setSubmitting(record.id);
    try {
      await cancelUserTodo(record.id);
      message.success('任务已取消，状态更新为待确认');
      loadTodos();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      const detail = err?.response?.data?.detail || err?.message || '取消失败';
      message.error(detail);
    } finally {
      setSubmitting(null);
    }
  };

  const handleRerunTask = async (record: Todo) => {
    setSubmitting(record.id);
    try {
      await rerunTodo(record.id);
      message.success('已生成新的待办任务');
      loadTodos();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      const detail = err?.response?.data?.detail || err?.message || '重新执行失败';
      message.error(detail);
    } finally {
      setSubmitting(null);
    }
  };

  const handleSmartDiscover = async () => {
    setDiscovering(true);
    try {
      const res = await smartDiscoverTodos();
      const body = (res as { data: { data?: { created_count?: number; dedup_count?: number } } }).data;
      const payload = (body?.data ?? body) as { created_count?: number; dedup_count?: number };
      const createdCount = Number(payload.created_count ?? 0);
      const dedupCount = Number(payload.dedup_count ?? 0);
      message.success(`智能发掘完成：新增 ${createdCount} 条，直接去重 ${dedupCount} 条`);
      await loadTodos();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      message.error(err?.response?.data?.detail || err?.message || '智能发掘失败');
    } finally {
      setDiscovering(false);
    }
  };

  const getExecutionMode = (record: Todo) => record.execution_mode || TodoExecutionMode.System;
  const isUserExecution = (record: Todo) => getExecutionMode(record) === TodoExecutionMode.User;
  const isPendingLike = (record: Todo) =>
    record.status === TodoStatus.Pending || record.status === TodoStatus.PendingConfirm;
  const isCompleted = (record: Todo) => record.status === TodoStatus.Completed;
  const isSystemProcessing = (record: Todo) =>
    record.status === TodoStatus.Orchestrating || record.status === TodoStatus.Scheduling;

  const renderDeleteAction = (record: Todo, disabled = false) => {
    if (disabled) {
      return (
        <Button type="link" danger size="small" disabled>
          删除
        </Button>
      );
    }

    return (
      <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.id)}>
        <Button type="link" danger size="small">
          删除
        </Button>
      </Popconfirm>
    );
  };

  const renderExpandedRow = (record: Todo) => {
    const executionMode = getExecutionMode(record);
    const modeConfig = TODO_EXECUTION_MODE_MAP[executionMode] || TODO_EXECUTION_MODE_MAP[TodoExecutionMode.System];
    const responsibilities = Array.isArray(record.responsibility_titles) ? record.responsibility_titles : [];

    return (
      <div style={{ margin: 0, padding: 12, backgroundColor: '#fafafa', borderRadius: 4 }}>
        <Descriptions title="任务详情" column={1} size="small" bordered>
          <Descriptions.Item label="任务描述">{record.description || '无'}</Descriptions.Item>
          <Descriptions.Item label="循环设置">
            {record.is_recurring
              ? `开启（cron: ${record.recurrence_cron || '-'}，已执行 ${record.recurrence_count ?? 0} 次）`
              : '未开启'}
          </Descriptions.Item>
          <Descriptions.Item label="执行方式">
            <Tag color={modeConfig.color}>{modeConfig.text}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="工作职责">
            {responsibilities.length > 0 ? responsibilities.join('、') : '无'}
          </Descriptions.Item>
          <Descriptions.Item label={executionMode === TodoExecutionMode.User ? '执行提示' : '编排详情'}>
            {executionMode === TodoExecutionMode.User ? (
              '该任务由用户手动执行，完成后点击“完成”即可将状态更新为已完成。'
            ) : record.orchestration_id ? (
              <Space direction="vertical">
                <span>编排ID: {record.orchestration_id}</span>
              </Space>
            ) : (
              '未编排'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="调度详情">
            {executionMode === TodoExecutionMode.User
              ? '用户手动执行，无系统调度。'
              : record.status === TodoStatus.Scheduling
                ? '调度执行中'
                : record.status === TodoStatus.Orchestrating
                  ? '正在编排分析中'
                  : '无'}
          </Descriptions.Item>
          <Descriptions.Item label="添加时间">{formatDate(record.created_at)}</Descriptions.Item>
          <Descriptions.Item label="完成时间">{formatDate(record.completed_at)}</Descriptions.Item>
        </Descriptions>
      </div>
    );
  };

  const columns: ColumnsType<Todo> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: 200,
      ellipsis: true,
      render: (text: string) => <span title={text}>{text}</span>,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 90,
      render: (p: string) => <PriorityTag priority={p} />,
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 90,
      render: (s: string) => <SourceTag source={s} />,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (s: string) => {
        const cfg = TODO_STATUS_MAP[s] || { color: 'default', text: s };
        return <Tag color={cfg.color}>{cfg.text}</Tag>;
      },
    },
    {
      title: '循环',
      key: 'is_recurring',
      width: 120,
      render: (_, record) =>
        record.is_recurring ? <Tag color="processing">循环中</Tag> : <Tag>单次</Tag>,
    },
    {
      title: '截止时间',
      dataIndex: 'due_date',
      key: 'due_date',
      width: 140,
      render: (d: string) => formatDate(d),
    },
    {
      title: '添加时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (d: string) => formatDate(d),
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 120,
      render: (tags: string[]) =>
        Array.isArray(tags) && tags.length > 0 ? tags.slice(0, 3).join(', ') : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 260,
      fixed: 'right',
      render: (_, record) => {
        const isUserTodo = isUserExecution(record);
        const pendingLike = isPendingLike(record);
        const completed = isCompleted(record);
        const systemProcessing = isSystemProcessing(record);

        if (completed) {
          return (
            <Space>
              <Button
                type="primary"
                size="small"
                icon={<RedoOutlined />}
                onClick={() => handleRerunTask(record)}
                loading={submitting === record.id}
              >
                重新执行
              </Button>
              {renderDeleteAction(record)}
            </Space>
          );
        }

        if (isUserTodo) {
          if (record.status === TodoStatus.PendingConfirm) {
            return (
              <Space>
                <Button
                  type="primary"
                  size="small"
                  onClick={() => handleUserConfirmTask(record)}
                  loading={submitting === record.id}
                >
                  确认
                </Button>
                <Button
                  type="link"
                  size="small"
                  onClick={() => openEditDrawer(record)}
                >
                  编辑
                </Button>
                {renderDeleteAction(record)}
              </Space>
            );
          }

          if (record.status === TodoStatus.Pending) {
            return (
              <Space>
                <Button
                  type="primary"
                  size="small"
                  onClick={() => handleCompleteTask(record)}
                  loading={submitting === record.id}
                >
                  完成
                </Button>
                <Button
                  size="small"
                  onClick={() => handleUserCancelTask(record)}
                  loading={submitting === record.id}
                >
                  取消
                </Button>
              </Space>
            );
          }

          return (
            <Space>
              <Button
                type="primary"
                size="small"
                onClick={() => handleCompleteTask(record)}
                loading={submitting === record.id}
                disabled
              >
                完成
              </Button>
              <Button size="small" disabled>
                取消
              </Button>
            </Space>
          );
        }

        if (systemProcessing) {
          return (
            <Space>
              <Button type="primary" size="small" disabled>
                确认
              </Button>
              <Button type="link" size="small" disabled>
                编辑
              </Button>
              {renderDeleteAction(record, true)}
            </Space>
          );
        }

        return (
          <Space>
            <Button
              type="primary"
              size="small"
              onClick={() => handleConfirmTask(record)}
              loading={submitting === record.id}
              disabled={!pendingLike}
            >
              确认
            </Button>
            <Button
              type="link"
              size="small"
              onClick={() => openEditDrawer(record)}
              disabled={!pendingLike}
            >
              编辑
            </Button>
            {renderDeleteAction(record, !pendingLike)}
          </Space>
        );
      },
    },
  ];

  const userTodos = data.items.filter((item) => getExecutionMode(item) === TodoExecutionMode.User);
  const systemTodos = data.items.filter((item) => getExecutionMode(item) !== TodoExecutionMode.User);
  const showOnlyUserModule = filters.status === TodoStatus.Pending;
  const showOnlySystemModule =
    filters.status === TodoStatus.Orchestrating || filters.status === TodoStatus.Scheduling;
  const showUserModule = !showOnlySystemModule;
  const showSystemModule = !showOnlyUserModule;

  if (loading && data.items.length === 0) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Text type="secondary">加载待办列表...</Text>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          待办任务
        </Title>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateDrawer}>
            新建待办
          </Button>
          <Button onClick={handleSmartDiscover} loading={discovering}>
            智能发掘待办
          </Button>
          <Segmented
            value={viewMode}
            onChange={(v) => setViewMode(v as 'list' | 'board')}
            options={[
              { value: 'list', icon: <UnorderedListOutlined />, label: '列表' },
              { value: 'board', icon: <AppstoreOutlined />, label: '看板' },
            ]}
          />
        </Space>
      </div>

      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          placeholder="状态"
          allowClear
          style={{ width: 120 }}
          value={filters.status}
          onChange={(v) => setFilters((f) => ({ ...f, status: v }))}
          options={STATUS_OPTIONS}
        />
        <Select
          placeholder="优先级"
          allowClear
          style={{ width: 120 }}
          value={filters.priority}
          onChange={(v) => setFilters((f) => ({ ...f, priority: v }))}
          options={PRIORITY_OPTIONS}
        />
        <Select
          placeholder="来源"
          allowClear
          style={{ width: 120 }}
          value={filters.source}
          onChange={(v) => setFilters((f) => ({ ...f, source: v }))}
          options={SOURCE_OPTIONS}
        />
        <DatePicker.RangePicker
          placeholder={['开始日期', '结束日期']}
          onChange={(dates) =>
            setFilters((f) => ({
              ...f,
              dateRange: dates
                ? [dates[0]?.toISOString() ?? '', dates[1]?.toISOString() ?? '']
                : null,
            }))
          }
        />
      </Space>

      {data.total === 0 ? (
        <Card>
          <div style={{ padding: '16px 0' }}>
            <Alert
              type="info"
              showIcon
              message="暂无待办记录，可通过新建或智能发掘生成任务。"
              style={{ marginBottom: 16 }}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateDrawer}>
              立即新建待办
            </Button>
          </div>
        </Card>
      ) : viewMode === 'board' ? (
        <Card title="看板视图（预览）">
          <Text type="secondary">V1 当前以列表视图为主，看板视图即将上线。</Text>
        </Card>
      ) : (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          {showUserModule ? (
            <Card
              title="用户执行模块"
              extra={<Tag color={TODO_EXECUTION_MODE_MAP[TodoExecutionMode.User].color}>{userTodos.length}</Tag>}
            >
              <Alert
                type="info"
                showIcon
                message="用户执行任务：待确认时可确认、编辑和删除；确认后进入待处理，可完成或取消（取消后回到待确认）；已完成后可删除或重新执行。"
                style={{ marginBottom: 16 }}
              />
              <Table
                rowKey="id"
                loading={loading}
                columns={columns}
                dataSource={userTodos}
                pagination={false}
                scroll={{ x: 1300 }}
                locale={{ emptyText: '暂无用户执行任务' }}
                expandable={{ expandedRowRender: renderExpandedRow }}
              />
            </Card>
          ) : null}

          {showSystemModule ? (
            <Card
              title="系统执行模块"
              extra={<Tag color={TODO_EXECUTION_MODE_MAP[TodoExecutionMode.System].color}>{systemTodos.length}</Tag>}
            >
              <Alert
                type="warning"
                showIcon
                message="系统执行任务待确认时可确认、编辑和删除；编排中或调度中不可操作；已完成后可删除或重新执行。"
                style={{ marginBottom: 16 }}
              />
              <Table
                rowKey="id"
                loading={loading}
                columns={columns}
                dataSource={systemTodos}
                pagination={false}
                scroll={{ x: 1300 }}
                locale={{ emptyText: '暂无系统执行任务' }}
                expandable={{ expandedRowRender: renderExpandedRow }}
              />
            </Card>
          ) : null}
        </Space>
      )}

      <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <Pagination
          current={data.page}
          pageSize={data.size}
          total={data.total}
          showSizeChanger
          showTotal={(total) => `共 ${total} 条`}
          onChange={(page, size) => setData((d) => ({ ...d, page, size: size ?? d.size }))}
        />
      </div>

      <Drawer
        title={editingTodo ? '编辑待办' : '新建待办'}
        open={drawerOpen}
        onClose={closeDrawer}
        width={480}
        footer={null}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmitTodo}
          initialValues={{
            priority: 'medium',
            execution_mode: TodoExecutionMode.System,
            is_recurring: false,
            recurrence_count: 0,
          }}
        >
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input placeholder="请输入标题" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="请输入描述" />
          </Form.Item>
          <Form.Item name="execution_mode" label="执行模块" rules={[{ required: true, message: '请选择执行模块' }]}>
            <Select options={EXECUTION_MODE_OPTIONS} />
          </Form.Item>
          <Form.Item name="priority" label="优先级">
            <Select options={PRIORITY_OPTIONS} />
          </Form.Item>
          <Form.Item name="due_date" label="截止时间">
            <DatePicker style={{ width: '100%' }} showTime />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="输入后回车添加" />
          </Form.Item>
          <Form.Item name="responsibility_ids" label="工作职责">
            <Select
              mode="multiple"
              allowClear
              placeholder="选择工作职责"
              style={{ width: '100%' }}
              options={responsibilityOptions.map((r) => ({ value: r.id, label: r.title }))}
            />
          </Form.Item>
          <Form.Item name="is_recurring" valuePropName="checked">
            <Checkbox>循环执行</Checkbox>
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, curr) => prev.is_recurring !== curr.is_recurring}>
            {({ getFieldValue }) => {
              if (!getFieldValue('is_recurring')) return null;
              return (
                <>
                  <Form.Item
                    name="recurrence_cron"
                    label={
                      <Space size={6}>
                        <span>循环表达式 (cron)</span>
                        <Tooltip
                          title={
                            <div>
                              <div>格式：分 时 日 月 周</div>
                              <div>例如：`0 9 * * 1-5` 表示工作日 09:00</div>
                              <div>`0 15 * * 5` 表示每周五 15:00</div>
                              <div>`30 8 1 * *` 表示每月 1 日 08:30</div>
                            </div>
                          }
                        >
                          <QuestionCircleOutlined style={{ color: '#999' }} />
                        </Tooltip>
                      </Space>
                    }
                    rules={[{ required: true, message: '请输入 cron 表达式' }]}
                  >
                    <Input placeholder="例如: 0 9 * * 1-5" />
                  </Form.Item>
                  <Form.Item name="recurrence_count" label="已执行次数">
                    <Input type="number" min={0} />
                  </Form.Item>
                </>
              );
            }}
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={saving}>
                {editingTodo ? '保存修改' : '创建'}
              </Button>
              <Button onClick={closeDrawer}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
