<template>
  <section>
    <div class="d-flex flex-wrap justify-content-between align-items-end gap-3 mb-4">
      <div>
        <div class="small text-uppercase text-body-secondary fw-semibold mb-1">个人空间</div>
        <h1 class="fs-3 fw-semibold mb-1">你好，{{ profile?.display_name || profile?.username || '欢迎回来' }}</h1>
        <p class="text-body-secondary mb-0">上传 PDF 或图片，轻松提取文档内容。</p>
      </div>
      <RouterLink class="btn btn-primary btn-lg" :to="{ name: 'portal-new-task' }">
        <i class="bi bi-plus-lg me-2"></i>开始新解析
      </RouterLink>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="loading && !tasks.length" class="alert alert-light border text-body-secondary">正在加载您的任务…</div>

    <div class="row g-4 mb-4">
      <div class="col-lg-5">
        <div class="card h-100 border-primary-subtle bg-primary-subtle">
          <div class="card-body p-4 p-lg-5">
            <div class="d-flex align-items-center justify-content-between gap-3 mb-2">
              <div class="text-primary-emphasis fw-semibold">可用解析页数</div>
              <i class="bi bi-layers fs-3 text-primary"></i>
            </div>
            <div class="display-4 fw-semibold text-primary-emphasis lh-1 my-3">
              {{ unlimited ? '不限量' : (profile?.quota_remaining_pages ?? 0).toLocaleString() }}
              <span v-if="!unlimited" class="fs-5 fw-normal">页</span>
            </div>
            <template v-if="!unlimited">
              <div class="progress mb-2" role="progressbar" :aria-valuenow="usagePercent" aria-valuemin="0" aria-valuemax="100" aria-label="额度使用情况">
                <div class="progress-bar" :style="{ width: `${usagePercent}%` }"></div>
              </div>
              <div class="small text-body-secondary">
                已使用 {{ profile?.quota_used_pages ?? 0 }} / {{ profile?.quota_total_pages ?? 0 }} 页
              </div>
            </template>
            <div v-else class="small text-body-secondary">您的账户当前没有页数上限。</div>
            <div v-if="!unlimited && (profile?.quota_remaining_pages ?? 0) <= 0" class="alert alert-warning py-2 mt-3 mb-0 small">
              当前可用页数已用完，请补充额度后再提交解析。
            </div>
            <RouterLink class="btn btn-outline-primary mt-3" :to="{ name: 'portal-ledger' }">查看额度明细</RouterLink>
          </div>
        </div>
      </div>

      <div class="col-lg-7">
        <div class="card h-100">
          <div class="card-body p-4 p-lg-5">
            <div class="d-flex justify-content-between align-items-center gap-3 mb-3">
              <div>
                <h2 class="fs-5 fw-semibold mb-1">最近的任务</h2>
                <p class="small text-body-secondary mb-0">处理中的任务会自动更新进度。</p>
              </div>
              <RouterLink class="btn btn-outline-secondary btn-sm" :to="{ name: 'portal-tasks' }">查看全部</RouterLink>
            </div>
            <div v-if="!tasks.length" class="text-center py-5 text-body-secondary">
              <i class="bi bi-file-earmark-plus display-6 d-block mb-2"></i>
              还没有解析任务，上传文件即可开始。
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
                  <span class="badge flex-shrink-0" :class="statusClass(task.status)">{{ statusLabel(task.status) }}</span>
                </div>
              </RouterLink>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { apiFetch, ApiError } from '../lib/api'
import { usePortalStore } from '../stores/portal'
import type { PortalTaskItem, PortalTaskPage } from '../types'

const portal = usePortalStore()
const profile = computed(() => portal.profile)
const tasks = ref<PortalTaskItem[]>([])
const loading = ref(false)
const error = ref('')
let pollTimer = 0
const unlimited = computed(() => profile.value?.quota_total_pages === null)
const usagePercent = computed(() => {
  const total = profile.value?.quota_total_pages ?? 0
  if (!total) return 0
  return Math.min(100, Math.max(0, ((profile.value?.quota_used_pages ?? 0) / total) * 100))
})

function taskName(task: PortalTaskItem) {
  return task.filename || task.input_filename || '文档解析任务'
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: '排队中',
    processing: '解析中',
    completed: '已完成',
    failed: '未完成',
    cancelled: '已取消',
  }
  return labels[status] || status
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
    error.value = err instanceof ApiError ? err.message : '暂时无法加载任务，请稍后重试。'
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
