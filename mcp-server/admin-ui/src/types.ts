export interface AdminMe {
  username: string
  must_change_password: boolean
  locale?: string | null
}

export interface CallerItem {
  caller_id: string
  name: string
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

export interface DashboardTaskItem {
  task_id: string
  input_filename: string
  status: string
  message?: string | null
  created_at: string
  updated_at?: string | null
  completed_at?: string | null
  caller_id?: string | null
  caller_name?: string | null
}

export interface DashboardResponse {
  generated_at: string
  queue: {
    pending: number
    processing: number
    completed: number
    failed: number
    cancelled: number
    total: number
  }
  recent: {
    last_24h_total: number
    last_7d_total: number
    last_7d_completed: number
    last_7d_failed: number
    last_7d_success_rate?: number | null
    last_7d_failure_rate?: number | null
  }
  durations: {
    avg_queue_seconds?: number | null
    avg_parse_seconds?: number | null
  }
  postprocess: {
    pending: number
    running: number
    completed: number
    failed: number
    cancelled: number
  }
  callers: {
    total: number
    enabled: number
    disabled: number
    expired: number
  }
  runtime: {
    default_backend: string
    max_concurrent: number
    postprocess_max_concurrent: number
  }
  admin_security: {
    default_password_in_use: boolean
    default_username: string
    password_change_required: boolean
  }
  recent_failed_tasks: DashboardTaskItem[]
}

export interface DiagnosticCheck {
  key: string
  status: 'ok' | 'warning' | 'failed' | 'skipped' | string
  severity: 'info' | 'warning' | 'critical' | string
  message: string
  action_hint?: string
}

export interface DiagnosticsResponse {
  status: 'healthy' | 'warning' | 'critical' | string
  generated_at: string
  checks: DiagnosticCheck[]
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

export interface TaskDiagnosticsResponse {
  task_id: string
  status: string
  postprocess_status?: string | null
  request: {
    backend?: string | null
    lang?: string | null
    formula_enable: boolean
    table_enable: boolean
    image_analysis: boolean
    start_page_id?: number | null
    end_page_id?: number | null
    server_url_configured: boolean
    enable_postprocess: boolean
    postprocess_rule_id?: string | null
    postprocess_context_size?: number | null
  }
  timeline: {
    created_at?: string | null
    started_at?: string | null
    completed_at?: string | null
    postprocess_started_at?: string | null
    postprocess_finished_at?: string | null
  }
  durations: {
    queue_seconds?: number | null
    parse_seconds?: number | null
    postprocess_seconds?: number | null
    total_seconds?: number | null
  }
  error: {
    category: string
    suggestion: string
  }
  output_validation?: {
    required_missing?: string[]
    recommended_missing?: string[]
    optional_missing?: string[]
    diagnostic_error?: string
  } | null
  logs: {
    level?: string | null
    message?: string | null
    created_at?: string | null
  }[]
}

export interface TaskCloneResponse {
  status: string
  source_task_id: string
  task_id: string
  message?: string
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
