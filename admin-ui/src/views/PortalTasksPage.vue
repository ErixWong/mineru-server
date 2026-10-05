<template>
  <section>
    <div class="d-flex flex-wrap justify-content-between align-items-end gap-3 mb-4">
      <div>
        <div class="small text-uppercase text-body-secondary fw-semibold mb-1">{{ t('portal.tasks.eyebrow') }}</div>
        <h1 class="fs-3 fw-semibold mb-1">{{ t('portal.tasks.title') }}</h1>
        <p class="text-body-secondary mb-0">{{ t('portal.tasks.subtitle') }}</p>
      </div>
      <RouterLink class="btn btn-primary" :to="{ name: 'portal-new-task' }"><i class="bi bi-plus-lg me-1"></i>{{ t('portal.tasks.create') }}</RouterLink>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
      <label class="form-label mb-0" for="portal-status">{{ t('portal.tasks.filterLabel') }}</label>
      <select id="portal-status" v-model="status" class="form-select" style="max-width: 220px" @change="changeStatus">
        <option value="">{{ t('portal.tasks.filterAll') }}</option>
        <option value="pending">{{ t('portal.status.pending') }}</option>
        <option value="processing">{{ t('portal.status.processing') }}</option>
        <option value="completed">{{ t('portal.status.completed') }}</option>
        <option value="failed">{{ t('portal.status.failed') }}</option>
        <option value="cancelled">{{ t('portal.status.cancelled') }}</option>
      </select>
    </div>

    <div class="card">
      <div class="card-body">
        <div v-if="loading" class="text-center text-body-secondary py-5">{{ t('portal.tasks.loading') }}</div>
        <div v-else-if="!tasks.length" class="mk-empty">
          <i class="bi bi-inbox mk-empty-icon"></i>
          <h2 class="mk-empty-title">{{ t('portal.tasks.emptyTitle') }}</h2>
          <p class="mk-empty-description">{{ t('portal.tasks.emptyDescription') }}</p>
          <RouterLink class="btn btn-primary" :to="{ name: 'portal-new-task' }">{{ t('portal.tasks.create') }}</RouterLink>
        </div>
        <div v-else class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead>
              <tr>
                <th>{{ t('portal.tasks.file') }}</th>
                <th>{{ t('portal.tasks.submittedAt') }}</th>
                <th>{{ t('portal.tasks.progress') }}</th>
                <th>{{ t('portal.tasks.status') }}</th>
                <th class="text-end">{{ t('portal.tasks.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="task in tasks" :key="task.task_id">
                <td>
                  <RouterLink class="fw-semibold text-break" :to="{ name: 'portal-task-detail', params: { taskId: task.task_id } }">{{ taskName(task) }}</RouterLink>
                  <div class="small text-body-secondary font-monospace">{{ task.task_id }}</div>
                </td>
                <td class="small text-body-secondary">{{ formatDate(task.created_at) }}</td>
                <td style="min-width: 140px">
                  <div class="small mb-1">{{ task.status === 'processing' ? `${task.progress ?? 0}%` : '—' }}</div>
                  <div v-if="task.status === 'processing'" class="progress" style="height: 5px">
                    <div class="progress-bar progress-bar-striped progress-bar-animated" :style="{ width: `${task.progress ?? 0}%` }"></div>
                  </div>
                </td>
                <td><span class="badge mk-badge" :class="statusClass(task.status)">{{ statusLabel(task.status) }}</span></td>
                <td class="text-end">
                  <RouterLink class="btn btn-outline-secondary btn-sm" :to="{ name: 'portal-task-detail', params: { taskId: task.task_id } }">{{ t('portal.tasks.details') }}</RouterLink>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-3">
          <div class="small text-body-secondary">{{ t('portal.tasks.pagination', { total, page, totalPages }) }}</div>
          <div v-if="totalPages > 1" class="btn-group btn-group-sm">
            <button class="btn btn-outline-secondary" :disabled="page <= 1" @click="goToPage(page - 1)">{{ t('portal.tasks.previous') }}</button>
            <button class="btn btn-outline-secondary" :disabled="page >= totalPages" @click="goToPage(page + 1)">{{ t('portal.tasks.next') }}</button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch, ApiError } from '../lib/api'
import type { PortalTaskItem, PortalTaskPage } from '../types'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const tasks = ref<PortalTaskItem[]>([])
const status = ref(typeof route.query.status === 'string' ? route.query.status : '')
const page = ref(1)
const total = ref(0)
const totalPages = ref(0)
const loading = ref(false)
const error = ref('')
let pollTimer = 0

function taskName(task: PortalTaskItem) {
  return task.filename || task.input_filename || t('portal.tasks.taskFallback')
}

function statusLabel(value: string) {
  const labels: Record<string, string> = {
    pending: 'portal.status.pending',
    processing: 'portal.status.processing',
    completed: 'portal.status.completed',
    failed: 'portal.status.failed',
    cancelled: 'portal.status.cancelled',
  }
  return labels[value] ? t(labels[value]) : value
}

function statusClass(value: string) {
  const classes: Record<string, string> = {
    pending: 'bg-warning-subtle text-warning-emphasis',
    processing: 'bg-primary-subtle text-primary-emphasis',
    completed: 'bg-success-subtle text-success-emphasis',
    failed: 'bg-danger-subtle text-danger-emphasis',
    cancelled: 'bg-secondary-subtle text-secondary-emphasis',
  }
  return classes[value] || 'bg-body-secondary text-body-secondary'
}

function formatDate(value: string) {
  return new Date(value).toLocaleString()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const query = new URLSearchParams({ page: String(page.value), size: '10' })
    if (status.value) query.set('status', status.value)
    const result = await apiFetch<PortalTaskPage>(`/api/portal/tasks?${query}`)
    tasks.value = result.tasks
    total.value = result.total
    totalPages.value = Math.max(1, result.total_pages)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('portal.tasks.loadFailed')
  } finally {
    loading.value = false
  }
}

function changeStatus() {
  page.value = 1
  void load()
}

function goToPage(nextPage: number) {
  page.value = nextPage
  void load()
}

const hasActiveTasks = computed(() => tasks.value.some((task) => task.status === 'pending' || task.status === 'processing'))

watch(hasActiveTasks, (active) => {
  if (active && !pollTimer) {
    pollTimer = window.setInterval(() => void load(), 5000)
  } else if (!active && pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = 0
  }
})

onMounted(() => void load())
onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>
