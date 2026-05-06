import { Tag } from 'antd';
import {
  MailOutlined,
  CalendarOutlined,
  ProjectOutlined,
  EditOutlined,
  ForkOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { SOURCE_MAP } from '@/constants/status';

const iconMap: Record<string, React.ReactNode> = {
  EditOutlined: <EditOutlined />,
  MailOutlined: <MailOutlined />,
  CalendarOutlined: <CalendarOutlined />,
  ProjectOutlined: <ProjectOutlined />,
  ForkOutlined: <ForkOutlined />,
  TeamOutlined: <TeamOutlined />,
};

interface Props {
  source: string;
}

export default function SourceTag({ source }: Props) {
  const normalizedSource = (source || '').toLowerCase();
  const config = SOURCE_MAP[normalizedSource] || {
    color: '#8c8c8c',
    text: source,
    icon: 'EditOutlined',
  };
  const icon = iconMap[config.icon] ?? <EditOutlined />;
  return (
    <Tag color={config.color} icon={icon}>
      {config.text}
    </Tag>
  );
}
