import { Card, Typography } from 'antd';

const { Title, Paragraph } = Typography;

export default function DigitalHumanPlannerChatPage() {
  return (
    <Card>
      <Title level={4}>数字人 Planner - 对话页</Title>
      <Paragraph type="secondary" style={{ marginBottom: 0 }}>
        该页面当前为接口预留页，后续将补充数字人 Planner 对话能力。
      </Paragraph>
    </Card>
  );
}
