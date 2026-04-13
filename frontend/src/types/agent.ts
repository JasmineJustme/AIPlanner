import type { ParamDefinition } from './api';

export interface Agent {
  id: string;
  name: string;
  description?: string;
  capability_tags: string[];
  dify_endpoint: string;
  dify_api_key: string;
  input_params: ParamDefinition[];
  timeout_seconds: number;
  auto_execute: boolean;
  confirm_before_exec: boolean;
  is_enabled: boolean;
  call_count: number;
  success_count: number;
  created_at: string;
  updated_at: string;
  user_id: string;
}
