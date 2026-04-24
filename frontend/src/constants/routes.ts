export const ROUTES = {
  ROOT: '/',
  SETUP: '/setup',
  DASHBOARD: '/dashboard',

  TODOS: '/todos',

  ORCHESTRATION: '/orchestration',
  SCHEDULING: '/scheduling',

  HISTORY: '/history',
  HISTORY_ANALYTICS: '/history/analytics',

  CONFIG_AGENTS: '/config/agents',
  CONFIG_AGENTS_NEW: '/config/agents/new',
  CONFIG_AGENTS_DETAIL: '/config/agents/:id',
  CONFIG_WORKFLOWS: '/config/workflows',
  CONFIG_WORKFLOWS_NEW: '/config/workflows/new',
  CONFIG_WORKFLOWS_DETAIL: '/config/workflows/:id',
  CONFIG_WAGENTS: '/config/wagents',
  CONFIG_WAGENTS_NEW: '/config/wagents/new',
  CONFIG_WAGENTS_DETAIL: '/config/wagents/:id',
  CONFIG_WAGENTS_VERSIONS: '/config/wagents/:id/versions',
  CONFIG_DATASOURCES: '/config/datasources',
  CONFIG_LLM: '/config/llm',
  CONFIG_NOTIFICATIONS: '/config/notifications',
  CONFIG_IMPORT_EXPORT: '/config/import-export',
  CONFIG_RESPONSIBILITIES: '/config/responsibilities',
  DEPARTMENT_AGENT_USAGE: '/department-agent-usage',

  MESSAGES: '/messages',

  SETTINGS: '/settings',
  SETTINGS_NOTIFICATION_PREFS: '/settings/notification-prefs',

  AUDIT_LOGS: '/audit-logs',
} as const;
