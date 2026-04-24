import { App as AntdApp, ConfigProvider, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import theme from '@/theme/antdTheme';
import AppLayout from '@/components/Layout';
import { lazy, Suspense, useEffect } from 'react';
import { setAntdMessageApi } from '@/utils/antdFeedback';
import { useAuthStore } from '@/stores/useAuthStore';

const SetupPage = lazy(() => import('@/pages/Setup'));
const LoginPage = lazy(() => import('@/pages/Login'));
const DashboardPage = lazy(() => import('@/pages/Dashboard'));
const TodosPage = lazy(() => import('@/pages/Todos'));
const OrchestrationPage = lazy(() => import('@/pages/Orchestration'));
const SchedulingPage = lazy(() => import('@/pages/Scheduling'));
const HistoryPage = lazy(() => import('@/pages/History'));
const HistoryAnalyticsPage = lazy(() => import('@/pages/History/Analytics'));
const ConfigAgentsPage = lazy(() => import('@/pages/Config/Agents'));
const ConfigAgentsDetailPage = lazy(() => import('@/pages/Config/Agents/Detail'));
const ConfigDataSourcesPage = lazy(() => import('@/pages/Config/DataSources'));
const ConfigLLMPage = lazy(() => import('@/pages/Config/LLM'));
const ConfigNotificationsPage = lazy(() => import('@/pages/Config/Notifications'));
const ConfigImportExportPage = lazy(() => import('@/pages/Config/ImportExport'));
const ConfigResponsibilitiesPage = lazy(() => import('@/pages/Config/Responsibilities'));
const MessagesPage = lazy(() => import('@/pages/Messages'));
const TodoFlowsPage = lazy(() => import('@/pages/TodoFlows'));
const DepartmentAgentUsagePage = lazy(() => import('@/pages/DepartmentAgentUsage'));
const SettingsPage = lazy(() => import('@/pages/Settings'));
const SettingsNotificationPrefsPage = lazy(() => import('@/pages/Settings/NotificationPrefs'));
const AuditLogsPage = lazy(() => import('@/pages/AuditLogs'));
const AdminPage = lazy(() => import('@/pages/Admin'));
const AdminUsersPage = lazy(() => import('@/pages/Admin/Users'));
const AdminOrgUnitsPage = lazy(() => import('@/pages/Admin/OrgUnits'));

function Loading() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
      <Spin size="large" />
    </div>
  );
}

function AntdFeedbackBridge() {
  const { message } = AntdApp.useApp();

  useEffect(() => {
    setAntdMessageApi(message);
  }, [message]);

  return null;
}

function AuthGuard({ children }: { children: React.ReactNode }) {
  const initialized = useAuthStore((s) => s.initialized);
  const currentUser = useAuthStore((s) => s.currentUser);
  const token = useAuthStore((s) => s.token);
  const fetchCurrentUser = useAuthStore((s) => s.fetchCurrentUser);

  useEffect(() => {
    if (!initialized && token) {
      fetchCurrentUser();
    }
  }, [initialized, token, fetchCurrentUser]);

  if (!initialized) return <Loading />;
  if (!currentUser) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <ConfigProvider theme={theme} locale={zhCN}>
      <AntdApp>
        <AntdFeedbackBridge />
        <BrowserRouter>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/setup" element={<SetupPage />} />
              <Route
                element={
                  <AuthGuard>
                    <AppLayout />
                  </AuthGuard>
                }
              >
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<DashboardPage />} />

                <Route path="/todos" element={<TodosPage />} />
                <Route path="/todo-flows" element={<TodoFlowsPage />} />

                <Route path="/orchestration" element={<OrchestrationPage />} />
                <Route path="/scheduling" element={<SchedulingPage />} />
                <Route path="/department-agent-usage" element={<DepartmentAgentUsagePage />} />

                <Route path="/history" element={<HistoryPage />} />
                <Route path="/history/analytics" element={<HistoryAnalyticsPage />} />

                <Route path="/config/agents" element={<ConfigAgentsPage />} />
                <Route path="/config/agents/new" element={<ConfigAgentsDetailPage />} />
                <Route path="/config/agents/:id" element={<ConfigAgentsDetailPage />} />
                <Route path="/config/workflows/*" element={<Navigate to="/config/agents" replace />} />
                <Route path="/config/wagents/*" element={<Navigate to="/config/agents" replace />} />
                <Route path="/config/datasources" element={<ConfigDataSourcesPage />} />
                <Route path="/config/llm" element={<ConfigLLMPage />} />
                <Route path="/config/notifications" element={<ConfigNotificationsPage />} />
                <Route path="/config/import-export" element={<ConfigImportExportPage />} />
                <Route path="/config/responsibilities" element={<ConfigResponsibilitiesPage />} />

                <Route path="/messages" element={<MessagesPage />} />

                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/settings/notification-prefs" element={<SettingsNotificationPrefsPage />} />

                <Route path="/audit-logs" element={<AuditLogsPage />} />
                <Route path="/admin" element={<AdminPage />} />
                <Route path="/admin/users" element={<AdminUsersPage />} />
                <Route path="/admin/org-units" element={<AdminOrgUnitsPage />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AntdApp>
    </ConfigProvider>
  );
}
