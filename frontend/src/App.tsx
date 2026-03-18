import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import theme from '@/theme/antdTheme';
import AppLayout from '@/components/Layout';
import { lazy, Suspense } from 'react';
import { Spin } from 'antd';

const SetupPage = lazy(() => import('@/pages/Setup'));
const DashboardPage = lazy(() => import('@/pages/Dashboard'));
const TodosPage = lazy(() => import('@/pages/Todos'));
const TodosReviewPage = lazy(() => import('@/pages/Todos/Review'));
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
const SettingsPage = lazy(() => import('@/pages/Settings'));
const SettingsNotificationPrefsPage = lazy(() => import('@/pages/Settings/NotificationPrefs'));
const AuditLogsPage = lazy(() => import('@/pages/AuditLogs'));

function Loading() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
      <Spin size="large" />
    </div>
  );
}

export default function App() {
  return (
    <ConfigProvider theme={theme} locale={zhCN}>
      <BrowserRouter>
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/setup" element={<SetupPage />} />
            <Route element={<AppLayout />}>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />

              <Route path="/todos" element={<TodosPage />} />
              <Route path="/todos/review" element={<TodosReviewPage />} />

              <Route path="/orchestration" element={<OrchestrationPage />} />
              <Route path="/scheduling" element={<SchedulingPage />} />

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
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ConfigProvider>
  );
}
