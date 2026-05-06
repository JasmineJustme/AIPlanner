import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Space, Select, DatePicker, Button, Tag, Typography, message, Tooltip, Tabs, Modal, Input, Empty } from 'antd';
import {
  BellOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  SendOutlined,
  ReadOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import {
  getMessages,
  getUnreadCount,
  markMessageRead,
  markMessageProcessed,
  batchReadMessages,
  batchDeleteMessages,
} from '@/api/messages';
import { getCollaborateRequests, getDispatchMessages, acceptCollaborateRequest, rejectCollaborateRequest } from '@/api/taskFlow';
import type { Message } from '@/types/message';
import { useNotificationStore } from '@/stores/useNotificationStore';
import { useSSE } from '@/hooks/useSSE';
import { formatDate } from '@/utils/format';

const { Title } = Typography;
const { RangePicker } = DatePicker;
const { TextArea } = Input;

const MESSAGE_TYPE_OPTIONS = [
  { value: 'review_new', label: '新待审' },
  { value: 'orchestration_confirm', label: '编排确认' },
  { value: 'task_confirm', label: '任务确认' },
  { value: 'task_completed', label: '任务完成' },
  { value: 'task_failed', label: '任务失败' },
  { value: 'deadline_reminder', label: '到期提醒' },
  { value: 'system', label: '系统通知' },
];

const SYSTEM_MESSAGE_TYPE_LABEL_MAP: Record<string, string> = {
  review_new: '新待审',
  orchestration_confirm: '编排确认',
  task_confirm: '任务确认',
  task_completed: '任务完成',
  task_failed: '任务失败',
  deadline_reminder: '到期提醒',
  system: '系统通知',
  dispatch_message: '派发消息',
  collaboration_request: '协作请求',
};

const SYSTEM_MESSAGE_TYPES = new Set([
  'review_new',
  'orchestration_confirm',
  'task_confirm',
  'task_completed',
  'task_failed',
  'deadline_reminder',
  'system',
]);

const STATUS_OPTIONS = [
  { value: 'unread', label: '未读' },
  { value: 'read', label: '已读' },
  { value: 'processed', label: '已处理' },
];

const STATUS_TAG_MAP: Record<string, { color: string; text: string }> = {
  unread: { color: 'blue', text: '未读' },
  read: { color: 'default', text: '已读' },
  processed: { color: 'success', text: '已处理' },
};

function getTypeIcon(type: string) {
  switch (type) {
    case 'task_completed':
      return <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 6 }} />;
    case 'task_failed':
      return <CloseCircleOutlined style={{ color: '#ff4d4f', marginRight: 6 }} />;
    case 'orchestration_confirm':
    case 'task_confirm':
      return <ExclamationCircleOutlined style={{ color: '#1890ff', marginRight: 6 }} />;
    case 'deadline_reminder':
      return <ExclamationCircleOutlined style={{ color: '#faad14', marginRight: 6 }} />;
    default:
      return <BellOutlined style={{ marginRight: 6 }} />;
  }
}

function truncate(str: string, len: number) {
  if (!str) return '';
  return str.length > len ? str.slice(0, len) + '...' : str;
}

export default function MessagesPage() {
  const navigate = useNavigate();
  const { on, off } = useSSE();
  const { setUnreadCount, incrementUnread } = useNotificationStore();
  const [loading, setLoading] = useState(false);
  const [tabKey, setTabKey] = useState<'dispatch' | 'collaboration' | 'system'>('dispatch');
  const [data, setData] = useState<{ items: Message[]; total: number; page: number; size: number; pages: number }>({ items: [], total: 0, page: 1, size: 20, pages: 0 });
  const [dispatchData, setDispatchData] = useState<{ items: any[]; total: number; page: number; size: number; pages: number }>({ items: [], total: 0, page: 1, size: 20, pages: 0 });
  const [collabData, setCollabData] = useState<{ items: any[]; total: number; page: number; size: number; pages: number }>({ items: [], total: 0, page: 1, size: 20, pages: 0 });
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [rejectingRecord, setRejectingRecord] = useState<any | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [filters, setFilters] = useState<{ type?: string; status?: string; dateRange?: [string, string] | null }>({});

  const loadMessages = async () => {
    setLoading(true);
    try {
      if (tabKey === 'system') {
        const params: Record<string, unknown> = { page: data.page, size: data.size };
        if (filters.type) params.type = filters.type;
        if (filters.status) params.status = filters.status;
        if (filters.dateRange?.[0]) params.start_date = filters.dateRange[0];
        if (filters.dateRange?.[1]) params.end_date = filters.dateRange[1];
        const res = await getMessages(params as Parameters<typeof getMessages>[0]);
        const body = (res as { data: { data?: typeof data } }).data;
        const payload = body?.data ?? body;
        if (payload && typeof payload === 'object' && 'items' in payload) {
          const items = ((payload as { items: Message[] }).items ?? [])
            .filter((item) => SYSTEM_MESSAGE_TYPES.has(item.type))
            .map((item) => ({
              ...item,
              type: item.type === 'dispatch_message' || item.type === 'collaboration_request'
                ? item.type
                : item.type,
            }));
          setData((prev) => ({ ...prev, items, total: (payload as { total: number }).total, pages: (payload as { pages: number }).pages }));
        }
      } else if (tabKey === 'dispatch') {
        const res = await getDispatchMessages({ page: dispatchData.page, size: dispatchData.size });
        const body = (res as { data: { data?: typeof dispatchData } }).data;
        const payload = body?.data ?? body;
        if (payload && typeof payload === 'object' && 'items' in payload) {
          setDispatchData((prev) => ({ ...prev, items: (payload as { items: any[] }).items, total: (payload as { total: number }).total, pages: (payload as { pages: number }).pages }));
        }
      } else {
        const res = await getCollaborateRequests({ page: collabData.page, size: collabData.size });
        const body = (res as { data: { data?: typeof collabData } }).data;
        const payload = body?.data ?? body;
        if (payload && typeof payload === 'object' && 'items' in payload) {
          setCollabData((prev) => ({ ...prev, items: (payload as { items: any[] }).items, total: (payload as { total: number }).total, pages: (payload as { pages: number }).pages }));
        }
      }
    } catch {
      message.error('加载消息失败');
    } finally {
      setLoading(false);
    }
  };

  const loadUnreadCount = async () => {
    try {
      const res = await getUnreadCount();
      const body = (res as { data: { data?: { count: number } } }).data;
      const payload = body?.data ?? body;
      const count = (payload as { count?: number })?.count ?? 0;
      setUnreadCount(count);
    } catch {
      // ignore
    }
  };

  useEffect(() => { loadMessages(); }, [tabKey, data.page, data.size, dispatchData.page, dispatchData.size, collabData.page, collabData.size, filters.type, filters.status, filters.dateRange]);
  useEffect(() => { loadUnreadCount(); }, []);

  useEffect(() => {
    const handler = () => {
      incrementUnread();
      loadMessages();
    };
    on('message', handler);
    return () => { off('message', handler); };
  }, [on, off, incrementUnread]);

  const hoverReadTimers = useRef<Record<string, ReturnType<typeof setTimeout> | undefined>>({});

  useEffect(() => () => {
    Object.values(hoverReadTimers.current).forEach((timer) => timer && clearTimeout(timer));
  }, []);

  const handleMarkRead = async (id: string, showToast = true) => {
    try {
      await markMessageRead(id);
      if (showToast) {
        message.success('已标记为已读');
      }
      loadMessages();
      loadUnreadCount();
    } catch {
      if (showToast) {
        message.error('操作失败');
      }
    }
  };

  const handleRowHoverRead = (record: Message) => {
    if (record.status !== 'unread') return;
    const timerKey = record.id;
    if (hoverReadTimers.current[timerKey]) {
      clearTimeout(hoverReadTimers.current[timerKey]);
    }
    hoverReadTimers.current[timerKey] = setTimeout(() => {
      void handleMarkRead(record.id, false);
      delete hoverReadTimers.current[timerKey];
    }, 500);
  };

  const handleRowHoverLeave = (record: Message) => {
    const timer = hoverReadTimers.current[record.id];
    if (timer) {
      clearTimeout(timer);
      delete hoverReadTimers.current[record.id];
    }
  };

  const handleMarkProcessed = async (id: string) => { try { await markMessageProcessed(id); message.success('已标记为已处理'); loadMessages(); loadUnreadCount(); } catch { message.error('操作失败'); } };
  const handleBatchRead = async () => { const ids = selectedRowKeys.length > 0 ? selectedRowKeys : data.items.filter((m) => m.status === 'unread').map((m) => m.id); if (ids.length === 0) { message.warning('当前无未读消息'); return; } try { await batchReadMessages(ids); message.success('已全部标记为已读'); setSelectedRowKeys([]); loadMessages(); loadUnreadCount(); } catch { message.error('操作失败'); } };
  const handleBatchDelete = async () => { const processed = data.items.filter((m) => m.status === 'processed'); const ids = selectedRowKeys.length > 0 ? selectedRowKeys : processed.map((m) => m.id); if (ids.length === 0) { message.warning(selectedRowKeys.length === 0 ? '没有已处理的消息可删除' : '请选择消息'); return; } try { await batchDeleteMessages(ids); message.success('已删除'); setSelectedRowKeys([]); loadMessages(); loadUnreadCount(); } catch { message.error('操作失败'); } };

  const systemColumns: ColumnsType<Message> = [
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 160,
      render: (type: string) => {
        const label = SYSTEM_MESSAGE_TYPE_LABEL_MAP[type] ?? type;
        return <span>{getTypeIcon(type)}{label}</span>;
      },
    },
    { title: '标题', dataIndex: 'title', key: 'title', render: (title: string, record) => (<span style={{ fontWeight: record.status === 'unread' ? 600 : 400 }}>{title}</span>) },
    { title: '内容', dataIndex: 'content', key: 'content', ellipsis: true, render: (content: string, record) => (<Tooltip title={content}><span style={{ fontWeight: record.status === 'unread' ? 600 : 400 }}>{truncate(content, 60)}</span></Tooltip>) },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (status: string) => { const cfg = STATUS_TAG_MAP[status] ?? { color: 'default', text: status }; return <Tag color={cfg.color}>{cfg.text}</Tag>; } },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 100, render: (v: string) => formatDate(v) },
  ];

  const dispatchColumns: ColumnsType<any> = [
    { title: '标题', dataIndex: 'title', key: 'title' },
    { title: '内容', dataIndex: 'content', key: 'content', ellipsis: true, render: (content: string) => <Tooltip title={content}><span>{truncate(content, 60)}</span></Tooltip> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (status: string) => { const cfg = STATUS_TAG_MAP[status] ?? { color: 'default', text: status }; return <Tag color={cfg.color}>{cfg.text}</Tag>; } },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 100, render: (v: string) => formatDate(v) },
  ];

  const collabColumns: ColumnsType<any> = [
    { title: '标题', dataIndex: 'title', key: 'title' },
    { title: '内容', dataIndex: 'content', key: 'content' },
    {
      title: '状态',
      dataIndex: 'type',
      key: 'type',
      width: 140,
      render: (v: string) => {
        const map: Record<string, string> = {
          collaboration_request: '待处理',
          collaboration_accepted: '已接受',
          collaboration_rejected: '已拒绝',
        };
        return <Tag>{map[v] ?? v}</Tag>;
      },
    },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 140 },
    {
      title: '操作',
      key: 'action',
      width: 220,
      render: (_, record) => (
        <Space>
          {record.type === 'collaboration_request' && record.status !== 'processed' ? (
            <>
              <Button type="link" onClick={async () => { await acceptCollaborateRequest(record.related_request_id || record.id); message.success('已接受'); loadMessages(); loadUnreadCount(); }}>
                接受
              </Button>
              <Button type="link" danger onClick={() => { setRejectingRecord(record); setRejectReason(''); }}>
                拒绝
              </Button>
            </>
          ) : (
            <Tag color={record.type === 'collaboration_accepted' ? 'success' : 'error'}>
              {record.type === 'collaboration_accepted' ? '已处理为接受' : '已处理为拒绝'}
            </Tag>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Title level={3} style={{ marginBottom: 16 }}>消息中心</Title>
      <Tabs
        activeKey={tabKey}
        onChange={(key) => setTabKey(key as 'dispatch' | 'collaboration' | 'system')}
        items={[
          { key: 'dispatch', label: '派发消息', children: (
            <Table
              rowKey="id"
              loading={loading}
              columns={dispatchColumns}
              dataSource={dispatchData.items}
              pagination={false}
              locale={{ emptyText: <Empty description="暂无派发消息" /> }}
            />
          ) },
          { key: 'collaboration', label: '协作请求', children: (
            <Table
              rowKey="id"
              loading={loading}
              columns={collabColumns}
              dataSource={collabData.items}
              pagination={false}
              locale={{ emptyText: <Empty description="暂无协作请求" /> }}
            />
          ) },
          { key: 'system', label: '系统消息', children: (
            <>
              <Space wrap style={{ marginBottom: 16 }} size="middle">
                <Select placeholder="消息类型" allowClear style={{ width: 140 }} value={filters.type} onChange={(v) => setFilters((f) => ({ ...f, type: v }))} options={MESSAGE_TYPE_OPTIONS} />
                <Select placeholder="状态" allowClear style={{ width: 120 }} value={filters.status} onChange={(v) => setFilters((f) => ({ ...f, status: v }))} options={STATUS_OPTIONS} />
                <RangePicker value={filters.dateRange ? [filters.dateRange[0] ? dayjs(filters.dateRange[0]) : null, filters.dateRange[1] ? dayjs(filters.dateRange[1]) : null] : null} onChange={(dates) => setFilters((f) => ({ ...f, dateRange: dates ? [dates[0]?.format('YYYY-MM-DD') ?? '', dates[1]?.format('YYYY-MM-DD') ?? ''] : null }))} />
              </Space>
              <Space style={{ marginBottom: 16 }}>
                <Button icon={<ReadOutlined />} onClick={handleBatchRead}>全部标记已读</Button>
                <Button icon={<DeleteOutlined />} onClick={handleBatchDelete}>删除已处理</Button>
              </Space>
              <Table
                rowKey="id"
                loading={loading}
                columns={systemColumns}
                dataSource={data.items}
                onRow={(record) => ({
                  onMouseEnter: () => {
                    void handleRowHoverRead(record);
                  },
                  onMouseLeave: () => handleRowHoverLeave(record),
                })}
                pagination={{ current: data.page, pageSize: data.size, total: data.total, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
                onChange={(pagination) => setData((prev) => ({ ...prev, page: pagination.current ?? 1, size: pagination.pageSize ?? 20 }))}
                locale={{ emptyText: <Empty description="暂无系统消息" /> }}
              />
            </>
          ) },
        ]}
      />

      <Modal
        title="拒绝协作请求"
        open={!!rejectingRecord}
        onCancel={() => { setRejectingRecord(null); setRejectReason(''); }}
        onOk={async () => {
          if (!rejectingRecord) return;
          try {
            await rejectCollaborateRequest(rejectingRecord.related_request_id || rejectingRecord.id, { reason: rejectReason || undefined });
            message.success('已拒绝');
            setRejectingRecord(null);
            setRejectReason('');
            loadMessages();
            loadUnreadCount();
          } catch {
            message.error('拒绝失败');
          }
        }}
        okText="确认拒绝"
        cancelText="取消"
      >
        <TextArea
          rows={4}
          placeholder="请输入拒绝原因（可选）"
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
        />
      </Modal>
    </div>
  );
}
