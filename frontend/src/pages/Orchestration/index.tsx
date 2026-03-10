import { useEffect, useRef, useState, useCallback } from 'react';
import {
  Card,
  Spin,
  Typography,
  Tag,
  Button,
  Space,
  Form,
  Input,
  InputNumber,
  Select,
  DatePicker,
  Collapse,
  Modal,
  Empty,
  Alert,
  message,
  Tabs,
  Checkbox,
} from 'antd';
import {
  CheckOutlined,
  SwapOutlined,
  CloseOutlined,
  LoadingOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  getPendingOrchestrations,
  getOrchestration,
  confirmOrchestration,
  confirmWAgent,
  modifyOrchestrationAgent,
  modifyOrchestrationParams,
  cancelOrchestration,
  retryOrchestration,
} from '@/api/orchestration';
import { getAgents, getWAgents } from '@/api/config';
import ReasonCollapse from '@/components/ReasonCollapse';
import { useSSE } from '@/hooks/useSSE';
import type { Agent } from '@/types/agent';
import type { WAgent } from '@/types/wagent';
import type { Todo } from '@/types/todo';
import { PRIORITY_MAP } from '@/constants/status';

const { Title, Text } = Typography;

interface OrchestrationItem {
  orch_id: string;
  summary?: string;
  todos_count?: number;
  status: string;
  submitted_at?: string;
  error?: string;
  recommended_name?: string;
}

interface OrchestrationDetail {
  orch_id: string;
  status: string;
  todos: Todo[];
  suggested_agent?: Agent | null;
  suggested_wagent?: WAgent | null;
  plan?: {
    plan_type: 'agent' | 'wagent' | 'new_wagent';
    recommended_id?: string;
    recommended_name?: string;
    reason?: string;
    input_params?: Record<string, unknown>;
    priority?: string;
    estimated_duration_minutes?: number;
    start_time?: string | null;
    deadline?: string | null;
    steps?: Array<{ order: number; workflow_name: string }>;
  };
  llm_reason?: string;
  error?: string;
}

const STATUS_CONFIG: Record<string, { color: string; text: string; icon: React.ReactNode }> = {
  analyzing: { color: 'processing', text: '智能编排中', icon: <LoadingOutlined /> },
  pending_confirm: { color: 'blue', text: '待确认', icon: <ClockCircleOutlined /> },
  confirmed: { color: 'success', text: '已确认', icon: <CheckCircleOutlined /> },
  cancelled: { color: 'default', text: '已取消', icon: <CloseOutlined /> },
  failed: { color: 'error', text: '失败', icon: <ExclamationCircleOutlined /> },
};

function OrchestrationCard({
  orch,
  onRefreshList,
  selectable,
  checked,
  onCheck,
}: {
  orch: OrchestrationItem;
  onRefreshList: () => void;
  selectable?: boolean;
  checked?: boolean;
  onCheck?: (checked: boolean) => void;
}) {
  const [detail, setDetail] = useState<OrchestrationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [agentModalOpen, setAgentModalOpen] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [wagents, setWAgents] = useState<WAgent[]>([]);
  const [form] = Form.useForm();

  const loadDetail = useCallback(async () => {
    setDetailLoading(true);
    try {
      const res = await getOrchestration(orch.orch_id);
      const data = (res as { data: { data?: OrchestrationDetail } }).data;
      const d = (data?.data ?? data) as OrchestrationDetail | null;
      setDetail(d || null);
      if (d) {
        const plan = d.plan;
        const inputParams = plan?.input_params ?? {};
        form.setFieldsValue({
          ...inputParams,
          priority: plan?.priority || 'medium',
          estimated_duration_minutes: plan?.estimated_duration_minutes ?? 30,
          start_time: plan?.start_time ? dayjs(plan.start_time) : null,
          deadline: plan?.deadline ? dayjs(plan.deadline) : null,
        });
      }
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
      setLoaded(true);
    }
  }, [orch.orch_id, form]);

  const handleExpandToggle = (keys: string | string[]) => {
    const active = Array.isArray(keys) ? keys : [keys];
    if (active.includes(orch.orch_id) && !loaded) {
      loadDetail();
    }
  };

  useEffect(() => {
    if (agentModalOpen) {
      Promise.all([getAgents({ size: 100 }), getWAgents({ size: 100 })]).then(
        ([aRes, wRes]) => {
          const aData = (aRes as { data: { data?: { items?: Agent[] } } }).data;
          const wData = (wRes as { data: { data?: { items?: WAgent[] } } }).data;
          setAgents(aData?.data?.items ?? (aData as unknown as { items?: Agent[] })?.items ?? []);
          setWAgents(wData?.data?.items ?? (wData as unknown as { items?: WAgent[] })?.items ?? []);
        }
      );
    }
  }, [agentModalOpen]);

  const buildInputParams = (values: Record<string, unknown>) => {
    const paramKeys = Object.keys(detail?.plan?.input_params || {});
    return paramKeys.reduce<Record<string, unknown>>((acc, key) => {
      acc[key] = values[key];
      return acc;
    }, {});
  };

  const handleConfirm = async () => {
    if (!detail) return;
    try {
      const values = form.getFieldsValue();
      const plan = detail.plan;
      const planType = plan?.plan_type || (detail.suggested_wagent ? 'wagent' : 'agent');
      const payload = {
        input_params: buildInputParams(values),
        priority: values.priority,
        estimated_duration_minutes: values.estimated_duration_minutes,
        start_time: values.start_time?.toISOString?.(),
        deadline: values.deadline?.toISOString?.(),
      };
      if (planType === 'wagent' || planType === 'new_wagent') {
        await confirmWAgent(orch.orch_id, payload);
      } else {
        await confirmOrchestration(orch.orch_id, payload);
      }
      message.success('已确认执行');
      onRefreshList();
    } catch (e) {
      message.error((e as Error).message || '确认失败');
    }
  };

  const handleModifyAgent = async (agentId: string, type: 'agent' | 'wagent') => {
    try {
      await modifyOrchestrationAgent(orch.orch_id, {
        plan_type: type,
        recommended_id: agentId,
      });
      message.success('已修改');
      setAgentModalOpen(false);
      loadDetail();
    } catch (e) {
      message.error((e as Error).message || '修改失败');
    }
  };

  const handleModifyParams = async () => {
    try {
      const values = form.getFieldsValue();
      await modifyOrchestrationParams(orch.orch_id, {
        input_params: buildInputParams(values),
        priority: values.priority,
        estimated_duration_minutes: values.estimated_duration_minutes,
        start_time: values.start_time?.toISOString?.(),
        deadline: values.deadline?.toISOString?.(),
      });
      message.success('参数已更新');
    } catch (e) {
      message.error((e as Error).message || '更新失败');
    }
  };

  const handleCancel = async () => {
    try {
      await cancelOrchestration(orch.orch_id);
      message.success('已取消');
      onRefreshList();
    } catch (e) {
      message.error((e as Error).message || '取消失败');
    }
  };

  const handleRetry = async () => {
    setRetrying(true);
    try {
      const res = await retryOrchestration(orch.orch_id);
      const body = (res as { data: { data?: { status?: string; error?: string } } }).data;
      const result = (body?.data ?? body) as { status?: string; error?: string } | undefined;
      if (result?.error) {
        message.error(`重新编排失败: ${result.error}`);
      } else {
        message.success('已重新提交编排');
      }
      onRefreshList();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      message.error(err?.response?.data?.detail || err?.message || '重试失败');
    } finally {
      setRetrying(false);
    }
  };

  const getRecommendedName = () => {
    if (!detail) return '';
    const plan = detail.plan;
    if (plan?.recommended_name) return plan.recommended_name;
    if (detail.suggested_agent) return detail.suggested_agent.name;
    if (detail.suggested_wagent) return detail.suggested_wagent.name;
    return '-';
  };

  const getPlanType = () => {
    if (!detail) return 'agent';
    const plan = detail.plan;
    if (plan?.plan_type) return plan.plan_type;
    if (detail.suggested_wagent) return 'wagent';
    return 'agent';
  };

  const getReason = () => {
    if (!detail) return '';
    return detail.llm_reason || detail.plan?.reason || '';
  };

  const statusCfg = STATUS_CONFIG[orch.status] || { color: 'default', text: orch.status, icon: null };

  const getHeaderName = () => {
      const firstTodo = detail?.todos?.[0];
      const detailTitle = firstTodo?.title?.trim() || '';
      return detailTitle || orch.summary || `编排 #${orch.orch_id.slice(-6)}`;
  };
  const getMetaInfo = () => {
      // Show orch_id and agent name
      const id = orch.orch_id.slice(-6);
      const parts = [`ID: ${id}`];
      if (orch.recommended_name) parts.push(orch.recommended_name);
      return parts.join(' | ');
  };

  const cardHeader = (
    <div style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }} onClick={(e) => e.stopPropagation()}>
       <Space style={{ flex: 1, minWidth: 0 }}>
        {selectable && (
             <Checkbox
                checked={checked}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => onCheck?.(e.target.checked)}
             />
        )}
        <Text strong ellipsis style={{ maxWidth: 300 }}>{getHeaderName()}</Text>
        <Text type="secondary" style={{ fontSize: 12 }}>{getMetaInfo()}</Text>
        <Tag>{orch.todos_count ?? 0} 个任务</Tag>
        <Tag icon={statusCfg.icon} color={statusCfg.color}>
          {statusCfg.text}
        </Tag>
      </Space>
      <Space>
        {orch.submitted_at && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {new Date(orch.submitted_at).toLocaleString()}
          </Text>
        )}
      </Space>
    </div>
  );

  if (orch.status === 'analyzing') {
    return (
      <Card size="small" style={{ borderLeft: '3px solid #1890ff' }}>
        {cardHeader}
        <div style={{ padding: '12px 0', textAlign: 'center' }}>
          <Spin indicator={<LoadingOutlined />} />
          <Text type="secondary" style={{ marginLeft: 8 }}>LLM 正在分析任务，请稍候...</Text>
        </div>
      </Card>
    );
  }

  if (orch.status === 'failed') {
    return (
      <Card size="small" style={{ borderLeft: '3px solid #ff4d4f' }}>
        {cardHeader}
        <Alert
          type="error"
          showIcon
          message="编排失败"
          description={orch.error || '未知错误，请检查 LLM 配置后重试'}
          style={{ marginTop: 8 }}
        />
        <Space style={{ marginTop: 12 }}>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={retrying}
            onClick={handleRetry}
          >
            重新编排
          </Button>
          <Button
            danger
            icon={<CloseOutlined />}
            onClick={handleCancel}
          >
            取消
          </Button>
        </Space>
      </Card>
    );
  }

  if (orch.status === 'cancelled') {
    return (
      <Card size="small" style={{ borderLeft: '3px solid #d9d9d9', opacity: 0.7 }}>
        {cardHeader}
      </Card>
    );
  }

  if (orch.status === 'confirmed') {
    return (
      <Card size="small" style={{ borderLeft: '3px solid #52c41a' }}>
        <Collapse ghost onChange={handleExpandToggle}>
          <Collapse.Panel header={cardHeader} key={orch.orch_id}>
            {detailLoading ? (
              <Spin tip="加载中..." />
            ) : detail ? (
              <div style={{ paddingTop: 8 }}>
                <div style={{ marginBottom: 12 }}>
                  <Text strong>任务摘要：</Text>
                  <div style={{ marginTop: 4 }}>
                    {detail.todos?.map((t) => (
                      <Tag key={t.id} style={{ marginBottom: 4 }}>{t.description?.trim() || '无描述'}</Tag>
                    ))}
                  </div>
                </div>
                <div style={{ marginBottom: 12 }}>
                  <Text strong>执行者：</Text>
                  <Tag color="green" style={{ marginLeft: 8 }}>{getRecommendedName()}</Tag>
                </div>
                <ReasonCollapse reason={getReason()} />
              </div>
            ) : (
              <Empty description="加载失败" />
            )}
          </Collapse.Panel>
        </Collapse>
      </Card>
    );
  }

  return (
    <Card size="small" style={{ borderLeft: '3px solid #1890ff' }}>
      <Collapse ghost onChange={handleExpandToggle}>
        <Collapse.Panel header={cardHeader} key={orch.orch_id}>
          {detailLoading ? (
            <Spin tip="加载中..." />
          ) : detail ? (
            <div style={{ paddingTop: 8 }}>
              <div style={{ marginBottom: 16 }}>
                <Text strong>任务摘要：</Text>
                <div style={{ marginTop: 4 }}>
                  {detail.todos?.map((t) => (
                    <Tag key={t.id} style={{ marginBottom: 4 }}>{t.description?.trim() || '无描述'}</Tag>
                  ))}
                  {(!detail.todos || detail.todos.length === 0) && (
                    <Text type="secondary">-</Text>
                  )}
                </div>
              </div>

              <div style={{ marginBottom: 16 }}>
                <Text strong>推荐执行者：</Text>
                <Tag color="blue" style={{ marginLeft: 8 }}>
                  {getRecommendedName()}
                </Tag>
                {getPlanType() === 'new_wagent' && (
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    (新 W-Agent 编排)
                  </Text>
                )}
              </div>

              <div style={{ marginBottom: 16 }}>
                <ReasonCollapse reason={getReason()} />
              </div>

              {getPlanType() === 'new_wagent' && detail.plan?.steps && (
                <div style={{ marginBottom: 16 }}>
                  <Text strong>Workflow 步骤：</Text>
                  <ul style={{ marginTop: 4, paddingLeft: 20 }}>
                    {detail.plan.steps.map((s) => (
                      <li key={s.order}>
                        {s.order}. {s.workflow_name}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <Form form={form} layout="vertical">
                <Collapse style={{ marginBottom: 16 }}>
                  <Collapse.Panel header="输入参数" key="input_params">
                    {Object.entries(detail.plan?.input_params || {}).length > 0 ? (
                      <>
                        {Object.entries(detail.plan?.input_params || {}).map(
                          ([key, val]) => (
                            <Form.Item key={key} name={key} label={key}>
                              <Input
                                placeholder={String(val ?? '')}
                                defaultValue={String(val ?? '')}
                              />
                            </Form.Item>
                          )
                        )}
                      </>
                    ) : (
                      <Text type="secondary">暂无输入参数</Text>
                    )}
                  </Collapse.Panel>

                  <Collapse.Panel header="调度设置" key="scheduling">
                    <Form.Item name="priority" label="优先级">
                      <Select
                        options={Object.entries(PRIORITY_MAP).map(([k, v]) => ({
                          value: k,
                          label: v.text,
                        }))}
                      />
                    </Form.Item>
                    <Form.Item name="estimated_duration_minutes" label="预计时长(分钟)">
                      <InputNumber min={1} style={{ width: 120 }} />
                    </Form.Item>
                    <Form.Item name="start_time" label="开始时间">
                      <DatePicker showTime style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="deadline" label="截止时间">
                      <DatePicker showTime style={{ width: '100%' }} />
                    </Form.Item>
                  </Collapse.Panel>
                </Collapse>

                <Form.Item style={{ marginBottom: 0 }}>
                  <Button type="primary" onClick={handleModifyParams} style={{ marginRight: 8 }}>
                    保存参数
                  </Button>
                </Form.Item>
              </Form>

              <Space style={{ marginTop: 16 }}>
                <Button type="primary" icon={<CheckOutlined />} onClick={handleConfirm}>
                  确认执行
                </Button>
                <Button
                  icon={<SwapOutlined />}
                  onClick={() => setAgentModalOpen(true)}
                >
                  修改Agent
                </Button>
                <Button danger icon={<CloseOutlined />} onClick={handleCancel}>
                  取消
                </Button>
              </Space>
            </div>
          ) : (
            <Empty description="加载失败" />
          )}
        </Collapse.Panel>
      </Collapse>

      <Modal
        title="选择 Agent / W-Agent"
        open={agentModalOpen}
        onCancel={() => setAgentModalOpen(false)}
        footer={null}
        width={480}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <Text strong>Agent：</Text>
            {agents.map((a) => (
              <Button
                key={a.id}
                type="link"
                size="small"
                onClick={() => handleModifyAgent(a.id, 'agent')}
              >
                {a.name}
              </Button>
            ))}
            {agents.length === 0 && <Text type="secondary"> 无</Text>}
          </div>
          <div>
            <Text strong>W-Agent：</Text>
            {wagents.map((w) => (
              <Button
                key={w.id}
                type="link"
                size="small"
                onClick={() => handleModifyAgent(w.id, 'wagent')}
              >
                {w.name}
              </Button>
            ))}
            {wagents.length === 0 && <Text type="secondary"> 无</Text>}
          </div>
        </Space>
      </Modal>
    </Card>
  );
}

export default function OrchestrationPage() {
  const [loading, setLoading] = useState(true);
  const [orchestrations, setOrchestrations] = useState<OrchestrationItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const { on, off } = useSSE();
  const loadPendingRef = useRef<(() => Promise<void>) | null>(null);

  const loadPending = async () => {
    setLoading(true);
    try {
      const res = await getPendingOrchestrations();
      const data = (res as { data: { data?: OrchestrationItem[] } }).data;
      const list = (data?.data ?? data) as OrchestrationItem[] | undefined;
      setOrchestrations(Array.isArray(list) ? list : []);
      setSelectedIds(new Set()); // Reset selection on reload
    } catch {
      setOrchestrations([]);
    } finally {
      setLoading(false);
    }
  };
  loadPendingRef.current = loadPending;

  useEffect(() => {
    loadPending();
  }, []);

  useEffect(() => {
    const handler = () => loadPendingRef.current?.();
    on('orchestration_complete', handler);
    return () => off('orchestration_complete', handler);
  }, [on, off]);

  const handleBatchConfirm = async () => {
    if (selectedIds.size === 0) return;
    try {
        const promises = Array.from(selectedIds).map(id => confirmOrchestration(id));
        await Promise.all(promises);
        message.success(`已批量确认 ${selectedIds.size} 个任务`);
        loadPending(); // Refresh list will clear selection
    } catch {
        message.error("批量确认失败，请重试");
    }
  };

  const toggleSelect = (id: string, checked: boolean) => {
      const newSet = new Set(selectedIds);
      if (checked) newSet.add(id);
      else newSet.delete(id);
      setSelectedIds(newSet);
  };

  const renderList = (status: string) => {
      const allVisibleStatuses = new Set(['analyzing', 'pending_confirm']);
      const items = status === 'all'
        ? orchestrations.filter(o => allVisibleStatuses.has(o.status))
        : orchestrations.filter(o => o.status === status);

      if (items.length === 0) {
        const description = status === 'all' ? '暂无分析中或待确认的编排任务' : '暂无任务';
        return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description} />;
      }

      const isPending = status === 'pending_confirm';

      return (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
             {isPending && items.length > 0 && (
                <div style={{ marginBottom: 8, display: 'flex', gap: 8 }}>
                    <Button
                        size="small"
                        onClick={() => {
                            if (selectedIds.size === items.length) {
                                setSelectedIds(new Set());
                            } else {
                                setSelectedIds(new Set(items.map(i => i.orch_id)));
                            }
                        }}
                    >
                        {selectedIds.size === items.length && items.length > 0 ? '取消全选' : '全选'}
                    </Button>
                    <Button
                        type="primary"
                        size="small"
                        disabled={selectedIds.size === 0}
                        onClick={handleBatchConfirm}
                    >
                        批量执行 ({selectedIds.size})
                    </Button>
                </div>
             )}
            {items.map((orch) => (
            <OrchestrationCard
                key={orch.orch_id}
                orch={orch}
                onRefreshList={loadPending}
                selectable={isPending}
                checked={isPending ? selectedIds.has(orch.orch_id) : false}
                onCheck={(c) => toggleSelect(orch.orch_id, c)}
            />
            ))}
        </Space>
      );
  };


  if (loading) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Spin size="large" />
        <div style={{ marginTop: 16 }}>
          <Text type="secondary">加载编排列表...</Text>
        </div>
      </div>
    );
  }

  if (orchestrations.length === 0) {
    return (
      <div>
        <Title level={3}>智能编排</Title>
        <Empty
          description="暂无编排记录，请在待办任务中选择任务并提交到编排"
          style={{ marginTop: 48 }}
        />
      </div>
    );
  }

  const items = [
      { key: 'all', label: '全部', children: renderList('all') },
      { key: 'analyzing', label: '分析中', children: renderList('analyzing') },
      { key: 'pending_confirm', label: '待确认', children: renderList('pending_confirm') },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>智能编排</Title>
        <Button onClick={loadPending}>刷新</Button>
      </div>
      <Tabs defaultActiveKey="pending_confirm" items={items} />
    </div>
  );
}
