import { Card, Col, Row, Typography, Button, Space } from 'antd';
import { useNavigate } from 'react-router-dom';

const { Title, Paragraph } = Typography;

export default function AdminPage() {
  const navigate = useNavigate();

  return (
    <div style={{ padding: 24 }}>
      <Title level={2}>管理员工作台</Title>
      <Paragraph type="secondary">管理员可在此维护员工与部门信息。</Paragraph>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card title="员工信息管理" bordered>
            <Paragraph>支持添加、删除、修改员工账号信息，并按组织单元选择对应主管。</Paragraph>
            <Space>
              <Button type="primary" onClick={() => navigate('/admin/users')}>进入员工管理</Button>
            </Space>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="部门信息管理" bordered>
            <Paragraph>支持添加、删除、修改部门/区段信息，并校验父级关系。</Paragraph>
            <Space>
              <Button type="primary" onClick={() => navigate('/admin/org-units')}>进入部门管理</Button>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
