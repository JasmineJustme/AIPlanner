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
  MessageOutlined,
  ToolOutlined,
  AuditOutlined,
  NotificationOutlined,
  ProfileOutlined,
  PieChartOutlined,
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
    key: 'workspace',
    label: '工作台',
    icon: DashboardOutlined,
    children: [
      { key: 'dashboard', label: 'Dashboard 总览', icon: DashboardOutlined, path: ROUTES.DASHBOARD },
      { key: 'todos', label: '待办任务', icon: CheckSquareOutlined, path: ROUTES.TODOS },
    ],
  },
  {
    key: 'smart',
    label: '智能处理',
    icon: RobotOutlined,
    children: [
      { key: 'orchestration', label: '智能编排', icon: ApartmentOutlined, path: ROUTES.ORCHESTRATION },
      { key: 'scheduling', label: '调度监控', icon: ScheduleOutlined, path: ROUTES.SCHEDULING },
      { key: 'history', label: '执行历史', icon: HistoryOutlined, path: ROUTES.HISTORY },
    ],
  },
  {
    key: 'department-agent-usage',
    label: 'Agent 使用情况',
    icon: PieChartOutlined,
    path: ROUTES.DEPARTMENT_AGENT_USAGE,
  },
  {
    key: 'config',
    label: '配置中心',
    icon: SettingOutlined,
    children: [
      { key: 'config-agents', label: 'Agent 管理', icon: ApiOutlined, path: ROUTES.CONFIG_AGENTS },
      { key: 'config-datasources', label: '数据源配置', icon: DatabaseOutlined, path: ROUTES.CONFIG_DATASOURCES },
      { key: 'config-responsibilities', label: '工作职责配置', icon: ProfileOutlined, path: ROUTES.CONFIG_RESPONSIBILITIES },
      { key: 'config-llm', label: '大模型配置', icon: OpenAIOutlined, path: ROUTES.CONFIG_LLM },
      { key: 'config-notifications', label: '提醒渠道配置', icon: NotificationOutlined, path: ROUTES.CONFIG_NOTIFICATIONS },
      { key: 'config-import-export', label: '配置导入/导出', icon: ImportOutlined, path: ROUTES.CONFIG_IMPORT_EXPORT },
    ],
  },
  {
    key: 'messages',
    label: '消息中心',
    icon: MessageOutlined,
    path: ROUTES.MESSAGES,
  },
  {
    key: 'system',
    label: '系统',
    icon: ToolOutlined,
    children: [
      { key: 'settings', label: '系统设置', icon: SettingOutlined, path: ROUTES.SETTINGS },
      { key: 'audit-logs', label: '操作审计日志', icon: AuditOutlined, path: ROUTES.AUDIT_LOGS },
      { key: 'notification-prefs', label: '提醒偏好设置', icon: BellOutlined, path: ROUTES.SETTINGS_NOTIFICATION_PREFS },
    ],
  },
];
