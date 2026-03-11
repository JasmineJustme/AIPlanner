import { useEffect, useState, useRef } from 'react';
import {
  Tabs,
  Card,
  Form,
  Select,
  Input,
  InputNumber,
  Slider,
  Button,
  message,
  Typography,
  Switch,
  Space,
} from 'antd';
import {
  getLLMConfig,
  updateLLMConfig,
  testLLMConfig,
  getLLMUsage,
} from '@/api/config';

const { Title, Text } = Typography;

const PURPOSES = [
  { key: 'todo_analysis', label: '待办梳理 LLM' },
  { key: 'orchestration', label: '智能编排 LLM' },
  { key: 'scheduling', label: '智能调度 LLM' },
] as const;

const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'azure', label: 'Azure' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'qwen', label: 'Qwen' },
  { value: 'dify', label: 'Dify' },
  { value: 'custom', label: 'Custom' },
];

function LLMTab({
  purpose,
  label,
}: {
  purpose: string;
  label: string;
}) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [hasConfig, setHasConfig] = useState(false);
  // Add state for collapsibility and switches
  const [configExpanded, setConfigExpanded] = useState(true);
  const [useTemperature, setUseTemperature] = useState(true);
  const [useTopP, setUseTopP] = useState(true);

  const [usage, setUsage] = useState<Record<string, unknown> | null>(null);
  // Add ref to track notification state
  const notifiedRef = useRef(false);

  useEffect(() => {
      // Reset notification state when purpose changes
      notifiedRef.current = false;
  }, [purpose]);

  useEffect(() => {
    getLLMConfig(purpose)
      .then((res) => {
        const body = (res as { data: unknown }).data;
        const raw = (body as { data?: Record<string, unknown> })?.data ?? body;
        const config = raw as Record<string, unknown>;
        if (config && typeof config === 'object') {
          const isConfigured = !!(config.api_key && config.api_endpoint);
          setHasConfig(isConfigured);

          setConfigExpanded(!isConfigured);

          if (!isConfigured && !notifiedRef.current) {
              message.info('模型尚未配置，请填写相应内容');
              notifiedRef.current = true;
          }
          setUseTemperature((config.temperature_enabled as boolean | undefined) ?? true);
          setUseTopP((config.top_p_enabled as boolean | undefined) ?? true);
          form.setFieldsValue({
            provider: config.provider ?? 'openai',
            model_name: config.model_name ?? '',
            api_endpoint: config.api_endpoint ?? '',
            api_key: config.api_key ?? '',
            temperature: config.temperature ?? 0.7,
            top_p: config.top_p ?? 0.9,
            max_tokens: config.max_tokens ?? 4096,
            prompt_template: config.prompt_template ?? '',
          });
        }
      })
      .catch(() => message.error('加载失败'));
  }, [purpose, form]);

  const loadUsage = () => {
    getLLMUsage(purpose)
      .then((res) => {
        const body = (res as { data: unknown }).data;
        const u = (body as { data?: Record<string, unknown> })?.data ?? body;
        setUsage(u as Record<string, unknown>);
      })
      .catch(() => setUsage(null));
  };

  const onFinish = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      await updateLLMConfig(purpose, {
        provider: values.provider,
        model_name: values.model_name,
        api_endpoint: values.api_endpoint,
        api_key: values.api_key,
        temperature: values.temperature,
        temperature_enabled: useTemperature,
        top_p: values.top_p,
        top_p_enabled: useTopP,
        max_tokens: values.max_tokens,
        prompt_template: values.prompt_template,
      });
      message.success('保存成功');
      setHasConfig(true);
      setConfigExpanded(false); // Collapse on successful save
    } catch {
      message.error('保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    try {
      // Validate form fields first
      const values = await form.validateFields();

      // If validation passes, we still need to save first or use current form values for testing if API supports it
      // Assuming testLLMConfig uses the saved config on backend, so we might want to save first?
      // Or if testLLMConfig just pings based on purpose, it relies on saved data.
      // Let's assume we need to save first to ensure test runs against latest input.

      // However, usually "Test" button sends current form values to a test endpoint
      // OR orchestrates a save-then-test flow.
      // Based on current API usage: testLLMConfig(purpose) likely tests the *saved* config.

      // Let's try to update first, then test, to ensure WYSIWYG
      await updateLLMConfig(purpose, {
        provider: values.provider,
        model_name: values.model_name,
        api_endpoint: values.api_endpoint,
        api_key: values.api_key,
        temperature: values.temperature,
        temperature_enabled: useTemperature,
        top_p: values.top_p,
        top_p_enabled: useTopP,
        max_tokens: values.max_tokens,
        prompt_template: values.prompt_template,
      });

      await testLLMConfig(purpose);
      message.success('测试成功');
    } catch (e) {
      // Check if it's a validation error
      if (e && typeof e === 'object' && 'errorFields' in e) {
        message.error('请填写必填项');
        return;
      }

      // Check if it's an API error
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      const detail = err?.response?.data?.detail || err?.message || '测试失败';
      message.error(`测试失败: ${detail}`);
    }
  };

  return (
    <div>
      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
        initialValues={{
          provider: 'openai',
          model_name: '',
          api_endpoint: '',
          api_key: '',
          temperature: 0.7,
          top_p: 0.9,
          max_tokens: 4096,
          prompt_template: '',
        }}
      >
        <Card
          title={`${label} 配置`}
          style={{ marginBottom: 16 }}
          extra={
            <Space>
              <Button onClick={handleTest}>测试</Button>
              <Button type="link" onClick={() => setConfigExpanded(!configExpanded)}>
                {configExpanded ? '收起' : '展开'}
              </Button>
            </Space>
          }
          bodyStyle={{ display: configExpanded ? 'block' : 'none' }}
        >
            <Form.Item name="provider" label="Provider">
              <Select options={PROVIDER_OPTIONS} placeholder="选择 Provider" />
            </Form.Item>
            <Form.Item name="model_name" label="模型名称">
              <Input placeholder="如 gpt-4, gpt-3.5-turbo" />
            </Form.Item>
            <Form.Item
              name="api_endpoint"
              label="API Endpoint"
              rules={[{ required: true, message: '请输入 API Endpoint' }]}
            >
              <Input placeholder="https://api.openai.com/v1" />
            </Form.Item>
            <Form.Item
              name="api_key"
              label="API Key"
              rules={[{ required: true, message: '请输入 API Key' }]}
            >
              <Input.Password placeholder="API Key" />
            </Form.Item>
            <Form.Item
              label={
                <Space>
                  <span>Temperature</span>
                  <Switch
                    size="small"
                    checked={useTemperature}
                    onChange={setUseTemperature}
                  />
                </Space>
              }
              extra={useTemperature ? "0-2, 步长 0.1" : undefined}
            >
              {useTemperature ? (
                 <Form.Item name="temperature" noStyle>
                    <Slider min={0} max={2} step={0.1} />
                 </Form.Item>
              ) : null}
            </Form.Item>
            <Form.Item
              label={
                <Space>
                  <span>Top P</span>
                  <Switch
                    size="small"
                    checked={useTopP}
                    onChange={setUseTopP}
                  />
                </Space>
              }
              extra={useTopP ? "0-1" : undefined}
            >
              {useTopP ? (
                <Form.Item name="top_p" noStyle>
                  <Slider min={0} max={1} step={0.05} />
                </Form.Item>
              ) : null}
            </Form.Item>
            <Form.Item name="max_tokens" label="Max Tokens">
              <InputNumber min={1} max={128000} style={{ width: 120 }} />
            </Form.Item>
            <Form.Item name="prompt_template" label="Prompt 模板">
              <Input.TextArea rows={8} placeholder="输入 prompt 模板" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading}>
                保存
              </Button>
            </Form.Item>
        </Card>
      </Form>

      {hasConfig && (
        <Card title="使用统计" style={{ marginTop: 16 }}>
          <Button size="small" onClick={loadUsage} style={{ marginBottom: 8 }}>
            刷新统计
          </Button>
          {usage ? (
            <pre style={{ margin: 0, fontSize: 12 }}>
              {JSON.stringify(usage, null, 2)}
            </pre>
          ) : (
            <Text type="secondary">暂无使用数据</Text>
          )}
        </Card>
      )}
    </div>
  );
}

export default function ConfigLLMPage() {
  return (
    <div>
      <Title level={3} style={{ marginBottom: 16 }}>
        大模型配置
      </Title>
      <Tabs
        items={PURPOSES.map(({ key, label }) => ({
          key,
          label,
          children: <LLMTab purpose={key} label={label} />,
        }))}
      />
    </div>
  );
}
