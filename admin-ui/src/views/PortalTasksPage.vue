<template>
  <section>
    <div class="d-flex flex-wrap justify-content-between align-items-end gap-3 mb-4">
      <div>
        <div class="small text-uppercase text-body-secondary fw-semibold mb-1">个人空间</div>
        <h1 class="fs-3 fw-semibold mb-1">我的任务</h1>
        <p class="text-body-secondary mb-0">查看文档解析进度和历史结果。</p>
      </div>
      <RouterLink class="btn btn-primary" :to="{ name: 'portal-new-task' }"><i class="bi bi-plus-lg me-1"></i>新建解析</RouterLink>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
      <label class="form-label mb-0" for="portal-status">任务状态</label>
      <select id="portal-status" v-model="status" class="form-select" style="max-width: 220px" @change="changeStatus">
        <option value="">全部任务</option>
        <option value="pending">排队中</option>
        <option value="processing">解析中</option>
        <option value="completed">已完成</option>
        <option value="failed">未完成</option>
        <option value="cancelled">已取消</option>
      </select>
    </div>

    <div class="card">
      <div class="card-body">
        <div v-if="loading" class="text-center text-body-secondary py-5">正在加载任务…</div>
        <div v-else-if="!tasks.length" class="text-center text-body-secondary py-5">
          <i class="bi bi-inbox display-6 d-block mb-2"></i>没有找到符合条件的任务。
        </div>
        <div v-else class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead>
              <tr>
                <th>文档</th>
                <th>提交时间</th>
                <th>进度</th>
                <th>状态</th>
                <th class="text-end">操作</th>
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
                <td><span class="badge" :class="statusClass(task.status)">{{ statusLabel(task.status) }}</span></td>
                <td class="text-end">
                  <RouterLink class="btn btn-outline-primary btn-sm" :to="{ name: 'portal-task-detail', params: { taskId: task.task_id } }">查看详情</RouterLink>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-3">
          <div class="small text-body-secondary">共 {{ total }} 个任务，第 {{ page }} / {{ totalPages }} 页</div>
          <div v-if="totalPages > 1" class="btn-group btn-group-sm">
            <button class="btn btn-outline-secondary" :disabled="page <= 1" @click="goToPage(page - 1)">上一页</button>
            <button class="btn btn-outline-secondary" :disabled="page >= totalPages" @click="goToPage(page + 1)">下一页</button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch, ApiError } from '../lib/api'
import type { PortalTaskItem, PortalTaskPage } from '../types'

const route = useRoute()
const router = useRouter()
const tasks = ref<PortalTaskItem[]>([])
const status = ref(typeof route.query.status === 'string' ? route.query.status : '')
const page = ref(1)
const total = ref(0)
const totalPages = ref(0)
const loading = ref(false)
const error = ref('')
let pollTimer = 0

function taskName(task: PortalTaskItem) {
  return task.filename || task.input_filename || '文档解析任务'
}

function statusLabel(value: string) {
  const labels: Record<string, string> = { pending: '排队中', processing: '解析中', completed: '已完成', failed: '未完成', cancelled: '已取消' }
  return labels[value] || value
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
    error.value = err instanceof ApiError ? err.message : '暂时无法加载任务，请稍后重试。'
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
