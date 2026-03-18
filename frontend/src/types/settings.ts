import type { ParamDefinition } from './api';

export interface SystemSettings {
  [key: string]: any;
}

export interface NotificationPref {
  id: string;
  message_type: string;
  in_app_enabled: boolean;
  email_enabled: boolean;
  wechat_enabled: boolean;
  channel_enabled_map?: Record<string, boolean>;
}

export interface NotificationGlobalPref {
  id: string;
  dnd_start?: string;
  dnd_end?: string;
  merge_strategy: string;
  merge_window_minutes: number;
  deadline_advance_minutes: number;
}

export interface NotificationChannel {
  id: string;
  channel_type: string;
  name: string;
  agent_id?: string;
  dify_endpoint: string;
  dify_api_key: string;
  input_params?: ParamDefinition[];
  input_mapping: Record<string, unknown>;
  message_field?: string | null;
  is_enabled: boolean;
}

export interface DataSource {
  id: string;
  type: string;
  name: string;
  agent_id?: string;
  dify_endpoint: string;
  dify_api_key: string;
  input_params: ParamDefinition[];
  output_params: ParamDefinition[];
  is_enabled: boolean;
  last_sync_at?: string;
  last_sync_status?: string;
  last_sync_error?: string;
}

export interface LLMUsageSummary {
  total_tokens_used: number;
  total_cost: number;
  prompt_version: number;
}

export interface LLMConfig {
  id: string;
  purpose: string;
  provider: string;
  model_name: string;
  api_endpoint: string;
  api_key: string;
  temperature: number;
  temperature_enabled: boolean;
  top_p: number;
  top_p_enabled: boolean;
  max_tokens: number;
  prompt_template: string;
  prompt_version: number;
  total_tokens_used: number;
  total_cost: number;
  cost_alert_threshold?: number;
}
