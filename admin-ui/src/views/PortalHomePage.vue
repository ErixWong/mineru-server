<template>
  <section>
    <RouterLink class="card mk-hero mk-hero-link mb-4" :to="{ name: 'portal-new-task' }" :aria-label="t('portal.home.heroAria')">
      <div class="card-body d-flex flex-column flex-md-row align-items-start align-items-md-center gap-4 gap-lg-5">
        <div class="mk-hero-icon"><i class="bi bi-cloud-arrow-up"></i></div>
        <div class="flex-grow-1">
          <div class="small text-uppercase text-body-secondary fw-semibold mb-2">{{ t('portal.home.eyebrow') }}</div>
          <h1 class="mk-hero-title mb-2">{{ t('portal.home.title') }}</h1>
          <p class="text-body-secondary mb-0">{{ t('portal.home.subtitle') }}</p>
        </div>
        <span class="btn btn-primary btn-lg px-4 flex-shrink-0">
          <i class="bi bi-plus-lg me-2"></i>{{ t('portal.home.create') }}
        </span>
      </div>
    </RouterLink>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="loading && !tasks.length" class="alert alert-light border text-body-secondary">{{ t('portal.home.loading') }}</div>

    <div class="mk-quota-strip d-flex flex-wrap align-items-center gap-3 gap-md-4 px-3 px-md-4 py-3 mb-4">
      <div class="d-flex align-items-center gap-2">
        <i class="bi bi-layers text-primary fs-5"></i>
        <span class="small text-body-secondary">{{ t('portal.home.quotaLabel') }}</span>
      </div>
      <div class="mk-quota-value">
        {{ unlimited ? t('portal.home.unlimited') : (profile?.quota_remaining_pages ?? 0).toLocaleString() }}
        <span v-if="!unlimited" class="fs-6 fw-normal">{{ t('portal.home.pageUnit') }}</span>
      </div>
      <div v-if="!unlimited" class="small text-body-secondary">
        {{ t('portal.home.quotaUsage', { used: profile?.quota_used_pages ?? 0, total: profile?.quota_total_pages ?? 0 }) }}
      </div>
      <div v-if="!unlimited && (profile?.quota_remaining_pages ?? 0) <= 0" class="small text-danger fw-semibold">
        {{ t('portal.home.quotaEmpty') }}
      </div>
      <RouterLink class="btn btn-outline-secondary btn-sm ms-md-auto" :to="{ name: 'portal-ledger' }">
        {{ t('portal.home.quotaLink') }}<i class="bi bi-arrow-right ms-2"></i>
      </RouterLink>
    </div>

    <div class="card">
      <div class="card-body p-3 p-md-4">
        <div class="d-flex justify-content-between align-items-center gap-3 mb-3">
          <div>
            <h2 class="fs-5 fw-semibold mb-1">{{ t('portal.home.recentTitle') }}</h2>
            <p class="small text-body-secondary mb-0">{{ t('portal.home.recentSubtitle') }}</p>
          </div>
          <RouterLink class="btn btn-outline-secondary btn-sm" :to="{ name: 'portal-tasks' }">{{ t('portal.home.viewAll') }}</RouterLink>
        </div>
        <div v-if="!tasks.length" class="mk-empty">
          <i class="bi bi-file-earmark-plus mk-empty-icon"></i>
          <h3 class="mk-empty-title">{{ t('portal.home.emptyTitle') }}</h3>
          <p class="mk-empty-description">{{ t('portal.home.emptyDescription') }}</p>
          <RouterLink class="btn btn-primary" :to="{ name: 'portal-new-task' }">{{ t('portal.home.create') }}</RouterLink>
        </div>
        <div v-else class="list-group list-group-flush">
          <RouterLink
            v-for="task in tasks"
            :key="task.task_id"
            class="list-group-item list-group-item-action px-0 py-3"
            :to="{ name: 'portal-task-detail', params: { taskId: task.task_id } }"
          >
            <div class="d-flex justify-content-between align-items-start gap-3">
              <div class="min-w-0">
                <div class="fw-semibold text-break">{{ taskName(task) }}</div>
                <div class="small text-body-secondary mt-1">{{ formatDate(task.created_at) }}</div>
                <div v-if="task.status === 'processing'" class="progress mt-2" style="height: 5px">
                  <div class="progress-bar progress-bar-striped progress-bar-animated" :style="{ width: `${task.progress ?? 0}%` }"></div>
                </div>
              </div>
              <span class="badge mk-badge flex-shrink-0" :class="statusClass(task.status)">{{ statusLabel(task.status) }}</span>
            </div>
          </RouterLink>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiFetch, ApiError } from '../lib/api'
import { usePortalStore } from '../stores/portal'
import type { PortalTaskItem, PortalTaskPage } from '../types'

const portal = usePortalStore()
const { t } = useI18n()
const profile = computed(() => portal.profile)
const tasks = ref<PortalTaskItem[]>([])
const loading = ref(false)
const error = ref('')
let pollTimer = 0
const unlimited = computed(() => profile.value?.quota_total_pages === null)

function taskName(task: PortalTaskItem) {
  return task.filename || task.input_filename || t('portal.tasks.taskFallback')
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: 'portal.status.pending',
    processing: 'portal.status.processing',
    completed: 'portal.status.completed',
    failed: 'portal.status.failed',
    cancelled: 'portal.status.cancelled',
  }
  return labels[status] ? t(labels[status]) : status
}

function statusClass(status: string) {
  const classes: Record<string, string> = {
    pending: 'bg-warning-subtle text-warning-emphasis',
    processing: 'bg-primary-subtle text-primary-emphasis',
    completed: 'bg-success-subtle text-success-emphasis',
    failed: 'bg-danger-subtle text-danger-emphasis',
    cancelled: 'bg-secondary-subtle text-secondary-emphasis',
  }
  return classes[status] || 'bg-body-secondary text-body-secondary'
}

function formatDate(value: string) {
  return new Date(value).toLocaleString()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [result] = await Promise.all([
      apiFetch<PortalTaskPage>('/api/portal/tasks?page=1&size=5'),
      portal.loadProfile(),
    ])
    tasks.value = result.tasks
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('portal.tasks.loadFailed')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
  pollTimer = window.setInterval(() => {
    if (tasks.value.some((task) => task.status === 'pending' || task.status === 'processing')) void load()
  }, 6000)
})

onBeforeUnmount(() => window.clearInterval(pollTimer))
</script>
