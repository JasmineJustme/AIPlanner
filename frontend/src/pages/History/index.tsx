import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Button,
  DatePicker,
  Input,
  Select,
  Space,
  Table,
  Typography,
  message,
} from 'antd';
import { ExportOutlined, BarChartOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { saveAs } from 'file-saver';
import {
  getHistory,
  getHistoryDetail,
  exportHistory,
} from '@/api/history';
import StatusTag from '@/components/StatusTag';
import JsonViewer from '@/components/JsonViewer';
import { formatDate, formatDuration } from '@/utils/format';
import { ROUTES } from '@/constants/routes';
import { STATUS_TAG_MAP } from '@/constants/status';

const STATUS_OPTIONS = Object.entries(STATUS_TAG_MAP).map(([k, v]) => ({
  value: k,
  label: v.text,
}));

interface HistoryItem {
  id?: string;
  task_id?: string;
  agent_id?: string;
  agent_name?: string;
  wagent_id?: string;
  wagent_name?: string;
  status?: string;
  input_params?: Record<string, unknown> | string;
  output_result?: unknown;
  error_message?: string;
  execution_log?: string;
  tokens_used?: number;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  [key: string]: unknown;
}

function extractData<T>(res: unknown): T | null {
  const body = (res as { data?: { data?: T } })?.data;
  if (!body || typeof body !== 'object') return null;
  return (body as { data?: T }).data ?? (body as T);
}

function truncate(str: string, len: number) {
  if (!str || str.length <= len) return str ?? '-';
  return str.slice(0, len) + '...';
}

function formatInputParamsPreview(inputParams?: Record<string, unknown> | string) {
  if (inputParams === null || inputParams === undefined) return '-';
  if (typeof inputParams === 'string') {
    const trimmed = inputParams.trim();
    if (!trimmed) return '-';
    return truncate(trimmed, 50);
  }

  const keys = Object.keys(inputParams);
  if (keys.length === 0) return '{}';
  return truncate(JSON.stringify(inputParams, null, 0), 50);
}

export default function HistoryPage() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<{ items: HistoryItem[]; total: number; page: number; size: number }>({
    items: [],
    total: 0,
    page: 1,
    size: 20,
  });
  const [filters, setFilters] = useState<{
    start_time?: string;
    end_time?: string;
    keyword?: string;
    status?: string;
  }>({});
  const [detailRecords, setDetailRecords] = useState<Record<string, HistoryItem>>({});
  const [detailLoadingId, setDetailLoadingId] = useState<string | null>(null);
  const [exportLoading, setExportLoading] = useState(false);

  const formatTokenCount = useCallback((value?: number) => {
    if (!value) return '0';
    return new Intl.NumberFormat('zh-CN').format(value);
  }, []);

  const loadHistory = async () => {
    setLoading(true);
    try {
      const res = await getHistory({
        page: data.page,
        size: data.size,
        status: filters.status || undefined,
        start_time: filters.start_time,
        end_time: filters.end_time,
        keyword: filters.keyword,
      });
      const payload = extractData<{ items?: HistoryItem[]; total?: number; page?: number; size?: number }>(res);
      const items = payload?.items ?? [];
      const total = payload?.total ?? 0;
      const page = payload?.page ?? 1;
      const size = payload?.size ?? 20;
      setData({ items: Array.isArray(items) ? items : [], total, page, size });
    } catch {
      setData((d) => ({ ...d, items: [] }));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, [data.page, data.size, filters.status, filters.start_time, filters.end_time, filters.keyword]);

  const loadHistoryDetail = useCallback(async (record: HistoryItem) => {
    if (!record.id || detailRecords[record.id]) return;
    setDetailLoadingId(record.id);
    try {
      const res = await getHistoryDetail(record.id);
      const full = extractData<HistoryItem>(res);
      if (full?.id) {
        setDetailRecords((current) => ({ ...current, [full.id as string]: full }));
      }
    } catch {
      message.error('获取详情失败');
    } finally {
      setDetailLoadingId((current) => (current === record.id ? null : current));
    }
  }, [detailRecords]);

  const handleExport = async () => {
    setExportLoading(true);
    try {
      const res = await exportHistory({
        start_time: filters.start_time,
        end_time: filters.end_time,
      });
      const blob = (res as { data?: Blob }).data;
      if (blob instanceof Blob) {
        saveAs(blob, `history-export-${dayjs().format('YYYY-MM-DD-HHmm')}.xlsx`);
        message.success('导出成功');
      } else {
        message.error('导出失败');
      }
    } catch {
      message.error('导出失败');
    } finally {
      setExportLoading(false);
    }
  };

  const columns: ColumnsType<HistoryItem> = [
    {
      title: 'Agent名称',
      key: 'agent_name',
      render: (_, r) => r.wagent_name || r.agent_name || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string) => (s ? <StatusTag status={s} /> : '-'),
    },
    {
      title: '输入参数',
      key: 'input_params',
      ellipsis: true,
      render: (_, r) => formatInputParamsPreview(r.input_params),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 160,
      render: (d: string) => formatDate(d),
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 90,
      render: (ms: number) => formatDuration(ms),
    },
  ];

  const expandedRowRender = (record: HistoryItem) => {
    const detail = (record.id && detailRecords[record.id]) || record;
    const isLoading = detailLoadingId === record.id;

    return (
      <div style={{ padding: '8px 24px' }}>
        <div style={{ marginBottom: 12, display: 'flex', flexWrap: 'wrap', gap: 16 }}>
          <Typography.Text><strong>任务ID：</strong>{detail.task_id || '-'}</Typography.Text>
          <Typography.Text><strong>执行器：</strong>{detail.wagent_name || detail.agent_name || '-'}</Typography.Text>
          <Typography.Text><strong>状态：</strong>{detail.status ? <StatusTag status={detail.status} /> : '-'}</Typography.Text>
        </div>
        <div style={{ marginBottom: 12, display: 'flex', flexWrap: 'wrap', gap: 16 }}>
          <Typography.Text><strong>开始时间：</strong>{formatDate(detail.started_at)}</Typography.Text>
          <Typography.Text><strong>完成时间：</strong>{formatDate(detail.completed_at)}</Typography.Text>
          <Typography.Text><strong>耗时：</strong>{formatDuration(detail.duration_ms)}</Typography.Text>
          <Typography.Text><strong>Token 使用量：</strong>{formatTokenCount(detail.tokens_used)}</Typography.Text>
        </div>
        <div style={{ marginBottom: 12 }}>
          <strong>输入参数：</strong>
          <JsonViewer data={detail.input_params ?? {}} />
        </div>
        <div style={{ marginBottom: 12 }}>
          <strong>输出结果：</strong>
          <JsonViewer data={detail.output_result ?? {}} />
        </div>
        {detail.execution_log && (
          <div style={{ marginBottom: 12 }}>
            <strong>执行日志：</strong>
            <pre
              style={{
                background: '#f5f5f5',
                padding: 12,
                borderRadius: 4,
                fontSize: 12,
                margin: 0,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                overflowWrap: 'anywhere',
              }}
            >
              {detail.execution_log}
            </pre>
          </div>
        )}
        {detail.error_message && (
          <div>
            <strong>错误信息：</strong>
            <pre
              style={{
                background: '#fff2f0',
                padding: 12,
                borderRadius: 4,
                fontSize: 12,
                color: '#cf1322',
                margin: 0,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                overflowWrap: 'anywhere',
              }}
            >
              {detail.error_message}
            </pre>
          </div>
        )}
        {isLoading && (
          <Typography.Text type="secondary" style={{ display: 'block', marginTop: 12 }}>
            正在加载完整执行详情...
          </Typography.Text>
        )}
      </div>
    );
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          执行历史
        </Typography.Title>
        <Space>
          <Link to={ROUTES.HISTORY_ANALYTICS}>
            <Button icon={<BarChartOutlined />}>数据分析</Button>
          </Link>
          <Button
            icon={<ExportOutlined />}
            onClick={handleExport}
            loading={exportLoading}
          >
            导出
          </Button>
        </Space>
      </div>

      <Space style={{ marginBottom: 16 }} wrap>
        <DatePicker.RangePicker
          placeholder={['开始时间', '结束时间']}
          showTime
          onChange={(dates) =>
            setFilters((f) => ({
              ...f,
              start_time: dates?.[0]?.toISOString(),
              end_time: dates?.[1]?.toISOString(),
            }))
          }
        />
        <Input.Search
          placeholder="Agent/W-Agent 名称"
          allowClear
          style={{ width: 200 }}
          onSearch={(v) => setFilters((f) => ({ ...f, keyword: v || undefined }))}
        />
        <Select
          placeholder="状态"
          allowClear
          style={{ width: 120 }}
          value={filters.status}
          onChange={(v) => setFilters((f) => ({ ...f, status: v }))}
          options={STATUS_OPTIONS}
        />
      </Space>

      <Table
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={data.items}
        expandable={{
          expandedRowRender,
          rowExpandable: () => true,
          onExpand: (expanded, record) => {
            if (expanded) {
              void loadHistoryDetail(record);
            }
          },
        }}
        pagination={{
          current: data.page,
          pageSize: data.size,
          total: data.total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, s) => setData((d) => ({ ...d, page: p, size: s ?? 20 })),
        }}
      />
    </div>
  );
}
