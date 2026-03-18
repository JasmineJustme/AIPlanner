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
import { getNotificationChannels } from '@/api/config';

const { Title, Text } = Typography;

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
  channel_enabled_map?: Record<string, boolean>;
}

interface ChannelConfig {
  channel_type: string;
  name?: string;
  agent_id?: string;
  dify_endpoint?: string;
  dify_api_key?: string;
  is_enabled?: boolean;
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
  const [visibleChannels, setVisibleChannels] = useState<Array<{ key: string; label: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [globalForm] = Form.useForm();

  const isConfiguredChannel = (channel: ChannelConfig) => {
    if (channel.agent_id) {
      return true;
    }
    return Boolean((channel.dify_endpoint ?? '').trim() && (channel.dify_api_key ?? '').trim());
  };

  const resolvePrefMap = (row?: NotificationPrefRow): Record<string, boolean> => {
    const map = { ...(row?.channel_enabled_map ?? {}) };
    map.in_app = map.in_app ?? row?.in_app_enabled ?? true;
    map.email_workflow = map.email_workflow ?? row?.email_enabled ?? false;
    map.wechat_workflow = map.wechat_workflow ?? row?.wechat_enabled ?? false;
    return map;
  };

  const loadPrefs = async () => {
    setLoading(true);
    try {
      const [prefsRes, globalRes, channelRes] = await Promise.all([
        getNotificationPrefs(),
        getNotificationGlobal(),
        getNotificationChannels(),
      ]);
      const prefsData = (prefsRes as { data: { data?: NotificationPrefRow[] } }).data?.data ?? [];
      const globalData = ((globalRes as { data: { data?: Partial<GlobalPref> } }).data?.data ?? {}) as Partial<GlobalPref>;
      const channelData = (channelRes as { data: { data?: ChannelConfig[] } }).data?.data ?? [];

      const nextVisibleChannels = (Array.isArray(channelData) ? channelData : [])
        .filter((item) => item?.channel_type !== 'in_app')
        .filter((item) => item?.is_enabled !== false)
        .filter((item) => isConfiguredChannel(item))
        .map((item) => ({
          key: item.channel_type,
          label: item.name || item.channel_type,
        }));
      setVisibleChannels(nextVisibleChannels);

      const prefsMap: Record<string, NotificationPrefRow> = {};
      MESSAGE_TYPES.forEach(({ key }) => {
        const p = (prefsData as NotificationPrefRow[]).find((x) => x.message_type === key);
        const channelEnabledMap = resolvePrefMap(p);
        prefsMap[key] = p ?? {
          message_type: key,
          in_app_enabled: true,
          email_enabled: false,
          wechat_enabled: false,
          channel_enabled_map: channelEnabledMap,
        };
        prefsMap[key].channel_enabled_map = channelEnabledMap;
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
    channelType: string,
    value: boolean
  ) => {
    const current = prefs[messageType] ?? {
      message_type: messageType,
      in_app_enabled: true,
      email_enabled: false,
      wechat_enabled: false,
      channel_enabled_map: {},
    };
    const channelEnabledMap = {
      ...resolvePrefMap(current),
      [channelType]: value,
    };
    const next = {
      ...current,
      channel_enabled_map: channelEnabledMap,
      in_app_enabled: channelEnabledMap.in_app ?? true,
      email_enabled: channelEnabledMap.email_workflow ?? false,
      wechat_enabled: channelEnabledMap.wechat_workflow ?? false,
    };
    const previous = prefs[messageType];
    setPrefs((p) => ({ ...p, [messageType]: next }));
    try {
      await updateNotificationPref({
        message_type: messageType,
        in_app_enabled: next.in_app_enabled,
        email_enabled: next.email_enabled,
        wechat_enabled: next.wechat_enabled,
        channel_enabled_map: channelEnabledMap,
      });
      message.success('已更新');
    } catch {
      setPrefs((p) => ({ ...p, [messageType]: previous }));
      message.error('更新失败');
    }
  };

  const handleBatchSave = async () => {
    setSaving(true);
    try {
      await Promise.all(
        MESSAGE_TYPES.map(({ key }) =>
          (() => {
            const row = prefs[key];
            const channelEnabledMap = resolvePrefMap(row);
            return updateNotificationPref({
              message_type: key,
              in_app_enabled: channelEnabledMap.in_app ?? true,
              email_enabled: channelEnabledMap.email_workflow ?? false,
              wechat_enabled: channelEnabledMap.wechat_workflow ?? false,
              channel_enabled_map: channelEnabledMap,
            });
          })()
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

  const channelColumns: ColumnsType<NotificationPrefRow & { label: string }> = visibleChannels.map((channel) => ({
    title: channel.label,
    dataIndex: channel.key,
    key: channel.key,
    width: 140,
    render: (_, record) => {
      const channelEnabledMap = resolvePrefMap(record);
      return (
        <Switch
          checked={Boolean(channelEnabledMap[channel.key])}
          onChange={(v) => handlePrefChange(record.message_type, channel.key, v)}
        />
      );
    },
  }));

  const columns: ColumnsType<NotificationPrefRow & { label: string }> = [
    {
      title: '消息类型',
      dataIndex: 'label',
      key: 'label',
      width: 140,
    },
    ...channelColumns,
  ];

  const tableData = MESSAGE_TYPES.map(({ key, label }) => ({
    ...prefs[key],
    message_type: key,
    label,
    in_app_enabled: prefs[key]?.in_app_enabled ?? true,
    email_enabled: prefs[key]?.email_enabled ?? false,
    wechat_enabled: prefs[key]?.wechat_enabled ?? false,
    channel_enabled_map: resolvePrefMap(prefs[key]),
  }));

  const hasEditableChannels = visibleChannels.length > 0;

  return (
    <div>
      <Title level={3} style={{ marginBottom: 16 }}>
        提醒偏好设置
      </Title>

      <Card title="按消息类型" style={{ marginBottom: 24 }}>
        {hasEditableChannels ? (
          <Table
            rowKey="message_type"
            loading={loading}
            columns={columns}
            dataSource={tableData}
            pagination={false}
          />
        ) : (
          <Text type="secondary">当前无可用提醒渠道</Text>
        )}
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
