<template>
  <AdminLayout>
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <div>
        <h3 class="mb-1">{{ t('dashboard.title') }}</h3>
        <div class="text-muted small">{{ t('dashboard.subtitle') }}</div>
      </div>
      <button class="btn btn-outline-primary" :disabled="loading" @click="load">
        <i class="bi bi-arrow-clockwise me-1"></i>
        {{ t('common.refresh') }}
      </button>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="loading && !dashboard" class="text-muted">{{ t('common.loading') }}</div>

    <template v-if="dashboard">
      <div class="row g-3 mb-3">
        <div v-for="metric in metrics" :key="metric.key" class="col-6 col-lg-3">
          <div class="card page-card h-100">
            <div class="card-body">
              <div class="text-muted small">{{ metric.label }}</div>
              <div class="fs-3 fw-semibold">{{ metric.value }}</div>
              <div class="small" :class="metric.tone">{{ metric.hint }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="row g-3 mb-3">
        <div class="col-lg-7">
          <div class="card page-card h-100">
            <div class="card-body">
              <div class="d-flex justify-content-between align-items-center mb-2">
                <h5 class="card-title mb-0">{{ t('dashboard.queueTitle') }}</h5>
                <span class="badge text-bg-light border">{{ t('dashboard.generatedAt', { time: formatDate(dashboard.generated_at) }) }}</span>
              </div>
              <div class="table-responsive">
                <table class="table table-sm align-middle mb-0">
                  <tbody>
                    <tr><th>{{ t('status.pending') }}</th><td>{{ dashboard.queue.pending }}</td></tr>
                    <tr><th>{{ t('status.processing') }}</th><td>{{ dashboard.queue.processing }}</td></tr>
                    <tr><th>{{ t('status.completed') }}</th><td>{{ dashboard.queue.completed }}</td></tr>
                    <tr><th>{{ t('status.failed') }}</th><td>{{ dashboard.queue.failed }}</td></tr>
                    <tr><th>{{ t('status.cancelled') }}</th><td>{{ dashboard.queue.cancelled }}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        <div class="col-lg-5">
          <div class="card page-card h-100">
            <div class="card-body">
              <h5 class="card-title">{{ t('dashboard.runtimeTitle') }}</h5>
              <div class="table-responsive">
                <table class="table table-sm mb-0">
                  <tbody>
                    <tr><th>{{ t('dashboard.defaultBackend') }}</th><td class="font-monospace">{{ dashboard.runtime.default_backend }}</td></tr>
                    <tr><th>{{ t('dashboard.parseConcurrency') }}</th><td>{{ dashboard.runtime.max_concurrent }}</td></tr>
                    <tr><th>{{ t('dashboard.postprocessConcurrency') }}</th><td>{{ dashboard.runtime.postprocess_max_concurrent }}</td></tr>
                    <tr><th>{{ t('dashboard.callers') }}</th><td>{{ t('dashboard.callerStats', dashboard.callers) }}</td></tr>
                    <tr><th>{{ t('dashboard.avgQueue') }}</th><td>{{ formatDuration(dashboard.durations.avg_queue_seconds) }}</td></tr>
                    <tr><th>{{ t('dashboard.avgParse') }}</th><td>{{ formatDuration(dashboard.durations.avg_parse_seconds) }}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="row g-3">
        <div class="col-lg-6">
          <div class="card page-card h-100">
            <div class="card-body">
              <div class="d-flex justify-content-between align-items-center mb-2">
                <h5 class="card-title mb-0">{{ t('dashboard.diagnosticsTitle') }}</h5>
                <span class="badge" :class="diagnosticsBadgeClass">{{ diagnosticsLabel }}</span>
              </div>
              <div v-if="diagnosticsError" class="alert alert-warning py-2">{{ diagnosticsError }}</div>
              <div v-else-if="!diagnostics" class="text-muted">{{ t('common.loading') }}</div>
              <ul v-else class="list-group list-group-flush">
                <li v-for="check in diagnostics.checks" :key="check.key" class="list-group-item px-0">
                  <div class="d-flex justify-content-between gap-2">
                    <div>
                      <div class="fw-semibold">{{ diagnosticName(check.key) }}</div>
                      <div class="small text-muted">{{ check.message }}</div>
                      <div v-if="check.action_hint" class="small text-secondary">{{ check.action_hint }}</div>
                    </div>
                    <span class="badge align-self-start" :class="checkBadgeClass(check.status)">{{ checkStatusLabel(check.status) }}</span>
                  </div>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <div class="col-lg-6">
          <div class="card page-card h-100">
            <div class="card-body">
              <div class="d-flex justify-content-between align-items-center mb-2">
                <h5 class="card-title mb-0">{{ t('dashboard.recentFailedTitle') }}</h5>
                <RouterLink class="btn btn-outline-danger btn-sm" :to="{ name: 'tasks', query: { status: 'failed' } }">{{ t('dashboard.viewAllFailed') }}</RouterLink>
              </div>
              <div v-if="dashboard.recent_failed_tasks.length === 0" class="text-muted">{{ t('dashboard.noFailedTasks') }}</div>
              <ul v-else class="list-group list-group-flush">
                <li v-for="task in dashboard.recent_failed_tasks" :key="task.task_id" class="list-group-item px-0">
                  <RouterLink class="fw-semibold text-break" :to="`/tasks/${task.task_id}`">{{ task.input_filename }}</RouterLink>
                  <div class="small text-muted">{{ task.caller_name || t('tasks.unassigned') }} · {{ formatDate(task.updated_at || task.completed_at || task.created_at) }}</div>
                  <div class="small text-danger text-break">{{ task.message || t('dashboard.noErrorMessage') }}</div>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </template>
  </AdminLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import type { DashboardResponse, DiagnosticsResponse } from '../types'

const { t } = useI18n()

const dashboard = ref<DashboardResponse | null>(null)
const diagnostics = ref<DiagnosticsResponse | null>(null)
const loading = ref(false)
const error = ref('')
const diagnosticsError = ref('')

const metrics = computed(() => {
  if (!dashboard.value) return []
  const data = dashboard.value
  return [
    {
      key: 'total',
      label: t('dashboard.metricTotal'),
      value: data.queue.total,
      hint: t('dashboard.metric24h', { count: data.recent.last_24h_total }),
      tone: 'text-muted',
    },
    {
      key: 'active',
      label: t('dashboard.metricActive'),
      value: data.queue.pending + data.queue.processing,
      hint: t('dashboard.metricActiveHint', { pending: data.queue.pending, processing: data.queue.processing }),
      tone: data.queue.pending + data.queue.processing > 0 ? 'text-primary' : 'text-muted',
    },
    {
      key: 'success',
      label: t('dashboard.metricSuccessRate'),
      value: formatRate(data.recent.last_7d_success_rate),
      hint: t('dashboard.metric7dCompleted', { count: data.recent.last_7d_completed }),
      tone: 'text-success',
    },
    {
      key: 'failed',
      label: t('dashboard.metricFailureRate'),
      value: formatRate(data.recent.last_7d_failure_rate),
      hint: t('dashboard.metric7dFailed', { count: data.recent.last_7d_failed }),
      tone: data.recent.last_7d_failed > 0 ? 'text-danger' : 'text-muted',
    },
  ]
})

const diagnosticsBadgeClass = computed(() => {
  switch (diagnostics.value?.status) {
    case 'healthy':
      return 'text-bg-success'
    case 'warning':
      return 'text-bg-warning'
    case 'critical':
      return 'text-bg-danger'
    default:
      return 'text-bg-secondary'
  }
})

const diagnosticsLabel = computed(() => {
  if (!diagnostics.value) return t('dashboard.diagnosticsUnknown')
  return t(`dashboard.diagnostics_${diagnostics.value.status}`)
})

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : '-'
}

function formatRate(value?: number | null) {
  return value === null || value === undefined ? '-' : `${value.toFixed(1)}%`
}

function formatDuration(value?: number | null) {
  if (value === null || value === undefined) return '-'
  if (value < 60) return t('dashboard.seconds', { value: value.toFixed(1) })
  return t('dashboard.minutes', { value: (value / 60).toFixed(1) })
}

function checkBadgeClass(status: string) {
  switch (status) {
    case 'ok':
      return 'text-bg-success'
    case 'warning':
      return 'text-bg-warning'
    case 'failed':
      return 'text-bg-danger'
    case 'skipped':
      return 'text-bg-secondary'
    default:
      return 'text-bg-light border'
  }
}

function checkStatusLabel(status: string) {
  const key = `dashboard.check_${status}`
  if (['ok', 'warning', 'failed', 'skipped'].includes(status)) return t(key)
  return status
}

function diagnosticName(key: string) {
  const known = ['default_backend', 'vlm_config', 'postprocess_llm', 'output_root', 'db_path', 'caller_key_master_key', 'admin_password', 'single_instance']
  return known.includes(key) ? t(`dashboard.diagnostic_${key}`) : key
}

async function load() {
  loading.value = true
  error.value = ''
  diagnosticsError.value = ''
  try {
    const [dashboardPayload, diagnosticsPayload] = await Promise.all([
      apiFetch<DashboardResponse>('/api/admin/dashboard'),
      apiFetch<DiagnosticsResponse>('/api/admin/diagnostics'),
    ])
    dashboard.value = dashboardPayload
    diagnostics.value = diagnosticsPayload
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.loadFailed')
    try {
      diagnostics.value = await apiFetch<DiagnosticsResponse>('/api/admin/diagnostics')
    } catch (diagErr) {
      diagnosticsError.value = diagErr instanceof ApiError ? diagErr.message : t('common.loadFailed')
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
