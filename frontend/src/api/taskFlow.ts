import client from '@/api/client';

export const getDispatchableTodos = (params?: { page?: number; size?: number }) =>
  client.get('/todo-flows/dispatchable', { params });

export const getEligibleTargetUsers = (action: 'dispatch' | 'collaboration' = 'collaboration') =>
  client.get('/todo-flows/eligible-target-users', { params: { action } });

export const batchDispatchTodos = (data: {
  todo_ids: string[];
  target_user_id: string;
  action: 'dispatch' | 'collaboration';
}) => client.post('/todo-flows/batch-action', data);

export const getTodoFlowDetail = (todoId: string) => client.get(`/todo-flows/${todoId}`);

export const getManagedFlowTodos = (params?: { page?: number; size?: number }) =>
  client.get('/todo-flows/managed', { params });

export const getDispatchMessages = (params?: { page?: number; size?: number }) =>
  client.get('/todo-flows/dispatch-messages', { params });

export const getCollaborateRequests = (params?: { page?: number; size?: number }) =>
  client.get('/todo-flows/collaboration-requests', { params });

export const acceptCollaborateRequest = (requestId: string) =>
  client.post(`/todo-flows/collaboration-requests/${requestId}/accept`);

export const rejectCollaborateRequest = (requestId: string, data?: { reason?: string }) =>
  client.post(`/todo-flows/collaboration-requests/${requestId}/reject`, data);
