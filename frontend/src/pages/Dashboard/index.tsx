import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Col, Row, Skeleton, Statistic, Typography } from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import {
  getDashboardStats,
  getNextTask,
  getDashboardTrend,
  getAgentRanking,
  getSyncStatus,
} from '@/api/dashboard';
import { ROUTES } from '@/constants/routes';

const CHART_COLORS = ['#1677ff', '#52c41a', '#faad14', '#ff4d4f', '#722ed1', '#13c2c2'];

interface DashboardStats {
  today_todo?: number;
  pending_confirm?: number;
  running?: number;
  today_completed?: number;
  failed?: number;
}

interface NextTask {
  id?: string;
  name?: string;
  scheduled_at?: string;
  countdown_seconds?: number;
}

interface TrendPoint {
  date?: string;
  count?: number;
}

interface AgentRankItem {
  name?: string;
  count?: number;
}

interface SyncStatusItem {
  id?: string;
  name?: string;
  last_sync?: string;
  status?: 'success' | 'failed' | 'syncing';
}

function extractData<T>(res: unknown): T | null {
  const data = (res as { data?: { data?: T; code?: number } })?.data;
  if (!data || typeof data !== 'object') return null;
  if ('data' in (data as Record<string, unknown>)) {
    return (data as { data?: T | null }).data ?? null;
  }
  return data as T;
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const [statsLoading, setStatsLoading] = useState(true);
  const [nextTaskLoading, setNextTaskLoading] = useState(true);
  const [trendLoading, setTrendLoading] = useState(true);
  const [rankingLoading, setRankingLoading] = useState(true);
  const [syncLoading, setSyncLoading] = useState(true);

  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [nextTask, setNextTask] = useState<NextTask | null>(null);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [ranking, setRanking] = useState<AgentRankItem[]>([]);
  const [syncStatus, setSyncStatus] = useState<SyncStatusItem[]>([]);
  const [countdown, setCountdown] = useState<number | null>(null);

  useEffect(() => {
    const load = async () => {
      setStatsLoading(true);
      try {
        const res = await getDashboardStats();
        const data = extractData<DashboardStats>(res);
        setStats(data ?? null);
      } catch {
        setStats(null);
      } finally {
        setStatsLoading(false);
      }
    };
    load();
  }, []);

  useEffect(() => {
    const load = async () => {
      setNextTaskLoading(true);
      try {
        const res = await getNextTask();
        const data = extractData<NextTask>(res);
        setNextTask(data ?? null);
        if (data?.countdown_seconds != null) {
          setCountdown(data.countdown_seconds);
        }
      } catch {
        setNextTask(null);
      } finally {
        setNextTaskLoading(false);
      }
    };
    load();
  }, []);

  useEffect(() => {
    if (countdown == null || countdown <= 0) return;
    const t = setInterval(() => setCountdown((c) => (c != null && c > 0 ? c - 1 : 0)), 1000);
    return () => clearInterval(t);
  }, [countdown]);

  useEffect(() => {
    const load = async () => {
      setTrendLoading(true);
      try {
        const res = await getDashboardTrend();
        const data = extractData<{ items?: TrendPoint[]; data?: TrendPoint[] }>(res);
        const items = data?.items ?? data?.data ?? (Array.isArray(data) ? data : []);
        setTrend(Array.isArray(items) ? items : []);
      } catch {
        setTrend([]);
      } finally {
        setTrendLoading(false);
      }
    };
    load();
  }, []);

  useEffect(() => {
    const load = async () => {
      setRankingLoading(true);
      try {
        const res = await getAgentRanking();
        const data = extractData<{ items?: AgentRankItem[]; data?: AgentRankItem[] }>(res);
        const items = data?.items ?? data?.data ?? (Array.isArray(data) ? data : []);
        setRanking(Array.isArray(items) ? items : []);
      } catch {
        setRanking([]);
      } finally {
        setRankingLoading(false);
      }
    };
    load();
  }, []);

  useEffect(() => {
    const load = async () => {
      setSyncLoading(true);
      try {
        const res = await getSyncStatus();
        const data = extractData<{ items?: SyncStatusItem[]; data?: SyncStatusItem[] }>(res);
        const items = data?.items ?? data?.data ?? (Array.isArray(data) ? data : []);
        setSyncStatus(Array.isArray(items) ? items : []);
      } catch {
        setSyncStatus([]);
      } finally {
        setSyncLoading(false);
      }
    };
    load();
  }, []);

  const trendOption = {
    color: CHART_COLORS,
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: trend.map((p) => p.date ?? ''),
    },
    yAxis: { type: 'value', name: '完成数' },
    series: [{ name: '完成', type: 'line', data: trend.map((p) => p.count ?? 0), smooth: true }],
  };

  const rankingOption = {
    color: CHART_COLORS,
    tooltip: { trigger: 'axis' },
    grid: { left: '20%', right: '10%', top: 10, bottom: 10 },
    xAxis: { type: 'value' },
    yAxis: {
      type: 'category',
      data: [...ranking].reverse().map((r) => r.name ?? ''),
    },
    series: [
      {
        name: '调用次数',
        type: 'bar',
        data: [...ranking].reverse().map((r) => r.count ?? 0),
      },
    ],
  };

  const statCards = [
    {
      key: 'today_todo',
      title: '今日待办',
      value: stats?.today_todo ?? 0,
      color: '#1677ff',
      icon: <UnorderedListOutlined />,
      route: ROUTES.TODOS,
    },
    {
      key: 'pending_confirm',
      title: '待确认',
      value: stats?.pending_confirm ?? 0,
      color: '#fa8c16',
      icon: <ClockCircleOutlined />,
      route: `${ROUTES.TODOS}?status=pending_confirm`,
    },
    {
      key: 'running',
      title: '调度中',
      value: stats?.running ?? 0,
      color: '#fa8c16',
      icon: <SyncOutlined spin />,
      route: ROUTES.SCHEDULING,
    },
    {
      key: 'today_completed',
      title: '今日完成',
      value: stats?.today_completed ?? 0,
      color: '#52c41a',
      icon: <CheckCircleOutlined />,
      route: `${ROUTES.TODOS}?status=completed`,
    },
    {
      key: 'failed',
      title: '失败',
      value: stats?.failed ?? 0,
      color: '#ff4d4f',
      icon: <CloseCircleOutlined />,
      route: `${ROUTES.SCHEDULING}?status=failed`,
    },
  ];

  const formatCountdown = (s: number) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return [h, m, sec].map((n) => String(n).padStart(2, '0')).join(':');
  };

  return (
    <div>
      <Typography.Title level={3} style={{ marginBottom: 24 }}>
        Dashboard 总览
      </Typography.Title>

      {/* Top row: 5 stat cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {statCards.map((card) => (
          <Col key={card.key} xs={24} sm={12} md={8} lg={6} xl={4}>
            <Card
              hoverable
              onClick={() => navigate(card.route)}
              style={{ borderLeft: `4px solid ${card.color}` }}
            >
              {statsLoading ? (
                <Skeleton active paragraph={{ rows: 1 }} />
              ) : (
                <Statistic
                  title={card.title}
                  value={card.value}
                  prefix={card.icon}
                  valueStyle={{ color: card.color }}
                />
              )}
            </Card>
          </Col>
        ))}
      </Row>

      {/* Second row: 下一个任务 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col span={24}>
          <Card title="下一个任务">
            {nextTaskLoading ? (
              <Skeleton active paragraph={{ rows: 1 }} />
            ) : nextTask ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
                <Typography.Text strong style={{ fontSize: 16 }}>
                  {nextTask.name ?? '未知任务'}
                </Typography.Text>
                {countdown != null && countdown > 0 && (
                  <Typography.Text type="secondary">
                    倒计时: {formatCountdown(countdown)}
                  </Typography.Text>
                )}
              </div>
            ) : (
              <Typography.Text type="secondary">暂无待执行任务</Typography.Text>
            )}
          </Card>
        </Col>
      </Row>

      {/* Third row: Charts */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={12}>
          <Card title="近7天完成趋势">
            {trendLoading ? (
              <Skeleton active paragraph={{ rows: 6 }} />
            ) : (
              <ReactECharts option={trendOption} style={{ height: 300 }} />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Agent调用频次">
            {rankingLoading ? (
              <Skeleton active paragraph={{ rows: 6 }} />
            ) : (
              <ReactECharts option={rankingOption} style={{ height: 300 }} />
            )}
          </Card>
        </Col>
      </Row>

      {/* Fourth row: 数据源同步状态 */}
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Typography.Title level={5} style={{ marginBottom: 12 }}>
            数据源同步状态
          </Typography.Title>
        </Col>
        {syncLoading ? (
          <Col span={24}>
            <Skeleton active paragraph={{ rows: 1 }} />
          </Col>
        ) : syncStatus.length > 0 ? (
          syncStatus.map((s) => (
            <Col key={s.id ?? s.name ?? ''} xs={24} sm={12} md={8}>
              <Card size="small" title={s.name ?? '数据源'}>
                <Typography.Text type="secondary">
                  上次同步: {s.last_sync ?? '-'}
                </Typography.Text>
                <br />
                <Typography.Text
                  type={s.status === 'success' ? 'success' : s.status === 'failed' ? 'danger' : undefined}
                >
                  {s.status === 'success' ? '成功' : s.status === 'failed' ? '失败' : '同步中'}
                </Typography.Text>
              </Card>
            </Col>
          ))
        ) : (
          <Col span={24}>
            <Typography.Text type="secondary">暂无数据源</Typography.Text>
          </Col>
        )}
      </Row>
    </div>
  );
}
