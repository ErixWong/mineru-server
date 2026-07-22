<template>
  <AdminLayout>
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <div>
        <h3 class="mb-1">任务列表</h3>
        <div class="text-muted small">默认显示最近一周任务，每页 10 条</div>
      </div>
      <button class="btn btn-primary" @click="openCreateModal">
        <i class="bi bi-plus-lg me-1"></i>
        新建任务
      </button>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card shadow-sm mb-3">
      <div class="card-body">
        <div class="row g-3 align-items-end">
          <div class="col-12 col-md-4 col-xl-2"><label class="form-label">调用方ID</label><input v-model="filters.caller_id" class="form-control" placeholder="精确匹配" /></div>
          <div class="col-12 col-md-4 col-xl-2"><label class="form-label">API Key</label><input v-model="filters.key" class="form-control" placeholder="精确匹配" /></div>
          <div class="col-12 col-md-4 col-xl-2"><label class="form-label">状态</label>
            <select v-model="filters.status" class="form-select">
              <option value="">全部</option>
              <option value="pending">待处理</option>
              <option value="processing">处理中</option>
              <option value="completed">已完成</option>
              <option value="failed">失败</option>
              <option value="cancelled">已取消</option>
            </select>
          </div>
          <div class="col-12 col-md-4 col-xl-2"><label class="form-label">开始日期</label><input v-model="filters.start_date" class="form-control" type="date" /></div>
          <div class="col-12 col-md-4 col-xl-2"><label class="form-label">结束日期</label><input v-model="filters.end_date" class="form-control" type="date" /></div>
          <div class="col-12 col-md-4 col-xl-2"><label class="form-label">Task ID</label><input v-model="filters.task_id" class="form-control" placeholder="精确匹配" /></div>
          <div class="col-12 col-xl-2 d-flex gap-2">
            <button class="btn btn-outline-primary flex-grow-1" @click="applyFilters">筛选</button>
            <button class="btn btn-outline-secondary" @click="resetFilters">重置</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showCreateModal" class="modal fade show d-block" tabindex="-1" role="dialog" aria-modal="true" aria-labelledby="create-task-title">
      <div class="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
        <div class="modal-content">
          <div class="modal-header">
            <h5 id="create-task-title" class="modal-title">新建任务</h5>
            <button type="button" class="btn-close" aria-label="关闭" @click="closeCreateModal"></button>
          </div>
          <div class="modal-body">
            <form class="row g-3" @submit.prevent="createTask">
              <div class="col-12 col-md-4"><label class="form-label">PDF 文件</label><input ref="fileInput" class="form-control" type="file" accept=".pdf" @change="onFileChange" required /></div>
              <div class="col-12 col-md-4"><label class="form-label">后端</label>
                <select v-model="uploadForm.backend" class="form-select">
                  <option value="">默认</option>
                  <option value="pipeline">pipeline</option>
                  <option value="vlm-auto-engine">vlm-auto-engine</option>
                  <option value="vlm-http-client">vlm-http-client</option>
                  <option value="hybrid-auto-engine">hybrid-auto-engine</option>
                  <option value="hybrid-http-client">hybrid-http-client</option>
                </select>
              </div>
              <div class="col-12 col-md-4"><label class="form-label">语言</label>
                <select v-model="uploadForm.lang" class="form-select">
                  <option value="">默认（中文）</option>
                  <option value="ch">中文</option><option value="en">英文</option><option value="ja">日文</option><option value="ko">韩文</option><option value="fr">法文</option><option value="de">德文</option>
                </select>
              </div>
              <div class="col-12 col-md-4"><label class="form-label">归属调用方</label>
                <select v-model="uploadForm.caller_id" class="form-select">
                  <option value="">不指派（仅管理台可见）</option>
                  <option v-for="caller in callers" :key="caller.caller_id" :value="caller.caller_id">{{ caller.name }}</option>
                </select>
                <div class="form-text">指派后该调用方的 API key 可查询并下载本任务结果。</div>
              </div>
              <div class="col-12">
                <div class="form-check form-switch">
                  <input id="enable-postprocess" v-model="uploadForm.enable_postprocess" class="form-check-input" type="checkbox" />
                  <label class="form-check-label" for="enable-postprocess">启用后处理</label>
                </div>
              </div>
              <template v-if="uploadForm.enable_postprocess">
                <div class="col-12 col-md-6"><label class="form-label">后处理方案</label>
                  <select v-model="uploadForm.postprocess_rule_id" class="form-select">
                    <option value="">请选择方案</option>
                    <option v-for="rule in enabledRules" :key="rule.plan_id" :value="rule.plan_id">{{ rule.title }}</option>
                  </select>
                </div>
              </template>
              <div class="col-12 d-flex justify-content-end gap-2">
                <button type="button" class="btn btn-outline-secondary" @click="closeCreateModal">取消</button>
                <button class="btn btn-primary" :disabled="creating">{{ creating ? '提交中...' : '提交' }}</button>
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
                <th>文件名</th>
                <th>调用方</th>
                <th>摘要</th>
                <th>创建时间</th>
                <th>完成时间</th>
                <th>处理/后处理</th>
                <th class="text-end">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading"><td colspan="7" class="text-center text-muted py-4">加载中...</td></tr>
              <tr v-else-if="tasks.length === 0"><td colspan="7" class="text-center text-muted py-4">暂无任务</td></tr>
              <tr v-for="task in tasks" :key="task.task_id">
                <td>
                  <RouterLink class="fw-semibold text-break d-inline-block" :to="`/tasks/${task.task_id}`">{{ task.input_filename }}</RouterLink>
                  <div class="small text-muted font-monospace text-break">{{ task.task_id }}</div>
                </td>
                <td class="small text-break">{{ task.caller_name || '-' }}</td>
                <td class="small text-break">{{ task.result_summary || task.message || task.error || '暂无摘要' }}</td>
                <td class="small text-muted">{{ formatDate(task.created_at) }}</td>
                <td class="small text-muted">{{ formatDate(task.completed_at) || '-' }}</td>
                <td>
                  <div><span class="badge" :class="statusBadgeClass(task.status)">{{ statusLabel(task.status) }}</span></div>
                  <div class="mt-1">
                    <span v-if="task.enable_postprocess || (task.postprocess_status && task.postprocess_status !== 'not_enabled')" class="badge" :class="postprocessBadgeClass(task.postprocess_status)">{{ postprocessStatusLabel(task.postprocess_status) }}</span>
                    <span v-else class="text-muted small">后处理: -</span>
                  </div>
                </td>
                <td>
                  <div class="btn-group btn-group-sm d-flex justify-content-end" role="group">
                    <button class="btn btn-outline-danger btn-sm" @click="deleteTask(task.task_id)">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-3">
          <div class="text-muted small">共 {{ total }} 条 / 第 {{ page }} / {{ totalPages }} 页</div>
          <nav v-if="totalPages > 1" aria-label="任务列表分页">
            <ul class="pagination pagination-sm mb-0">
              <li class="page-item" :class="{ disabled: page <= 1 }">
                <button class="page-link" :disabled="page <= 1" @click="goToPage(page - 1)">上一页</button>
              </li>
              <li
                v-for="item in pageItems"
                :key="item.key"
                class="page-item"
                :class="{ active: item.page === page, disabled: item.page === null }"
              >
                <span v-if="item.page === null" class="page-link">…</span>
                <button v-else class="page-link" @click="goToPage(item.page)">{{ item.page }}</button>
              </li>
              <li class="page-item" :class="{ disabled: page >= totalPages }">
                <button class="page-link" :disabled="page >= totalPages" @click="goToPage(page + 1)">下一页</button>
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
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import { postprocessBadgeClass, postprocessStatusLabel } from '../lib/postprocess'
import type { CallerItem, PostprocessPlanItem, PostprocessPlanListResponse, TaskListItem, TaskListResponse } from '../types'

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
  switch (status) {
    case 'pending':
      return '待处理'
    case 'processing':
      return '处理中'
    case 'completed':
      return '已完成'
    case 'failed':
      return '失败'
    case 'cancelled':
      return '已取消'
    default:
      return status
  }
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
  // 默认归属第一个可用调用方（减少"忘记指派"导致的不可用任务）；
  // 需要"不指派"时可显式选择
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
    error.value = err instanceof ApiError ? err.message : '加载失败'
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
    error.value = '请选择文件'
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
    // 显式传递 enable_postprocess：管理台意图以表单为准，
    // 不随被指派 caller 的默认方案发生隐式继承
    formData.append('enable_postprocess', uploadForm.enable_postprocess ? 'true' : 'false')
    if (uploadForm.enable_postprocess) {
      if (!uploadForm.postprocess_rule_id) {
        error.value = '请选择后处理方案'
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
    error.value = err instanceof ApiError ? err.message : '创建失败'
  } finally {
    creating.value = false
  }
}

async function deleteTask(taskId: string) {
  if (!window.confirm(`确定删除任务 ${taskId} 吗？`)) return
  error.value = ''
  try {
    await apiFetch('/api/admin/tasks/' + encodeURIComponent(taskId), { method: 'DELETE' })
    if (tasks.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    await loadTasks()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
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
