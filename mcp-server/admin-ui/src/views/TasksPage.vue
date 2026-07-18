<template>
  <AdminLayout>
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <div>
        <h3 class="mb-1">任务列表</h3>
        <div class="text-muted small">默认显示最近 50 条任务</div>
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
            <button class="btn btn-outline-primary flex-grow-1" @click="loadTasks">筛选</button>
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
                  <option value="ch">中文</option><option value="en">英文</option><option value="ja">日文</option><option value="ko">韩文</option><option value="fr">法文</option><option value="de">德文</option>
                </select>
              </div>
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
                <th>状态</th>
                <th>文件名</th>
                <th>调用方</th>
                <th>摘要</th>
                <th>创建时间</th>
                <th>完成时间</th>
                <th class="text-end">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading"><td colspan="7" class="text-center text-muted py-4">加载中...</td></tr>
              <tr v-else-if="tasks.length === 0"><td colspan="7" class="text-center text-muted py-4">暂无任务</td></tr>
              <tr v-for="task in tasks" :key="task.task_id">
                <td><span class="badge" :class="statusBadgeClass(task.status)">{{ statusLabel(task.status) }}</span></td>
                <td>
                  <div class="fw-semibold text-break">{{ task.input_filename }}</div>
                  <div class="small text-muted font-monospace text-break">{{ task.task_id }}</div>
                </td>
                <td class="small text-break">{{ task.caller_name || '-' }}</td>
                <td class="small text-break">{{ task.result_summary || task.message || task.error || '暂无摘要' }}</td>
                <td class="small text-muted">{{ formatDate(task.created_at) }}</td>
                <td class="small text-muted">{{ formatDate(task.completed_at) || '-' }}</td>
                <td>
                  <div class="btn-group btn-group-sm d-flex justify-content-end" role="group">
                    <RouterLink class="btn btn-outline-primary btn-sm" :to="`/tasks/${task.task_id}`">详情</RouterLink>
                    <button class="btn btn-outline-danger btn-sm" @click="deleteTask(task.task_id)">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </AdminLayout>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, nextTick, reactive, ref } from 'vue'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import type { TaskListItem, TaskListResponse } from '../types'

const tasks = ref<TaskListItem[]>([])
const loading = ref(false)
const creating = ref(false)
const showCreateModal = ref(false)
const selectedFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const error = ref('')
const filters = reactive({ caller_id: '', key: '', status: '', start_date: '', end_date: '', task_id: '' })
const uploadForm = reactive({ backend: '', lang: 'ch' })

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
  uploadForm.lang = 'ch'
  if (fileInput.value) {
    fileInput.value.value = ''
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
    const params = new URLSearchParams({ limit: '50' })
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(key, value)
    })
    const payload = await apiFetch<TaskListResponse>('/api/admin/tasks?' + params.toString())
    tasks.value = payload.tasks
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
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
    formData.append('lang', uploadForm.lang)
    if (uploadForm.backend) formData.append('backend', uploadForm.backend)
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
    await loadTasks()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  }
}

function resetFilters() {
  filters.caller_id = ''
  filters.key = ''
  filters.status = ''
  filters.start_date = ''
  filters.end_date = ''
  filters.task_id = ''
  loadTasks()
}

onMounted(() => {
  loadTasks()
  window.addEventListener('keydown', handleKeydown)
})
onBeforeUnmount(() => window.removeEventListener('keydown', handleKeydown))
</script>
