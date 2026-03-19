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

export const confirmUserTodo = (todoId: string) =>
  client.patch(`/todos/${todoId}/confirm`);

export const cancelUserTodo = (todoId: string) =>
  client.patch(`/todos/${todoId}/cancel`);

export const rerunTodo = (todoId: string) =>
  client.post(`/todos/${todoId}/rerun`);

export const deleteTodo = (todoId: string) =>
  client.delete(`/todos/${todoId}`);

export const batchImportTodos = (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  return client.post('/todos/batch-import', formData);
};


export const smartDiscoverTodos = () =>
  client.post('/todos/smart-discover', undefined, { timeout: 180000 });
