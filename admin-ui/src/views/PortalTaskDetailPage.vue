<template>
  <section>
    <div class="d-flex flex-wrap justify-content-between align-items-end gap-3 mb-4">
      <div>
        <RouterLink class="small text-decoration-none" :to="{ name: 'portal-tasks' }"><i class="bi bi-arrow-left me-1"></i>{{ t('portal.detail.backToTasks') }}</RouterLink>
        <h1 class="fs-3 fw-semibold mt-2 mb-1 text-break">{{ taskName }}</h1>
        <div class="small text-body-secondary font-monospace text-break">{{ taskId }}</div>
      </div>
      <button class="btn btn-outline-secondary" :disabled="loading" @click="load">
        <i class="bi bi-arrow-clockwise me-1"></i>{{ t('portal.detail.refresh') }}
      </button>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="task" class="row g-4">
      <div class="col-lg-4 col-xxl-3">
        <div class="card mb-4">
          <div class="card-body p-4">
            <div class="d-flex justify-content-between align-items-center gap-3 mb-3">
              <h2 class="fs-5 fw-semibold mb-0">{{ t('portal.detail.progressTitle') }}</h2>
              <span class="badge mk-badge" :class="statusClass(task.status)">{{ statusLabel(task.status) }}</span>
            </div>
            <div v-if="task.status === 'processing' || task.status === 'pending'" class="mb-3">
              <div class="d-flex justify-content-between small mb-1">
                <span>{{ task.status === 'pending' ? t('portal.detail.waiting') : (task.message || t('portal.detail.parsing')) }}</span>
                <span>{{ task.status === 'pending' ? '—' : `${task.progress ?? 0}%` }}</span>
              </div>
              <div class="progress" style="height: 8px">
                <div
                  class="progress-bar"
                  :class="{ 'progress-bar-striped progress-bar-animated': task.status === 'pending' || task.status === 'processing' }"
                  :style="{ width: `${task.status === 'pending' ? 100 : (task.progress ?? 0)}%` }"
                ></div>
              </div>
              <p class="small text-body-secondary mt-3 mb-0">{{ t('portal.detail.autoRefreshHint') }}</p>
            </div>
            <div class="small text-body-secondary">{{ t('portal.detail.submittedAt', { time: formatDate(task.created_at) }) }}</div>
            <div v-if="task.error" class="alert alert-warning mt-3 mb-0">{{ task.error }}</div>
          </div>
        </div>

        <div v-if="task.status === 'completed'" class="card">
          <div class="card-body p-4">
            <h2 class="fs-5 fw-semibold mb-3">{{ t('portal.detail.downloadsTitle') }}</h2>
            <div v-if="deliverables.length" class="list-group list-group-flush">
              <div v-for="item in mainDeliverables" :key="item.download_key" class="list-group-item px-0 py-3">
                <div class="d-flex justify-content-between align-items-center gap-3">
                  <div class="flex-grow-1 min-w-0">
                    <div class="fw-medium text-truncate" :title="item.filename">{{ item.filename }}</div>
                    <div class="small text-body-secondary">{{ item.name }}</div>
                  </div>
                  <a class="btn btn-outline-primary btn-sm flex-shrink-0" :href="downloadUrl(item)" :download="item.filename">
                    <i class="bi bi-download me-1"></i>{{ t('portal.detail.download') }}
                  </a>
                </div>
              </div>
              <details v-if="imageDeliverables.length" class="portal-image-group">
                <summary class="list-group-item px-0 py-3 fw-medium">
                  {{ t('portal.detail.imageResources', { count: imageDeliverables.length }) }}
                </summary>
                <div class="list-group list-group-flush">
                  <div v-for="item in imageDeliverables" :key="item.download_key" class="list-group-item px-0 py-3">
                    <div class="d-flex justify-content-between align-items-center gap-3">
                      <div class="flex-grow-1 min-w-0">
                        <div class="fw-medium text-truncate" :title="item.filename">{{ item.filename }}</div>
                        <div class="small text-body-secondary">{{ item.name }}</div>
                      </div>
                      <a class="btn btn-outline-primary btn-sm flex-shrink-0" :href="downloadUrl(item)" :download="item.filename">
                        <i class="bi bi-download me-1"></i>{{ t('portal.detail.download') }}
                      </a>
                    </div>
                  </div>
                </div>
              </details>
            </div>
            <div v-else class="mk-empty py-4">
              <i class="bi bi-folder2-open mk-empty-icon"></i>
              <h3 class="mk-empty-title">{{ t('portal.detail.noDownloadsTitle') }}</h3>
              <p class="mk-empty-description mb-0">{{ t('portal.detail.noDownloadsDescription') }}</p>
            </div>
          </div>
        </div>
      </div>

      <div class="col-lg-8 col-xxl-9">
        <div class="card">
          <div class="card-body p-4 p-lg-5">
            <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
              <div>
                <h2 class="fs-5 fw-semibold mb-1">{{ t('portal.detail.resultTitle') }}</h2>
                <p class="small text-body-secondary mb-0">{{ t('portal.detail.resultSubtitle') }}</p>
              </div>
              <a v-if="markdown" class="btn btn-outline-primary btn-sm" :href="markdownDownloadUrl" download="result.md">
                <i class="bi bi-download me-1"></i>{{ t('portal.detail.downloadMarkdown') }}
              </a>
            </div>
            <div v-if="task.status !== 'completed'" class="mk-empty">
              <div v-if="task.status === 'pending' || task.status === 'processing'" class="spinner-border text-primary mb-3" role="status"><span class="visually-hidden">{{ t('portal.detail.processing') }}</span></div>
              <i v-else class="bi bi-file-earmark-x mk-empty-icon"></i>
              <p class="mk-empty-description mb-0">{{ task.status === 'pending' || task.status === 'processing' ? t('portal.detail.resultPending') : t('portal.detail.resultFailed') }}</p>
            </div>
            <div v-else-if="resultLoading" class="text-body-secondary py-5 text-center">{{ t('portal.detail.resultLoading') }}</div>
            <div v-else-if="markdown" class="result-markdown portal-markdown" v-html="renderedMarkdown"></div>
            <div v-else class="mk-empty">
              <i class="bi bi-file-earmark-text mk-empty-icon"></i>
              <h3 class="mk-empty-title">{{ t('portal.detail.noMarkdownTitle') }}</h3>
              <p class="mk-empty-description mb-0">{{ t('portal.detail.noMarkdownDescription') }}</p>
            </div>
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
import { useI18n } from 'vue-i18n'
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
const { t } = useI18n()
const taskId = computed(() => String(route.params.taskId || ''))
const task = ref<TaskStatus | null>(null)
const deliverables = ref<DeliverableItem[]>([])
const markdown = ref('')
const loading = ref(false)
const resultLoading = ref(false)
const error = ref('')
let pollTimer = 0
const markdownParser = new MarkdownIt({ html: true, linkify: true, breaks: true })
const taskName = computed(() => {
  return task.value?.input_filename || t('portal.detail.taskFallback', { taskId: taskId.value })
})
const imageDeliverables = computed(() => deliverables.value.filter(isImageDeliverable))
const mainDeliverables = computed(() => deliverables.value.filter((item) => !isImageDeliverable(item)))
const renderedMarkdown = computed(() => renderMarkdown(markdown.value))
const markdownArtifact = computed(() => deliverables.value.find((item) => item.is_default || item.filename.toLowerCase().endsWith('.md')))
const markdownDownloadUrl = computed(() => markdownArtifact.value ? downloadUrl(markdownArtifact.value) : '')

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

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString() : '—'
}

function downloadUrl(item: DeliverableItem) {
  return `/api/portal/tasks/${encodeURIComponent(taskId.value)}/deliverables/download?download_key=${encodeURIComponent(item.download_key)}`
}

function isImageDeliverable(item: DeliverableItem) {
  const key = item.download_key.replace(/\\/g, '/')
  return /(?:^|\/)images\//i.test(key) && /\.(?:avif|bmp|gif|jpe?g|png|svg|tiff?|webp)$/i.test(key)
}

function findImageDeliverable(src: string) {
  const rawPath = src.split(/[?#]/, 1)[0].replace(/^(?:\.\/)+/, '')
  if (!rawPath || rawPath.startsWith('/') || /^[a-z][a-z\d+.-]*:/i.test(rawPath)) return undefined

  let path = rawPath
  try {
    path = decodeURIComponent(rawPath)
  } catch {
    // 保留原始路径继续匹配，避免异常编码导致整个结果页无法渲染。
  }
  path = path.replace(/\\/g, '/').toLowerCase()
  if (path.split('/').includes('..')) return undefined

  return deliverables.value.find((item) => {
    const key = item.download_key.replace(/\\/g, '/').toLowerCase()
    return key === path || key.endsWith(`/${path}`)
  })
}

function renderMarkdown(source: string) {
  const safeHtml = DOMPurify.sanitize(markdownParser.render(source), {
    ADD_ATTR: ['target', 'rel'],
  })
  const container = document.createElement('div')
  container.innerHTML = safeHtml

  container.querySelectorAll('img[src]').forEach((image) => {
    const item = findImageDeliverable(image.getAttribute('src') || '')
    if (item) image.setAttribute('src', downloadUrl(item))
    image.classList.add('img-fluid', 'rounded', 'border', 'my-2')
  })

  container.querySelectorAll<HTMLAnchorElement>('a[href]').forEach((link) => {
    const url = new URL(link.href, window.location.href)
    if ((url.protocol === 'http:' || url.protocol === 'https:') && url.origin !== window.location.origin) {
      link.setAttribute('target', '_blank')
      link.setAttribute('rel', 'noreferrer')
    }
  })

  container.querySelectorAll('table').forEach((table) => {
    const parent = table.parentNode
    if (!parent) return
    const scrollContainer = document.createElement('div')
    scrollContainer.className = 'portal-table-scroll'
    parent.insertBefore(scrollContainer, table)
    scrollContainer.appendChild(table)
  })

  return DOMPurify.sanitize(container.innerHTML, {
    ADD_ATTR: ['target', 'rel'],
  })
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
      ? t('portal.detail.notFound')
      : err instanceof ApiError ? err.message : t('portal.detail.loadFailed')
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
  overflow-x: hidden;
  overflow-y: auto;
  overflow-wrap: anywhere;
}

.portal-markdown :deep(.portal-table-scroll) {
  max-width: 100%;
  overflow-x: auto;
}

.portal-image-group > summary {
  cursor: pointer;
}
</style>
