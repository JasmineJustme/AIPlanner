import { useEffect, useMemo, useState } from 'react';
import {
  Row,
  Col,
  Card,
  Form,
  Input,
  Switch,
  Button,
  Modal,
  Popconfirm,
  Select,
  message,
  Typography,
  Empty,
  Tag,
  Tooltip,
} from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import {
  getDataSources,
  createDataSource,
  updateDataSource,
  toggleDataSource,
  testDataSource,
  syncDataSource,
  deleteDataSource,
  getAgents,
} from '@/api/config';
import type { ParamDefinition } from '@/components/ParamTable';

const { Title, Text } = Typography;

const normalizeParams = (arr?: ParamDefinition[]): ParamDefinition[] => {
  if (!Array.isArray(arr)) return [];
  return arr.map((p) => ({
    name: p.name ?? '',
    type: p.type ?? 'string',
    required: p.required ?? false,
    user_fill_enabled: p.user_fill_enabled ?? false,
    default: p.default ?? '',
    value: p.value ?? '',
    description: p.description ?? '',
  }));
};

interface DataSourceItem {
  id: string;
  type: string;
  name?: string;
  agent_id?: string;
  dify_endpoint?: string;
  dify_api_key?: string;
  input_params?: ParamDefinition[];
  output_params?: ParamDefinition[];
  is_enabled?: boolean;
  last_sync_at?: string;
  last_sync_status?: string;
  last_sync_error?: string;
}

interface AgentItem {
  id: string;
  name: string;
  is_enabled?: boolean;
  dify_endpoint?: string;
  dify_api_key?: string;
  input_params?: ParamDefinition[];
  output_params?: ParamDefinition[];
}

const inferAgentIdForDatasource = (ds: DataSourceItem, agents: AgentItem[]) => {
  if (ds.agent_id) {
    return ds.agent_id;
  }
  const endpoint = ds.dify_endpoint ?? '';
  const apiKey = ds.dify_api_key ?? '';
  const found = agents.find(
    (agent) => (agent.dify_endpoint ?? '') === endpoint && (agent.dify_api_key ?? '') === apiKey
  );
  return found?.id;
};

function DataSourceCard({
  ds,
  agents,
  onUpdate,
  onToggle,
  onTest,
  onSync,
  onDelete,
}: {
  ds: DataSourceItem;
  agents: AgentItem[];
  onUpdate: (dsType: string, selectedAgentId: string, inputValues: Record<string, string>) => Promise<void>;
  onToggle: (dsType: string) => Promise<void>;
  onTest: (dsType: string) => Promise<void>;
  onSync: (dsType: string) => Promise<void>;
  onDelete: (dsType: string) => Promise<void>;
}) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(ds.last_sync_status !== 'success');

  const selectedAgentId = Form.useWatch('agent_id', form) as string | undefined;
  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === selectedAgentId),
    [agents, selectedAgentId]
  );
  const allParams = useMemo(
    () => normalizeParams(selectedAgent?.input_params),
    [selectedAgent]
  );

  useEffect(() => {
    const inferredAgentId = inferAgentIdForDatasource(ds, agents);
    const baseValues: Record<string, unknown> = { agent_id: inferredAgentId };
    const inferredAgent = agents.find((agent) => agent.id === inferredAgentId);
    const paramsToRender = normalizeParams(inferredAgent?.input_params);

    const savedMap = new Map<string, string>();
    for (const item of normalizeParams(ds.input_params)) {
      savedMap.set(item.name, String(item.value ?? ''));
    }

    const prefillValues = paramsToRender.reduce<Record<string, string>>((acc, param) => {
      if (savedMap.has(param.name)) {
        acc[param.name] = savedMap.get(param.name) ?? '';
      } else {
        acc[param.name] = String(param.default ?? '');
      }
      return acc;
    }, {});

    baseValues.input_param_values = prefillValues;
    form.setFieldsValue(baseValues);
  }, [ds, agents, form]);

  useEffect(() => {
    // Default behavior: auto collapse only when latest persisted status is success.
    setExpanded(ds.last_sync_status !== 'success');
  }, [ds.id, ds.last_sync_status]);

  const statusTag = useMemo(() => {
    if (ds.last_sync_status === 'success') {
      return <Tag color="success">测试成功</Tag>;
    }
    if (ds.last_sync_status === 'failed') {
      return (
        <Tooltip title={ds.last_sync_error || '最近一次检查失败'}>
          <Tag color="error">测试失败</Tag>
        </Tooltip>
      );
    }
    return <Tag>未测试</Tag>;
  }, [ds.last_sync_error, ds.last_sync_status]);

  const statusTime = ds.last_sync_at
    ? new Date(ds.last_sync_at).toLocaleString()
    : '暂无记录';

  const handleFinish = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const selected = String(values.agent_id ?? '');
      const inputValues = (values.input_param_values as Record<string, string> | undefined) ?? {};
      await onUpdate(ds.type, selected, inputValues);
      setExpanded(false);
    } finally {
      setLoading(false);
    }
  };

  const options = agents.map((agent) => ({
    value: agent.id,
    label: `${agent.name}${agent.is_enabled === false ? '（已禁用）' : ''}`,
  }));

  return (
    <Card
      title={ds.name ?? ds.type}
      extra={
        <Switch
          checked={ds.is_enabled ?? false}
          onChange={() => onToggle(ds.type)}
        />
      }
    >
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          {statusTag}
          <Text type="secondary" style={{ marginLeft: 8 }}>最近检查: {statusTime}</Text>
        </div>
        <Button type="link" onClick={() => setExpanded((v) => !v)}>
          {expanded ? '收起详情' : '展开详情'}
        </Button>
      </div>
      {expanded ? (
      <Form
        form={form}
        layout="vertical"
        onFinish={handleFinish}
        initialValues={{
          agent_id: inferAgentIdForDatasource(ds, agents),
        }}
      >
        <Form.Item
          name="agent_id"
          label="绑定 Agent"
          rules={[{ required: true, message: '请选择一个已导入的 Agent' }]}
          extra="该数据源将直接复用所选 Agent 的 Endpoint、API Key 和参数定义"
        >
          <Select
            placeholder="请选择已导入 Agent"
            options={options}
          />
        </Form.Item>
        {options.length === 0 ? (
          <Text type="warning">暂无可选 Agent，请先在 Agent 管理中创建</Text>
        ) : null}
        {allParams.length > 0 ? (
          <Card size="small" title="输入参数" style={{ marginBottom: 12 }}>
            {allParams.map((param) => (
              <Form.Item
                key={param.name}
                name={['input_param_values', param.name]}
                label={param.name}
                tooltip={param.description || undefined}
                rules={param.required ? [{ required: true, message: `请填写 ${param.name}` }] : undefined}
              >
                <Input placeholder={String(param.default ?? '')} />
              </Form.Item>
            ))}
          </Card>
        ) : null}
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>
            保存
          </Button>
          <Button style={{ marginLeft: 8 }} onClick={() => onTest(ds.type)}>
            测试
          </Button>
          <Button style={{ marginLeft: 8 }} onClick={() => onSync(ds.type)}>
            手动同步
          </Button>
          <Popconfirm
            title="确定删除该数据源？"
            onConfirm={() => onDelete(ds.type)}
          >
            <Button
              danger
              type="link"
              style={{ marginLeft: 8 }}
              icon={<DeleteOutlined />}
            >
              删除
            </Button>
          </Popconfirm>
        </Form.Item>
      </Form>
      ) : null}
    </Card>
  );
}

export default function ConfigDataSourcesPage() {
  const [dataSources, setDataSources] = useState<DataSourceItem[]>([]);
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createForm] = Form.useForm();
  const [creating, setCreating] = useState(false);

  const loadAgents = async () => {
    try {
      // Backend currently enforces size<=100, so request within allowed range.
      const res = await getAgents({ page: 1, size: 100 });
      const body = (res as { data: unknown }).data;
      const payload = (body as { data?: { items?: AgentItem[] } })?.data ?? body;
      const items = (payload as { items?: AgentItem[] })?.items;
      setAgents(Array.isArray(items) ? items : []);
    } catch {
      setAgents([]);
    }
  };

  const loadDataSources = async () => {
    try {
      const res = await getDataSources();
      const body = (res as { data: unknown }).data;
      const payload = (body as { data?: DataSourceItem[] })?.data ?? body;
      setDataSources(Array.isArray(payload) ? payload : []);
    } catch {
      setDataSources([]);
    }
  };

  useEffect(() => {
    loadDataSources();
    loadAgents();
  }, []);

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      setCreating(true);
      await createDataSource({
        type: values.type,
        name: values.name,
      });
      message.success('数据源创建成功');
      setCreateModalOpen(false);
      createForm.resetFields();
      loadDataSources();
      loadAgents();
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'errorFields' in e) return;
      const err = e as { response?: unknown };
      if (!err?.response) {
        message.error('创建失败');
      }
    } finally {
      setCreating(false);
    }
  };

  const handleUpdate = async (
    dsType: string,
    selectedAgentId: string,
    inputValues: Record<string, string>
  ) => {
    const selectedAgent = agents.find((agent) => agent.id === selectedAgentId);
    if (!selectedAgent) {
      message.error('未找到所选 Agent，请刷新后重试');
      return;
    }

    const mergedInputParams = normalizeParams(selectedAgent.input_params).map((param) => ({
      ...param,
      value: Object.prototype.hasOwnProperty.call(inputValues, param.name)
        ? String(inputValues[param.name] ?? '')
        : String(param.default ?? ''),
    }));

    await updateDataSource(dsType, {
      name: dsType,
      agent_id: selectedAgent.id,
      input_params: mergedInputParams,
    });
    message.success('保存成功');
    loadDataSources();
  };

  const handleToggle = async (dsType: string) => {
    try {
      await toggleDataSource(dsType);
      message.success('状态已更新');
      loadDataSources();
    } catch {
      message.error('更新失败');
    }
  };

  const handleTest = async (dsType: string) => {
    try {
      const res = await testDataSource(dsType);
      const body = (res as { data: { data?: { latency_ms?: number } } }).data;
      const latency = body?.data?.latency_ms;
      message.success(`连接测试成功${latency != null ? `（延迟 ${latency}ms）` : ''}`);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      const detail = err?.response?.data?.detail || err?.message;
      message.error(detail || '连接测试失败');
    }
  };

  const handleSync = async (dsType: string) => {
    try {
      await syncDataSource(dsType);
      message.success('手动同步已触发');
    } catch {
      message.error('同步失败');
    }
  };

  const handleDelete = async (dsType: string) => {
    try {
      await deleteDataSource(dsType);
      message.success('已删除');
      loadDataSources();
    } catch {
      message.error('删除失败');
    }
  };

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <Title level={3} style={{ margin: 0 }}>
          数据源配置
        </Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setCreateModalOpen(true)}
        >
          添加数据源
        </Button>
      </div>

      {dataSources.length === 0 ? (
        <Empty description="暂无数据源，请点击「添加数据源」创建">
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalOpen(true)}
          >
            添加数据源
          </Button>
        </Empty>
      ) : (
        <Row gutter={[16, 16]}>
          {dataSources.map((ds) => (
            <Col xs={24} lg={8} key={ds.id}>
              <DataSourceCard
                ds={ds}
                agents={agents}
                onUpdate={handleUpdate}
                onToggle={handleToggle}
                onTest={handleTest}
                onSync={handleSync}
                onDelete={handleDelete}
              />
            </Col>
          ))}
        </Row>
      )}

      <Modal
        title="添加数据源"
        open={createModalOpen}
        onCancel={() => {
          setCreateModalOpen(false);
          createForm.resetFields();
        }}
        onOk={handleCreate}
        confirmLoading={creating}
        okText="创建"
        cancelText="取消"
      >
        <Form form={createForm} layout="vertical">
          <Form.Item
            name="type"
            label="类型标识"
            rules={[
              { required: true, message: '请输入类型标识' },
              {
                pattern: /^[a-z][a-z0-9_]*$/,
                message: '仅支持小写字母、数字和下划线，需以字母开头',
              },
            ]}
            extra="唯一标识，如 email、erp_data、contract_review"
          >
            <Input placeholder="如 email" />
          </Form.Item>
          <Form.Item
            name="name"
            label="显示名称"
            rules={[{ required: true, message: '请输入显示名称' }]}
          >
            <Input placeholder="如 邮件数据源" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
