<template>
  <section class="portal-master-detail">
    <aside v-if="!isNarrow || !routeTaskId" class="portal-task-sidebar" :aria-label="t('portal.tasks.listLabel')">
      <header class="portal-task-sidebar-header">
        <div class="d-flex justify-content-between align-items-center gap-2 mb-3">
          <h1 class="fs-5 fw-semibold mb-0">{{ t('portal.tasks.title') }}</h1>
          <RouterLink class="btn btn-primary btn-sm text-nowrap" :to="{ name: 'portal-new-task' }">
            <i class="bi bi-plus-lg me-1"></i>{{ t('portal.tasks.create') }}
          </RouterLink>
        </div>
        <label class="form-label small text-body-secondary mb-1" for="portal-status">{{ t('portal.tasks.filterLabel') }}</label>
        <select id="portal-status" v-model="status" class="form-select form-select-sm" @change="changeStatus">
          <option value="">{{ t('portal.tasks.filterAll') }}</option>
          <option value="pending">{{ t('portal.status.pending') }}</option>
          <option value="processing">{{ t('portal.status.processing') }}</option>
          <option value="completed">{{ t('portal.status.completed') }}</option>
          <option value="failed">{{ t('portal.status.failed') }}</option>
          <option value="cancelled">{{ t('portal.status.cancelled') }}</option>
        </select>
      </header>

      <div class="portal-task-list-scroll">
        <div v-if="error" class="alert alert-danger m-3 mb-0">{{ error }}</div>
        <div v-if="loading && !tasks.length" class="text-center text-body-secondary p-4">{{ t('portal.tasks.loading') }}</div>
        <div v-else-if="!tasks.length && !error" class="mk-empty py-5">
          <i class="bi bi-inbox mk-empty-icon"></i>
          <h2 class="mk-empty-title">{{ t('portal.tasks.emptyTitle') }}</h2>
          <p class="mk-empty-description">{{ t('portal.tasks.emptyDescription') }}</p>
          <RouterLink class="btn btn-primary btn-sm" :to="{ name: 'portal-new-task' }">{{ t('portal.tasks.create') }}</RouterLink>
        </div>
        <nav v-else-if="tasks.length" class="portal-task-list" :aria-label="t('portal.tasks.listLabel')">
          <RouterLink
            v-for="task in tasks"
            :key="task.task_id"
            class="portal-task-link"
            :class="{ 'portal-task-link-selected': selectedTaskId === task.task_id }"
            :to="{ name: 'portal-task-detail', params: { taskId: task.task_id }, query: route.query }"
            :aria-current="selectedTaskId === task.task_id ? 'page' : undefined"
          >
            <div class="d-flex align-items-start justify-content-between gap-2">
              <div class="portal-task-filename d-flex" :title="taskName(task)">
                <span class="portal-task-filename-base">{{ splitFilename(taskName(task)).base }}</span>
                <span class="portal-task-filename-extension">{{ splitFilename(taskName(task)).extension }}</span>
              </div>
              <span class="badge mk-badge portal-task-status" :class="statusClass(task.status)">{{ statusLabel(task.status) }}</span>
            </div>
            <div class="d-flex align-items-center justify-content-between gap-2 mt-2">
              <span class="small text-body-secondary">{{ relativeTime(task.created_at) }}</span>
              <span v-if="task.status === 'processing'" class="small text-primary-emphasis">{{ task.progress ?? 0 }}%</span>
            </div>
            <div v-if="task.status === 'processing'" class="progress portal-task-progress mt-1" role="progressbar" :aria-valuenow="task.progress ?? 0" aria-valuemin="0" aria-valuemax="100">
              <div class="progress-bar progress-bar-striped progress-bar-animated" :style="{ width: `${task.progress ?? 0}%` }"></div>
            </div>
          </RouterLink>
        </nav>
      </div>

      <footer class="portal-task-pagination">
        <div class="small text-body-secondary">{{ t('portal.tasks.pagination', { total, page, totalPages }) }}</div>
        <div v-if="totalPages > 1" class="btn-group btn-group-sm mt-2 w-100">
          <button class="btn btn-outline-secondary" :disabled="page <= 1 || loading" @click="goToPage(page - 1)">{{ t('portal.tasks.previous') }}</button>
          <button class="btn btn-outline-secondary" :disabled="page >= totalPages || loading" @click="goToPage(page + 1)">{{ t('portal.tasks.next') }}</button>
        </div>
      </footer>
    </aside>

    <div
      v-if="!isNarrow || routeTaskId"
      class="portal-detail-column"
      role="region"
      :aria-label="t('portal.detail.resultTitle')"
    >
      <PortalTaskDetailPanel
        v-if="selectedTaskId"
        :task-id="selectedTaskId"
        :show-back-button="isNarrow"
        @back="backToList"
      />
      <div v-else-if="loading" class="text-center text-body-secondary py-5">{{ t('portal.tasks.loading') }}</div>
      <div v-else class="mk-empty h-100">
        <i class="bi bi-file-earmark-text mk-empty-icon"></i>
        <h2 class="mk-empty-title">{{ t('portal.tasks.selectTaskTitle') }}</h2>
        <p class="mk-empty-description mb-0">{{ t('portal.tasks.selectTaskDescription') }}</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import PortalTaskDetailPanel from '../components/PortalTaskDetailPanel.vue'
import { apiFetch, ApiError } from '../lib/api'
import type { PortalTaskItem, PortalTaskPage } from '../types'

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const tasks = ref<PortalTaskItem[]>([])
const status = ref(typeof route.query.status === 'string' ? route.query.status : '')
const page = ref(1)
const total = ref(0)
const totalPages = ref(1)
const loading = ref(false)
const error = ref('')
const isNarrow = ref(false)
const routeTaskId = computed(() => String(route.params.taskId || ''))
const selectedTaskId = computed(() => routeTaskId.value || tasks.value[0]?.task_id || '')
const hasActiveTasks = computed(() => tasks.value.some((task) => task.status === 'pending' || task.status === 'processing'))
let pollTimer = 0
let requestSequence = 0
let mediaQuery: MediaQueryList | undefined

function taskName(task: PortalTaskItem) {
  return task.filename || task.input_filename || t('portal.tasks.taskFallback')
}

function splitFilename(filename: string) {
  const extensionStart = filename.lastIndexOf('.')
  if (extensionStart > 0) {
    return { base: filename.slice(0, extensionStart), extension: filename.slice(extensionStart) }
  }
  return { base: filename, extension: '' }
}

function relativeTime(value: string) {
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) return '—'

  const seconds = Math.max(1, Math.floor((Date.now() - timestamp) / 1000))
  const intervals: [number, Intl.RelativeTimeFormatUnit, number][] = [
    [31_536_000, 'year', 31_536_000],
    [2_592_000, 'month', 2_592_000],
    [604_800, 'week', 604_800],
    [86_400, 'day', 86_400],
    [3_600, 'hour', 3_600],
    [60, 'minute', 60],
  ]
  let amount = seconds
  let unit: Intl.RelativeTimeFormatUnit = 'second'
  for (const [threshold, nextUnit, divisor] of intervals) {
    if (seconds < threshold) continue
    amount = Math.floor(seconds / divisor)
    unit = nextUnit
    break
  }
  return new Intl.RelativeTimeFormat(locale.value, { numeric: 'auto' }).format(-amount, unit)
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

async function load(background = false) {
  if (background && loading.value) return
  const sequence = ++requestSequence
  if (!background) loading.value = true
  error.value = ''
  try {
    const query = new URLSearchParams({ page: String(page.value), size: '10' })
    if (status.value) query.set('status', status.value)
    const result = await apiFetch<PortalTaskPage>(`/api/portal/tasks?${query}`)
    if (sequence !== requestSequence) return
    tasks.value = result.tasks
    total.value = result.total
    totalPages.value = Math.max(1, result.total_pages)
  } catch (err) {
    if (sequence !== requestSequence) return
    error.value = err instanceof ApiError ? err.message : t('portal.tasks.loadFailed')
  } finally {
    if (!background && sequence === requestSequence) loading.value = false
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

function backToList() {
  void router.push({ name: 'portal-tasks', query: route.query })
}

function updateNarrowState(event: MediaQueryListEvent | MediaQueryList) {
  isNarrow.value = event.matches
}

watch(hasActiveTasks, (active) => {
  if (active && !pollTimer) {
    pollTimer = window.setInterval(() => void load(true), 5000)
  } else if (!active && pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = 0
  }
}, { immediate: true })

onMounted(() => {
  mediaQuery = window.matchMedia('(max-width: 991.98px)')
  updateNarrowState(mediaQuery)
  mediaQuery.addEventListener('change', updateNarrowState)
  void load()
})

onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer)
  mediaQuery?.removeEventListener('change', updateNarrowState)
})
</script>

<style scoped>
.portal-master-detail {
  display: flex;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  flex: 1 1 auto;
  overflow: hidden;
}

.portal-task-sidebar {
  display: flex;
  width: 340px;
  min-width: 0;
  min-height: 0;
  flex: 0 0 340px;
  flex-direction: column;
  border-right: 1px solid var(--mk-border);
  background: var(--bs-body-bg);
}

.portal-task-sidebar-header {
  flex: 0 0 auto;
  padding: 1.25rem;
  border-bottom: 1px solid var(--mk-border);
}

.portal-task-list-scroll {
  min-height: 0;
  flex: 1 1 auto;
  overflow-x: hidden;
  overflow-y: auto;
}

.portal-task-link {
  display: block;
  padding: 0.9rem 1rem;
  border-bottom: 1px solid var(--mk-border);
  color: inherit;
  text-decoration: none;
  transition: background-color var(--mk-transition);
}

.portal-task-link:hover {
  background: rgba(8, 127, 152, 0.045);
  color: inherit;
}

.portal-task-link-selected {
  background: var(--mk-brand-soft);
  box-shadow: inset 3px 0 var(--mk-brand);
}

.portal-task-filename {
  min-width: 0;
  overflow: hidden;
  font-weight: 600;
}

.portal-task-filename-base {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.portal-task-filename-extension {
  flex: 0 0 auto;
  white-space: nowrap;
}

.portal-task-status {
  flex: 0 0 auto;
  font-size: 0.68rem;
}

.portal-task-progress {
  height: 3px;
}

.portal-task-pagination {
  flex: 0 0 auto;
  padding: 0.85rem 1rem;
  border-top: 1px solid var(--mk-border);
}

.portal-detail-column {
  min-width: 0;
  min-height: 0;
  flex: 1 1 auto;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 1.5rem;
  background: var(--mk-page);
}

@media (max-width: 991.98px) {
  .portal-task-sidebar,
  .portal-detail-column {
    width: 100%;
    flex: 1 1 100%;
    border-right: 0;
  }

  .portal-detail-column {
    padding: 0.75rem;
  }
}
</style>
