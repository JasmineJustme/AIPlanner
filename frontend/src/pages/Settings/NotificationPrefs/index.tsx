import { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Switch,
  Form,
  InputNumber,
  Select,
  Button,
  message,
  Typography,
  Space,
  TimePicker,
} from 'antd';
import dayjs from 'dayjs';
import type { ColumnsType } from 'antd/es/table';
import {
  getNotificationPrefs,
  updateNotificationPref,
  getNotificationGlobal,
  updateNotificationGlobal,
} from '@/api/settings';

const { Title } = Typography;

const MESSAGE_TYPES = [
  { key: 'review_new', label: '新待审' },
  { key: 'orchestration_confirm', label: '编排确认' },
  { key: 'task_confirm', label: '任务确认' },
  { key: 'task_completed', label: '任务完成' },
  { key: 'task_failed', label: '任务失败' },
  { key: 'deadline_reminder', label: '到期提醒' },
  { key: 'system', label: '系统通知' },
];

const MERGE_STRATEGY_OPTIONS = [
  { value: 'none', label: '不合并' },
  { value: 'by_type', label: '按类型合并' },
  { value: 'by_time', label: '按时间窗口合并' },
];

interface NotificationPrefRow {
  message_type: string;
  in_app_enabled: boolean;
  email_enabled: boolean;
  wechat_enabled: boolean;
}

interface GlobalPref {
  dnd_start: string | null;
  dnd_end: string | null;
  merge_strategy: string;
  merge_window_minutes: number;
  deadline_advance_minutes: number;
}

export default function SettingsNotificationPrefsPage() {
  const [prefs, setPrefs] = useState<Record<string, NotificationPrefRow>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [globalForm] = Form.useForm();

  const loadPrefs = async () => {
    setLoading(true);
    try {
      const [prefsRes, globalRes] = await Promise.all([
        getNotificationPrefs(),
        getNotificationGlobal(),
      ]);
      const prefsData = (prefsRes as { data: { data?: NotificationPrefRow[] } }).data?.data ?? [];
      const globalData = ((globalRes as { data: { data?: Partial<GlobalPref> } }).data?.data ?? {}) as Partial<GlobalPref>;

      const prefsMap: Record<string, NotificationPrefRow> = {};
      MESSAGE_TYPES.forEach(({ key }) => {
        const p = (prefsData as NotificationPrefRow[]).find((x) => x.message_type === key);
        prefsMap[key] = p ?? {
          message_type: key,
          in_app_enabled: true,
          email_enabled: false,
          wechat_enabled: false,
        };
      });
      setPrefs(prefsMap);

      globalForm.setFieldsValue({
        dnd_start: globalData.dnd_start ? dayjs(globalData.dnd_start, 'HH:mm') : undefined,
        dnd_end: globalData.dnd_end ? dayjs(globalData.dnd_end, 'HH:mm') : undefined,
        merge_strategy: globalData.merge_strategy ?? 'none',
        merge_window_minutes: globalData.merge_window_minutes ?? 5,
        deadline_advance_minutes: globalData.deadline_advance_minutes ?? 60,
      });
    } catch {
      message.error('加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPrefs();
  }, []);

  const handlePrefChange = async (
    messageType: string,
    field: keyof NotificationPrefRow,
    value: boolean
  ) => {
    const next = { ...prefs[messageType], [field]: value };
    setPrefs((p) => ({ ...p, [messageType]: next }));
    try {
      await updateNotificationPref({
        message_type: messageType,
        in_app_enabled: next.in_app_enabled,
        email_enabled: next.email_enabled,
        wechat_enabled: next.wechat_enabled,
      });
      message.success('已更新');
    } catch {
      setPrefs((p) => ({ ...p, [messageType]: prefs[messageType] }));
      message.error('更新失败');
    }
  };

  const handleBatchSave = async () => {
    setSaving(true);
    try {
      await Promise.all(
        MESSAGE_TYPES.map(({ key }) =>
          updateNotificationPref({
            message_type: key,
            in_app_enabled: prefs[key]?.in_app_enabled ?? true,
            email_enabled: prefs[key]?.email_enabled ?? false,
            wechat_enabled: prefs[key]?.wechat_enabled ?? false,
          })
        )
      );
      const values = await globalForm.validateFields();
      const dndStart = values.dnd_start?.format?.('HH:mm') ?? null;
      const dndEnd = values.dnd_end?.format?.('HH:mm') ?? null;
      await updateNotificationGlobal({
        dnd_start: dndStart,
        dnd_end: dndEnd,
        merge_strategy: values.merge_strategy ?? 'none',
        merge_window_minutes: values.merge_window_minutes ?? 5,
        deadline_advance_minutes: values.deadline_advance_minutes ?? 60,
      });
      message.success('全部保存成功');
    } catch {
      message.error('保存失败');
    } finally {
      setSaving(false);
    }
  };

  const columns: ColumnsType<NotificationPrefRow & { label: string }> = [
    {
      title: '消息类型',
      dataIndex: 'label',
      key: 'label',
      width: 140,
    },
    {
      title: '站内通知',
      dataIndex: 'in_app_enabled',
      key: 'in_app_enabled',
      width: 120,
      render: (_, record) => (
        <Switch
          checked={record.in_app_enabled}
          onChange={(v) => handlePrefChange(record.message_type, 'in_app_enabled', v)}
        />
      ),
    },
    {
      title: '邮件推送',
      dataIndex: 'email_enabled',
      key: 'email_enabled',
      width: 120,
      render: (_, record) => (
        <Switch
          checked={record.email_enabled}
          onChange={(v) => handlePrefChange(record.message_type, 'email_enabled', v)}
        />
      ),
    },
    {
      title: '企微推送',
      dataIndex: 'wechat_enabled',
      key: 'wechat_enabled',
      width: 120,
      render: (_, record) => (
        <Switch
          checked={record.wechat_enabled}
          onChange={(v) => handlePrefChange(record.message_type, 'wechat_enabled', v)}
        />
      ),
    },
  ];

  const tableData = MESSAGE_TYPES.map(({ key, label }) => ({
    ...prefs[key],
    message_type: key,
    label,
    in_app_enabled: prefs[key]?.in_app_enabled ?? true,
    email_enabled: prefs[key]?.email_enabled ?? false,
    wechat_enabled: prefs[key]?.wechat_enabled ?? false,
  }));

  return (
    <div>
      <Title level={3} style={{ marginBottom: 16 }}>
        提醒偏好设置
      </Title>

      <Card title="按消息类型" style={{ marginBottom: 24 }}>
        <Table
          rowKey="message_type"
          loading={loading}
          columns={columns}
          dataSource={tableData}
          pagination={false}
        />
      </Card>

      <Card title="全局设置" style={{ marginBottom: 24 }}>
        <Form
          form={globalForm}
          layout="vertical"
          initialValues={{
            dnd_start: undefined,
            dnd_end: undefined,
            merge_strategy: 'none',
            merge_window_minutes: 5,
            deadline_advance_minutes: 60,
          }}
        >
          <Form.Item
            name="dnd_start"
            label="免打扰时段 - 开始"
            extra="格式 HH:mm"
          >
            <TimePicker
              format="HH:mm"
              placeholder="不设置"
              allowClear
              showNow={false}
              style={{ width: 120 }}
            />
          </Form.Item>
          <Form.Item
            name="dnd_end"
            label="免打扰时段 - 结束"
            extra="格式 HH:mm"
          >
            <TimePicker
              format="HH:mm"
              placeholder="不设置"
              allowClear
              showNow={false}
              style={{ width: 120 }}
            />
          </Form.Item>
          <Form.Item name="merge_strategy" label="合并策略">
            <Select options={MERGE_STRATEGY_OPTIONS} />
          </Form.Item>
          <Form.Item name="merge_window_minutes" label="合并时间窗口（分钟）">
            <InputNumber min={1} max={1440} style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="deadline_advance_minutes" label="到期预警提前量（分钟）">
            <InputNumber min={1} max={10080} style={{ width: 120 }} />
          </Form.Item>
        </Form>
      </Card>

      <Space>
        <Button type="primary" loading={saving} onClick={handleBatchSave}>
          保存
        </Button>
      </Space>
    </div>
  );
}
