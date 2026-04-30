import {
  DashboardOutlined,
  CheckSquareOutlined,
  RobotOutlined,
  ScheduleOutlined,
  HistoryOutlined,
  SettingOutlined,
  ApiOutlined,
  ApartmentOutlined,
  DatabaseOutlined,
  OpenAIOutlined,
  BellOutlined,
  ImportOutlined,
  ToolOutlined,
  AuditOutlined,
  NotificationOutlined,
  ProfileOutlined,
  PieChartOutlined,
  TeamOutlined,
  MessageOutlined,
} from '@ant-design/icons';
import { ROUTES } from './routes';

export interface MenuItem {
  key: string;
  label: string;
  icon: typeof DashboardOutlined;
  path?: string;
  children?: MenuItem[];
}

export const menuConfig: MenuItem[] = [
  {
    key: 'agent-planner',
    label: 'Agent Planner',
    icon: RobotOutlined,
    children: [
      { key: 'dashboard', label: 'Dashboard 总览', icon: DashboardOutlined, path: ROUTES.DASHBOARD },
      { key: 'todos', label: '待办任务', icon: CheckSquareOutlined, path: ROUTES.TODOS },
      { key: 'orchestration', label: '智能编排', icon: ApartmentOutlined, path: ROUTES.ORCHESTRATION },
      { key: 'scheduling', label: '调度监控', icon: ScheduleOutlined, path: ROUTES.SCHEDULING },
      { key: 'history', label: '执行历史', icon: HistoryOutlined, path: ROUTES.HISTORY },
    ],
  },
  {
    key: 'digital-human-planner',
    label: '数字人 Planner',
    icon: TeamOutlined,
    children: [
      { key: 'digital-human-chat', label: '对话页', icon: MessageOutlined, path: ROUTES.DIGITAL_HUMAN_PLANNER_CHAT },
    ],
  },
  {
    key: 'department-agent-usage',
    label: 'Agent 使用情况',
    icon: PieChartOutlined,
    path: ROUTES.DEPARTMENT_AGENT_USAGE,
  },

];
