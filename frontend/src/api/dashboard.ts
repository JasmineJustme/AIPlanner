import client from '@/api/client';

export const getDashboardStats = () => client.get('/dashboard/stats');

export const getNextTask = () => client.get('/dashboard/next-task');

export const getDashboardTrend = () => client.get('/dashboard/trend');

export const getAgentRanking = () => client.get('/dashboard/agent-ranking');
