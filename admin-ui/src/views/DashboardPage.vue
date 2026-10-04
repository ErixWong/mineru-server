<template>
  <AdminLayout>
    <div class="d-flex flex-wrap justify-content-between align-items-end gap-3 mb-5">
      <div>
        <div class="small text-uppercase text-body-secondary fw-semibold mb-1">{{ t('nav.dashboard') }}</div>
        <h1 class="fs-3 fw-semibold mb-1">{{ t('dashboard.title') }}</h1>
        <div class="text-body-secondary">{{ t('dashboard.subtitle') }}</div>
      </div>
      <button class="btn btn-outline-primary" :disabled="loading" @click="load">
        <i class="bi bi-arrow-clockwise me-1"></i>
        {{ t('common.refresh') }}
      </button>
    </div>

    <div v-if="error" class="alert bg-body border border-danger-subtle rounded-3 py-2 text-danger-emphasis">{{ error }}</div>
    <div v-if="loading && !dashboard" class="alert bg-body border rounded-3 text-body-secondary">{{ t('common.loading') }}</div>

    <template v-if="dashboard">
      <div class="row g-4 mb-5">
        <div v-for="metric in metrics" :key="metric.key" class="col-6 col-lg-3">
          <div class="card h-100" :class="metric.key === 'active' ? 'border-primary-subtle bg-primary-subtle' : ''">
            <div class="card-body p-4 p-lg-5">
              <div class="d-flex justify-content-between align-items-start gap-2 mb-3">
                <div class="small text-body-secondary">{{ metric.label }}</div>
                <span class="rounded-3 p-2 bg-primary-subtle text-primary-emphasis">
                  <i class="bi" :class="metric.key === 'total' ? 'bi-files' : metric.key === 'active' ? 'bi-hourglass-split' : metric.key === 'success' ? 'bi-check2-circle' : 'bi-exclamation-triangle'"></i>
                </span>
              </div>
              <div class="fw-semibold lh-1 mb-3" :class="[metric.key === 'active' ? 'display-5 text-primary-emphasis' : 'display-6']">{{ metric.value }}</div>
              <div class="small text-body-secondary">{{ metric.hint }}</div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="quotaAlertsError" class="alert alert-warning" role="alert">{{ quotaAlertsError }}</div>
      <div v-if="quotaAlerts.length" class="card border-warning-subtle mb-5">
        <div class="card-body p-4 p-xl-5">
          <div class="d-flex flex-wrap justify-content-between align-items-start gap-2 mb-3">
            <div>
              <h2 class="fs-5 fw-semibold mb-1">{{ t('dashboard.quotaAlertsTitle') }}</h2>
              <div class="small text-body-secondary">{{ t('dashboard.quotaAlertsHint') }}</div>
            </div>
            <span class="badge bg-warning-subtle text-warning-emphasis">{{ quotaAlerts.length }}</span>
          </div>
          <div class="table-responsive">
            <table class="table table-hover align-middle mb-0">
              <thead>
                <tr>
                  <th class="small text-body-secondary fw-semibold">{{ t('users.username') }}</th>
                  <th class="small text-body-secondary fw-semibold">{{ t('users.displayName') }}</th>
                  <th class="small text-body-secondary fw-semibold text-end">{{ t('users.quotaRemaining') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="user in quotaAlerts" :key="user.user_id">
                  <td><RouterLink class="fw-semibold" :to="{ name: 'users' }">{{ user.username }}</RouterLink></td>
                  <td>{{ user.display_name || '-' }}</td>
                  <td class="text-end text-nowrap">
                    {{ t('dashboard.quotaRemaining', {
                      remaining: (user.quota_remaining_pages ?? 0).toLocaleString(),
                      total: (user.quota_total_pages ?? 0).toLocaleString(),
                      percent: quotaPercent(user).toFixed(1),
                    }) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="row g-4 mb-5">
        <div class="col-lg-7">
          <div class="card h-100">
            <div class="card-body p-4 p-xl-5">
              <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
                <h2 class="fs-5 fw-semibold mb-0">{{ t('dashboard.queueTitle') }}</h2>
                <span class="badge bg-body-secondary text-body-secondary border fw-normal">{{ t('dashboard.generatedAt', { time: formatDate(dashboard.generated_at) }) }}</span>
              </div>
              <div class="table-responsive">
                <table class="table table-hover align-middle mb-0">
                  <tbody>
                    <tr><th class="fw-normal text-body-secondary">{{ t('status.pending') }}</th><td class="text-end fw-semibold">{{ dashboard.queue.pending }}</td></tr>
                    <tr><th class="fw-normal text-body-secondary">{{ t('status.processing') }}</th><td class="text-end fw-semibold">{{ dashboard.queue.processing }}</td></tr>
                    <tr><th class="fw-normal text-body-secondary">{{ t('status.completed') }}</th><td class="text-end fw-semibold">{{ dashboard.queue.completed }}</td></tr>
                    <tr><th class="fw-normal text-body-secondary">{{ t('status.failed') }}</th><td class="text-end fw-semibold">{{ dashboard.queue.failed }}</td></tr>
                    <tr><th class="fw-normal text-body-secondary">{{ t('status.cancelled') }}</th><td class="text-end fw-semibold">{{ dashboard.queue.cancelled }}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        <div class="col-lg-5">
          <div class="card h-100">
            <div class="card-body p-4 p-xl-5">
              <h2 class="fs-5 fw-semibold mb-3">{{ t('dashboard.runtimeTitle') }}</h2>
              <div class="table-responsive">
                <table class="table table-hover align-middle mb-0">
                  <tbody>
                    <tr><th class="fw-normal text-body-secondary">{{ t('dashboard.defaultBackend') }}</th><td class="font-monospace">{{ dashboard.runtime.default_backend }}</td></tr>
                    <tr><th class="fw-normal text-body-secondary">{{ t('dashboard.parseConcurrency') }}</th><td>{{ dashboard.runtime.max_concurrent }}</td></tr>
                    <tr><th class="fw-normal text-body-secondary">{{ t('dashboard.postprocessConcurrency') }}</th><td>{{ dashboard.runtime.postprocess_max_concurrent }}</td></tr>
                    <tr><th class="fw-normal text-body-secondary">{{ t('dashboard.callers') }}</th><td>{{ t('dashboard.callerStats', dashboard.callers) }}</td></tr>
                    <tr><th class="fw-normal text-body-secondary">{{ t('dashboard.avgQueue') }}</th><td>{{ formatDuration(dashboard.durations.avg_queue_seconds) }}</td></tr>
                    <tr><th class="fw-normal text-body-secondary">{{ t('dashboard.avgParse') }}</th><td>{{ formatDuration(dashboard.durations.avg_parse_seconds) }}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="row g-4">
        <div class="col-lg-6">
          <div class="card h-100">
            <div class="card-body p-4 p-xl-5">
              <div class="d-flex justify-content-between align-items-center mb-2">
                <h2 class="fs-5 fw-semibold mb-0">{{ t('dashboard.diagnosticsTitle') }}</h2>
                <span class="badge" :class="diagnosticsBadgeClass">{{ diagnosticsLabel }}</span>
              </div>
              <div v-if="diagnosticsError" class="alert bg-body border border-warning-subtle rounded-3 py-2 text-warning-emphasis">{{ diagnosticsError }}</div>
              <div v-else-if="!diagnostics" class="text-body-secondary">{{ t('common.loading') }}</div>
              <ul v-else class="list-group list-group-flush">
                <li v-for="check in diagnostics.checks" :key="check.key" class="list-group-item px-0 py-4">
                  <div class="d-flex justify-content-between gap-3">
                    <div>
                      <div class="fw-semibold">{{ diagnosticName(check.key) }}</div>
                      <div class="small text-body-secondary lh-base mt-1">{{ check.message }}</div>
                      <div v-if="check.action_hint" class="small text-body-secondary lh-base mt-2">{{ check.action_hint }}</div>
                    </div>
                    <span class="badge align-self-start" :class="checkBadgeClass(check.status)">{{ checkStatusLabel(check.status) }}</span>
                  </div>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <div class="col-lg-6">
          <div class="card h-100">
            <div class="card-body p-4 p-xl-5">
              <div class="d-flex justify-content-between align-items-center gap-3 mb-3">
                <h2 class="fs-5 fw-semibold mb-0">{{ t('dashboard.recentFailedTitle') }}</h2>
                <RouterLink class="btn btn-outline-danger btn-sm" :to="{ name: 'tasks', query: { status: 'failed' } }">{{ t('dashboard.viewAllFailed') }}</RouterLink>
              </div>
              <div v-if="dashboard.recent_failed_tasks.length === 0" class="text-body-secondary py-3">{{ t('dashboard.noFailedTasks') }}</div>
              <ul v-else class="list-group list-group-flush">
                <li v-for="task in dashboard.recent_failed_tasks" :key="task.task_id" class="list-group-item px-0 py-4">
                  <div class="d-flex justify-content-between align-items-start gap-3">
                    <RouterLink class="fw-semibold text-break" :to="`/tasks/${task.task_id}`">{{ task.input_filename }}</RouterLink>
                    <span class="badge bg-danger-subtle text-danger-emphasis flex-shrink-0">{{ t('status.failed') }}</span>
                  </div>
                  <div class="small text-body-secondary mt-1">{{ task.caller_name || t('tasks.unassigned') }} · {{ formatDate(task.updated_at || task.completed_at || task.created_at) }}</div>
                  <div class="small text-body-secondary text-truncate mt-2" :title="task.message || t('dashboard.noErrorMessage')">{{ task.message || t('dashboard.noErrorMessage') }}</div>
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
import type { AdminUserItem, DashboardResponse, DiagnosticsResponse } from '../types'

const { t } = useI18n()

const dashboard = ref<DashboardResponse | null>(null)
const diagnostics = ref<DiagnosticsResponse | null>(null)
const quotaAlerts = ref<AdminUserItem[]>([])
const loading = ref(false)
const error = ref('')
const diagnosticsError = ref('')
const quotaAlertsError = ref('')

const metrics = computed(() => {
  if (!dashboard.value) return []
  const data = dashboard.value
  return [
    {
      key: 'total',
      label: t('dashboard.metricTotal'),
      value: data.queue.total,
      hint: t('dashboard.metric24h', { count: data.recent.last_24h_total }),
    },
    {
      key: 'active',
      label: t('dashboard.metricActive'),
      value: data.queue.pending + data.queue.processing,
      hint: t('dashboard.metricActiveHint', { pending: data.queue.pending, processing: data.queue.processing }),
    },
    {
      key: 'success',
      label: t('dashboard.metricSuccessRate'),
      value: formatRate(data.recent.last_7d_success_rate),
      hint: t('dashboard.metric7dCompleted', { count: data.recent.last_7d_completed }),
    },
    {
      key: 'failed',
      label: t('dashboard.metricFailureRate'),
      value: formatRate(data.recent.last_7d_failure_rate),
      hint: t('dashboard.metric7dFailed', { count: data.recent.last_7d_failed }),
    },
  ]
})

const diagnosticsBadgeClass = computed(() => {
  switch (diagnostics.value?.status) {
    case 'healthy':
      return 'bg-success-subtle text-success-emphasis'
    case 'warning':
      return 'bg-warning-subtle text-warning-emphasis'
    case 'critical':
      return 'bg-danger-subtle text-danger-emphasis'
    default:
      return 'bg-secondary-subtle text-secondary-emphasis'
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

function quotaPercent(user: AdminUserItem) {
  const total = user.quota_total_pages ?? 0
  const remaining = user.quota_remaining_pages ?? 0
  return total > 0 ? Math.max(0, remaining / total * 100) : 0
}

function formatDuration(value?: number | null) {
  if (value === null || value === undefined) return '-'
  if (value < 60) return t('dashboard.seconds', { value: value.toFixed(1) })
  return t('dashboard.minutes', { value: (value / 60).toFixed(1) })
}

function checkBadgeClass(status: string) {
  switch (status) {
    case 'ok':
      return 'bg-success-subtle text-success-emphasis'
    case 'warning':
      return 'bg-warning-subtle text-warning-emphasis'
    case 'failed':
      return 'bg-danger-subtle text-danger-emphasis'
    case 'skipped':
      return 'bg-secondary-subtle text-secondary-emphasis'
    default:
      return 'bg-body-secondary text-body-secondary border'
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
  quotaAlertsError.value = ''
  quotaAlerts.value = []
  try {
    const [dashboardPayload, diagnosticsPayload] = await Promise.all([
      apiFetch<DashboardResponse>('/api/admin/dashboard'),
      apiFetch<DiagnosticsResponse>('/api/admin/diagnostics'),
      loadQuotaAlerts(),
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

async function loadQuotaAlerts() {
  try {
    const users = await apiFetch<AdminUserItem[]>('/api/admin/users?include_disabled=true')
    quotaAlerts.value = users.filter((user) => {
      const total = user.quota_total_pages
      if (total === null) return false
      const remaining = user.quota_remaining_pages ?? 0
      return total > 0 ? remaining / total <= 0.2 : remaining <= 0
    })
  } catch (err) {
    quotaAlertsError.value = err instanceof ApiError ? err.message : t('dashboard.quotaAlertsLoadFailed')
  }
}

onMounted(load)
</script>
