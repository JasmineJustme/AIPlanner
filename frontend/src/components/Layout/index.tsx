import { useState, useEffect } from 'react';
import { Layout, Menu, Badge, Avatar } from 'antd';
import ConfirmModal from '@/components/ConfirmModal';
import { useConfirmModal } from '@/hooks/useConfirmModal';
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BellOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { menuConfig } from '@/constants/menu';
import { useGlobalStore } from '@/stores/useGlobalStore';
import { useNotificationStore } from '@/stores/useNotificationStore';
import { useSSE } from '@/hooks/useSSE';
import { getUnreadCount } from '@/api/messages';
import { ROUTES } from '@/constants/routes';
import SearchBar from '@/components/SearchBar';
import styles from './index.module.css';

const { Header, Sider, Content } = Layout;

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
  const { unreadCount, setUnreadCount, incrementUnread } = useNotificationStore();
  const { on, off } = useSSE();
  const confirmModal = useConfirmModal();
  const [openKeys, setOpenKeys] = useState<string[]>(
    findOpenKeys(location.pathname),
  );

  const selectedKey = location.pathname;

  const handleMenuClick = ({ key }: { key: string }) => {
    if (key.startsWith('/')) {
      navigate(key);
    }
  };

  const handleOpenChange = (keys: string[]) => {
    setOpenKeys(keys);
  };

  useEffect(() => {
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
    const handler = () => incrementUnread();
    on('message', handler);
    MESSAGE_EVENT_TYPES.forEach((evt) => on(evt, handler));
    return () => {
      off('message', handler);
      MESSAGE_EVENT_TYPES.forEach((evt) => off(evt, handler));
    };
  }, [on, off, incrementUnread]);

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
          {siderCollapsed ? 'AC' : 'Audit Coworker'}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          openKeys={siderCollapsed ? [] : openKeys}
          onOpenChange={handleOpenChange}
          onClick={handleMenuClick}
          items={buildMenuItems(menuConfig)}
        />
      </Sider>
      <Layout>
        <Header className={styles.header} style={{ background: '#fff' }}>
          <div className={styles.headerLeft}>
            <span className={styles.siderTrigger} onClick={toggleSider}>
              {siderCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            </span>
            <SearchBar />
          </div>
          <div className={styles.headerRight}>
            <Badge count={unreadCount} size="small">
              <BellOutlined
                style={{ fontSize: 18, cursor: 'pointer' }}
                onClick={() => navigate(ROUTES.MESSAGES)}
              />
            </Badge>
            <Avatar size="small" icon={<UserOutlined />} />
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
