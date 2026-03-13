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
} from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { getAgent, createAgent, updateAgent } from '@/api/config';
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
              dify_endpoint: agent.dify_endpoint ?? '',
              dify_api_key: agent.dify_api_key ?? '',
              input_params: normalizeParams(agent.input_params),
              output_params: normalizeParams(agent.output_params),
              timeout_seconds: agent.timeout_seconds ?? 30,
              auto_execute: agent.auto_execute ?? false,
              confirm_before_exec: agent.confirm_before_exec ?? true,
            });
          }
        })
        .catch(() => message.error('加载失败'));
    }
  }, [id, isEdit, form]);

  const onFinish = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const payload = {
        name: values.name,
        description: values.description,
        capability_tags: values.capability_tags,
        dify_endpoint: values.dify_endpoint,
        dify_api_key: values.dify_api_key,
        input_params: values.input_params,
        output_params: values.output_params,
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
          output_params: [],
          timeout_seconds: 30,
          auto_execute: false,
          confirm_before_exec: true,
        }}
      >
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

        <Card title="Dify 连接" style={{ marginBottom: 16 }}>
          <Form.Item
            name="dify_endpoint"
            label="Dify 端点"
            rules={[{ required: true, message: '请输入 Dify 端点' }]}
          >
            <Input placeholder="https://api.dify.ai/v1" />
          </Form.Item>
          <Form.Item
            name="dify_api_key"
            label="API Key"
            rules={[{ required: true, message: '请输入 API Key' }]}
          >
            <Input.Password placeholder="API Key" />
          </Form.Item>
        </Card>

        <Card title="输入参数" style={{ marginBottom: 16 }}>
          <Form.Item name="input_params">
            <ParamTable showRequired showUserFillSwitch />
          </Form.Item>
        </Card>

        <Card title="输出参数" style={{ marginBottom: 16 }}>
          <Form.Item name="output_params">
            <ParamTable showRequired={false} />
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
