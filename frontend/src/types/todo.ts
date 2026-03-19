export interface Todo {
  id: string;
  title: string;
  description?: string;
  status: string;
  priority: string;
  source: string;
  execution_mode: string;
  source_ref?: string;
  due_date?: string;
  completed_at?: string;
  tags: string[];
  responsibility_ids: string[];
  responsibility_titles: string[];
  project?: string;
  review_status?: string;
  review_reason?: string;
  duplicate_of?: string;
  orchestration_id?: string;
  is_recurring: boolean;
  recurrence_cron?: string;
  recurrence_count: number;
  created_at: string;
  updated_at: string;
}
