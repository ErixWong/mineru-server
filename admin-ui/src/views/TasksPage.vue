<template>
  <AdminLayout>
    <div class="d-flex flex-wrap justify-content-between align-items-end gap-3 mb-4 mk-page-header">
      <div>
        <div class="mk-page-eyebrow mb-1">{{ t('nav.tasks') }}</div>
        <h1 class="mk-page-title mb-1">{{ t('tasks.title') }}</h1>
        <div class="text-body-secondary">{{ t('tasks.subtitle') }}</div>
        <div class="small text-primary-emphasis mt-2">{{ t('admin.tasks.currentScope', { scope: activeScopeLabel }) }}</div>
      </div>
      <div class="d-flex flex-wrap gap-2">
        <button class="btn btn-light border" type="button" data-bs-toggle="offcanvas" data-bs-target="#task-filters" aria-controls="task-filters">
          <i class="bi bi-sliders me-1"></i>{{ t('common.filter') }}
        </button>
        <button class="btn btn-primary" @click="openCreateModal">
          <i class="bi bi-plus-lg me-1"></i>{{ t('tasks.newTask') }}
        </button>
      </div>
    </div>

    <div v-if="error" class="alert bg-body border border-danger-subtle rounded-3 py-2 text-danger-emphasis">{{ error }}</div>

    <div class="mb-3" style="max-width: 32rem">
      <label class="form-label" for="task-scope">{{ t('admin.tasks.scopeSelect') }}</label>
      <select id="task-scope" v-model="scopeSelection" class="form-select" @change="updateScopeQuery">
        <option value="my">{{ t('admin.tasks.scopeMine') }}</option>
        <option value="all">{{ t('admin.tasks.scopeAll') }}</option>
        <option value="unassigned">{{ t('admin.tasks.scopeUnassigned') }}</option>
        <optgroup v-if="scopeUsers.length" :label="t('admin.tasks.scopeUsers')">
          <option v-for="user in scopeUsers" :key="user.user_id" :value="`user:${user.user_id}`">
            {{ t('admin.tasks.scopeUserOption', { name: user.display_name || user.username, username: user.username }) }}
          </option>
        </optgroup>
        <optgroup v-if="scopeCallers.length" :label="t('admin.tasks.scopeCallers')">
          <option v-for="caller in scopeCallers" :key="caller.caller_id" :value="`caller:${caller.caller_id}`">{{ caller.name }}</option>
        </optgroup>
      </select>
      <div v-if="scopeOptionsError" class="small text-danger mt-1">{{ scopeOptionsError }}</div>
    </div>

    <div class="d-flex flex-wrap gap-2 mb-3">
      <button class="btn btn-light border text-danger btn-sm" @click="quickFailed"><i class="bi bi-exclamation-circle me-1"></i>{{ t('tasks.quickFailed') }}</button>
      <button class="btn btn-light border text-primary btn-sm" @click="quickStale"><i class="bi bi-clock-history me-1"></i>{{ t('tasks.quickStale') }}</button>
      <button class="btn btn-light border btn-sm" @click="quickToday"><i class="bi bi-calendar-day me-1"></i>{{ t('tasks.quickToday') }}</button>
      <button class="btn btn-light border btn-sm" @click="quickUnassigned"><i class="bi bi-person-dash me-1"></i>{{ t('tasks.quickUnassigned') }}</button>
    </div>

    <div class="offcanvas offcanvas-end" tabindex="-1" id="task-filters" aria-labelledby="task-filters-title">
      <div class="offcanvas-header border-bottom">
        <h2 id="task-filters-title" class="offcanvas-title fs-5 fw-semibold">
          <i class="bi bi-sliders me-2 text-primary"></i>{{ t('common.filter') }}
        </h2>
        <button type="button" class="btn-close" data-bs-dismiss="offcanvas" :aria-label="t('common.close')"></button>
      </div>
      <div class="offcanvas-body">
        <div class="d-flex flex-column gap-3">
          <div><label class="form-label">{{ t('tasks.filter_caller') }}</label>
            <select v-model="filters.caller_id" class="form-select">
              <option value="">{{ t('tasks.filter_all') }}</option>
              <option value="__unassigned__">{{ t('tasks.unassigned') }}</option>
              <option v-for="caller in callers" :key="caller.caller_id" :value="caller.caller_id">{{ caller.name }}</option>
            </select>
          </div>
          <div><label class="form-label">{{ t('tasks.filter_filename') }}</label><input v-model="filters.filename" class="form-control" :placeholder="t('tasks.filter_fuzzyMatch')" /></div>
          <div><label class="form-label">{{ t('tasks.filter_status') }}</label>
            <select v-model="filters.status" class="form-select">
              <option value="">{{ t('tasks.filter_all') }}</option>
              <option value="pending">{{ t('status.pending') }}</option>
              <option value="processing">{{ t('status.processing') }}</option>
              <option value="completed">{{ t('status.completed') }}</option>
              <option value="failed">{{ t('status.failed') }}</option>
              <option value="cancelled">{{ t('status.cancelled') }}</option>
            </select>
          </div>
          <div><label class="form-label">{{ t('tasks.filter_backend') }}</label>
            <select v-model="filters.backend" class="form-select">
              <option value="">{{ t('tasks.filter_all') }}</option>
              <option v-for="backend in backendOptions" :key="backend" :value="backend">{{ backend }}</option>
            </select>
          </div>
          <div><label class="form-label">{{ t('tasks.filter_postprocess') }}</label>
            <select v-model="filters.postprocess_status" class="form-select">
              <option value="">{{ t('tasks.filter_all') }}</option>
              <option value="not_enabled">{{ t('status.notEnabled') }}</option>
              <option value="pending">{{ t('status.pending') }}</option>
              <option value="processing">{{ t('status.processing') }}</option>
              <option value="completed">{{ t('status.completed') }}</option>
              <option value="failed">{{ t('status.failed') }}</option>
              <option value="cancelled">{{ t('status.cancelled') }}</option>
            </select>
          </div>
          <div><label class="form-label">{{ t('tasks.filter_startDate') }}</label><input v-model="filters.start_date" class="form-control" type="date" /></div>
          <div><label class="form-label">{{ t('tasks.filter_endDate') }}</label><input v-model="filters.end_date" class="form-control" type="date" /></div>
          <div><label class="form-label">{{ t('tasks.filter_taskId') }}</label><input v-model="filters.task_id" class="form-control" :placeholder="t('tasks.filter_exactMatch')" /></div>
          <div><label class="form-label">{{ t('tasks.filter_apiKey') }}</label><input v-model="filters.key" class="form-control" :placeholder="t('tasks.filter_exactMatch')" /></div>
          <div><label class="form-label">{{ t('tasks.filter_stale') }}</label>
            <select v-model.number="filters.stale_processing_minutes" class="form-select">
              <option :value="0">{{ t('tasks.filter_all') }}</option>
              <option :value="10">{{ t('tasks.stale10') }}</option>
              <option :value="30">{{ t('tasks.stale30') }}</option>
              <option :value="60">{{ t('tasks.stale60') }}</option>
            </select>
          </div>
        </div>
      </div>
      <div class="sticky-bottom d-flex gap-2 border-top bg-body p-3">
        <button class="btn btn-primary flex-grow-1" data-bs-dismiss="offcanvas" @click="applyFilters">{{ t('common.filter') }}</button>
        <button class="btn btn-light border" @click="resetFilters">{{ t('common.reset') }}</button>
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

    <div class="card">
      <div class="card-body">
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead>
              <tr>
                <th class="small text-body-secondary fw-semibold">{{ t('tasks.fileName') }}</th>
                <th v-if="scopeShowsCaller" class="small text-body-secondary fw-semibold">{{ t('tasks.caller') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('tasks.summary') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('tasks.createdAt') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('tasks.completedAt') }}</th>
                <th class="small text-body-secondary fw-semibold">{{ t('tasks.processStatus') }}</th>
                <th class="text-end">{{ t('tasks.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading"><td :colspan="scopeShowsCaller ? 7 : 6" class="text-center text-body-secondary py-4">{{ t('common.loading') }}</td></tr>
              <tr v-else-if="tasks.length === 0"><td :colspan="scopeShowsCaller ? 7 : 6" class="p-0"><div class="mk-empty"><i class="bi bi-inbox mk-empty-icon"></i><h3 class="mk-empty-title">{{ t('common.noData') }}</h3></div></td></tr>
              <tr v-for="task in tasks" :key="task.task_id">
                <td>
                  <i
                    v-if="scopeShowsCaller && isOtherAdminTask(task)"
                    class="bi bi-shield-exclamation text-body-secondary me-1"
                    :title="t('admin.tasks.otherAccountTask')"
                    :aria-label="t('admin.tasks.otherAccountTask')"
                  ></i>
                  <RouterLink
                    class="fw-semibold text-break d-inline-block"
                    :to="{ name: 'task-detail', params: { taskId: task.task_id }, query: route.query }"
                  >{{ task.input_filename }}</RouterLink>
                  <div class="small text-body-secondary font-monospace text-break">{{ task.task_id }}</div>
                </td>
                <td v-if="scopeShowsCaller" class="small text-break">
                  <span class="badge bg-body-secondary text-body-secondary border">{{ task.caller_name || t('tasks.unassigned') }}</span>
                </td>
                <td class="small text-break">{{ task.result_summary || task.message || task.error || t('tasks.noSummary') }}</td>
                <td class="small text-body-secondary">{{ formatDate(task.created_at) }}</td>
                <td class="small text-body-secondary">{{ formatDate(task.completed_at) || '-' }}</td>
                <td>
                  <div><span class="badge mk-badge" :class="statusBadgeClass(task.status)">{{ statusLabel(task.status) }}</span></div>
                  <div class="mt-1">
                    <span v-if="task.enable_postprocess || (task.postprocess_status && task.postprocess_status !== 'not_enabled')" class="badge mk-badge" :class="postprocessBadgeClass(task.postprocess_status)">{{ postprocessStatusLabel(task.postprocess_status) }}</span>
                    <span v-else class="text-body-secondary small">{{ t('tasks.postprocessDisabled') }}</span>
                  </div>
                </td>
                <td>
                  <div class="btn-group btn-group-sm d-flex justify-content-end" role="group">
                    <button class="btn btn-light border text-primary btn-sm" :disabled="cloningTaskId === task.task_id" @click="cloneTask(task.task_id)">
                      {{ cloningTaskId === task.task_id ? t('tasks.cloning') : t('tasks.clone') }}
                    </button>
                    <button class="btn btn-light border text-danger btn-sm" @click="deleteTask(task.task_id)">{{ t('common.delete') }}</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-3">
          <div class="text-body-secondary small">{{ t('tasks.pagination_total', { total, page, totalPages }) }}</div>
          <nav v-if="totalPages > 1" :aria-label="t('tasks.title')">
            <ul class="pagination pagination-sm mb-0">
              <li class="page-item" :class="{ disabled: page <= 1 }">
                <button class="page-link" :disabled="page <= 1" @click="goToPage(page - 1)">{{ t('tasks.pagination_prev') }}</button>
              </li>
              <li
                v-for="item in pageItems"
                :key="item.key"
                class="page-item"
                :class="{ disabled: item.page === null }"
              >
                <span v-if="item.page === null" class="page-link">&hellip;</span>
                <button
                  v-else
                  class="page-link"
                  :class="{ 'bg-body text-primary border-primary fw-semibold': item.page === page }"
                  :aria-current="item.page === page ? 'page' : undefined"
                  @click="goToPage(item.page)"
                >{{ item.page }}</button>
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
import { computed, onMounted, onBeforeUnmount, nextTick, reactive, ref, watch } from 'vue'
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import { postprocessBadgeClass, postprocessStatusLabel } from '../lib/postprocess'
import { useAuthStore } from '../stores/auth'
import type { AdminUserItem, CallerItem, PostprocessPlanItem, PostprocessPlanListResponse, TaskCloneResponse, TaskListItem, TaskListResponse } from '../types'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const tasks = ref<TaskListItem[]>([])
const loading = ref(false)
const creating = ref(false)
const showCreateModal = ref(false)
const selectedFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const error = ref('')
const cloningTaskId = ref('')
const rules = ref<PostprocessPlanItem[]>([])
const callers = ref<CallerItem[]>([])
const scopeUsers = ref<AdminUserItem[]>([])
const scopeCallers = ref<CallerItem[]>([])
const scopeSelection = ref('my')
const scopeOptionsError = ref('')

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
const filters = reactive({
  caller_id: '',
  key: '',
  status: '',
  start_date: defaultDates.start,
  end_date: defaultDates.end,
  task_id: '',
  filename: '',
  backend: '',
  postprocess_status: '',
  stale_processing_minutes: 0,
})
const uploadForm = reactive({ backend: '', lang: '', enable_postprocess: false, postprocess_rule_id: '', caller_id: '' })
const backendOptions = ['pipeline', 'vlm-auto-engine', 'vlm-http-client', 'hybrid-auto-engine', 'hybrid-http-client']

const enabledRules = computed(() => rules.value.filter((rule) => Boolean(rule.enabled)))
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const activeScope = computed(() => parseScopeSelection(scopeSelection.value))
const currentAdminUsername = computed(() => auth.user?.username ?? '')
const scopeShowsCaller = computed(() => activeScope.value.kind === 'all')
function isOtherAdminTask(task: TaskListItem) {
  return Boolean(currentAdminUsername.value && task.created_by !== currentAdminUsername.value)
}

const activeScopeLabel = computed(() => {
  const scope = activeScope.value
  if (scope.kind === 'my') return t('admin.tasks.scopeMine')
  if (scope.kind === 'all') return t('admin.tasks.scopeAll')
  if (scope.kind === 'unassigned') return t('admin.tasks.scopeUnassigned')
  if (scope.kind === 'user') {
    const user = scopeUsers.value.find((item) => item.user_id === scope.id)
    return user ? t('admin.tasks.scopeUserOption', { name: user.display_name || user.username, username: user.username }) : scope.id
  }
  return scopeCallers.value.find((item) => item.caller_id === scope.id)?.name || scope.id
})

type TaskScope =
  | { kind: 'my' }
  | { kind: 'all' }
  | { kind: 'unassigned' }
  | { kind: 'user'; id: string }
  | { kind: 'caller'; id: string }

function parseScopeSelection(value: string): TaskScope {
  if (value === 'all' || value === 'unassigned') return { kind: value }
  if (value.startsWith('user:') && value.length > 5) return { kind: 'user', id: value.slice(5) }
  if (value.startsWith('caller:') && value.length > 7) return { kind: 'caller', id: value.slice(7) }
  return { kind: 'my' }
}

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
      return 'bg-warning-subtle text-warning-emphasis'
    case 'processing':
      return 'bg-primary-subtle text-primary-emphasis'
    case 'completed':
      return 'bg-success-subtle text-success-emphasis'
    case 'failed':
      return 'bg-danger-subtle text-danger-emphasis'
    case 'cancelled':
      return 'bg-secondary-subtle text-secondary-emphasis'
    default:
      return 'bg-secondary-subtle text-secondary-emphasis'
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

async function loadScopeOptions() {
  scopeOptionsError.value = ''
  try {
    const [userPayload, callerPayload] = await Promise.all([
      apiFetch<AdminUserItem[]>('/api/admin/users?include_disabled=true'),
      apiFetch<CallerItem[]>('/api/admin/callers?include_disabled=true'),
    ])
    scopeUsers.value = userPayload
    scopeCallers.value = callerPayload
  } catch (err) {
    scopeOptionsError.value = err instanceof ApiError ? err.message : t('common.loadFailed')
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
      if (value) params.set(key, String(value))
    })
    if (filters.caller_id === '__unassigned__') {
      params.delete('caller_id')
      params.set('caller_id', '__unassigned__')
    }
    const scope = activeScope.value
    if (scope.kind === 'my') {
      const username = auth.user?.username
      if (!username) throw new Error(t('admin.tasks.currentAdminUnavailable'))
      params.set('created_by', username)
    } else if (scope.kind === 'user') {
      params.set('scope_user_id', scope.id)
    } else if (scope.kind === 'caller') {
      params.set('scope_caller_id', scope.id)
    } else if (scope.kind === 'unassigned') {
      params.set('admin_console_only', 'true')
    }
    const payload = await apiFetch<TaskListResponse>('/api/admin/tasks?' + params.toString())
    tasks.value = payload.tasks
    total.value = payload.total
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.loadFailed')
  } finally {
    loading.value = false
  }
}

function hydrateScopeFromQuery() {
  const kind = typeof route.query.scope === 'string' ? route.query.scope : 'my'
  const id = typeof route.query.scope_id === 'string' ? route.query.scope_id : ''
  scopeSelection.value = kind === 'user' && id
    ? `user:${id}`
    : kind === 'caller' && id
      ? `caller:${id}`
      : kind === 'all' || kind === 'unassigned' || kind === 'my'
        ? kind
        : 'my'
}

function updateScopeQuery() {
  const scope = activeScope.value
  const query: LocationQueryRaw = { ...route.query, scope: scope.kind }
  delete query.scope_id
  if ('id' in scope) query.scope_id = scope.id
  void router.replace({ query })
}

watch(
  () => [route.query.scope, route.query.scope_id],
  () => {
    hydrateScopeFromQuery()
    page.value = 1
    void loadTasks()
  },
)

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
  const task = tasks.value.find((item) => item.task_id === taskId)
  const owner = task?.caller_name || task?.caller_id || t('tasks.unassigned')
  if (!window.confirm(t('admin.tasks.deleteConfirm', { taskId, owner }))) return
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

async function cloneTask(taskId: string) {
  const task = tasks.value.find((item) => item.task_id === taskId)
  if (!task || !window.confirm(t('admin.tasks.cloneConfirm', {
    name: task.input_filename,
    owner: task.caller_name || task.caller_id || t('tasks.unassigned'),
  }))) return
  cloningTaskId.value = taskId
  error.value = ''
  try {
    const payload = await apiFetch<TaskCloneResponse>('/api/admin/tasks/' + encodeURIComponent(taskId) + '/clone', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    await router.push({
      name: 'task-detail',
      params: { taskId: payload.task_id },
      query: route.query,
    })
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('tasks.cloneFailed')
  } finally {
    cloningTaskId.value = ''
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
  filters.filename = ''
  filters.backend = ''
  filters.postprocess_status = ''
  filters.stale_processing_minutes = 0
  page.value = 1
  loadTasks()
}

function quickFailed() {
  filters.status = 'failed'
  filters.stale_processing_minutes = 0
  page.value = 1
  loadTasks()
}

function quickStale() {
  filters.status = ''
  filters.stale_processing_minutes = 10
  page.value = 1
  loadTasks()
}

function quickToday() {
  const today = toLocalDate(new Date())
  filters.start_date = today
  filters.end_date = today
  filters.stale_processing_minutes = 0
  page.value = 1
  loadTasks()
}

function quickUnassigned() {
  filters.caller_id = '__unassigned__'
  page.value = 1
  loadTasks()
}

function hydrateFiltersFromQuery() {
  const query = route.query
  hydrateScopeFromQuery()
  if (typeof query.status === 'string') filters.status = query.status
  if (typeof query.caller_id === 'string') filters.caller_id = query.caller_id
  if (typeof query.filename === 'string') filters.filename = query.filename
  if (typeof query.backend === 'string') filters.backend = query.backend
  if (typeof query.postprocess_status === 'string') filters.postprocess_status = query.postprocess_status
}

onMounted(() => {
  hydrateFiltersFromQuery()
  loadRules()
  loadCallers()
  loadScopeOptions()
  loadTasks()
  window.addEventListener('keydown', handleKeydown)
})
onBeforeUnmount(() => window.removeEventListener('keydown', handleKeydown))
</script>
