import client from '@/api/client';

export const getSettings = () => client.get('/settings');

export const updateSettings = (settings: Record<string, unknown>) =>
  client.put('/settings', { settings });

export const getNotificationPrefs = () =>
  client.get('/settings/notification-prefs');

export const updateNotificationPref = (data: {
  message_type: string;
  in_app_enabled?: boolean;
  email_enabled?: boolean;
  wechat_enabled?: boolean;
  channel_enabled_map?: Record<string, boolean>;
}) => client.put('/settings/notification-prefs', data);

export const getNotificationGlobal = () =>
  client.get('/settings/notification-global');

export const updateNotificationGlobal = (data: Record<string, unknown>) =>
  client.put('/settings/notification-global', data);
