<template>
  <AdminLayout>
    <div class="mb-3">
      <RouterLink class="btn btn-link px-0" to="/tasks">&larr; 返回任务列表</RouterLink>
    </div>
    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="loading" class="text-muted">加载中...</div>
    <template v-else-if="task">
      <div class="row g-3 mb-3">
        <div class="col-lg-6">
          <div class="card page-card h-100"><div class="card-body">
            <h5 class="card-title">任务详情</h5>
            <table class="table table-sm mb-0">
              <tbody>
                <tr><th>Task ID</th><td class="monospace small">{{ task.task_id }}</td></tr>
                <tr><th>状态</th><td>{{ task.status }}</td></tr>
                <tr><th>文件名</th><td>{{ task.input_filename }}</td></tr>
                <tr><th>Backend</th><td>{{ task.backend || '-' }}</td></tr>
                <tr><th>调用方</th><td>{{ task.caller_name || '-' }}</td></tr>
                <tr><th>创建</th><td>{{ formatDate(task.created_at) }}</td></tr>
                <tr><th>开始</th><td>{{ formatDate(task.started_at) || '-' }}</td></tr>
                <tr><th>完成</th><td>{{ formatDate(task.completed_at) || '-' }}</td></tr>
              </tbody>
            </table>
            <div v-if="task.status === 'completed'" class="mt-3">
              <a class="btn btn-outline-primary btn-sm" :href="`/api/admin/tasks/${task.task_id}/source?name=${encodeURIComponent(task.input_filename)}`" target="_blank">下载原始文件</a>
            </div>
          </div></div>
        </div>
        <div class="col-lg-6">
          <div class="card page-card h-100"><div class="card-body">
            <h5 class="card-title">附件</h5>
            <div v-if="deliverables.length === 0" class="text-muted">暂无交付物</div>
            <ul v-else class="list-group list-group-flush">
              <li v-for="item in deliverables" :key="item.download_key" class="list-group-item d-flex justify-content-between align-items-center px-0">
                <a :href="`/api/admin/tasks/${task.task_id}/deliverables/download?download_key=${encodeURIComponent(item.download_key)}`" target="_blank">{{ item.filename }}</a>
                <span class="text-muted small">{{ item.size ? `${(item.size / 1024).toFixed(1)} KB` : '-' }}</span>
              </li>
            </ul>
          </div></div>
        </div>
      </div>

      <div v-if="task.error" class="card page-card mb-3 border-danger"><div class="card-body">
        <h5 class="card-title text-danger">错误信息</h5>
        <pre class="result-block mb-0">{{ task.error }}</pre>
      </div></div>

      <div v-if="task.result_raw" class="card page-card"><div class="card-body">
        <h5 class="card-title">解析结果</h5>
        <pre class="result-block mb-0">{{ task.result_raw }}</pre>
      </div></div>
    </template>
  </AdminLayout>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import type { DeliverableItem, DeliverablesResponse, TaskDetail } from '../types'

const route = useRoute()
const task = ref<TaskDetail | null>(null)
const deliverables = ref<DeliverableItem[]>([])
const loading = ref(false)
const error = ref('')

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : ''
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const taskId = String(route.params.taskId)
    task.value = await apiFetch<TaskDetail>('/api/admin/tasks/' + encodeURIComponent(taskId))
    if (task.value.status === 'completed') {
      const payload = await apiFetch<DeliverablesResponse>('/api/admin/tasks/' + encodeURIComponent(taskId) + '/deliverables')
      deliverables.value = payload.artifacts
    }
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
