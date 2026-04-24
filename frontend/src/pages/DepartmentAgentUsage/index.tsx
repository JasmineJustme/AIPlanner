import { useEffect, useMemo, useState } from 'react';
import { Alert, Card, Col, DatePicker, Empty, Result, Row, Select, Skeleton, Space, Statistic, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { getDepartmentAgentUsage, type DepartmentAgentUsageResponse } from '@/api/departmentAgentUsage';
import { useAuthStore } from '@/stores/useAuthStore';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

const TOP_N_OPTIONS = [
  { value: 5, label: 'Top 5' },
  { value: 10, label: 'Top 10' },
  { value: 15, label: 'Top 15' },
];

export default function DepartmentAgentUsagePage() {
  const currentUser = useAuthStore((s) => s.currentUser);
  const [loading, setLoading] = useState(false);
  const [range, setRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([dayjs().subtract(30, 'day'), dayjs()]);
  const [topN, setTopN] = useState(10);
  const [data, setData] = useState<DepartmentAgentUsageResponse | null>(null);

  useEffect(() => {
    if (currentUser && currentUser.org_unit_type !== 'department' && !currentUser.is_superuser) {
      setData(null);
      setLoading(false);
      return;
    }
    const load = async () => {
      setLoading(true);
      try {
        const res = await getDepartmentAgentUsage({
          start_date: range[0]?.format('YYYY-MM-DD'),
          end_date: range[1]?.format('YYYY-MM-DD'),
          top_n: topN,
        });
        const body = (res as { data?: { data?: DepartmentAgentUsageResponse } }).data;
        setData((body?.data ?? body) as DepartmentAgentUsageResponse);
      } catch {
        setData(null);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [currentUser, range[0]?.valueOf(), range[1]?.valueOf(), topN]);

  const employeeSeries = data?.matrix.employees ?? [];
  const agentSeries = data?.matrix.agents ?? [];
  const matrixRows = data?.matrix.rows ?? [];

  const matrixOption = useMemo(() => ({
    tooltip: {
      position: 'top',
      formatter: (params: any) => {
        const employee = employeeSeries[params.data[1]];
        const agent = agentSeries[params.data[0]];
        return `${employee?.employee_name ?? ''} / ${agent?.agent_name ?? ''}<br/>使用次数：${params.data[2] ?? 0}`;
      },
    },
    grid: { left: 100, right: 40, top: 40, bottom: 30 },
    xAxis: {
      type: 'category',
      data: agentSeries.map((a) => a.agent_name),
      axisLabel: { rotate: 30 },
      splitArea: { show: true },
    },
    yAxis: {
      type: 'category',
      data: employeeSeries.map((e) => e.employee_name),
      splitArea: { show: true },
    },
    visualMap: {
      min: 0,
      max: Math.max(...matrixRows.flatMap((row) => row.values), 1),
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
    },
    series: [
      {
        name: 'Agent 使用热力图',
        type: 'heatmap',
        data: matrixRows.flatMap((row, yIndex) => row.values.map((value, xIndex) => [xIndex, yIndex, value])),
        label: { show: true },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.3)' } },
      },
    ],
  }), [agentSeries, employeeSeries, matrixRows]);

  const employeeColumns: ColumnsType<typeof data extends DepartmentAgentUsageResponse ? DepartmentAgentUsageResponse['employees'][number] : never> = [
    { title: '员工', dataIndex: 'employee_name', key: 'employee_name' },
    { title: '所属 Section', dataIndex: 'section_name', key: 'section_name' },
    { title: '使用次数', dataIndex: 'usage_count', key: 'usage_count', sorter: (a, b) => a.usage_count - b.usage_count },
    { title: '使用 Agent 数', dataIndex: 'agent_count', key: 'agent_count', sorter: (a, b) => a.agent_count - b.agent_count },
    { title: 'Top Agent', key: 'top_agents', render: (_, record) => (
      <Space wrap>
        {record.top_agents.slice(0, 3).map((item) => <Tag key={item.agent_id}>{item.agent_name} · {item.usage_count}</Tag>)}
      </Space>
    ) },
  ];

  if (currentUser && currentUser.org_unit_type !== 'department' && !currentUser.is_superuser) {
    return <Result status="403" title="无权访问" subTitle="仅 department 账户可查看 Agent 使用情况" />;
  }

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }} align="center">
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>Agent 使用情况</Title>
          <Text type="secondary">统计当前 department 及其 section 用户的 Agent 使用概览</Text>
        </div>
        <Space>
          <RangePicker value={range} onChange={(dates) => dates?.[0] && dates?.[1] && setRange([dates[0], dates[1]])} />
          <Select value={topN} onChange={setTopN} style={{ width: 120 }} options={TOP_N_OPTIONS} />
        </Space>
      </Space>

      {data?.department ? <Alert style={{ marginBottom: 16 }} type="info" showIcon message={`当前组织：${data.department.name}`} /> : null}

      {loading ? <Skeleton active paragraph={{ rows: 8 }} /> : (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col xs={24} sm={12} lg={6}><Card><Statistic title="总使用次数" value={data?.summary.total_usage_count ?? 0} /></Card></Col>
            <Col xs={24} sm={12} lg={6}><Card><Statistic title="使用员工数" value={data?.summary.employee_count ?? 0} /></Card></Col>
            <Col xs={24} sm={12} lg={6}><Card><Statistic title="Agent 数" value={data?.summary.agent_count ?? 0} /></Card></Col>
            <Col xs={24} sm={12} lg={6}><Card><Statistic title="人均使用次数" value={data?.summary.avg_usage_per_employee ?? 0} precision={2} /></Card></Col>
          </Row>

          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col xs={24} xl={12}>
              <Card title="员工使用次数排行">
                {employeeSeries.length ? <ReactECharts option={{ tooltip: { trigger: 'axis' }, xAxis: { type: 'value' }, yAxis: { type: 'category', data: employeeSeries.map((e) => e.employee_name) }, series: [{ type: 'bar', data: employeeSeries.map((e) => e.usage_count) }] }} style={{ height: 360 }} /> : <Empty description="暂无数据" />}
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="Agent 使用次数排行">
                {agentSeries.length ? <ReactECharts option={{ tooltip: { trigger: 'axis' }, xAxis: { type: 'value' }, yAxis: { type: 'category', data: agentSeries.map((a) => a.agent_name) }, series: [{ type: 'bar', data: agentSeries.map((a) => a.usage_count) }] }} style={{ height: 360 }} /> : <Empty description="暂无数据" />}
              </Card>
            </Col>
          </Row>

          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={24}>
              <Card title="员工 × Agent 使用热力图">
                {employeeSeries.length && agentSeries.length ? <ReactECharts option={matrixOption} style={{ height: 440 }} /> : <Empty description="暂无数据" />}
              </Card>
            </Col>
          </Row>

          <Card title="员工统计明细">
            <Table
              rowKey="employee_id"
              dataSource={data?.employees ?? []}
              columns={employeeColumns}
              pagination={{ pageSize: 10, showSizeChanger: true }}
              expandable={{
                expandedRowRender: (record) => (
                  <Space wrap>
                    {record.top_agents.map((item) => (
                      <Tag key={item.agent_id} color="blue">{item.agent_name}：{item.usage_count}</Tag>
                    ))}
                  </Space>
                ),
              }}
            />
          </Card>
        </>
      )}
    </div>
  );
}
