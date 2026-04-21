import { Alert, Button, Card, Form, Input, Modal, Select, Space, Table, Tag, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import client from '@/api/client';

interface OrgUnit {
  id: string;
  name: string;
  unit_type: string;
  parent_id?: string | null;
}

interface User {
  id: string;
  username: string;
  email: string;
  full_name?: string | null;
  role: string;
  org_unit_id?: string | null;
  manager_id?: string | null;
  is_active: boolean;
  is_superuser: boolean;
}

export default function AdminUsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [orgUnits, setOrgUnits] = useState<OrgUnit[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [form] = Form.useForm();
  const orgUnitId = Form.useWatch('org_unit_id', form);

  const loadData = async () => {
    setLoading(true);
    try {
      const [uRes, oRes] = await Promise.all([client.get('/accounts/users'), client.get('/accounts/org-units')]);
      setUsers((uRes as any).data.data);
      setOrgUnits((oRes as any).data.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData().catch(() => {}); }, []);

  const managers = useMemo(() => users.filter((u) => u.org_unit_id === orgUnitId), [users, orgUnitId]);
  const orgUnitNameById = useMemo(() => new Map(orgUnits.map((item) => [item.id, item.name])), [orgUnits]);
  const managerLabelById = useMemo(() => new Map(users.map((item) => [item.id, `${item.username} / ${item.email}`])), [users]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ role: 'member', is_active: true, manager_id: undefined, password: '' });
    setModalOpen(true);
  };
  const openEdit = (record: User) => {
    setEditing(record);
    form.setFieldsValue({ ...record, password: '' });
    setModalOpen(true);
  };

  const formatErrorDetail = (detail: unknown) => {
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          const loc = Array.isArray(item?.loc) ? item.loc.filter(Boolean).join('.') : '';
          return loc ? `${loc}: ${item?.msg ?? '校验失败'}` : (item?.msg ?? '校验失败');
        })
        .join('；');
    }
    if (detail && typeof detail === 'object') {
      return JSON.stringify(detail);
    }
    return '';
  };

  const save = async () => {
    try {
      const values = await form.validateFields();
      const payload = { ...values, is_active: values.is_active ?? true };
      console.log('[AdminUsers] submit payload', payload);
      if (editing) await client.put(`/accounts/users/${editing.id}`, payload);
      else await client.post('/accounts/users', payload);
      message.success('保存成功');
      setModalOpen(false);
      await loadData();
    } catch (error: any) {
      const detail = formatErrorDetail(error?.response?.data?.detail);
      if (detail) {
        if (detail.includes('邮箱已存在')) {
          form.setFields([{ name: 'email', errors: ['邮箱已存在'] }]);
        }
        if (detail.includes('密码至少 8 位')) {
          form.setFields([{ name: 'password', errors: ['密码至少 8 位'] }]);
        }
        if (detail.includes('请选择组织单元')) {
          form.setFields([{ name: 'org_unit_id', errors: ['请选择组织单元'] }]);
        }
        if (detail.includes('请选择角色')) {
          form.setFields([{ name: 'role', errors: ['请选择角色'] }]);
        }
        message.error(detail);
      } else if (error?.errorFields) {
        message.error('请先完善表单必填项');
      } else {
        message.error('保存失败，请稍后重试');
      }
      console.error('保存员工失败', error);
    }
  };

  const remove = async (record: User) => {
    await client.delete(`/accounts/users/${record.id}`);
    message.success('已禁用');
    await loadData();
  };

  return (
    <Card title="员工信息管理" extra={<Button type="primary" onClick={openCreate}>新增员工</Button>}>
      <Alert style={{ marginBottom: 16 }} message="邮箱会校验唯一性；manager 可为空，若填写则必须属于同一 org-unit。保存失败时会把错误定位到具体输入框。" type="info" showIcon />
      <Table loading={loading} rowKey="id" dataSource={users} columns={[
        { title: '用户名', dataIndex: 'username' },
        { title: '邮箱', dataIndex: 'email' },
        { title: '角色', dataIndex: 'role', render: (v) => <Tag>{v}</Tag> },
        { title: '组织单元', dataIndex: 'org_unit_id', render: (v) => (v ? orgUnitNameById.get(v) ?? v : '-') },
        { title: '主管', dataIndex: 'manager_id', render: (v) => (v ? managerLabelById.get(v) ?? v : '-') },
        { title: '状态', dataIndex: 'is_active', render: (v) => v ? '启用' : '禁用' },
        { title: '操作', render: (_, record) => <Space><Button onClick={() => openEdit(record)}>编辑</Button><Button danger onClick={() => remove(record)}>禁用</Button></Space> },
      ]} />

      <Modal open={modalOpen} onCancel={() => setModalOpen(false)} onOk={save} confirmLoading={loading} okText="确定" cancelText="取消" title={editing ? '编辑员工' : '新增员工'}>
        <Form form={form} layout="vertical" initialValues={{ role: 'member', is_active: true }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}><Input /></Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }, { type: 'email', message: '请输入正确的邮箱格式' }]}><Input /></Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={editing ? [] : [{ required: true, message: '请输入密码' }, { min: 8, message: '密码至少 8 位' }]}
          >
            <Input.Password placeholder={editing ? '留空表示不修改密码' : '请输入至少 8 位密码'} />
          </Form.Item>
          <Form.Item name="full_name" label="姓名"><Input /></Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true, message: '请选择角色' }]}><Select options={[{ value: 'member' }, { value: 'admin' }]} /></Form.Item>
          <Form.Item name="org_unit_id" label="组织单元" rules={[{ required: true, message: '请选择组织单元' }]}><Select options={orgUnits.map((o) => ({ value: o.id, label: `${o.name} (${o.unit_type})` }))} /></Form.Item>
          <Form.Item name="manager_id" label="主管">
            <Select allowClear placeholder="可选" options={managers.map((m) => ({ value: m.id, label: `${m.username} / ${m.email}` }))} />
          </Form.Item>
          <Form.Item name="is_active" label="状态"><Select options={[{ value: true, label: '启用' }, { value: false, label: '禁用' }]} /></Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
