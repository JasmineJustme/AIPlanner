import { Alert, Button, Card, Form, Input, Modal, Select, Space, Table, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import client from '@/api/client';

interface OrgUnit {
  id: string;
  name: string;
  unit_type: string;
  parent_id?: string | null;
  is_active: boolean;
}

export default function AdminOrgUnitsPage() {
  const [items, setItems] = useState<OrgUnit[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<OrgUnit | null>(null);
  const [form] = Form.useForm();
  const unitType = Form.useWatch('unit_type', form);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await client.get('/accounts/org-units');
      setItems((res as any).data.data);
    } finally { setLoading(false); }
  };

  useEffect(() => { loadData().catch(() => {}); }, []);

  const parents = useMemo(() => items.filter((i) => i.unit_type === 'department'), [items]);
  const parentNameById = useMemo(() => new Map(items.map((item) => [item.id, item.name])), [items]);
  const openCreate = () => { setEditing(null); form.resetFields(); setModalOpen(true); };
  const openEdit = (record: OrgUnit) => { setEditing(record); form.setFieldsValue(record); setModalOpen(true); };
  const save = async () => { const values = await form.validateFields(); editing ? await client.put(`/accounts/org-units/${editing.id}`, values) : await client.post('/accounts/org-units', values); message.success('保存成功'); setModalOpen(false); await loadData(); };
  const remove = async (record: OrgUnit) => { await client.delete(`/accounts/org-units/${record.id}`); message.success('已删除'); await loadData(); };

  return (
    <Card title="部门信息管理" extra={<Button type="primary" onClick={openCreate}>新增部门</Button>}>
      <Alert style={{ marginBottom: 16 }} message="section 必须选择 parent_id，department 不能选择 parent_id" type="info" showIcon />
      <Table rowKey="id" loading={loading} dataSource={items} columns={[
        { title: '名称', dataIndex: 'name' },
        { title: '类型', dataIndex: 'unit_type' },
        { title: '父级', dataIndex: 'parent_id', render: (v) => (v ? parentNameById.get(v) ?? v : '-') },
        { title: '状态', dataIndex: 'is_active', render: (v) => v ? '启用' : '禁用' },
        { title: '操作', render: (_, record) => <Space><Button onClick={() => openEdit(record)}>编辑</Button><Button danger onClick={() => remove(record)}>删除</Button></Space> },
      ]} />

      <Modal open={modalOpen} onCancel={() => setModalOpen(false)} onOk={save} title={editing ? '编辑部门' : '新增部门'}>
        <Form form={form} layout="vertical" initialValues={{ unit_type: 'department', is_active: true }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="unit_type" label="类型" rules={[{ required: true }]}><Select options={[{ value: 'department' }, { value: 'section' }]} /></Form.Item>
          <Form.Item name="parent_id" label="父级部门" rules={unitType === 'section' ? [{ required: true, message: 'section 必须选择父级部门' }] : []}>
            <Select allowClear options={parents.map((p) => ({ value: p.id, label: p.name }))} />
          </Form.Item>
          <Form.Item name="is_active" label="状态"><Select options={[{ value: true, label: '启用' }, { value: false, label: '禁用' }]} /></Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
