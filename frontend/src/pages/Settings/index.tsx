import { useEffect, useState } from 'react';
import {
  Card,
  Form,
  Descriptions,
  Input,
  InputNumber,
  TimePicker,
  Switch,
  Tooltip,
  Button,
  message,
  Typography,
} from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { getSettings, updateSettings } from '@/api/settings';

const { Title } = Typography;

function unwrapValue(v: unknown): unknown {
  if (v && typeof v === 'object' && 'value' in v) {
    return (v as { value: unknown }).value;
  }
  return v;
}

export default function SettingsPage() {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [setupCompleted, setSetupCompleted] = useState<boolean | null>(null);

  const loadSettings = async () => {
    try {
      const res = await getSettings();
      const body = (res as { data: Record<string, unknown> }).data;
      const data = (body as { data?: Record<string, unknown> })?.data ?? body;
      const raw = (data as Record<string, unknown>) ?? {};

      const get = (key: string, def: unknown) => {
        const v = raw[key];
        const u = unwrapValue(v);
        return u !== undefined && u !== null ? u : def;
      };

      form.setFieldsValue({
        max_concurrency: get('max_concurrency', 5),
        execution_window_start: get('execution_window_start', '09:00')
          ? dayjs(get('execution_window_start', '09:00') as string, 'HH:mm')
          : null,
        execution_window_end: get('execution_window_end', '18:00')
          ? dayjs(get('execution_window_end', '18:00') as string, 'HH:mm')
          : null,
        auto_confirm_timeout_minutes: get('auto_confirm_timeout_minutes', 30),
        task_timeout_seconds: get('task_timeout_seconds', 600),
        sync_interval_hours: get('sync_interval_hours', 24),
        sync_require_confirm: get('sync_require_confirm', true),
        auto_smart_discovery_enabled: get('auto_smart_discovery_enabled', false),
        auto_smart_discovery_interval_minutes: get('auto_smart_discovery_interval_minutes', 15),
        data_retention_days: get('data_retention_days', 365),
        dify_endpoint: get('dify_endpoint', ''),
      });

      const initVal = raw['system_initialized'];
      const initObj = typeof initVal === 'object' && initVal && 'initialized' in initVal
        ? (initVal as { initialized?: boolean })
        : null;
      setSetupCompleted(initObj?.initialized ?? false);
    } catch {
      message.error('加载设置失败');
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const onFinish = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const payload: Record<string, unknown> = {
        max_concurrency: values.max_concurrency,
        execution_window_start: values.execution_window_start
          ? dayjs(values.execution_window_start as dayjs.Dayjs).format('HH:mm')
          : null,
        execution_window_end: values.execution_window_end
          ? dayjs(values.execution_window_end as dayjs.Dayjs).format('HH:mm')
          : null,
        auto_confirm_timeout_minutes: values.auto_confirm_timeout_minutes,
        task_timeout_seconds: values.task_timeout_seconds,
        sync_interval_hours: values.sync_interval_hours,
        sync_require_confirm: values.sync_require_confirm,
        auto_smart_discovery_enabled: values.auto_smart_discovery_enabled,
        auto_smart_discovery_interval_minutes: values.auto_smart_discovery_interval_minutes,
        data_retention_days: values.data_retention_days,
        dify_endpoint: values.dify_endpoint,
      };
      await updateSettings(payload);
      message.success('保存成功');
      loadSettings();
    } catch {
      message.error('保存失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Title level={3} style={{ marginBottom: 16 }}>
        系统设置
      </Title>

      <Form form={form} layout="vertical" onFinish={onFinish}>
        <Card title="执行配置" style={{ marginBottom: 16 }}>
          <Form.Item name="max_concurrency" label="最大并发数">
            <InputNumber min={1} max={50} style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="execution_window_start" label="执行时间窗口（开始）">
            <TimePicker format="HH:mm" style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="execution_window_end" label="执行时间窗口（结束）">
            <TimePicker format="HH:mm" style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="auto_confirm_timeout_minutes" label="自动确认超时（分钟）">
            <InputNumber min={1} max={1440} style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="task_timeout_seconds" label="默认任务超时（秒）">
            <InputNumber min={60} max={86400} style={{ width: 120 }} />
          </Form.Item>
        </Card>

        <Card title="同步配置" style={{ marginBottom: 16 }}>
          <Form.Item name="sync_interval_hours" label="数据源同步间隔（小时）">
            <InputNumber min={1} max={168} style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="sync_require_confirm" label="同步后需要确认" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            name="auto_smart_discovery_enabled"
            label={(
              <span>
                自动智能发掘待办
                <Tooltip title="开启后系统将每个时间间隔后根据工作职责对数据源进行一次智能发掘待办。">
                  <QuestionCircleOutlined style={{ marginLeft: 6, color: '#999' }} />
                </Tooltip>
              </span>
            )}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, curr) => prev.auto_smart_discovery_enabled !== curr.auto_smart_discovery_enabled}>
            {({ getFieldValue }) => {
              if (!getFieldValue('auto_smart_discovery_enabled')) {
                return null;
              }
              return (
                <Form.Item name="auto_smart_discovery_interval_minutes" label="智能发掘时间间隔（分钟）">
                  <InputNumber min={1} max={60} style={{ width: 120 }} />
                </Form.Item>
              );
            }}
          </Form.Item>
        </Card>

        <Card title="系统" style={{ marginBottom: 16 }}>
          <Form.Item name="dify_endpoint" label="Dify 端点">
            <Input placeholder="https://api.dify.ai/v1" />
          </Form.Item>
          <Form.Item name="data_retention_days" label="数据保留天数">
            <InputNumber min={1} max={3650} style={{ width: 120 }} />
          </Form.Item>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="初始化状态">
              {setupCompleted === null
                ? '加载中...'
                : setupCompleted
                  ? '已完成'
                  : '未完成'}
            </Descriptions.Item>
          </Descriptions>
        </Card>

        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>
            保存
          </Button>
        </Form.Item>
      </Form>
    </div>
  );
}
