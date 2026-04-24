import client from '@/api/client';

export interface DepartmentAgentUsageEmployee {
  employee_id: string;
  employee_name: string;
  section_name: string;
  usage_count: number;
  agent_count: number;
  top_agents: Array<{ agent_api_key: string; agent_name: string; usage_count: number }>;
  last_used_at?: string | null;
}

export interface DepartmentAgentUsageAgent {
  agent_api_key: string;
  agent_name: string;
  usage_count: number;
  employee_count: number;
}

export interface DepartmentAgentUsageResponse {
  department: { id: string; name: string };
  summary: {
    total_usage_count: number;
    employee_count: number;
    agent_count: number;
    avg_usage_per_employee: number;
  };
  employees: DepartmentAgentUsageEmployee[];
  agents: DepartmentAgentUsageAgent[];
  matrix: {
    employees: DepartmentAgentUsageEmployee[];
    agents: DepartmentAgentUsageAgent[];
    rows: Array<{ employee_id: string; employee_name: string; values: number[] }>;
  };
  links: Array<{ employee_id: string; agent_id: string; value: number }>;
}

export const getDepartmentAgentUsage = (params?: { start_date?: string; end_date?: string; top_n?: number }) =>
  client.get('/department-agent-usage', { params });
