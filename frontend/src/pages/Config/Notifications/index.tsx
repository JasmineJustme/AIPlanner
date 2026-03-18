import { useEffect, useMemo, useState } from 'react';
import {
  Row,
  Col,
  Card,
  Form,
  Input,
  Switch,
  Button,
  Select,
  Modal,
  Popconfirm,
  message,
  Typography,
  Tag,
} from 'antd';
import {
  createNotificationChannel,
  deleteNotificationChannel,
  getNotificationChannels,
  updateNotificationChannel,
  toggleNotificationChannel,
  testNotificationChannel,
  getAgents,
} from '@/api/config';
import type { ParamDefinition } from '@/components/ParamTable';

const { Title, Text } = Typography;

const CHANNEL_TYPE_PATTERN = /^[a-z][a-z0-9_]{1,19}$/;

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

interface ChannelConfig {
  id: string;
  channel_type: string;
  name?: string;
  agent_id?: string;
  dify_endpoint?: string;
  dify_api_key?: string;
  input_params?: ParamDefinition[];
  is_enabled?: boolean;
  message_field?: string;
}

interface AgentItem {
  id: string;
  name: string;
  is_enabled?: boolean;
  dify_endpoint?: string;
  dify_api_key?: string;
  input_params?: ParamDefinition[];
}

const inferAgentIdForChannel = (channel: ChannelConfig, agents: AgentItem[]) => {
  if (channel.agent_id) {
    return channel.agent_id;
  }
  const endpoint = channel.dify_endpoint ?? '';
  const apiKey = channel.dify_api_key ?? '';
  const found = agents.find(
    (agent) => (agent.dify_endpoint ?? '') === endpoint
      && (agent.dify_api_key ?? '') === apiKey
  );
  return found?.id;
};

function NotificationCard({
  channelKey,
  label,
  config,
  agents,
  onUpdate,
  onToggle,
  onTest,
  onDelete,
}: {
  channelKey: string;
  label: string;
  config: ChannelConfig;
  agents: AgentItem[];
  onUpdate: (
    channelKey: string,
    selectedAgentId: string,
    inputValues: Record<string, string>,
    messageField?: string
  ) => Promise<void>;
  onToggle: (channelKey: string) => Promise<void>;
  onTest: (channelKey: string) => Promise<void>;
  onDelete: (channelKey: string) => Promise<void>;
}) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  const selectedAgentId = Form.useWatch('agent_id', form) as string | undefined;
  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === selectedAgentId),
    [agents, selectedAgentId]
  );
  const allParams = useMemo(() => normalizeParams(selectedAgent?.input_params), [selectedAgent]);
  const selectedMessageField = Form.useWatch('message_field', form) as string | undefined;
  const userEditableParams = useMemo(
    () => allParams.filter((param) => param.name !== selectedMessageField),
    [allParams, selectedMessageField]
  );

  useEffect(() => {
    const inferredAgentId = inferAgentIdForChannel(config, agents);
    const selected = agents.find((agent) => agent.id === inferredAgentId);
    const selectedParams = normalizeParams(selected?.input_params);

    const saved = new Map<string, string>();
    for (const param of normalizeParams(config.input_params)) {
      saved.set(param.name, String(param.value ?? ''));
    }

    const prefill = selectedParams.reduce<Record<string, string>>((acc, param) => {
      acc[param.name] = saved.has(param.name)
        ? (saved.get(param.name) ?? '')
        : String(param.default ?? '');
      return acc;
    }, {});

    form.setFieldsValue({
      agent_id: inferredAgentId,
      input_param_values: prefill,
      message_field: config.message_field,
    });
  }, [agents, config, form, label]);

  const handleFinish = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const selected = String(values.agent_id ?? '');
      const inputValues = (values.input_param_values as Record<string, string> | undefined) ?? {};
      const messageField = String(values.message_field ?? '').trim() || undefined;
      await onUpdate(channelKey, selected, inputValues, messageField);
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
      title={config.name ?? label}
      extra={<Switch checked={config.is_enabled ?? false} onChange={() => onToggle(channelKey)} />}
    >
      <div style={{ marginBottom: 12 }}>
        <Tag color={config.is_enabled ? 'success' : 'default'}>{config.is_enabled ? '已启用' : '已停用'}</Tag>
        <Text type="secondary" style={{ marginLeft: 8 }}>渠道类型: {channelKey}</Text>
      </div>
      <Form form={form} layout="vertical" onFinish={handleFinish}>
        <Form.Item
          name="agent_id"
          label="绑定 Agent"
          rules={[{ required: true, message: '请选择一个已导入的 Agent' }]}
          extra="提醒渠道将复用所选 Agent 的 Endpoint、API Key 和参数定义"
        >
          <Select placeholder="请选择已导入 Agent" options={options} />
        </Form.Item>
        {allParams.length > 0 ? (
          <Form.Item
            name="message_field"
            label="消息字段"
            extra="选择后，提醒内容将自动写入该字段，且该字段不会作为手动输入参数展示"
          >
            <Select
              allowClear
              placeholder="请选择接收提醒内容的字段"
              options={allParams.map((param) => ({ value: param.name, label: param.name }))}
            />
          </Form.Item>
        ) : null}
        {userEditableParams.length > 0 ? (
          <Card size="small" title="输入参数" style={{ marginBottom: 12 }}>
            {userEditableParams.map((param) => (
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
        ) : (
          <Text type="secondary">
            {allParams.length > 0 ? '当前可手动配置参数为空（可能都由系统自动填充）' : '所选 Agent 没有可配置输入参数'}
          </Text>
        )}
        <Form.Item style={{ marginTop: 12 }}>
          <Button type="primary" htmlType="submit" loading={loading}>保存</Button>
          <Button style={{ marginLeft: 8 }} onClick={() => onTest(channelKey)}>测试</Button>
          <Popconfirm
            title="删除提醒渠道"
            description="删除后不可恢复，是否继续？"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={() => onDelete(channelKey)}
          >
            <Button danger style={{ marginLeft: 8 }}>删除</Button>
          </Popconfirm>
        </Form.Item>
      </Form>
    </Card>
  );
}

export default function ConfigNotificationsPage() {
  const [channels, setChannels] = useState<ChannelConfig[]>([]);
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [createVisible, setCreateVisible] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [createForm] = Form.useForm();

  const loadAgents = async () => {
    try {
      const res = await getAgents({ page: 1, size: 100 });
      const body = (res as { data: unknown }).data;
      const payload = (body as { data?: { items?: AgentItem[] } })?.data ?? body;
      const items = (payload as { items?: AgentItem[] })?.items;
      setAgents(Array.isArray(items) ? items : []);
    } catch {
      setAgents([]);
    }
  };

  const loadChannels = async () => {
    try {
      const res = await getNotificationChannels();
      const body = (res as { data: unknown }).data;
      const payload = (body as { data?: ChannelConfig[] })?.data ?? body;
      const rows = Array.isArray(payload) ? payload : [];
      setChannels(rows);
    } catch {
      setChannels([]);
    }
  };

  useEffect(() => {
    loadChannels();
    loadAgents();
  }, []);

  const handleUpdate = async (
    channelKey: string,
    selectedAgentId: string,
    inputValues: Record<string, string>,
    messageField?: string
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

    await updateNotificationChannel(channelKey, {
      agent_id: selectedAgent.id,
      input_params: mergedInputParams,
      message_field: messageField ?? null,
    });
    message.success('保存成功');
    loadChannels();
  };

  const handleToggle = async (channelKey: string) => {
    try {
      await toggleNotificationChannel(channelKey);
      message.success('状态已更新');
      loadChannels();
    } catch {
      message.error('更新失败');
    }
  };

  const handleTest = async (channelKey: string) => {
    try {
      await testNotificationChannel(channelKey);
      message.success('测试成功');
    } catch {
      message.error('测试失败');
    }
  };

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      setCreateLoading(true);
      await createNotificationChannel({
        channel_type: String(values.channel_type ?? '').trim(),
      });
      message.success('提醒渠道已创建');
      setCreateVisible(false);
      createForm.resetFields();
      await loadChannels();
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) {
        return;
      }
      message.error('创建失败');
    } finally {
      setCreateLoading(false);
    }
  };

  const handleDelete = async (channelKey: string) => {
    try {
      await deleteNotificationChannel(channelKey);
      message.success('提醒渠道已删除');
      await loadChannels();
    } catch {
      message.error('删除失败');
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          提醒渠道配置
        </Title>
        <Button type="primary" onClick={() => setCreateVisible(true)}>新增提醒渠道</Button>
      </div>
      <Row gutter={[16, 16]}>
        {channels.map((channel) => (
          <Col xs={24} md={12} key={channel.id}>
            <NotificationCard
              channelKey={channel.channel_type}
              label={channel.name ?? channel.channel_type}
              config={channel}
              agents={agents}
              onUpdate={handleUpdate}
              onToggle={handleToggle}
              onTest={handleTest}
              onDelete={handleDelete}
            />
          </Col>
        ))}
      </Row>
      <Modal
        title="新增提醒渠道"
        open={createVisible}
        onCancel={() => {
          setCreateVisible(false);
          createForm.resetFields();
        }}
        onOk={handleCreate}
        confirmLoading={createLoading}
        destroyOnClose
      >
        <Form
          form={createForm}
          layout="vertical"
          initialValues={{
            channel_type: '',
          }}
        >
          <Form.Item
            name="channel_type"
            label="渠道标识"
            extra="仅支持小写字母、数字和下划线，长度 2-20，例如 sms_workflow"
            rules={[
              { required: true, message: '请输入渠道标识' },
              {
                validator: (_, value: string) => {
                  const normalized = String(value ?? '').trim();
                  if (!normalized || CHANNEL_TYPE_PATTERN.test(normalized)) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('格式不正确，请使用小写字母、数字和下划线，且以字母开头'));
                },
              },
            ]}
          >
            <Input placeholder="sms_workflow" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
