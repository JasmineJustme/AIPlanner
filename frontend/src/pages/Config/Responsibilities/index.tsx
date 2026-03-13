import { useEffect, useState } from 'react';
import {
  Card,
  Button,
  Space,
  Typography,
  Modal,
  Form,
  Input,
  Empty,
  message,
  Popconfirm,
  Divider,
} from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import {
  createResponsibility,
  deleteResponsibility,
  getResponsibilities,
  updateResponsibility,
} from '@/api/config';

const { Title, Text, Paragraph } = Typography;

interface ResponsibilityNode {
  id: string;
  parent_id?: string | null;
  title: string;
  description: string;
  sort_order: number;
  children: ResponsibilityNode[];
}

export default function ConfigResponsibilitiesPage() {
  const [items, setItems] = useState<ResponsibilityNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [parentId, setParentId] = useState<string | null>(null);
  const [form] = Form.useForm();

  const loadItems = async () => {
    setLoading(true);
    try {
      const res = await getResponsibilities();
      const body = (res as { data: unknown }).data;
      const payload = (body as { data?: ResponsibilityNode[] })?.data ?? body;
      setItems(Array.isArray(payload) ? payload : []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadItems();
  }, []);

  const openCreateRoot = () => {
    setEditingId(null);
    setParentId(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openCreateChild = (pid: string) => {
    setEditingId(null);
    setParentId(pid);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (item: ResponsibilityNode) => {
    setEditingId(item.id);
    setParentId(item.parent_id ?? null);
    form.setFieldsValue({
      title: item.title,
      description: item.description,
      sort_order: item.sort_order,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingId) {
        await updateResponsibility(editingId, {
          title: values.title,
          description: values.description,
          sort_order: Number(values.sort_order ?? 0),
        });
        message.success('更新成功');
      } else {
        await createResponsibility({
          parent_id: parentId,
          title: values.title,
          description: values.description,
          sort_order: Number(values.sort_order ?? 0),
        });
        message.success('创建成功');
      }
      setModalOpen(false);
      form.resetFields();
      loadItems();
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'errorFields' in e) return;
      message.error('保存失败');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteResponsibility(id);
      message.success('已删除');
      loadItems();
    } catch {
      message.error('删除失败');
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>工作职责配置</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateRoot}>新增职责大类</Button>
      </div>

      {items.length === 0 ? (
        <Empty description="暂无工作职责，请先添加职责大类" />
      ) : (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {items.map((category) => (
            <Card
              key={category.id}
              loading={loading}
              title={category.title}
              extra={
                <Space>
                  <Button type="link" onClick={() => openEdit(category)}>编辑</Button>
                  <Button type="link" onClick={() => openCreateChild(category.id)}>新增细化职责</Button>
                  <Popconfirm title="确定删除该职责（含子职责）？" onConfirm={() => handleDelete(category.id)}>
                    <Button type="link" danger>删除</Button>
                  </Popconfirm>
                </Space>
              }
            >
              <Paragraph style={{ marginBottom: 8 }}>{category.description}</Paragraph>
              <Divider style={{ margin: '12px 0' }} />
              {category.children.length === 0 ? (
                <Text type="secondary">暂无细化职责</Text>
              ) : (
                <Space direction="vertical" style={{ width: '100%' }}>
                  {category.children.map((child) => (
                    <Card
                      key={child.id}
                      size="small"
                      title={child.title}
                      extra={
                        <Space>
                          <Button type="link" onClick={() => openEdit(child)}>编辑</Button>
                          <Popconfirm title="确定删除该细化职责？" onConfirm={() => handleDelete(child.id)}>
                            <Button type="link" danger>删除</Button>
                          </Popconfirm>
                        </Space>
                      }
                    >
                      <Paragraph style={{ marginBottom: 0 }}>{child.description}</Paragraph>
                    </Card>
                  ))}
                </Space>
              )}
            </Card>
          ))}
        </Space>
      )}

      <Modal
        title={editingId ? '编辑工作职责' : parentId ? '新增细化职责' : '新增职责大类'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSubmit}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" initialValues={{ sort_order: 0 }}>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input placeholder="请输入职责标题" />
          </Form.Item>
          <Form.Item
            name="description"
            label="详细描述"
            rules={[{ required: true, message: '请输入详细描述' }]}
          >
            <Input.TextArea rows={4} placeholder="请填写详细描述" />
          </Form.Item>
          <Form.Item name="sort_order" label="排序（可选）">
            <Input placeholder="默认 0，数值越小越靠前" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
