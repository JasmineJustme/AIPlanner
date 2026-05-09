import { useCallback, useEffect, useMemo, useState } from 'react';
import { Layout, Menu, Badge, Avatar, Dropdown, Button, Segmented } from 'antd';
import ConfirmModal from '@/components/ConfirmModal';
import { useConfirmModal } from '@/hooks/useConfirmModal';
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BellOutlined,
  UserOutlined,
  LogoutOutlined,
  ToolOutlined,
  SettingOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { menuConfig } from '@/constants/menu';
import { useGlobalStore } from '@/stores/useGlobalStore';
import { useNotificationStore } from '@/stores/useNotificationStore';
import { useSSE } from '@/hooks/useSSE';
import { getUnreadCount } from '@/api/messages';
import { ROUTES } from '@/constants/routes';
import SearchBar from '@/components/SearchBar';
import { useAuthStore } from '@/stores/useAuthStore';
import styles from './index.module.css';

const { Header, Sider, Content } = Layout;

type NavMode = 'main' | 'settings' | 'messages';
type SettingsTab = 'config' | 'system';

const adminOnlyMenuItems = [
  {
    key: '/admin',
    icon: <ToolOutlined />,
    label: '管理员工作台',
  },
];

const configMenuItems = [
  { key: ROUTES.CONFIG_AGENTS, icon: <ToolOutlined />, label: 'Agent 管理' },
  { key: ROUTES.CONFIG_DATASOURCES, icon: <ToolOutlined />, label: '数据源配置' },
  { key: ROUTES.CONFIG_RESPONSIBILITIES, icon: <ToolOutlined />, label: '工作职责配置' },
  { key: ROUTES.CONFIG_LLM, icon: <ToolOutlined />, label: '大模型配置' },
  { key: ROUTES.CONFIG_NOTIFICATIONS, icon: <ToolOutlined />, label: '提醒渠道配置' },
  { key: ROUTES.CONFIG_IMPORT_EXPORT, icon: <ToolOutlined />, label: '配置导入/导出' },
];

const systemMenuItems = [
  { key: ROUTES.SETTINGS, icon: <SettingOutlined />, label: '系统设置' },
  { key: ROUTES.AUDIT_LOGS, icon: <ToolOutlined />, label: '操作审计日志' },
  { key: ROUTES.SETTINGS_NOTIFICATION_PREFS, icon: <BellOutlined />, label: '提醒偏好设置' },
];

function buildMenuItems(items: typeof menuConfig): any[] {
  return items.map((item) => {
    const Icon = item.icon;
    if (item.children) {
      return {
        key: item.key,
        icon: <Icon />,
        label: item.label,
        children: item.children.map((child) => {
          const ChildIcon = child.icon;
          return {
            key: child.path || child.key,
            icon: <ChildIcon />,
            label: child.label,
          };
        }),
      };
    }
    return {
      key: item.path || item.key,
      icon: <Icon />,
      label: item.label,
    };
  });
}

function findOpenKeys(pathname: string): string[] {
  for (const group of menuConfig) {
    if (group.children) {
      for (const child of group.children) {
        if (child.path && pathname.startsWith(child.path)) {
          return [group.key];
        }
      }
    }
  }
  return [];
}

const MESSAGE_EVENT_TYPES = [
  'review_new',
  'orchestration_confirm',
  'task_confirm',
  'task_completed',
  'task_failed',
  'deadline_reminder',
  'system',
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { siderCollapsed, toggleSider } = useGlobalStore();
  const { unreadCount, setUnreadCount } = useNotificationStore();
  const { on, off } = useSSE();
  const confirmModal = useConfirmModal();
  const currentUser = useAuthStore((s) => s.currentUser);
  const logout = useAuthStore((s) => s.logout);
  const [openKeys, setOpenKeys] = useState<string[]>(findOpenKeys(location.pathname));
  const [settingsTab, setSettingsTab] = useState<SettingsTab>('config');

  const isAdmin = currentUser?.role === 'admin' || currentUser?.is_superuser;
  const canViewDepartmentAgentUsage = currentUser?.is_superuser || currentUser?.org_unit_type === 'department' || currentUser?.role === 'department';
  const selectedKey = location.pathname;

  const navMode = useMemo<NavMode>(() => {
    if (location.pathname.startsWith('/config/') || location.pathname.startsWith('/settings') || location.pathname.startsWith('/audit-logs')) return 'settings';
    if (location.pathname.startsWith('/messages')) return 'messages';
    return 'main';
  }, [location.pathname]);

  useEffect(() => {
    if (location.pathname.startsWith('/config/')) setSettingsTab('config');
    if (location.pathname.startsWith('/settings') || location.pathname.startsWith('/audit-logs')) setSettingsTab('system');
  }, [location.pathname]);

  const handleMenuClick = ({ key }: { key: string }) => {
    if (key.startsWith('/')) {
      navigate(key);
    }
  };

  const handleOpenChange = (keys: string[]) => {
    setOpenKeys(keys);
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  const syncUnreadCount = useCallback(() => {
    getUnreadCount()
      .then((res) => {
        const body = (res as { data: { data?: { count: number } } }).data;
        const payload = body?.data ?? body;
        const count = (payload as { count?: number })?.count ?? 0;
        setUnreadCount(count);
      })
      .catch(() => {});
  }, [setUnreadCount]);

  useEffect(() => {
    // 切换账号时先清零，避免短暂显示上一个用户的未读数
    setUnreadCount(0);

    if (!currentUser?.id) {
      return;
    }

    syncUnreadCount();
  }, [currentUser?.id, setUnreadCount, syncUnreadCount]);

  useEffect(() => {
    const handler = () => {
      // 通过后端真实值回填，避免本地自增与实际未读数漂移
      syncUnreadCount();
    };

    on('message', handler);
    MESSAGE_EVENT_TYPES.forEach((evt) => on(evt, handler));
    return () => {
      off('message', handler);
      MESSAGE_EVENT_TYPES.forEach((evt) => off(evt, handler));
    };
  }, [on, off, syncUnreadCount]);

  const userMenu = [
    {
      key: 'logout',
      label: '退出登录',
      icon: <LogoutOutlined />,
      onClick: handleLogout,
    },
  ];

  const mainMenuItems = isAdmin
    ? adminOnlyMenuItems
    : buildMenuItems(menuConfig.filter((item) => item.key !== 'department-agent-usage' || canViewDepartmentAgentUsage));

  const settingsItems = settingsTab === 'config' ? configMenuItems : systemMenuItems;

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={siderCollapsed}
        width={220}
        collapsedWidth={60}
        theme="dark"
      >
        <div
          style={{
            height: 56,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontSize: siderCollapsed ? 16 : 18,
            fontWeight: 600,
          }}
        >
          {navMode === 'settings' ? (siderCollapsed ? '设置' : '设置中心') : navMode === 'messages' ? (siderCollapsed ? '消息' : '消息中心') : (siderCollapsed ? 'AP' : 'AI Planner')}
        </div>

        {navMode === 'main' && (
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[selectedKey]}
            openKeys={isAdmin || siderCollapsed ? [] : openKeys}
            onOpenChange={handleOpenChange}
            onClick={handleMenuClick}
            items={mainMenuItems}
          />
        )}

        {navMode === 'settings' && (
          <>
            {!siderCollapsed && (
              <div className={styles.settingsTabsWrap}>
                <Segmented
                  block
                  size="middle"
                  value={settingsTab}
                  onChange={(v) => setSettingsTab(v as SettingsTab)}
                  options={[
                    { label: '配置中心', value: 'config' },
                    { label: '系统', value: 'system' },
                  ]}
                />
              </div>
            )}
            <Menu
              theme="dark"
              mode="inline"
              selectedKeys={[selectedKey]}
              onClick={handleMenuClick}
              items={settingsItems}
            />
          </>
        )}

        {navMode === 'messages' && (
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[selectedKey]}
            onClick={handleMenuClick}
            items={[{ key: ROUTES.MESSAGES, icon: <BellOutlined />, label: '消息中心' }]}
          />
        )}
      </Sider>
      <Layout>
        <Header className={styles.header} style={{ background: '#fff' }}>
          <div className={styles.headerLeft}>
            <span className={styles.siderTrigger} onClick={toggleSider}>
              {siderCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            </span>
            {navMode !== 'main' && (
              <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate(ROUTES.DASHBOARD)}>
                返回主页
              </Button>
            )}
            {!isAdmin && navMode === 'main' && <SearchBar />}
          </div>
          <div className={styles.headerRight}>
            <SettingOutlined style={{ fontSize: 18, cursor: 'pointer' }} onClick={() => navigate(ROUTES.CONFIG_AGENTS)} />
            <Badge count={unreadCount} size="small">
              <BellOutlined style={{ fontSize: 18, cursor: 'pointer' }} onClick={() => navigate(ROUTES.MESSAGES)} />
            </Badge>
            <Dropdown
              menu={{ items: userMenu as any }}
              trigger={['click']}
              placement="bottomRight"
            >
              <Button type="text" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Avatar size="small" icon={<UserOutlined />} />
                {!siderCollapsed && <span>{currentUser?.username ?? '用户'}</span>}
              </Button>
            </Dropdown>
          </div>
        </Header>
        <Content className={styles.content}>
          <Outlet />
        </Content>
      </Layout>
      <ConfirmModal
        visible={confirmModal.visible}
        task={confirmModal.task}
        onConfirm={confirmModal.onConfirm}
        onDelay={confirmModal.onDelay}
        onCancel={confirmModal.onCancel}
        onClose={confirmModal.onClose}
      />
    </Layout>
  );
}
