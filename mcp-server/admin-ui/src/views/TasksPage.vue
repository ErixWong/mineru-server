<template>
  <AdminLayout>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h3 class="mb-0">任务列表</h3>
      <button class="btn btn-primary" @click="showUpload = !showUpload">{{ showUpload ? '取消' : '新建任务' }}</button>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card page-card mb-3">
      <div class="card-body">
        <div class="row g-3 align-items-end">
          <div class="col-md-2"><label class="form-label">调用方ID</label><input v-model="filters.caller_id" class="form-control" /></div>
          <div class="col-md-2"><label class="form-label">API Key</label><input v-model="filters.key" class="form-control" /></div>
          <div class="col-md-2"><label class="form-label">状态</label>
            <select v-model="filters.status" class="form-select">
              <option value="">全部</option><option value="pending">pending</option><option value="processing">processing</option><option value="completed">completed</option><option value="failed">failed</option><option value="cancelled">cancelled</option>
            </select>
          </div>
          <div class="col-md-2"><label class="form-label">开始日期</label><input v-model="filters.start_date" class="form-control" type="date" /></div>
          <div class="col-md-2"><label class="form-label">结束日期</label><input v-model="filters.end_date" class="form-control" type="date" /></div>
          <div class="col-md-2"><label class="form-label">Task ID</label><input v-model="filters.task_id" class="form-control" /></div>
          <div class="col-12"><button class="btn btn-outline-primary" @click="loadTasks">筛选</button></div>
        </div>
      </div>
    </div>

    <div v-if="showUpload" class="card page-card mb-3">
      <div class="card-body">
        <h5 class="card-title">新建任务</h5>
        <form class="row g-3" @submit.prevent="createTask">
          <div class="col-md-4"><label class="form-label">PDF 文件</label><input class="form-control" type="file" accept=".pdf" @change="onFileChange" required /></div>
          <div class="col-md-4"><label class="form-label">后端</label>
            <select v-model="uploadForm.backend" class="form-select">
              <option value="">默认</option>
              <option value="pipeline">pipeline</option>
              <option value="vlm-auto-engine">vlm-auto-engine</option>
              <option value="vlm-http-client">vlm-http-client</option>
              <option value="hybrid-auto-engine">hybrid-auto-engine</option>
              <option value="hybrid-http-client">hybrid-http-client</option>
            </select>
          </div>
          <div class="col-md-4"><label class="form-label">语言</label>
            <select v-model="uploadForm.lang" class="form-select">
              <option value="ch">中文</option><option value="en">英文</option><option value="ja">日文</option><option value="ko">韩文</option><option value="fr">法文</option><option value="de">德文</option>
            </select>
          </div>
          <div class="col-12"><button class="btn btn-primary" :disabled="creating">{{ creating ? '提交中...' : '提交' }}</button></div>
        </form>
      </div>
    </div>

    <div class="card page-card">
      <div class="card-body">
        <div class="table-wrap">
          <table class="table table-hover align-middle mb-0">
            <thead><tr><th>状态</th><th>文件名</th><th>调用方</th><th>处理摘要</th><th>创建时间</th><th>完成时间</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-if="loading"><td colspan="7" class="text-center text-muted py-4">加载中...</td></tr>
              <tr v-else-if="tasks.length === 0"><td colspan="7" class="text-center text-muted py-4">暂无任务</td></tr>
              <tr v-for="task in tasks" :key="task.task_id">
                <td><span class="badge text-bg-secondary">{{ task.status }}</span></td>
                <td>{{ task.input_filename }}</td>
                <td>{{ task.caller_name || '-' }}</td>
                <td>{{ task.result_summary || task.message || task.error || '' }}</td>
                <td>{{ formatDate(task.created_at) }}</td>
                <td>{{ formatDate(task.completed_at) || '-' }}</td>
                <td>
                  <div class="btn-group btn-group-sm">
                    <RouterLink class="btn btn-outline-primary" :to="`/tasks/${task.task_id}`">详情</RouterLink>
                    <button class="btn btn-outline-danger" @click="deleteTask(task.task_id)">删除</button>
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
import { onMounted, reactive, ref } from 'vue'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import type { TaskListItem, TaskListResponse } from '../types'

const tasks = ref<TaskListItem[]>([])
const loading = ref(false)
const creating = ref(false)
const showUpload = ref(false)
const selectedFile = ref<File | null>(null)
const error = ref('')
const filters = reactive({ caller_id: '', key: '', status: '', start_date: '', end_date: '', task_id: '' })
const uploadForm = reactive({ backend: '', lang: 'ch' })

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : ''
}

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  selectedFile.value = target.files?.[0] ?? null
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
    showUpload.value = false
    selectedFile.value = null
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

onMounted(loadTasks)
</script>
