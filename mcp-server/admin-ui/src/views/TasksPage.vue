<template>
  <AdminLayout>
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <div>
        <h3 class="mb-1">{{ t('tasks.title') }}</h3>
        <div class="text-muted small">{{ t('tasks.subtitle') }}</div>
      </div>
      <button class="btn btn-primary" @click="openCreateModal">
        <i class="bi bi-plus-lg me-1"></i>
        {{ t('tasks.newTask') }}
      </button>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card shadow-sm mb-3">
      <div class="card-body">
        <div class="row g-3 align-items-end">
          <div class="col-12 col-md-4 col-xl-2"><label class="form-label">{{ t('tasks.filter_callerId') }}</label><input v-model="filters.caller_id" class="form-control" :placeholder="t('tasks.filter_exactMatch')" /></div>
          <div class="col-12 col-md-4 col-xl-2"><label class="form-label">{{ t('tasks.filter_apiKey') }}</label><input v-model="filters.key" class="form-control" :placeholder="t('tasks.filter_exactMatch')" /></div>
          <div class="col-12 col-md-4 col-xl-2"><label class="form-label">{{ t('tasks.filter_status') }}</label>
            <select v-model="filters.status" class="form-select">
              <option value="">{{ t('tasks.filter_all') }}</option>
              <option value="pending">{{ t('status.pending') }}</option>
              <option value="processing">{{ t('status.processing') }}</option>
              <option value="completed">{{ t('status.completed') }}</option>
              <option value="failed">{{ t('status.failed') }}</option>
              <option value="cancelled">{{ t('status.cancelled') }}</option>
            </select>
          </div>
          <div class="col-12 col-md-4 col-xl-2"><label class="form-label">{{ t('tasks.filter_startDate') }}</label><input v-model="filters.start_date" class="form-control" type="date" /></div>
          <div class="col-12 col-md-4 col-xl-2"><label class="form-label">{{ t('tasks.filter_endDate') }}</label><input v-model="filters.end_date" class="form-control" type="date" /></div>
          <div class="col-12 col-md-4 col-xl-2"><label class="form-label">{{ t('tasks.filter_taskId') }}</label><input v-model="filters.task_id" class="form-control" :placeholder="t('tasks.filter_exactMatch')" /></div>
          <div class="col-12 col-xl-2 d-flex gap-2">
            <button class="btn btn-outline-primary flex-grow-1" @click="applyFilters">{{ t('common.filter') }}</button>
            <button class="btn btn-outline-secondary" @click="resetFilters">{{ t('common.reset') }}</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showCreateModal" class="modal fade show d-block" tabindex="-1" role="dialog" aria-modal="true" aria-labelledby="create-task-title">
      <div class="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
        <div class="modal-content">
          <div class="modal-header">
            <h5 id="create-task-title" class="modal-title">{{ t('tasks.createTitle') }}</h5>
            <button type="button" class="btn-close" :aria-label="t('common.close')" @click="closeCreateModal"></button>
          </div>
          <div class="modal-body">
            <form class="row g-3" @submit.prevent="createTask">
              <div class="col-12 col-md-4"><label class="form-label">{{ t('tasks.file') }}</label><input ref="fileInput" class="form-control" type="file" accept=".pdf" @change="onFileChange" required /></div>
              <div class="col-12 col-md-4"><label class="form-label">{{ t('tasks.backend') }}</label>
                <select v-model="uploadForm.backend" class="form-select">
                  <option value="">{{ t('tasks.backend_default') }}</option>
                  <option value="pipeline">pipeline</option>
                  <option value="vlm-auto-engine">vlm-auto-engine</option>
                  <option value="vlm-http-client">vlm-http-client</option>
                  <option value="hybrid-auto-engine">hybrid-auto-engine</option>
                  <option value="hybrid-http-client">hybrid-http-client</option>
                </select>
              </div>
              <div class="col-12 col-md-4"><label class="form-label">{{ t('tasks.language') }}</label>
                <select v-model="uploadForm.lang" class="form-select">
                  <option value="">{{ t('tasks.lang_default') }}</option>
                  <option value="ch">{{ t('tasks.lang_ch') }}</option><option value="en">{{ t('tasks.lang_en') }}</option><option value="ja">{{ t('tasks.lang_ja') }}</option><option value="ko">{{ t('tasks.lang_ko') }}</option><option value="fr">{{ t('tasks.lang_fr') }}</option><option value="de">{{ t('tasks.lang_de') }}</option>
                </select>
              </div>
              <div class="col-12 col-md-4"><label class="form-label">{{ t('tasks.assignCaller') }}</label>
                <select v-model="uploadForm.caller_id" class="form-select">
                  <option value="">{{ t('tasks.unassigned') }}</option>
                  <option v-for="caller in callers" :key="caller.caller_id" :value="caller.caller_id">{{ caller.name }}</option>
                </select>
                <div class="form-text">{{ t('tasks.callerAssignmentHint') }}</div>
              </div>
              <div class="col-12">
                <div class="form-check form-switch">
                  <input id="enable-postprocess" v-model="uploadForm.enable_postprocess" class="form-check-input" type="checkbox" />
                  <label class="form-check-label" for="enable-postprocess">{{ t('tasks.enablePostprocess') }}</label>
                </div>
              </div>
              <template v-if="uploadForm.enable_postprocess">
                <div class="col-12 col-md-6"><label class="form-label">{{ t('tasks.postprocessPlan') }}</label>
                  <select v-model="uploadForm.postprocess_rule_id" class="form-select">
                    <option value="">{{ t('tasks.selectPlan') }}</option>
                    <option v-for="rule in enabledRules" :key="rule.plan_id" :value="rule.plan_id">{{ rule.title }}</option>
                  </select>
                </div>
              </template>
              <div class="col-12 d-flex justify-content-end gap-2">
                <button type="button" class="btn btn-outline-secondary" @click="closeCreateModal">{{ t('common.cancel') }}</button>
                <button class="btn btn-primary" :disabled="creating">{{ creating ? t('common.submitting') : t('common.submit') }}</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
    <div v-if="showCreateModal" class="modal-backdrop fade show"></div>

    <div class="card shadow-sm">
      <div class="card-body">
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead>
              <tr>
                <th>{{ t('tasks.fileName') }}</th>
                <th>{{ t('tasks.caller') }}</th>
                <th>{{ t('tasks.summary') }}</th>
                <th>{{ t('tasks.createdAt') }}</th>
                <th>{{ t('tasks.completedAt') }}</th>
                <th>{{ t('tasks.processStatus') }}</th>
                <th class="text-end">{{ t('tasks.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading"><td colspan="7" class="text-center text-muted py-4">{{ t('common.loading') }}</td></tr>
              <tr v-else-if="tasks.length === 0"><td colspan="7" class="text-center text-muted py-4">{{ t('common.noData') }}</td></tr>
              <tr v-for="task in tasks" :key="task.task_id">
                <td>
                  <RouterLink class="fw-semibold text-break d-inline-block" :to="`/tasks/${task.task_id}`">{{ task.input_filename }}</RouterLink>
                  <div class="small text-muted font-monospace text-break">{{ task.task_id }}</div>
                </td>
                <td class="small text-break">{{ task.caller_name || '-' }}</td>
                <td class="small text-break">{{ task.result_summary || task.message || task.error || t('tasks.noSummary') }}</td>
                <td class="small text-muted">{{ formatDate(task.created_at) }}</td>
                <td class="small text-muted">{{ formatDate(task.completed_at) || '-' }}</td>
                <td>
                  <div><span class="badge" :class="statusBadgeClass(task.status)">{{ statusLabel(task.status) }}</span></div>
                  <div class="mt-1">
                    <span v-if="task.enable_postprocess || (task.postprocess_status && task.postprocess_status !== 'not_enabled')" class="badge" :class="postprocessBadgeClass(task.postprocess_status)">{{ postprocessStatusLabel(task.postprocess_status) }}</span>
                    <span v-else class="text-muted small">{{ t('tasks.postprocessDisabled') }}</span>
                  </div>
                </td>
                <td>
                  <div class="btn-group btn-group-sm d-flex justify-content-end" role="group">
                    <button class="btn btn-outline-danger btn-sm" @click="deleteTask(task.task_id)">{{ t('common.delete') }}</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-3">
          <div class="text-muted small">{{ t('tasks.pagination_total', { total, page, totalPages }) }}</div>
          <nav v-if="totalPages > 1" :aria-label="t('tasks.title')">
            <ul class="pagination pagination-sm mb-0">
              <li class="page-item" :class="{ disabled: page <= 1 }">
                <button class="page-link" :disabled="page <= 1" @click="goToPage(page - 1)">{{ t('tasks.pagination_prev') }}</button>
              </li>
              <li
                v-for="item in pageItems"
                :key="item.key"
                class="page-item"
                :class="{ active: item.page === page, disabled: item.page === null }"
              >
                <span v-if="item.page === null" class="page-link">&hellip;</span>
                <button v-else class="page-link" @click="goToPage(item.page)">{{ item.page }}</button>
              </li>
              <li class="page-item" :class="{ disabled: page >= totalPages }">
                <button class="page-link" :disabled="page >= totalPages" @click="goToPage(page + 1)">{{ t('tasks.pagination_next') }}</button>
              </li>
            </ul>
          </nav>
        </div>
      </div>
    </div>
  </AdminLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, nextTick, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import { postprocessBadgeClass, postprocessStatusLabel } from '../lib/postprocess'
import type { CallerItem, PostprocessPlanItem, PostprocessPlanListResponse, TaskListItem, TaskListResponse } from '../types'

const { t } = useI18n()

const tasks = ref<TaskListItem[]>([])
const loading = ref(false)
const creating = ref(false)
const showCreateModal = ref(false)
const selectedFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const error = ref('')
const rules = ref<PostprocessPlanItem[]>([])
const callers = ref<CallerItem[]>([])

const PAGE_SIZE = 10
const page = ref(1)
const total = ref(0)

function toLocalDate(d: Date) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function defaultDateRange() {
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 6)
  return { start: toLocalDate(start), end: toLocalDate(end) }
}

const defaultDates = defaultDateRange()
const filters = reactive({ caller_id: '', key: '', status: '', start_date: defaultDates.start, end_date: defaultDates.end, task_id: '' })
const uploadForm = reactive({ backend: '', lang: '', enable_postprocess: false, postprocess_rule_id: '', caller_id: '' })

const enabledRules = computed(() => rules.value.filter((rule) => Boolean(rule.enabled)))
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

interface PageItem {
  key: string
  page: number | null
}

const pageItems = computed<PageItem[]>(() => {
  const count = totalPages.value
  const current = page.value
  const pages = new Set<number>([1, count, current - 2, current - 1, current, current + 1, current + 2])
  const sorted = [...pages].filter((p) => p >= 1 && p <= count).sort((a, b) => a - b)
  const items: PageItem[] = []
  let prev = 0
  for (const p of sorted) {
    if (p - prev > 1) items.push({ key: `gap-${p}`, page: null })
    items.push({ key: `p-${p}`, page: p })
    prev = p
  }
  return items
})

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : ''
}

function statusBadgeClass(status: string) {
  switch (status) {
    case 'pending':
      return 'text-bg-warning'
    case 'processing':
      return 'text-bg-primary'
    case 'completed':
      return 'text-bg-success'
    case 'failed':
      return 'text-bg-danger'
    case 'cancelled':
      return 'text-bg-dark'
    default:
      return 'text-bg-secondary'
  }
}

function statusLabel(status: string) {
  const key = `status.${status}`
  if (['pending', 'processing', 'completed', 'failed', 'cancelled'].includes(status)) {
    return t(key)
  }
  return status
}

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  selectedFile.value = target.files?.[0] ?? null
}

function resetCreateForm() {
  selectedFile.value = null
  uploadForm.backend = ''
  uploadForm.lang = ''
  uploadForm.enable_postprocess = false
  uploadForm.postprocess_rule_id = ''
  uploadForm.caller_id = callers.value[0]?.caller_id ?? ''
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

async function loadRules() {
  const payload = await apiFetch<PostprocessPlanListResponse>('/api/admin/postprocess-plans?include_disabled=false')
  rules.value = payload.items
}

async function loadCallers() {
  try {
    const payload = await apiFetch<CallerItem[]>('/api/admin/callers?include_disabled=false')
    callers.value = payload
  } catch {
    callers.value = []
  }
}

function openCreateModal() {
  error.value = ''
  resetCreateForm()
  showCreateModal.value = true
  nextTick(() => fileInput.value?.focus())
}

function closeCreateModal() {
  if (creating.value) return
  showCreateModal.value = false
  resetCreateForm()
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && showCreateModal.value) {
    event.preventDefault()
  }
}

async function loadTasks() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String((page.value - 1) * PAGE_SIZE),
    })
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(key, value)
    })
    const payload = await apiFetch<TaskListResponse>('/api/admin/tasks?' + params.toString())
    tasks.value = payload.tasks
    total.value = payload.total
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.loadFailed')
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  loadTasks()
}

function goToPage(target: number) {
  if (target < 1 || target > totalPages.value || target === page.value) return
  page.value = target
  loadTasks()
}

async function createTask() {
  if (!selectedFile.value) {
    error.value = t('tasks.fileRequired')
    return
  }
  creating.value = true
  error.value = ''
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    if (uploadForm.lang) formData.append('lang', uploadForm.lang)
    if (uploadForm.backend) formData.append('backend', uploadForm.backend)
    if (uploadForm.caller_id) formData.append('caller_id', uploadForm.caller_id)
    formData.append('enable_postprocess', uploadForm.enable_postprocess ? 'true' : 'false')
    if (uploadForm.enable_postprocess) {
      if (!uploadForm.postprocess_rule_id) {
        error.value = t('tasks.planRequired')
        creating.value = false
        return
      }
      formData.append('postprocess_rule_id', uploadForm.postprocess_rule_id)
    }
    await apiFetch('/api/admin/tasks', { method: 'POST', body: formData })
    showCreateModal.value = false
    resetCreateForm()
    await loadTasks()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.createFailed')
  } finally {
    creating.value = false
  }
}

async function deleteTask(taskId: string) {
  if (!window.confirm(t('tasks.deleteConfirm', { taskId }))) return
  error.value = ''
  try {
    await apiFetch('/api/admin/tasks/' + encodeURIComponent(taskId), { method: 'DELETE' })
    if (tasks.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    await loadTasks()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.deleteFailed')
  }
}

function resetFilters() {
  const dates = defaultDateRange()
  filters.caller_id = ''
  filters.key = ''
  filters.status = ''
  filters.start_date = dates.start
  filters.end_date = dates.end
  filters.task_id = ''
  page.value = 1
  loadTasks()
}

onMounted(() => {
  loadRules()
  loadCallers()
  loadTasks()
  window.addEventListener('keydown', handleKeydown)
})
onBeforeUnmount(() => window.removeEventListener('keydown', handleKeydown))
</script>
