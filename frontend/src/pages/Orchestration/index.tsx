import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
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
  TimePicker,
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
  QuestionCircleOutlined,
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
import { ROUTES } from '@/constants/routes';

const { Title, Text } = Typography;

const RECURRENCE_TYPE_OPTIONS = [
  { value: 'daily', label: '每日' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
];

const WEEKDAY_OPTIONS = [
  { value: 0, label: '周日' },
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
];

const MONTH_DAY_OPTIONS = Array.from({ length: 31 }, (_, i) => ({
  value: i + 1,
  label: `${i + 1} 日`,
}));

function parseCronToUi(cron?: string | null): {
  recurrence_type?: 'daily' | 'weekly' | 'monthly';
  recurrence_weekdays?: number[];
  recurrence_month_day?: number;
  recurrence_time?: dayjs.Dayjs;
} {
  if (!cron) return {};
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return {};
  const [minute, hour, day, _month, weekday] = parts;
  const h = Number(hour);
  const m = Number(minute);
  const recurrence_time = Number.isFinite(h) && Number.isFinite(m)
    ? dayjs().hour(h).minute(m).second(0)
    : undefined;

  if (day === '*' && weekday !== '*') {
    const weekdays = weekday.split(',').map((v) => Number(v)).filter((v) => Number.isInteger(v) && v >= 0 && v <= 6);
    return { recurrence_type: 'weekly', recurrence_weekdays: weekdays, recurrence_time };
  }
  if (day !== '*' && weekday === '*') {
    const monthDay = Number(day);
    if (Number.isInteger(monthDay) && monthDay >= 1 && monthDay <= 31) {
      return { recurrence_type: 'monthly', recurrence_month_day: monthDay, recurrence_time };
    }
  }
  if (day === '*' && weekday === '*') {
    return { recurrence_type: 'daily', recurrence_time };
  }
  return {};
}

function buildCronFromUi(values: Record<string, unknown>): string | null {
  const recurrenceType = values.recurrence_type as string | undefined;
  const time = values.recurrence_time as dayjs.Dayjs | undefined;
  const hour = dayjs.isDayjs(time) ? time.hour() : 9;
  const minute = dayjs.isDayjs(time) ? time.minute() : 0;

  if (recurrenceType === 'daily') {
    return `${minute} ${hour} * * *`;
  }
  if (recurrenceType === 'weekly') {
    const weekdays = Array.isArray(values.recurrence_weekdays)
      ? (values.recurrence_weekdays as number[]).filter((v) => Number.isInteger(v) && v >= 0 && v <= 6)
      : [];
    if (weekdays.length === 0) return null;
    return `${minute} ${hour} * * ${weekdays.sort((a, b) => a - b).join(',')}`;
  }
  if (recurrenceType === 'monthly') {
    const day = Number(values.recurrence_month_day ?? 1);
    if (!Number.isInteger(day) || day < 1 || day > 31) return null;
    return `${minute} ${hour} ${day} * *`;
  }
  return null;
}

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
  suggested_agent?: Agent | ({ id: string; name: string; is_enabled?: boolean; type?: string }) | null;
  suggested_wagent?: WAgent | ({ id: string; name: string; is_enabled?: boolean; type?: string }) | null;
  llm_recommended_id?: string | null;
  llm_recommended_name?: string | null;
  llm_recommended_type?: 'agent' | 'wagent' | null;
  llm_recommended_input_params?: Record<string, unknown> | null;
  plan?: {
    plan_type: 'agent' | 'wagent' | 'new_wagent';
    recommended_id?: string;
    recommended_name?: string;
    reason?: string;
    input_params?: Record<string, unknown>;
    editable_input_keys?: string[];
    priority?: string;
    estimated_duration_minutes?: number;
    start_time?: string | null;
    deadline?: string | null;
    is_recurring?: boolean;
    recurrence_cron?: string | null;
    recurrence_count?: number;
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
  onConfirmed,
  onRetryStarted,
  onAgentModified,
  selectable,
  checked,
  onCheck,
}: {
  orch: OrchestrationItem;
  onRefreshList: () => void;
  onConfirmed?: () => void;
  onRetryStarted?: (orch: OrchestrationItem) => Promise<void>;
  onAgentModified?: (orchId: string, patch: Partial<OrchestrationItem>) => void;
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
  const recurrenceType = Form.useWatch('recurrence_type', form) as 'daily' | 'weekly' | 'monthly' | undefined;
  const isRecurring = Form.useWatch('is_recurring', form) as boolean | undefined;

  const applyDetail = useCallback((nextDetail: OrchestrationDetail | null) => {
    setDetail(nextDetail);
    if (!nextDetail) return;
    const plan = nextDetail.plan;
    const rawParams = plan?.input_params ?? {};
    const hasParams = Object.keys(rawParams).some((k) => rawParams[k] !== undefined && rawParams[k] !== '' && rawParams[k] !== null);
    const llmSnapshot = nextDetail.llm_recommended_input_params;
    const inputParams = hasParams ? rawParams : (llmSnapshot && typeof llmSnapshot === 'object' ? { ...llmSnapshot } : rawParams);
    const recurrenceUi = parseCronToUi(plan?.recurrence_cron);
    form.setFieldsValue({
      ...inputParams,
      priority: plan?.priority || 'medium',
      estimated_duration_minutes: plan?.estimated_duration_minutes ?? 30,
      start_time: plan?.start_time ? dayjs(plan.start_time) : null,
      deadline: plan?.deadline ? dayjs(plan.deadline) : null,
      is_recurring: !!plan?.is_recurring,
      recurrence_type: recurrenceUi.recurrence_type ?? 'daily',
      recurrence_time: recurrenceUi.recurrence_time ?? dayjs().hour(9).minute(0).second(0),
      recurrence_weekdays: recurrenceUi.recurrence_weekdays ?? [1],
      recurrence_month_day: recurrenceUi.recurrence_month_day ?? 1,
      recurrence_count: plan?.recurrence_count ?? 0,
    });
  }, [form]);

  const loadDetail = useCallback(async () => {
    setDetailLoading(true);
    try {
      const res = await getOrchestration(orch.orch_id);
      const data = (res as { data: { data?: OrchestrationDetail } }).data;
      const d = (data?.data ?? data) as OrchestrationDetail | null;
      applyDetail(d || null);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
      setLoaded(true);
    }
  }, [applyDetail, orch.orch_id]);

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

  useEffect(() => {
    if (!isRecurring) return;
    if (!recurrenceType) return;

    if (recurrenceType === 'weekly') {
      const current = form.getFieldValue('recurrence_weekdays');
      if (!Array.isArray(current) || current.length === 0) {
        form.setFieldValue('recurrence_weekdays', [dayjs().day()]);
      }
    }

    if (recurrenceType === 'monthly') {
      const current = Number(form.getFieldValue('recurrence_month_day'));
      if (!Number.isInteger(current) || current < 1 || current > 31) {
        form.setFieldValue('recurrence_month_day', dayjs().date());
      }
    }
  }, [isRecurring, recurrenceType, form]);

  const buildInputParams = (values: Record<string, unknown>) => {
    const editableKeys = detail?.plan?.editable_input_keys;
    const fallbackKeys = Object.keys(detail?.plan?.input_params || {});
    const paramKeys = Array.isArray(editableKeys) && editableKeys.length > 0
      ? editableKeys
      : fallbackKeys;
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
      const resolvedCron = buildCronFromUi(values);
      const payload = {
        input_params: buildInputParams(values),
        priority: values.priority,
        estimated_duration_minutes: values.estimated_duration_minutes,
        start_time: values.start_time?.toISOString?.(),
        deadline: values.deadline?.toISOString?.(),
        is_recurring: Boolean(values.is_recurring),
        recurrence_cron: values.is_recurring ? resolvedCron : null,
        recurrence_count: values.is_recurring ? Number(values.recurrence_count ?? 0) : 0,
      };
      const res = planType === 'wagent' || planType === 'new_wagent'
        ? await confirmWAgent(orch.orch_id, payload)
        : await confirmOrchestration(orch.orch_id, payload);
      const body = (res as { data: { data?: { recurrence_sync_warning?: string } } }).data;
      const syncWarning = body?.data?.recurrence_sync_warning;
      if (syncWarning) {
        message.warning(syncWarning);
      }
      message.success('已确认执行');
      onRefreshList();
      onConfirmed?.();
    } catch (e) {
      message.error((e as Error).message || '确认失败');
    }
  };

  const handleModifyAgent = async (agentId: string, type: 'agent' | 'wagent') => {
    try {
      const res = await modifyOrchestrationAgent(orch.orch_id, {
        plan_type: type,
        recommended_id: agentId,
      });
      const body = (res as { data: { data?: OrchestrationDetail } }).data;
      const updated = (body?.data ?? body) as OrchestrationDetail | null;
      message.success('已修改');
      setAgentModalOpen(false);
      applyDetail(updated || null);
      onAgentModified?.(orch.orch_id, {
        recommended_name: updated?.plan?.recommended_name || updated?.suggested_agent?.name || updated?.suggested_wagent?.name,
      });
    } catch (e) {
      message.error((e as Error).message || '修改失败');
    }
  };

  const handleModifyParams = async () => {
    try {
      const values = form.getFieldsValue();
      const resolvedCron = buildCronFromUi(values);
      const res = await modifyOrchestrationParams(orch.orch_id, {
        input_params: buildInputParams(values),
        priority: values.priority,
        estimated_duration_minutes: values.estimated_duration_minutes,
        start_time: values.start_time?.toISOString?.(),
        deadline: values.deadline?.toISOString?.(),
        is_recurring: Boolean(values.is_recurring),
        recurrence_cron: values.is_recurring ? resolvedCron : null,
        recurrence_count: values.is_recurring ? Number(values.recurrence_count ?? 0) : 0,
      });
      const body = (res as { data: { data?: { recurrence_sync_warning?: string } } }).data;
      const syncWarning = body?.data?.recurrence_sync_warning;
      if (syncWarning) {
        message.warning(syncWarning);
      }
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
    if (!onRetryStarted) return;
    setRetrying(true);
    try {
      await onRetryStarted(orch);
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
    const selectedType = detail.plan?.plan_type === 'agent' ? 'agent' : 'wagent';
    const selectedId = detail.plan?.recommended_id || detail.suggested_agent?.id || detail.suggested_wagent?.id;
    const isUsingLLMRecommendation = !!selectedId
      && selectedId === detail.llm_recommended_id
      && selectedType === detail.llm_recommended_type;

    if (isUsingLLMRecommendation) {
      return detail.llm_reason || detail.plan?.reason || '';
    }
    return '该Agent由用户自行选择';
  };

  const getExecutorLabel = () => {
    const planType = getPlanType();
    return planType === 'agent' ? 'Agent' : 'W-Agent';
  };

  const isLLMRecommendedOption = (id: string, type: 'agent' | 'wagent') =>
    detail?.llm_recommended_id === id && detail?.llm_recommended_type === type;

  const formatPlanTime = (value?: string | null) => {
    if (!value) return '未设置';
    const parsed = dayjs(value);
    return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm') : value;
  };

  const getRecurrenceText = () => {
    if (!detail?.plan?.is_recurring) return '不循环';
    return `循环执行（cron: ${detail.plan.recurrence_cron || '-'}，已执行 ${detail.plan.recurrence_count ?? 0} 次）`;
  };

  const getFallbackWarning = () => {
    const text = detail?.error || orch.error;
    if (!text) return '';
    if (text.includes('LLM') || text.includes('兜底')) return text;
    return '';
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
        <Space style={{ marginTop: 12 }}>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={retrying}
            onClick={handleRetry}
          >
            重新编排
          </Button>
        </Space>
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
                {getFallbackWarning() && (
                  <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 12 }}
                    message="已自动切换为非 LLM 兜底编排计划"
                    description={getFallbackWarning()}
                  />
                )}
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
                  <Text type="secondary" style={{ marginLeft: 8 }}>({getExecutorLabel()})</Text>
                </div>
                <div style={{ marginBottom: 12 }}>
                  <Text strong>开始时间：</Text>
                  <Text style={{ marginLeft: 8 }}>{formatPlanTime(detail.plan?.start_time)}</Text>
                </div>
                <div style={{ marginBottom: 12 }}>
                  <Text strong>截止时间：</Text>
                  <Text style={{ marginLeft: 8 }}>{formatPlanTime(detail.plan?.deadline)}</Text>
                </div>
                <div style={{ marginBottom: 12 }}>
                  <Text strong>循环：</Text>
                  <Text style={{ marginLeft: 8 }}>{getRecurrenceText()}</Text>
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
              {getFallbackWarning() && (
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message="已自动切换为非 LLM 兜底编排计划"
                  description={getFallbackWarning()}
                />
              )}
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
                <Text type="secondary" style={{ marginLeft: 8 }}>
                  ({getExecutorLabel()})
                </Text>
                {getPlanType() === 'new_wagent' && (
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    (新 W-Agent 编排)
                  </Text>
                )}
              </div>

              <div style={{ marginBottom: 16 }}>
                <Text strong>开始时间：</Text>
                <Text style={{ marginLeft: 8 }}>{formatPlanTime(detail.plan?.start_time)}</Text>
              </div>

              <div style={{ marginBottom: 16 }}>
                <Text strong>截止时间：</Text>
                <Text style={{ marginLeft: 8 }}>{formatPlanTime(detail.plan?.deadline)}</Text>
              </div>

              <div style={{ marginBottom: 16 }}>
                <Text strong>循环：</Text>
                <Text style={{ marginLeft: 8 }}>{getRecurrenceText()}</Text>
              </div>

              <div style={{ marginBottom: 16 }}>
                <Text strong>原因：</Text>
                <Text style={{ marginLeft: 8 }}>{getReason()}</Text>
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
                  <Collapse.Panel header="输入参数" key="input_params" forceRender>
                    {(() => {
                      const baseParams = detail.plan?.input_params || {};
                      const llmParams = detail.llm_recommended_input_params || {};
                      const effectiveParams = Object.keys(baseParams).length > 0 ? baseParams : llmParams;
                      const editableKeys = detail.plan?.editable_input_keys;
                      const renderKeys = Array.isArray(editableKeys) && editableKeys.length > 0
                        ? editableKeys
                        : Object.keys(effectiveParams);
                      if (renderKeys.length === 0) {
                        return <Text type="secondary">该执行器参数由系统自动处理，无需手动填写</Text>;
                      }
                      return (
                        <>
                          {renderKeys.map((key) => (
                            <Form.Item key={key} name={key} label={key}>
                              <Input
                                placeholder={String(effectiveParams[key] ?? '')}
                              />
                            </Form.Item>
                          ))}
                        </>
                      );
                    })()}
                  </Collapse.Panel>

                  <Collapse.Panel header="调度设置" key="scheduling" forceRender>
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
                    <Form.Item name="is_recurring" valuePropName="checked">
                      <Checkbox>循环执行</Checkbox>
                    </Form.Item>
                    <Form.Item noStyle shouldUpdate>
                      {({ getFieldValue }) => !getFieldValue('is_recurring') ? (
                        <>
                          <Form.Item name="start_time" label="开始时间">
                            <DatePicker showTime style={{ width: '100%' }} />
                          </Form.Item>
                          <Form.Item name="deadline" label="截止时间">
                            <DatePicker showTime style={{ width: '100%' }} />
                          </Form.Item>
                        </>
                      ) : null}
                    </Form.Item>
                    <Form.Item noStyle shouldUpdate>
                      {({ getFieldValue }) => {
                        if (!getFieldValue('is_recurring')) return null;
                        const recurrenceType = getFieldValue('recurrence_type');
                        return (
                          <>
                            <Form.Item name="recurrence_type" label="循环方式" rules={[{ required: true, message: '请选择循环方式' }]}>
                              <Select options={RECURRENCE_TYPE_OPTIONS} />
                            </Form.Item>
                            {recurrenceType === 'weekly' && (
                              <Form.Item
                                name="recurrence_weekdays"
                                label="每周几执行"
                                rules={[{ required: true, message: '请选择每周执行日' }]}
                              >
                                <Select mode="multiple" options={WEEKDAY_OPTIONS} />
                              </Form.Item>
                            )}
                            {recurrenceType === 'monthly' && (
                              <Form.Item
                                name="recurrence_month_day"
                                label="每月第几日执行"
                                rules={[{ required: true, message: '请选择每月执行日' }]}
                              >
                                <Select options={MONTH_DAY_OPTIONS} />
                              </Form.Item>
                            )}
                            <Form.Item name="recurrence_time" label="执行时间" rules={[{ required: true, message: '请选择执行时间' }]}>
                              <TimePicker format="HH:mm" minuteStep={5} style={{ width: 200 }} />
                            </Form.Item>
                            <Form.Item name="recurrence_count" label="循环次数（0 = 不限）">
                              <InputNumber min={0} style={{ width: 200 }} />
                            </Form.Item>
                          </>
                        );
                      }}
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
                  icon={<ReloadOutlined />}
                  loading={retrying}
                  onClick={handleRetry}
                >
                  重新编排
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
                {a.name}{isLLMRecommendedOption(a.id, 'agent') ? '（推荐）' : ''}
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
                {w.name}{isLLMRecommendedOption(w.id, 'wagent') ? '（推荐）' : ''}
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
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('all');
  const [orchestrations, setOrchestrations] = useState<OrchestrationItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const { on, off } = useSSE();
  const loadPendingRef = useRef<(() => Promise<void>) | null>(null);

  const patchOrchestration = useCallback((orchId: string, updater: (item: OrchestrationItem) => OrchestrationItem) => {
    setOrchestrations((current) => current.map((item) => (item.orch_id === orchId ? updater(item) : item)));
  }, []);

  const handleAgentModified = useCallback((orchId: string, patch: Partial<OrchestrationItem>) => {
    patchOrchestration(orchId, (item) => ({ ...item, ...patch }));
  }, [patchOrchestration]);

  const handleRetryStarted = useCallback(async (orch: OrchestrationItem) => {
    const previous = { ...orch };
    patchOrchestration(orch.orch_id, (item) => ({
      ...item,
      status: 'analyzing',
      error: undefined,
    }));

    try {
      const res = await retryOrchestration(orch.orch_id);
      const body = (res as { data: { data?: { status?: string; error?: string } } }).data;
      const result = (body?.data ?? body) as { status?: string; error?: string } | undefined;

      if (result?.status) {
        patchOrchestration(orch.orch_id, (item) => ({
          ...item,
          status: result.status ?? item.status,
          error: result.error,
        }));
      }

      if (result?.error) {
        message.error(`重新编排失败: ${result.error}`);
      } else {
        message.success('已重新提交编排');
      }
      loadPendingRef.current?.();
    } catch (e: unknown) {
      patchOrchestration(orch.orch_id, () => previous);
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      message.error(err?.response?.data?.detail || err?.message || '重试失败');
    }
  }, [patchOrchestration]);

  const handleOrchestrationEvent = useCallback((payload: unknown) => {
    const event = payload as { orch_id?: string; status?: string; error?: string; removed?: boolean } | undefined;
    loadPendingRef.current?.();

    if (event?.removed) {
      message.info('已取消的编排记录已移除');
      return;
    }
    if (event?.status === 'pending_confirm') {
      if (event.error) {
        message.warning(`编排分析出现错误：${event.error}`);
      } else {
        message.success('LLM 分析完成，编排已进入待确认');
      }
      return;
    }
    if (event?.status === 'failed') {
      message.warning(`编排分析失败${event.error ? `：${event.error}` : ''}`);
      return;
    }
    if (event?.status === 'completed') {
      message.success('编排执行完成');
    }
  }, []);

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
    on('orchestration_complete', handleOrchestrationEvent);
    return () => off('orchestration_complete', handleOrchestrationEvent);
  }, [handleOrchestrationEvent, on, off]);

  const handleConfirmedNavigate = useCallback(() => {
    navigate(ROUTES.SCHEDULING);
  }, [navigate]);

  const handleBatchConfirm = async () => {
    if (selectedIds.size === 0) return;
    const ids = Array.from(selectedIds);
    let successCount = 0;
    const failedIds: string[] = [];

    for (const orchId of ids) {
      try {
        await confirmOrchestration(orchId);
        successCount += 1;
      } catch {
        failedIds.push(orchId);
      }
    }

    if (successCount > 0) {
      message.success(`已确认 ${successCount} 个任务`);
      await loadPending(); // Refresh list will clear selection
      handleConfirmedNavigate();
    }

    if (failedIds.length > 0) {
      message.error(`有 ${failedIds.length} 个任务确认失败，请重试`);
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
                onConfirmed={handleConfirmedNavigate}
                onRetryStarted={handleRetryStarted}
                onAgentModified={handleAgentModified}
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
      <div style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>智能编排</Title>
      </div>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={items} />
    </div>
  );
}
