import client from '@/api/client';

export const getSchedulePlans = () => client.get('/scheduling/plans');

export const getScheduleTasks = (params?: { status?: string; plan_id?: string }) =>
  client.get('/scheduling/tasks', { params });

export const getScheduleTask = (taskId: string) =>
  client.get(`/scheduling/tasks/${taskId}`);

export const pausePlan = (planId: string) =>
  client.post(`/scheduling/plans/${planId}/pause`);

export const resumePlan = (planId: string) =>
  client.post(`/scheduling/plans/${planId}/resume`);

export const cancelPlan = (planId: string) =>
  client.post(`/scheduling/plans/${planId}/cancel`);

export const getGanttData = (params?: { plan_id?: string }) =>
  client.get('/scheduling/gantt', { params });

export const confirmExecute = (taskId: string) =>
  client.post(`/scheduling/tasks/${taskId}/confirm-execute`);

export const delayTask = (taskId: string, data?: { minutes?: number }) =>
  client.post(`/scheduling/tasks/${taskId}/delay`, data ?? { minutes: 30 });

export const skipTask = (taskId: string) =>
  client.post(`/scheduling/tasks/${taskId}/skip`);

export const cancelTask = (taskId: string) =>
  client.post(`/scheduling/tasks/${taskId}/cancel`);

export const retryTask = (taskId: string) =>
  client.post(`/scheduling/tasks/${taskId}/retry`);

export const pauseTask = (taskId: string) =>
  client.post(`/scheduling/tasks/${taskId}/pause`);

export const resumeTask = (taskId: string) =>
  client.post(`/scheduling/tasks/${taskId}/resume-task`);
