import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Descriptions, Empty, Modal, Select, Space, Table, Tag, message, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate } from 'react-router-dom';
import { batchDispatchTodos, getDispatchableTodos, getEligibleTargetUsers, getManagedFlowTodos, getTodoFlowDetail } from '@/api/taskFlow';
import type { DispatchableTodo, EligibleTargetUser, TodoFlowDetail } from '@/types/taskFlow';
import { useAuthStore } from '@/stores/useAuthStore';

const { Title, Text } = Typography;

type FlowMode = 'dispatch' | 'collaboration';

const modeMeta: Record<FlowMode, { title: string; actionText: string; targetLabel: string; emptyTip: string }> = {
  dispatch: {
    title: '派发',
    actionText: '派发',
    targetLabel: '可派发对象',
    emptyTip: '当前没有可派发的对象',
  },
  collaboration: {
    title: '协作',
    actionText: '协作',
    targetLabel: '可协作对象',
    emptyTip: '当前没有可协作的对象',
  },
};

const buildTargetLabel = (user: EligibleTargetUser, mode: FlowMode) => {
  const parts = [user.label];
  if (user.org_unit_id) parts.push(user.org_unit_id);
  if (mode === 'collaboration' && user.manager_id) parts.push(`负责人:${user.manager_id}`);
  return parts.join(' · ');
};

export default function TodoFlowsPage() {
  const navigate = useNavigate();
  const currentUser = useAuthStore((s) => s.currentUser);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<DispatchableTodo[]>([]);
  const [managedItems, setManagedItems] = useState<DispatchableTodo[]>([]);
  const [targets, setTargets] = useState<EligibleTargetUser[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [targetUserId, setTargetUserId] = useState<string | undefined>();
  const [actionType, setActionType] = useState<FlowMode>('collaboration');
  const [submitting, setSubmitting] = useState(false);
  const [detail, setDetail] = useState<TodoFlowDetail | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const selectedIdsKey = selectedRowKeys.join(',');
  const isDepartment = currentUser?.role === 'department' || currentUser?.is_superuser;

  const modeMeta: Record<FlowMode, { title: string; actionText: string; targetLabel: string; emptyTip: string }> = {
    dispatch: {
      title: '派发',
      actionText: '派发',
      targetLabel: '可派发对象',
      emptyTip: '当前没有可派发的对象',
    },
    collaboration: {
      title: '协作',
      actionText: '协作',
      targetLabel: '可协作对象',
      emptyTip: '当前没有可协作的对象',
    },
  };

  const selectedItems = items.filter((item) => selectedRowKeys.includes(item.id));

  const loadItems = async () => {
    setLoading(true);
    try {
      const [pendingRes, managedRes] = await Promise.all([getDispatchableTodos(), getManagedFlowTodos()]);
      const pendingBody = (pendingRes as { data: { data?: unknown } }).data;
      const pendingPayload = (pendingBody?.data ?? pendingBody) as { items?: DispatchableTodo[] } | DispatchableTodo[];
      const pendingList = Array.isArray(pendingPayload) ? pendingPayload : pendingPayload?.items ?? [];
      setItems(pendingList);

      const managedBody = (managedRes as { data: { data?: unknown } }).data;
      const managedPayload = (managedBody?.data ?? managedBody) as { items?: DispatchableTodo[] } | DispatchableTodo[];
      const managedList = Array.isArray(managedPayload) ? managedPayload : managedPayload?.items ?? [];
      setManagedItems(managedList);
    } catch {
      message.error('加载派发与协作任务失败');
    } finally {
      setLoading(false);
    }
  };

  const loadTargets = async (mode: FlowMode) => {
    try {
      const res = await getEligibleTargetUsers(mode);
      const body = (res as { data: { data?: unknown } }).data;
      const payload = (body?.data ?? body) as EligibleTargetUser[];
      setTargets(Array.isArray(payload) ? payload : []);
    } catch {
      setTargets([]);
    }
  };

  useEffect(() => {
    loadItems();
    loadTargets(actionType);
  }, []);

  useEffect(() => {
    loadTargets(actionType);
  }, [actionType]);

  useEffect(() => {
    setSelectedRowKeys([]);
    setTargetUserId(undefined);
    setPreviewOpen(false);
  }, [actionType]);

  useEffect(() => {
    if (!isDepartment && actionType === 'dispatch') {
      setActionType('collaboration');
    }
  }, [actionType, isDepartment]);

  useEffect(() => {
    const firstId = selectedRowKeys[0];
    if (!firstId) {
      setDetail(null);
      return;
    }
    getTodoFlowDetail(firstId)
      .then((res) => {
        const body = (res as { data: { data?: unknown } }).data;
        const payload = (body?.data ?? body) as TodoFlowDetail;
        setDetail(payload ?? null);
      })
      .catch(() => setDetail(null));
  }, [selectedIdsKey]);

  useEffect(() => {
    if (!targetUserId) return;
    if (!targets.some((u) => u.id === targetUserId)) {
      setTargetUserId(undefined);
    }
  }, [targets, targetUserId]);

  const canSubmit = useMemo(
    () => selectedRowKeys.length > 0 && !!targetUserId,
    [selectedRowKeys, targetUserId],
  );

  const selectedTarget = targets.find((u) => u.id === targetUserId);

  const openPreview = () => {
    if (!selectedRowKeys.length) {
      message.warning('请选择任务');
      return;
    }
    if (!targetUserId) {
      message.warning('请选择目标对象');
      return;
    }
    setPreviewOpen(true);
  };

  const handleSubmit = async () => {
    setConfirming(true);
    try {
      await batchDispatchTodos({ todo_ids: selectedRowKeys, target_user_id: targetUserId!, action: actionType });
      message.success(actionType === 'dispatch' ? '批量派发成功' : '批量协作请求已发送');
      setSelectedRowKeys([]);
      setTargetUserId(undefined);
      setDetail(null);
      setPreviewOpen(false);
      loadItems();
    } catch {
      message.error('批量操作失败');
    } finally {
      setConfirming(false);
    }
  };

  const columns: ColumnsType<DispatchableTodo> = [
    { title: '标题', dataIndex: 'title', key: 'title' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (v) => {
        const labelMap: Record<string, string> = {
          pending_confirm: '待确认',
          pending: '待处理',
          completed: '已完成',
          cancelled: '已取消',
        };
        return <Tag>{labelMap[v] ?? v}</Tag>;
      },
    },
    { title: '来源', dataIndex: 'source', key: 'source' },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
  ];

  const managedColumns: ColumnsType<DispatchableTodo> = [
    { title: '标题', dataIndex: 'title', key: 'title' },
    {
      title: '派发与协作状态',
      dataIndex: 'last_flow_state',
      key: 'last_flow_state',
      render: (v) => {
        const text = v === 'completed' ? '已完成' : v === 'requesting' ? '请求中' : '已移交';
        const color = v === 'completed' ? 'success' : v === 'requesting' ? 'warning' : 'processing';
        return <Tag color={color}>{text}</Tag>;
      },
    },
    { title: '执行模式', dataIndex: 'execution_mode', key: 'execution_mode' },
    { title: '更新时间', dataIndex: 'created_at', key: 'created_at' },
  ];

  return (
    <div>
      <Space direction="vertical" style={{ width: '100%' }} size="large">
        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
          <Title level={3} style={{ margin: 0 }}>派发与协作</Title>
          <Button onClick={() => navigate('/todos')}>返回</Button>
        </Space>

        <Card>
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Space>
              <Text strong>模式：</Text>
              <Button type={actionType === 'collaboration' ? 'primary' : 'default'} onClick={() => setActionType('collaboration')}>
                协作
              </Button>
              <Button
                type={actionType === 'dispatch' ? 'primary' : 'default'}
                onClick={() => isDepartment && setActionType('dispatch')}
                disabled={!isDepartment}
              >
                派发
              </Button>
              {!isDepartment && <Text type="secondary">当前账户仅可使用协作模式</Text>}
            </Space>

            <Space wrap>
              <Select
                placeholder={modeMeta[actionType].targetLabel}
                style={{ width: 280 }}
                value={targetUserId}
                onChange={setTargetUserId}
                options={targets.map((u) => ({ value: u.id, label: buildTargetLabel(u, actionType) }))}
                notFoundContent={modeMeta[actionType].emptyTip}
                disabled={targets.length === 0}
              />
              <Button type="primary" onClick={openPreview} loading={submitting} disabled={!canSubmit}>
                确认执行
              </Button>
            </Space>
          </Space>
        </Card>

        <Card>
          <Text type="secondary">仅展示当前账户自己创建的待确认任务。默认进入协作模式；department 账户可切换到派发模式，section 账户仅保留协作模式。</Text>
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={items}
            rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys as string[]) }}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无可派发或协作的待确认任务" /> }}
          />
        </Card>

        <Card title="派发与协作模块（原账户只读视图)">
          <Text type="secondary">任务被派发或协作确认后，将转入目标账户的系统执行模块或用户执行模块；原账户在此仅可查看 `已移交` 或 `已完成` 状态。</Text>
          <Table
            rowKey="id"
            loading={loading}
            columns={managedColumns}
            dataSource={managedItems}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无派发与协作中的任务" /> }}
          />
        </Card>

        {detail ? (
          <Card title="任务流转详情">
            <Space direction="vertical" style={{ width: '100%' }}>
              <div>来源：{detail.source_type ?? '-'}</div>
              <div>当前状态：{detail.current_status ?? '-'}</div>
              <div>当前负责人：{detail.current_owner_name ?? '-'}</div>
              <div>派发记录：{detail.dispatch_records?.length ? detail.dispatch_records.map((r) => `${r.created_at}`).join('；') : '无'}</div>
              <div>协作记录：{detail.collaboration_records?.length ? detail.collaboration_records.map((r) => `${r.created_at} / ${r.status}`).join('；') : '无'}</div>
              <div>历史记录：{detail.history?.length ? detail.history.map((r) => `${r.action} / ${r.created_at}`).join('；') : '无'}</div>
            </Space>
          </Card>
        ) : null}
      </Space>

      <Modal
        title={`确认${modeMeta[actionType].actionText}`}
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        onOk={handleSubmit}
        confirmLoading={confirming}
        okText="二次确认"
        cancelText="返回修改"
      >
        <Alert
          type="info"
          showIcon
          message={`请确认以下${modeMeta[actionType].actionText}信息`}
          description="确认后将提交本次操作，请再次核对任务与目标对象。"
          style={{ marginBottom: 16 }}
        />
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="操作类型">{modeMeta[actionType].title}</Descriptions.Item>
          <Descriptions.Item label="目标对象">{selectedTarget?.label ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="任务数量">{selectedRowKeys.length}</Descriptions.Item>
          <Descriptions.Item label="任务列表">{selectedItems.map((item) => item.title).join('；')}</Descriptions.Item>
          <Descriptions.Item label="当前模式">{isDepartment ? modeMeta[actionType].title : '协作'}</Descriptions.Item>
        </Descriptions>
      </Modal>
    </div>
  );
}
