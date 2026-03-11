export interface SchedulePlan {
  id: string;
  name: string;
  status: string;
  is_recurring: boolean;
  recurrence_cron?: string;
  recurrence_count: number;
  next_run_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ScheduleTask {
  id: string;
  plan_id: string;
  plan_name?: string;
  task_title?: string;
  orchestration_id: string;
  agent_id?: string;
  wagent_id?: string;
  agent_name?: string;
  wagent_version?: number;
  status: string;
  priority: string;
  scheduled_at: string;
  started_at?: string;
  completed_at?: string;
  input_params?: Record<string, unknown>;
  output_result?: unknown;
  error_message?: string;
  retry_count: number;
  max_retries: number;
  dependencies: string[];
  confirm_deadline?: string;
  confirm_action?: string;
  execution_log?: string;
  created_at: string;
  updated_at: string;
}
