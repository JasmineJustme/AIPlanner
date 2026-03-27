import client from '@/api/client';

// Agents
export const getAgents = (params?: { page?: number; size?: number }) =>
  client.get('/config/agents', { params });
export const getAgent = (id: string) => client.get(`/config/agents/${id}`);
export const createAgent = (data: Record<string, unknown>) =>
  client.post('/config/agents', data);
export const updateAgent = (id: string, data: Record<string, unknown>) =>
  client.put(`/config/agents/${id}`, data);
export const deleteAgent = (id: string) => client.delete(`/config/agents/${id}`);
export const toggleAgent = (id: string) =>
  client.patch(`/config/agents/${id}/toggle`);
export const testAgent = (id: string) =>
  client.post(`/config/agents/${id}/test`);

// Workflows
export const getWorkflows = (params?: { page?: number; size?: number }) =>
  client.get('/config/workflows', { params });
export const getWorkflow = (id: string) =>
  client.get(`/config/workflows/${id}`);
export const createWorkflow = (data: Record<string, unknown>) =>
  client.post('/config/workflows', data);
export const updateWorkflow = (id: string, data: Record<string, unknown>) =>
  client.put(`/config/workflows/${id}`, data);
export const deleteWorkflow = (id: string) =>
  client.delete(`/config/workflows/${id}`);
export const toggleWorkflow = (id: string) =>
  client.patch(`/config/workflows/${id}/toggle`);
export const testWorkflow = (id: string) =>
  client.post(`/config/workflows/${id}/test`);

// WAgents
export const getWAgents = (params?: { page?: number; size?: number }) =>
  client.get('/config/wagents', { params });
export const getWAgent = (id: string) => client.get(`/config/wagents/${id}`);
export const createWAgent = (data: Record<string, unknown>) =>
  client.post('/config/wagents', data);
export const updateWAgent = (id: string, data: Record<string, unknown>) =>
  client.put(`/config/wagents/${id}`, data);
export const deleteWAgent = (id: string) =>
  client.delete(`/config/wagents/${id}`);
export const toggleWAgent = (id: string) =>
  client.patch(`/config/wagents/${id}/toggle`);
export const getWAgentVersions = (id: string) =>
  client.get(`/config/wagents/${id}/versions`);
export const getWAgentVersion = (wagentId: string, versionId: string) =>
  client.get(`/config/wagents/${wagentId}/versions/${versionId}`);
export const rollbackWAgent = (wagentId: string, versionId: string) =>
  client.post(`/config/wagents/${wagentId}/rollback/${versionId}`);
export const testWAgent = (id: string) =>
  client.post(`/config/wagents/${id}/test`);

// DataSources
export const getDataSources = () => client.get('/config/datasources');
export const createDataSource = (data: Record<string, unknown>) =>
  client.post('/config/datasources', data);
export const updateDataSource = (dsType: string, data: Record<string, unknown>) =>
  client.put(`/config/datasources/${dsType}`, data);
export const toggleDataSource = (dsType: string) =>
  client.patch(`/config/datasources/${dsType}/toggle`);
export const testDataSource = (dsType: string) =>
  client.post(`/config/datasources/${dsType}/test`);
export const syncDataSource = (dsType: string) =>
  client.post(`/config/datasources/${dsType}/sync`);
export const deleteDataSource = (dsType: string) =>
  client.delete(`/config/datasources/${dsType}`);

// LLM
export const getLLMConfigs = () => client.get('/config/llm');
export const getLLMConfig = (purpose: string) =>
  client.get(`/config/llm/${purpose}`);
export const updateLLMConfig = (
  purpose: string,
  data: Record<string, unknown>
) => client.put(`/config/llm/${purpose}`, data);
export const testLLMConfig = (purpose: string) =>
  client.post(`/config/llm/${purpose}/test`);
export const getLLMUsage = (purpose: string) =>
  client.get(`/config/llm/${purpose}/usage`);

// Notification channels
export const getNotificationChannels = () =>
  client.get('/config/notifications');
export const createNotificationChannel = (data: Record<string, unknown>) =>
  client.post('/config/notifications', data);
export const updateNotificationChannel = (
  channelType: string,
  data: Record<string, unknown>
) => client.put(`/config/notifications/${channelType}`, data);
export const toggleNotificationChannel = (channelType: string) =>
  client.patch(`/config/notifications/${channelType}/toggle`);
export const testNotificationChannel = (channelType: string) =>
  client.post(`/config/notifications/${channelType}/test`);
export const deleteNotificationChannel = (channelType: string) =>
  client.delete(`/config/notifications/${channelType}`);

// Responsibilities
export const getResponsibilities = () => client.get('/config/responsibilities');
export const createResponsibility = (data: Record<string, unknown>) =>
  client.post('/config/responsibilities', data);
export const updateResponsibility = (id: string, data: Record<string, unknown>) =>
  client.put(`/config/responsibilities/${id}`, data);
export const deleteResponsibility = (id: string) =>
  client.delete(`/config/responsibilities/${id}`);

// Import/Export
export const exportConfig = () => client.get('/config/export');

export const previewImport = (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  return client.post('/config/import/preview', formData, { timeout: 60000 });
};
export const importConfig = (
  file: File,
  options?: { sections?: string[]; mode?: 'merge' | 'replace' },
) => {
  const formData = new FormData();
  formData.append('file', file);
  if (options?.sections?.length) {
    formData.append('sections', options.sections.join(','));
  }
  if (options?.mode) {
    formData.append('mode', options.mode);
  }
  return client.post('/config/import', formData, { timeout: 60000 });
};
