import client from '@/api/client';

export const submitOrchestration = (data: Record<string, unknown>) =>
  client.post('/orchestration/submit', data);

export const getPendingOrchestrations = () =>
  client.get('/orchestration/pending');

export const getOrchestration = (orchId: string) =>
  client.get(`/orchestration/${orchId}`);

export const confirmOrchestration = (orchId: string, data?: Record<string, unknown>) =>
  client.post(`/orchestration/${orchId}/confirm`, data);

export const confirmWAgent = (orchId: string, data: Record<string, unknown>) =>
  client.post(`/orchestration/${orchId}/confirm-wagent`, data);

export const modifyOrchestrationAgent = (
  orchId: string,
  data: Record<string, unknown>
) => client.patch(`/orchestration/${orchId}/modify-agent`, data);

export const modifyOrchestrationParams = (
  orchId: string,
  data: Record<string, unknown>
) => client.patch(`/orchestration/${orchId}/modify-params`, data);

export const cancelOrchestration = (orchId: string) =>
  client.post(`/orchestration/${orchId}/cancel`);

export const retryOrchestration = (orchId: string) =>
  client.post(`/orchestration/${orchId}/retry`);
