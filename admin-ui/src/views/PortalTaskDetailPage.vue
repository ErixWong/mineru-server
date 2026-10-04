<template>
  <section>
    <div class="d-flex flex-wrap justify-content-between align-items-end gap-3 mb-4">
      <div>
        <RouterLink class="small text-decoration-none" :to="{ name: 'portal-tasks' }"><i class="bi bi-arrow-left me-1"></i>返回我的任务</RouterLink>
        <h1 class="fs-3 fw-semibold mt-2 mb-1 text-break">{{ taskName }}</h1>
        <div class="small text-body-secondary font-monospace text-break">{{ taskId }}</div>
      </div>
      <button class="btn btn-outline-secondary" :disabled="loading" @click="load">
        <i class="bi bi-arrow-clockwise me-1"></i>刷新
      </button>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="task" class="row g-4">
      <div class="col-lg-4">
        <div class="card mb-4">
          <div class="card-body p-4">
            <div class="d-flex justify-content-between align-items-center gap-3 mb-3">
              <h2 class="fs-5 fw-semibold mb-0">解析进度</h2>
              <span class="badge" :class="statusClass(task.status)">{{ statusLabel(task.status) }}</span>
            </div>
            <div v-if="task.status === 'processing' || task.status === 'pending'" class="mb-3">
              <div class="d-flex justify-content-between small mb-1">
                <span>{{ task.status === 'pending' ? '正在等待开始' : (task.message || '正在解析文档') }}</span>
                <span>{{ task.status === 'pending' ? '—' : `${task.progress ?? 0}%` }}</span>
              </div>
              <div class="progress" style="height: 8px">
                <div
                  class="progress-bar"
                  :class="{ 'progress-bar-striped progress-bar-animated': task.status === 'pending' || task.status === 'processing' }"
                  :style="{ width: `${task.status === 'pending' ? 100 : (task.progress ?? 0)}%` }"
                ></div>
              </div>
              <p class="small text-body-secondary mt-3 mb-0">您可以稍后回来查看，页面会自动更新。</p>
            </div>
            <div class="small text-body-secondary">提交时间：{{ formatDate(task.created_at) }}</div>
            <div v-if="task.error" class="alert alert-warning mt-3 mb-0">{{ task.error }}</div>
          </div>
        </div>

        <div v-if="task.status === 'completed'" class="card">
          <div class="card-body p-4">
            <h2 class="fs-5 fw-semibold mb-3">可下载的文件</h2>
            <div v-if="deliverables.length" class="list-group list-group-flush">
              <div v-for="item in deliverables" :key="item.download_key" class="list-group-item px-0 py-3">
                <div class="d-flex justify-content-between align-items-center gap-3">
                  <div class="min-w-0">
                    <div class="fw-medium text-break">{{ item.filename }}</div>
                    <div class="small text-body-secondary">{{ item.name }}</div>
                  </div>
                  <a class="btn btn-outline-primary btn-sm flex-shrink-0" :href="downloadUrl(item)" :download="item.filename">
                    <i class="bi bi-download me-1"></i>下载
                  </a>
                </div>
              </div>
            </div>
            <div v-else class="small text-body-secondary">暂时没有可下载的文件。</div>
          </div>
        </div>
      </div>

      <div class="col-lg-8">
        <div class="card">
          <div class="card-body p-4 p-lg-5">
            <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
              <div>
                <h2 class="fs-5 fw-semibold mb-1">解析结果</h2>
                <p class="small text-body-secondary mb-0">解析完成后，您可以直接预览文档内容。</p>
              </div>
              <a v-if="markdown" class="btn btn-outline-primary btn-sm" :href="markdownDownloadUrl" download="result.md">
                <i class="bi bi-download me-1"></i>下载 Markdown
              </a>
            </div>
            <div v-if="task.status !== 'completed'" class="text-center text-body-secondary py-5">
              <div v-if="task.status === 'pending' || task.status === 'processing'" class="spinner-border text-primary mb-3" role="status"><span class="visually-hidden">处理中</span></div>
              <i v-else class="bi bi-file-earmark-x display-5 d-block mb-3"></i>
              <div>{{ task.status === 'pending' || task.status === 'processing' ? '结果生成后会显示在这里。' : '本次任务未能完成，请查看上方提示。' }}</div>
            </div>
            <div v-else-if="resultLoading" class="text-body-secondary py-5 text-center">正在读取解析结果…</div>
            <div v-else-if="markdown" class="result-markdown portal-markdown" v-html="renderedMarkdown"></div>
            <div v-else class="text-body-secondary py-5 text-center">任务已完成，但暂未生成 Markdown 内容。</div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import { useRoute } from 'vue-router'
import { apiFetch, ApiError } from '../lib/api'
import type { DeliverableItem, DeliverablesResponse, PortalTaskResult } from '../types'

interface TaskStatus {
  task_id: string
  status: string
  input_filename?: string
  progress?: number
  message?: string | null
  error?: string | null
  created_at?: string
}

const route = useRoute()
const taskId = computed(() => String(route.params.taskId || ''))
const task = ref<TaskStatus | null>(null)
const deliverables = ref<DeliverableItem[]>([])
const markdown = ref('')
const loading = ref(false)
const resultLoading = ref(false)
const error = ref('')
let pollTimer = 0
const markdownParser = new MarkdownIt({ html: false, breaks: true })
const taskName = computed(() => {
  return task.value?.input_filename || `任务 ${taskId.value}`
})
const renderedMarkdown = computed(() => DOMPurify.sanitize(markdownParser.render(markdown.value)))
const markdownArtifact = computed(() => deliverables.value.find((item) => item.is_default || item.filename.toLowerCase().endsWith('.md')))
const markdownDownloadUrl = computed(() => markdownArtifact.value ? downloadUrl(markdownArtifact.value) : '')

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

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString() : '—'
}

function downloadUrl(item: DeliverableItem) {
  return `/api/portal/tasks/${encodeURIComponent(taskId.value)}/deliverables/download?download_key=${encodeURIComponent(item.download_key)}`
}

async function load() {
  if (!taskId.value) return
  loading.value = true
  error.value = ''
  try {
    task.value = await apiFetch<TaskStatus>(`/api/portal/tasks/${encodeURIComponent(taskId.value)}`)
    if (task.value.status === 'completed') {
      resultLoading.value = true
      const [result, listed] = await Promise.all([
        apiFetch<PortalTaskResult>(`/api/portal/tasks/${encodeURIComponent(taskId.value)}/result`),
        apiFetch<DeliverablesResponse>(`/api/portal/tasks/${encodeURIComponent(taskId.value)}/deliverables`),
      ])
      markdown.value = result.postprocessed_markdown || result.markdown || ''
      deliverables.value = listed.artifacts || []
    } else {
      markdown.value = ''
      deliverables.value = []
    }
  } catch (err) {
    error.value = err instanceof ApiError && err.status === 404
      ? '找不到此任务，或您没有查看权限。'
      : err instanceof ApiError ? err.message : '暂时无法读取任务详情，请稍后重试。'
  } finally {
    loading.value = false
    resultLoading.value = false
  }
}

watch(taskId, () => void load())

onMounted(() => {
  void load()
  pollTimer = window.setInterval(() => {
    if (task.value?.status === 'pending' || task.value?.status === 'processing') void load()
  }, 5000)
})

onBeforeUnmount(() => window.clearInterval(pollTimer))
</script>

<style scoped>
.portal-markdown {
  max-height: 75vh;
  overflow: auto;
  overflow-wrap: anywhere;
}
</style>
