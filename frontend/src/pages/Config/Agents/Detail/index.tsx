import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Form,
  Card,
  Input,
  InputNumber,
  Switch,
  Button,
  Select,
  message,
  Typography,
  Space,
} from 'antd';
import { ArrowLeftOutlined, ImportOutlined } from '@ant-design/icons';
import { getAgent, createAgent, updateAgent } from '@/api/config';
import { fetchDifyInfo } from '@/api/settings';
import type { Agent } from '@/types/agent';
import ParamTable, { type ParamDefinition } from '@/components/ParamTable';

const { Title } = Typography;

const normalizeParams = (arr?: { name?: string; type?: string; required?: boolean; user_fill_enabled?: boolean; default?: string | null; value?: string | null; description?: string | null }[]): ParamDefinition[] => {
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

export default function ConfigAgentsDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id && id !== 'new');
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    if (isEdit && id) {
      getAgent(id)
        .then((res) => {
          const body = (res as { data: unknown }).data;
          const agent = ((body as { data?: Agent })?.data ?? body) as Agent;
          if (agent) {
            form.setFieldsValue({
              name: agent.name,
              description: agent.description ?? '',
              capability_tags: agent.capability_tags ?? [],
              dify_api_key: agent.dify_api_key ?? '',
              input_params: normalizeParams(agent.input_params),

              timeout_seconds: agent.timeout_seconds ?? 30,
              auto_execute: agent.auto_execute ?? false,
              confirm_before_exec: agent.confirm_before_exec ?? true,
            });
          }
        })
        .catch(() => message.error('加载失败'));
    }
  }, [id, isEdit, form]);

  const handleImportFromDify = async () => {
    const apiKey = form.getFieldValue('dify_api_key');
    if (!apiKey) {
      message.warning('请先填写 API Key');
      return;
    }
    setImporting(true);
    try {
      const res = await fetchDifyInfo({ dify_api_key: apiKey });
      const body = (res as { data: unknown }).data;
      const meta = ((body as { data?: Record<string, unknown> })?.data ?? body) as {
        name?: string;
        description?: string;
        tags?: string[];
        input_params?: { name: string; type: string; required: boolean; default?: string; description?: string }[];
      };

      const updates: Record<string, unknown> = {};
      if (meta.name) updates.name = meta.name;
      if (meta.description) updates.description = meta.description;
      if (Array.isArray(meta.tags) && meta.tags.length > 0) updates.capability_tags = meta.tags;
      if (Array.isArray(meta.input_params) && meta.input_params.length > 0) {
        updates.input_params = normalizeParams(meta.input_params);
      }

      if (Object.keys(updates).length === 0) {
        message.info('未获取到可导入的信息');
      } else {
        form.setFieldsValue(updates);
        message.success('导入成功，请确认各项配置');
      }
    } catch {
      message.error('导入失败，请检查系统 Dify 端点和 API Key 是否正确');
    } finally {
      setImporting(false);
    }
  };

  const onFinish = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const payload = {
        name: values.name,
        description: values.description,
        capability_tags: values.capability_tags,
        dify_api_key: values.dify_api_key,
        input_params: values.input_params,
        timeout_seconds: values.timeout_seconds,
        auto_execute: values.auto_execute,
        confirm_before_exec: values.confirm_before_exec,
      };
      if (isEdit && id) {
        await updateAgent(id, payload);
        message.success('更新成功');
      } else {
        await createAgent(payload);
        message.success('创建成功');
      }
      navigate('/config/agents');
    } catch {
      message.error(isEdit ? '更新失败' : '创建失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/config/agents')}
        >
          返回
        </Button>
        <Title level={3} style={{ margin: 0 }}>
          {isEdit ? '编辑 Agent' : '新建 Agent'}
        </Title>
      </div>

      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
        initialValues={{
          capability_tags: [],
          input_params: [],
          timeout_seconds: 30,
          auto_execute: false,
          confirm_before_exec: true,
        }}
      >
        <Card
          title="Dify 连接"
          style={{ marginBottom: 16 }}
          extra={
            <Button
              type="primary"
              icon={<ImportOutlined />}
              loading={importing}
              onClick={handleImportFromDify}
            >
              一键导入
            </Button>
          }
        >
          <Form.Item
            name="dify_api_key"
            label="API Key"
            rules={[{ required: true, message: '请输入 API Key' }]}
          >
            <Input.Password placeholder="API Key" />
          </Form.Item>
          <Space style={{ color: '#999', fontSize: 12 }}>
            系统 Dify 端点已统一配置在系统设置页，当前仅需填写 API Key 即可导入名称、描述、标签及输入参数
          </Space>
        </Card>

        <Card title="基础信息" style={{ marginBottom: 16 }}>
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="Agent 名称" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="描述" />
          </Form.Item>
          <Form.Item name="capability_tags" label="能力标签">
            <Select mode="tags" placeholder="输入后回车添加标签" />
          </Form.Item>
        </Card>

        <Card title="输入参数" style={{ marginBottom: 16 }}>
          <Form.Item name="input_params">
            <ParamTable showRequired showUserFillSwitch />
          </Form.Item>
        </Card>

        <Card title="执行配置" style={{ marginBottom: 16 }}>
          <Form.Item name="timeout_seconds" label="超时时间(秒)">
            <InputNumber min={1} max={300} style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="auto_execute" label="自动执行" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="confirm_before_exec" label="执行前确认" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Card>

        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>
            保存
          </Button>
          <Button style={{ marginLeft: 8 }} onClick={() => navigate('/config/agents')}>
            取消
          </Button>
        </Form.Item>
      </Form>
    </div>
  );
}
