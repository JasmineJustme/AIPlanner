import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  message,
  Pagination,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import { PlusOutlined, RedoOutlined, UploadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { ColumnsType } from 'antd/es/table';
import {
  completeTodo,
  createTodo,
  deleteTodo,
  getTodos,
  rerunTodo,
  updateTodo,
} from '@/api/todos';
import { submitOrchestration } from '@/api/orchestration';
import type { Todo } from '@/types/todo';
import PriorityTag from '@/components/PriorityTag';
import SourceTag from '@/components/SourceTag';
import { formatDate } from '@/utils/format';
import { parseExcelFile } from '@/utils/excel';
import { ROUTES } from '@/constants/routes';
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

export default function TodosPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingTodo, setEditingTodo] = useState<Todo | null>(null);
  const [saving, setSaving] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  const [submitting, setSubmitting] = useState<string | null>(null);
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
  }>({});
  const [form] = Form.useForm();

  const loadTodos = async () => {
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
      setData((d) => ({ ...d, items: [] }));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTodos();
  }, [data.page, data.size, filters.status, filters.priority, filters.source]);

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
    });
    setDrawerOpen(true);
  };

  const openEditDrawer = (record: Todo) => {
    setEditingTodo(record);
    form.resetFields();
    form.setFieldsValue({
      title: record.title,
      description: record.description,
      priority: record.priority,
      execution_mode: record.execution_mode || TodoExecutionMode.System,
      due_date: record.due_date ? dayjs(record.due_date) : null,
      tags: record.tags ?? [],
      project: record.project,
    });
    setDrawerOpen(true);
  };

  const handleSubmitTodo = async (values: Record<string, unknown>) => {
    setSaving(true);
    try {
      const payload = {
        title: values.title,
        description: values.description,
        priority: values.priority ?? 'medium',
        execution_mode: values.execution_mode ?? TodoExecutionMode.System,
        due_date: values.due_date ? (values.due_date as { toISOString?: () => string })?.toISOString?.() : undefined,
        tags: Array.isArray(values.tags) ? values.tags : [],
        project: values.project as string | undefined,
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

  const handleBatchImport = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.xlsx,.xls';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      setImportLoading(true);
      try {
        const rows = await parseExcelFile(file);
        const toCreate = rows
          .filter((r: Record<string, unknown>) => r['标题'] || r['title'])
          .map((r: Record<string, unknown>) => ({
            title: String(r['标题'] ?? r['title'] ?? ''),
            description: r['描述'] || r['description'] ? String(r['描述'] ?? r['description']) : undefined,
            priority: (r['优先级'] ?? r['priority'] ?? 'medium') as string,
            execution_mode: TodoExecutionMode.System,
            project: r['项目'] || r['project'] ? String(r['项目'] ?? r['project']) : undefined,
            tags: typeof r['标签'] === 'string' ? (r['标签'] as string).split(/[,，]/).map((s) => s.trim()).filter(Boolean) : [],
          }));
        let imported = 0;
        for (const item of toCreate) {
          try {
            await createTodo(item);
            imported++;
          } catch {
            // skip failed
          }
        }
        message.success(`成功导入 ${imported} 条`);
        loadTodos();
      } catch {
        message.error('导入失败');
      } finally {
        setImportLoading(false);
      }
    };
    input.click();
  };

  const handleConfirmTask = async (record: Todo) => {
    setSubmitting(record.id);
    try {
      const res = await submitOrchestration({ todo_ids: [record.id] });
      const body = (res as { data: { data?: { orch_id?: string; status?: string; error?: string } } }).data;
      const result = (body?.data ?? body) as { orch_id?: string; status?: string; error?: string } | undefined;
      if (result?.error) {
        message.error(`编排提交失败: ${result.error}`);
      } else {
        message.success('任务已提交编排');
        navigate(ROUTES.ORCHESTRATION);
      }
    } catch (e: unknown) {
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

    return (
      <div style={{ margin: 0, padding: 12, backgroundColor: '#fafafa', borderRadius: 4 }}>
        <Descriptions title="任务详情" column={1} size="small" bordered>
          <Descriptions.Item label="任务描述">{record.description || '无'}</Descriptions.Item>
          <Descriptions.Item label="执行方式">
            <Tag color={modeConfig.color}>{modeConfig.text}</Tag>
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
        </Descriptions>
      </div>
    );
  };

  const columns: ColumnsType<Todo> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
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
      title: '截止时间',
      dataIndex: 'due_date',
      key: 'due_date',
      width: 140,
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
          return (
            <Space>
              <Button
                type="primary"
                size="small"
                onClick={() => handleCompleteTask(record)}
                loading={submitting === record.id}
                disabled={!pendingLike}
              >
                完成
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

  if (loading && data.items.length === 0) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Text type="secondary">加载待办列表...</Text>
      </div>
    );
  }

  if (data.total === 0) {
    return (
      <div>
        <Title level={3}>待办任务</Title>
        <Text type="secondary">暂无待办记录，请先创建任务。</Text>
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
          <Button icon={<UploadOutlined />} onClick={handleBatchImport} loading={importLoading}>
            批量导入
          </Button>
          <Space>
            <span>列表</span>
            <Button disabled>看板</Button>
          </Space>
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

      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card
          title="用户执行模块"
          extra={<Tag color={TODO_EXECUTION_MODE_MAP[TodoExecutionMode.User].color}>{userTodos.length}</Tag>}
        >
          <Alert
            type="info"
            showIcon
            message="用户执行任务只做展示与提醒；待确认时可完成、编辑和删除，已完成后可删除或重新执行。"
            style={{ marginBottom: 16 }}
          />
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={userTodos}
            pagination={false}
            locale={{ emptyText: '暂无用户执行任务' }}
            expandable={{ expandedRowRender: renderExpandedRow }}
          />
        </Card>

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
            locale={{ emptyText: '暂无系统执行任务' }}
            expandable={{ expandedRowRender: renderExpandedRow }}
          />
        </Card>
      </Space>

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
          initialValues={{ priority: 'medium', execution_mode: TodoExecutionMode.System }}
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
          <Form.Item name="project" label="项目">
            <Input placeholder="项目名称" />
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
