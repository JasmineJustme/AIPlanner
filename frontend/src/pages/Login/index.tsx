import { useEffect, useState } from 'react';
import { App, Button, Card, Form, Input, Typography, Space } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/useAuthStore';
import { ROUTES } from '@/constants/routes';

const { Title, Paragraph } = Typography;

export default function LoginPage() {
  const [mode, setMode] = useState<'user' | 'admin'>('user');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { message } = App.useApp();
  const login = useAuthStore((s) => s.login);
  const currentUser = useAuthStore((s) => s.currentUser);

  useEffect(() => {
    if (currentUser) {
      navigate(ROUTES.DASHBOARD, { replace: true });
    }
  }, [currentUser, navigate]);

  const onFinish = async (values: { email: string; password: string }) => {
    setLoading(true);
    try {
      await login(values.email, values.password, mode);
      message.success(mode === 'admin' ? '管理员登录成功' : '登录成功');
      navigate(mode === 'admin' ? '/admin' : ROUTES.DASHBOARD, { replace: true });
    } catch {
      message.error(mode === 'admin' ? '管理员登录失败，请检查账号、密码和权限' : '登录失败，请检查邮箱和密码');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)', padding: 24 }}>
      <Card style={{ width: 420, borderRadius: 16, boxShadow: '0 20px 60px rgba(0,0,0,0.25)' }}>
        <Title level={3} style={{ textAlign: 'center', marginBottom: 8 }}>Audit Coworker</Title>
        <Paragraph type="secondary" style={{ textAlign: 'center', marginBottom: 24 }}>
          请选择登录身份后输入账户和密码
        </Paragraph>
        <Space style={{ width: '100%', justifyContent: 'center', marginBottom: 20 }}>
          <Button type={mode === 'user' ? 'primary' : 'default'} onClick={() => setMode('user')}>
            用户登录
          </Button>
          <Button type={mode === 'admin' ? 'primary' : 'default'} onClick={() => setMode('admin')}>
            管理员登录
          </Button>
        </Space>
        <Form layout="vertical" onFinish={onFinish}>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }]}>
            <Input autoComplete="email" placeholder="admin@example.com" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password autoComplete="current-password" placeholder="请输入密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            {mode === 'admin' ? '管理员登录' : '登录'}
          </Button>
        </Form>
      </Card>
    </div>
  );
}
