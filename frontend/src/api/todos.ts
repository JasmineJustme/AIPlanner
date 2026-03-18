import client from '@/api/client';

export const getTodos = (params?: {
  page?: number;
  size?: number;
  status?: string;
  priority?: string;
  source?: string;
  execution_mode?: string;
}) => client.get('/todos', { params });

export const createTodo = (data: Record<string, unknown>) =>
  client.post('/todos', data);

export const updateTodo = (todoId: string, data: Record<string, unknown>) =>
  client.put(`/todos/${todoId}`, data);

export const completeTodo = (todoId: string) =>
  client.patch(`/todos/${todoId}/complete`);

export const rerunTodo = (todoId: string) =>
  client.post(`/todos/${todoId}/rerun`);

export const deleteTodo = (todoId: string) =>
  client.delete(`/todos/${todoId}`);

export const batchImportTodos = (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  return client.post('/todos/batch-import', formData);
};

export const getReviewPending = () => client.get('/todos/review-pending');

export const confirmReview = (todoId: string, data?: Record<string, unknown>) =>
  client.patch(`/todos/review/${todoId}/confirm`, data);

export const rejectReview = (todoId: string) =>
  client.patch(`/todos/review/${todoId}/reject`);

export const batchConfirmReview = (todoIds: string[]) =>
  client.post('/todos/review/batch-confirm', { todo_ids: todoIds });

export const batchRejectReview = (todoIds: string[]) =>
  client.post('/todos/review/batch-reject', { todo_ids: todoIds });

export const smartDiscoverTodos = () =>
  client.post('/todos/smart-discover', undefined, { timeout: 180000 });
