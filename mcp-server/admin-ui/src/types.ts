export interface AdminMe {
  username: string
  must_change_password: boolean
  locale?: string | null
}

export interface CallerItem {
  caller_id: string
  name: string
  api_key?: string
  api_key_prefix?: string
  api_key_suffix?: string
  default_postprocess_rule_id?: string | null
  expires_at?: string | null
  disabled: boolean
  last_used_at?: string | null
  created_at?: string | null
  stats_last_7_days?: {
    total: number
    failed: number
  }
}

export interface TaskListItem {
  task_id: string
  status: string
  progress?: number
  message?: string | null
  created_at: string
  started_at?: string | null
  completed_at?: string | null
  error?: string | null
  input_filename: string
  caller_id?: string | null
  caller_name?: string | null
  api_key_suffix?: string | null
  result_summary?: string | null
  enable_postprocess?: boolean
  postprocess_status?: string | null
}

export interface TaskListResponse {
  tasks: TaskListItem[]
  total: number
  limit: number
  offset: number
}

export interface TaskDetail {
  task_id: string
  status: string
  progress?: number
  message?: string | null
  error?: string | null
  created_at: string
  started_at?: string | null
  completed_at?: string | null
  input_filename: string
  task_dir: string
  backend?: string | null
  caller_id?: string | null
  caller_name?: string | null
  api_key_suffix?: string | null
  request_summary?: string | null
  result_summary?: string | null
  result_raw?: string | null
  enable_postprocess?: boolean
  postprocess_status?: string | null
}

export interface DeliverableItem {
  name: string
  filename: string
  download_key: string
  size?: number | null
  artifact_type?: string | null
  role?: string | null
  available?: boolean
  is_default?: boolean
}

export interface DeliverablesResponse {
  task_id: string
  status: string
  artifacts: DeliverableItem[]
}

export interface RuntimeSettingsResponse {
  max_concurrent: number
  max_concurrent_source: string
  max_concurrent_note: string
  admin_security: {
    default_password_in_use: boolean
    default_username: string
    password_change_required: boolean
  }
}

export interface PostprocessActionItem {
  action_id: string
  name: string
  type: string
  config: {
    prompt?: string
    output_filename?: string
    context_size?: number | null
  }
  enabled: boolean | number
  created_at?: string | null
  updated_at?: string | null
}

export interface PostprocessActionListResponse {
  items: PostprocessActionItem[]
}

export interface PostprocessPlanStep {
  action_id: string
  output_filename?: string | null
}

export interface PostprocessPlanItem {
  plan_id: string
  title: string
  description?: string | null
  steps: PostprocessPlanStep[]
  enabled: boolean | number
  created_at?: string | null
  updated_at?: string | null
}

export interface PostprocessPlanListResponse {
  items: PostprocessPlanItem[]
  default_context_size: number
}

export interface PostprocessRunStep {
  action_id: string
  name: string
  output_filename: string
  status: string
  chunks?: number
  error?: string | null
}

export interface PostprocessRunItem {
  run_id: string
  task_id: string
  plan_id?: string | null
  plan_title: string
  status: string
  current_step: number
  trigger_source: string
  steps: PostprocessRunStep[]
  error?: string | null
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
}

export interface PostprocessRunListResponse {
  items: PostprocessRunItem[]
}
