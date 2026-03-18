import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Steps,
  Card,
  Button,
  Form,
  Input,
  Select,
  message,
  Typography,
} from 'antd';
import { Link } from 'react-router-dom';
import { updateDataSource } from '@/api/config';
import { updateLLMConfig } from '@/api/config';
import { initComplete } from '@/api/system';
import { ROUTES } from '@/constants/routes';

const { Title, Paragraph } = Typography;

const DS_TYPES = [
  { key: 'email', name: '邮件' },
  { key: 'calendar', name: '日程' },
  { key: 'project_progress', name: '项目进展' },
] as const;

const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'azure', label: 'Azure' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'qwen', label: 'Qwen' },
  { value: 'dify', label: 'Dify' },
  { value: 'custom', label: 'Custom' },
];

const STEPS = [
  { title: '欢迎' },
  { title: '数据源配置' },
  { title: 'LLM 配置' },
  { title: 'Agent 配置' },
  { title: '完成' },
];

export default function SetupPage() {
  const [current, setCurrent] = useState(0);
  const [loading, setLoading] = useState(false);
  const [dsForm] = Form.useForm();
  const [llmForm] = Form.useForm();
  const navigate = useNavigate();

  const handleNext = () => {
    if (current < STEPS.length - 1) {
      setCurrent((c) => c + 1);
    }
  };

  const handlePrev = () => {
    if (current > 0) {
      setCurrent((c) => c - 1);
    }
  };

  const handleSkip = () => {
    if (current < STEPS.length - 1) {
      setCurrent((c) => c + 1);
    } else {
      navigate(ROUTES.DASHBOARD);
    }
  };

  const handleStep1Save = async () => {
    try {
      const values = dsForm.getFieldsValue();
      for (const { key } of DS_TYPES) {
        const v = values[key];
        if (v?.endpoint) {
          await updateDataSource(key, {
            name: v.name ?? key,
            endpoint: v.endpoint,
            api_key: v.api_key ?? '',
          });
        }
      }
      message.success('数据源已保存');
      handleNext();
    } catch {
      message.error('保存失败');
    }
  };

  const handleStep2Save = async () => {
    try {
      const values = llmForm.getFieldsValue();
      await updateLLMConfig('orchestration', {
        provider: values.provider,
        api_endpoint: values.api_endpoint,
        api_key: values.api_key,
        model_name: values.model_name,
      });
      message.success('LLM 配置已保存');
      handleNext();
    } catch {
      message.error('保存失败');
    }
  };

  const handleComplete = async () => {
    setLoading(true);
    try {
      await initComplete();
      message.success('初始化完成！');
      navigate(ROUTES.DASHBOARD);
    } catch {
      message.error('完成失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: 24 }}>
      <Title level={3} style={{ marginBottom: 24 }}>
        引导式初始化
      </Title>

      <Steps current={current} style={{ marginBottom: 32 }} items={STEPS} />

      {current === 0 && (
        <Card>
          <Paragraph>欢迎使用 Audit Coworker！请按照以下步骤完成系统初始化。</Paragraph>
          <Button type="primary" onClick={handleNext}>
            开始
          </Button>
          <span style={{ marginLeft: 12 }}>
            <a onClick={handleSkip}>跳过</a>
          </span>
        </Card>
      )}

      {current === 1 && (
        <Card title="数据源配置">
          <Paragraph type="secondary" style={{ marginBottom: 16 }}>
            配置邮件、日程、项目进展等数据源（可后续在配置中心完善）
          </Paragraph>
          <Form form={dsForm} layout="vertical">
            {DS_TYPES.map(({ key, name }) => (
              <div key={key} style={{ marginBottom: 16, padding: 12, background: '#fafafa', borderRadius: 8 }}>
                <Title level={5}>{name}</Title>
                <Form.Item name={[key, 'name']} label="名称" initialValue={name}>
                  <Input placeholder="数据源名称" />
                </Form.Item>
                <Form.Item name={[key, 'endpoint']} label="Endpoint">
                  <Input placeholder="API 地址" />
                </Form.Item>
                <Form.Item name={[key, 'api_key']} label="API Key">
                  <Input.Password placeholder="API Key" />
                </Form.Item>
              </div>
            ))}
          </Form>
          <Button type="primary" onClick={handleStep1Save}>
            下一步
          </Button>
          <span style={{ marginLeft: 12 }}>
            <a onClick={handleSkip}>跳过</a>
          </span>
        </Card>
      )}

      {current === 2 && (
        <Card title="LLM 配置">
          <Paragraph type="secondary" style={{ marginBottom: 16 }}>
            配置智能编排 LLM（可后续在配置中心完善）
          </Paragraph>
          <Form form={llmForm} layout="vertical">
            <Form.Item name="provider" label="Provider" initialValue="openai">
              <Select options={PROVIDER_OPTIONS} placeholder="选择 Provider" />
            </Form.Item>
            <Form.Item name="api_endpoint" label="Endpoint">
              <Input placeholder="https://api.openai.com/v1" />
            </Form.Item>
            <Form.Item name="api_key" label="API Key">
              <Input.Password placeholder="API Key" />
            </Form.Item>
            <Form.Item name="model_name" label="模型名称">
              <Input placeholder="如 gpt-4, gpt-3.5-turbo" />
            </Form.Item>
          </Form>
          <Button type="primary" onClick={handleStep2Save}>
            下一步
          </Button>
          <span style={{ marginLeft: 12 }}>
            <a onClick={handleSkip}>跳过</a>
          </span>
        </Card>
      )}

      {current === 3 && (
        <Card title="Agent 配置">
          <Paragraph>请在配置中心添加至少一个 Agent。</Paragraph>
          <Paragraph>
            <Link to={ROUTES.CONFIG_AGENTS}>Agent 配置</Link>
          </Paragraph>
          <Button type="primary" onClick={handleNext}>
            下一步
          </Button>
          <span style={{ marginLeft: 12 }}>
            <a onClick={handleSkip}>跳过</a>
          </span>
        </Card>
      )}

      {current === 4 && (
        <Card title="完成">
          <Paragraph>初始化完成！</Paragraph>
          <Button type="primary" loading={loading} onClick={handleComplete}>
            进入系统
          </Button>
          <span style={{ marginLeft: 12 }}>
            <a onClick={handleSkip}>跳过</a>
          </span>
        </Card>
      )}

      {current > 0 && current < 4 && (
        <div style={{ marginTop: 16 }}>
          <Button onClick={handlePrev}>上一步</Button>
        </div>
      )}
    </div>
  );
}
