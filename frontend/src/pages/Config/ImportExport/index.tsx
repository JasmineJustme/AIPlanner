import { useState } from 'react';
import {
  Card,
  Button,
  Upload,
  message,
  Typography,
  Modal,
  Space,
  Table,
  Checkbox,
  Radio,
  Tag,
  Alert,
  Descriptions,
  Result,
} from 'antd';
import {
  DownloadOutlined,
  UploadOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { exportConfig, previewImport, importConfig } from '@/api/config';

const { Title, Text } = Typography;

interface SectionPreview {
  key: string;
  label: string;
  file_count: number;
  existing_count: number;
  new_count: number;
  update_count: number;
}

interface ImportResult {
  [key: string]: { added: number; updated: number; skipped: number };
}

export default function ConfigImportExportPage() {
  const [previewSections, setPreviewSections] = useState<SectionPreview[]>([]);
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [importMode, setImportMode] = useState<'merge' | 'replace'>('merge');
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [resultModalOpen, setResultModalOpen] = useState(false);

  const handleExport = async () => {
    try {
      const res = await exportConfig();
      const body = (res as { data: unknown }).data;
      const data = (body as { data?: unknown })?.data ?? body;
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-coworker-config-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      message.success('导出成功');
    } catch {
      message.error('导出失败');
    }
  };

  const handlePreview = async () => {
    if (!importFile) {
      message.warning('请先选择文件');
      return;
    }
    setPreviewLoading(true);
    setPreviewModalOpen(true);
    setPreviewSections([]);
    setImportResult(null);
    setImportMode('merge');
    try {
      const res = await previewImport(importFile);
      const body = (res as { data: unknown }).data;
      const payload = (body as { data?: { sections?: SectionPreview[] } })?.data ?? body;
      const sections = (payload as { sections?: SectionPreview[] })?.sections ?? [];
      setPreviewSections(sections);
      const nonEmpty = sections.filter((s) => s.file_count > 0).map((s) => s.key);
      setSelectedKeys(nonEmpty);
    } catch {
      message.error('预览失败');
      setPreviewModalOpen(false);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleConfirmImport = async () => {
    if (!importFile) {
      message.warning('请先选择文件并预览');
      return;
    }
    if (selectedKeys.length === 0) {
      message.warning('请至少选择一个配置分类');
      return;
    }
    setImportLoading(true);
    try {
      const res = await importConfig(importFile, {
        sections: selectedKeys,
        mode: importMode,
      });
      const body = (res as { data: unknown }).data;
      const result = (body as { data?: ImportResult })?.data ?? body;
      setImportResult(result as ImportResult);
      setPreviewModalOpen(false);
      setResultModalOpen(true);
      setImportFile(null);
    } catch {
      message.error('导入失败');
    } finally {
      setImportLoading(false);
    }
  };

  const closePreview = () => {
    setPreviewModalOpen(false);
    setPreviewSections([]);
  };

  const closeResult = () => {
    setResultModalOpen(false);
    setImportResult(null);
  };

  const allNonEmptyKeys = previewSections.filter((s) => s.file_count > 0).map((s) => s.key);
  const isAllSelected = allNonEmptyKeys.length > 0 && allNonEmptyKeys.every((k) => selectedKeys.includes(k));

  const toggleSelectAll = () => {
    if (isAllSelected) {
      setSelectedKeys([]);
    } else {
      setSelectedKeys(allNonEmptyKeys);
    }
  };

  const totalNew = previewSections
    .filter((s) => selectedKeys.includes(s.key))
    .reduce((sum, s) => sum + s.new_count, 0);
  const totalUpdate = previewSections
    .filter((s) => selectedKeys.includes(s.key))
    .reduce((sum, s) => sum + s.update_count, 0);

  const columns = [
    {
      title: (
        <Checkbox
          checked={isAllSelected}
          indeterminate={selectedKeys.length > 0 && !isAllSelected}
          onChange={toggleSelectAll}
        />
      ),
      dataIndex: 'key',
      width: 48,
      render: (_: unknown, record: SectionPreview) => (
        <Checkbox
          checked={selectedKeys.includes(record.key)}
          disabled={record.file_count === 0}
          onChange={(e) => {
            if (e.target.checked) {
              setSelectedKeys((prev) => [...prev, record.key]);
            } else {
              setSelectedKeys((prev) => prev.filter((k) => k !== record.key));
            }
          }}
        />
      ),
    },
    {
      title: '配置分类',
      dataIndex: 'label',
      render: (text: string, record: SectionPreview) => (
        <Space>
          <Text strong>{text}</Text>
          {record.file_count === 0 && (
            <Tag>文件中无数据</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '文件中',
      dataIndex: 'file_count',
      width: 80,
      align: 'center' as const,
    },
    {
      title: '当前系统',
      dataIndex: 'existing_count',
      width: 90,
      align: 'center' as const,
    },
    {
      title: '新增',
      dataIndex: 'new_count',
      width: 70,
      align: 'center' as const,
      render: (v: number) => v > 0 ? <Tag color="green">{v}</Tag> : <Text type="secondary">0</Text>,
    },
    {
      title: '覆盖更新',
      dataIndex: 'update_count',
      width: 90,
      align: 'center' as const,
      render: (v: number) => v > 0 ? <Tag color="orange">{v}</Tag> : <Text type="secondary">0</Text>,
    },
  ];

  const resultColumns = [
    {
      title: '配置分类',
      dataIndex: 'label',
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '新增',
      dataIndex: 'added',
      width: 80,
      align: 'center' as const,
      render: (v: number) => v > 0 ? <Tag color="green">{v}</Tag> : <Text type="secondary">0</Text>,
    },
    {
      title: '更新',
      dataIndex: 'updated',
      width: 80,
      align: 'center' as const,
      render: (v: number) => v > 0 ? <Tag color="blue">{v}</Tag> : <Text type="secondary">0</Text>,
    },
    {
      title: '跳过',
      dataIndex: 'skipped',
      width: 80,
      align: 'center' as const,
      render: (v: number) => v > 0 ? <Tag color="default">{v}</Tag> : <Text type="secondary">0</Text>,
    },
  ];

  const SECTION_LABELS: Record<string, string> = Object.fromEntries(
    [
      ['agents', 'Agent'],
      ['workflows', '工作流'],
      ['wagents', 'W-Agent'],
      ['wagent_versions', 'W-Agent 版本'],
      ['datasources', '数据源'],
      ['llm_configs', 'LLM 配置'],
      ['notification_channels', '通知渠道'],
      ['system_settings', '系统设置'],
      ['notification_prefs', '通知偏好'],
      ['notification_global_prefs', '全局通知偏好'],
    ],
  );

  const resultData = importResult
    ? Object.entries(importResult).map(([key, val]) => ({
        key,
        label: SECTION_LABELS[key] || key,
        ...val,
      }))
    : [];

  const totalAdded = resultData.reduce((s, r) => s + r.added, 0);
  const totalUpdated = resultData.reduce((s, r) => s + r.updated, 0);

  return (
    <div>
      <Title level={3} style={{ marginBottom: 16 }}>
        配置导入/导出
      </Title>

      <Card title="导出配置" style={{ marginBottom: 16 }}>
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          将所有配置（Agent、工作流、W-Agent、数据源、LLM、通知、系统设置）导出为 JSON 文件，可用于备份或迁移。
        </Text>
        <Button
          type="primary"
          icon={<DownloadOutlined />}
          onClick={handleExport}
        >
          导出所有配置
        </Button>
      </Card>

      <Card title="导入配置">
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          上传之前导出的 JSON 配置文件，预览后选择需要导入的分类并确认。
        </Text>
        <Space>
          <Upload
            accept=".json"
            maxCount={1}
            fileList={
              importFile
                ? [
                    {
                      uid: '-1',
                      name: importFile.name,
                      status: 'done' as const,
                    },
                  ]
                : []
            }
            beforeUpload={(file) => {
              setImportFile(file);
              return false;
            }}
            onRemove={() => setImportFile(null)}
          >
            <Button icon={<UploadOutlined />}>选择文件</Button>
          </Upload>
          <Button type="primary" onClick={handlePreview} disabled={!importFile}>
            预览并导入
          </Button>
        </Space>
      </Card>

      <Modal
        title="导入预览"
        open={previewModalOpen}
        onCancel={closePreview}
        width={720}
        footer={[
          <Button key="cancel" onClick={closePreview}>
            取消
          </Button>,
          <Button
            key="import"
            type="primary"
            loading={importLoading}
            onClick={handleConfirmImport}
            disabled={previewLoading || selectedKeys.length === 0}
          >
            确认导入 ({selectedKeys.length} 个分类)
          </Button>,
        ]}
      >
        {previewLoading ? (
          <div style={{ padding: 24, textAlign: 'center' }}>加载中...</div>
        ) : (
          <>
            <div style={{ marginBottom: 16 }}>
              <Text strong>导入模式：</Text>
              <Radio.Group
                value={importMode}
                onChange={(e) => setImportMode(e.target.value)}
                style={{ marginLeft: 12 }}
              >
                <Radio value="merge">
                  合并（已有则更新，没有则新增）
                </Radio>
                <Radio value="replace">
                  替换（清空该分类后重新写入）
                </Radio>
              </Radio.Group>
            </div>

            {importMode === 'replace' && (
              <Alert
                type="warning"
                showIcon
                icon={<InfoCircleOutlined />}
                message="替换模式会先删除所选分类的全部现有数据，再写入文件中的数据，请谨慎操作。"
                style={{ marginBottom: 16 }}
              />
            )}

            <Table
              dataSource={previewSections}
              columns={columns}
              rowKey="key"
              pagination={false}
              size="small"
              style={{ marginBottom: 16 }}
            />

            {importMode === 'merge' && (
              <Descriptions size="small" column={2} bordered>
                <Descriptions.Item label="将新增">
                  <Tag color="green">{totalNew}</Tag> 条记录
                </Descriptions.Item>
                <Descriptions.Item label="将更新">
                  <Tag color="orange">{totalUpdate}</Tag> 条记录
                </Descriptions.Item>
              </Descriptions>
            )}
          </>
        )}
      </Modal>

      <Modal
        title="导入结果"
        open={resultModalOpen}
        onCancel={closeResult}
        width={600}
        footer={[
          <Button key="ok" type="primary" onClick={closeResult}>
            确定
          </Button>,
        ]}
      >
        <Result
          status="success"
          title="导入完成"
          subTitle={`共新增 ${totalAdded} 条，更新 ${totalUpdated} 条`}
          style={{ padding: '16px 0' }}
        />
        <Table
          dataSource={resultData}
          columns={resultColumns}
          rowKey="key"
          pagination={false}
          size="small"
        />
      </Modal>
    </div>
  );
}
