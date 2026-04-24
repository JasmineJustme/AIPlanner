export interface DispatchableTodo {
  id: string;
  title: string;
  status: string;
  source: string;
  execution_mode: string;
  task_flow_type?: string;
  last_flow_state?: string | null;
  created_at: string;
  current_owner_name?: string;
  target_user_id?: string | null;
}

export interface TodoFlowRecord {
  id: string;
  target_user_name: string;
  created_at: string;
}

export interface CollaborationRecord {
  id: string;
  target_user_name: string;
  status: string;
  created_at: string;
  decided_at?: string;
}

export interface TodoFlowDetail {
  todo_id: string;
  source_type?: string;
  current_status?: string;
  current_owner_name?: string;
  dispatch_records?: TodoFlowRecord[];
  collaboration_records?: CollaborationRecord[];
  history?: Array<{
    id: string;
    action: string;
    operator_name: string;
    target_name?: string;
    created_at: string;
  }>;
}

export interface EligibleTargetUser {
  id: string;
  label: string;
  org_unit_id?: string;
  manager_id?: string;
}
