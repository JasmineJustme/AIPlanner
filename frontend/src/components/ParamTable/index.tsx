import {
  Table,
  Button,
  Input,
  Select,
  Switch,
  Popconfirm,
} from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { useState, useEffect } from 'react';

export interface ParamDefinition {
  name: string;
  type: string;
  required: boolean;
  default?: string;
  description?: string;
}

interface Props {
  value?: ParamDefinition[];
  onChange?: (params: ParamDefinition[]) => void;
  showRequired?: boolean;
  readonly?: boolean;
}

const TYPE_OPTIONS = [
  { value: 'string', label: 'string' },
  { value: 'number', label: 'number' },
  { value: 'boolean', label: 'boolean' },
  { value: 'object', label: 'object' },
  { value: 'array', label: 'array' },
  { value: 'file', label: 'file' },
];

export default function ParamTable({
  value = [],
  onChange,
  showRequired = true,
  readonly = false,
}: Props) {
  const [dataSource, setDataSource] = useState<ParamDefinition[]>([]);

  useEffect(() => {
    setDataSource(value.length > 0 ? [...value] : []);
  }, [value]);

  const handleAdd = () => {
    const newRow: ParamDefinition = {
      name: '',
      type: 'string',
      required: false,
      default: '',
      description: '',
    };
    const next = [...dataSource, newRow];
    setDataSource(next);
    onChange?.(next);
  };

  const handleDelete = (index: number) => {
    const next = dataSource.filter((_, i) => i !== index);
    setDataSource(next);
    onChange?.(next);
  };

  const handleChange = (index: number, field: keyof ParamDefinition, val: unknown) => {
    const next = dataSource.map((row, i) =>
      i === index ? { ...row, [field]: val } : row
    );
    setDataSource(next);
    onChange?.(next);
  };

  const columns = [
    {
      title: '参数名',
      dataIndex: 'name',
      width: 160,
      render: (_: string, __: ParamDefinition, index: number) =>
        readonly ? (
          dataSource[index]?.name
        ) : (
          <Input
            value={dataSource[index]?.name}
            onChange={(e) => handleChange(index, 'name', e.target.value)}
            placeholder="参数名"
          />
        ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 120,
      render: (_: string, __: ParamDefinition, index: number) =>
        readonly ? (
          dataSource[index]?.type
        ) : (
          <Select
            value={dataSource[index]?.type}
            onChange={(v) => handleChange(index, 'type', v)}
            options={TYPE_OPTIONS}
            style={{ width: '100%' }}
          />
        ),
    },
    ...(showRequired
      ? [
          {
            title: '必填',
            dataIndex: 'required',
            width: 80,
            render: (_: boolean, __: ParamDefinition, index: number) =>
              readonly ? (
                dataSource[index]?.required ? '是' : '否'
              ) : (
                <Switch
                  checked={dataSource[index]?.required}
                  onChange={(v) => handleChange(index, 'required', v)}
                />
              ),
          },
        ]
      : []),
    {
      title: '默认值',
      dataIndex: 'default',
      width: 140,
      render: (_: string, __: ParamDefinition, index: number) =>
        readonly ? (
          dataSource[index]?.default ?? '-'
        ) : (
          <Input
            value={dataSource[index]?.default ?? ''}
            onChange={(e) => handleChange(index, 'default', e.target.value)}
            placeholder="默认值"
          />
        ),
    },
    {
      title: '说明',
      dataIndex: 'description',
      width: 180,
      ellipsis: true,
      render: (_: string, __: ParamDefinition, index: number) =>
        readonly ? (
          dataSource[index]?.description ?? '-'
        ) : (
          <Input
            value={dataSource[index]?.description ?? ''}
            onChange={(e) => handleChange(index, 'description', e.target.value)}
            placeholder="说明"
          />
        ),
    },
    ...(!readonly
      ? [
          {
            title: '操作',
            width: 80,
            render: (_: unknown, __: ParamDefinition, index: number) => (
              <Popconfirm
                title="确定删除该参数？"
                onConfirm={() => handleDelete(index)}
              >
                <Button type="link" danger size="small" icon={<DeleteOutlined />}>
                  删除
                </Button>
              </Popconfirm>
            ),
          },
        ]
      : []),
  ];

  return (
    <div>
      <Table
        dataSource={dataSource}
        columns={columns}
        rowKey={(_, i) => String(i)}
        pagination={false}
        size="small"
        tableLayout="fixed"
        scroll={{ x: 'max-content' }}
      />
      {!readonly && (
        <Button
          type="dashed"
          onClick={handleAdd}
          icon={<PlusOutlined />}
          style={{ marginTop: 8 }}
        >
          添加参数
        </Button>
      )}
    </div>
  );
}
