<template>
  <section class="portal-detail-panel">
    <header class="portal-task-toolbar">
      <div class="portal-task-meta">
        <button v-if="showBackButton" class="btn btn-outline-secondary btn-sm flex-shrink-0" type="button" @click="$emit('back')">
          <i class="bi bi-arrow-left me-1"></i>{{ t('portal.detail.mobileBack') }}
        </button>
        <h1 class="portal-task-name fs-5 fw-semibold" :title="taskName">{{ taskName }}</h1>
        <template v-if="task">
          <span class="badge mk-badge flex-shrink-0" :class="statusClass(task.status)">{{ statusLabel(task.status) }}</span>
          <span class="portal-task-submitted small text-body-secondary">
            {{ t('portal.detail.submittedAt', { time: formatDate(task.created_at) }) }}
          </span>
          <div v-if="task.status === 'processing' || task.status === 'pending'" class="portal-task-progress">
            <span class="small text-body-secondary text-truncate" :title="task.message || ''">
              {{ task.status === 'pending' ? t('portal.detail.waiting') : (task.message || t('portal.detail.parsing')) }}
            </span>
            <div
              class="progress flex-grow-1"
              style="height: 6px"
              role="progressbar"
              :aria-valuenow="task.status === 'pending' ? undefined : (task.progress ?? 0)"
              aria-valuemin="0"
              aria-valuemax="100"
            >
              <div
                class="progress-bar"
                :class="{ 'progress-bar-striped progress-bar-animated': task.status === 'pending' || task.status === 'processing' }"
                :style="{ width: `${task.status === 'pending' ? 100 : (task.progress ?? 0)}%` }"
              ></div>
            </div>
            <span class="small text-body-secondary flex-shrink-0">{{ task.status === 'pending' ? '—' : `${task.progress ?? 0}%` }}</span>
          </div>
        </template>
      </div>
      <div class="portal-task-actions">
        <button class="btn btn-outline-secondary btn-sm flex-shrink-0" :disabled="loading" @click="load">
          <i class="bi bi-arrow-clockwise me-1"></i>{{ t('portal.detail.refresh') }}
        </button>
        <details v-if="task?.status === 'completed'" ref="downloadMenu" class="portal-download-dropdown">
          <summary class="btn btn-outline-primary btn-sm dropdown-toggle">
            <i class="bi bi-download me-1"></i>{{ t('portal.detail.downloadsTitle') }}
          </summary>
          <div class="portal-download-menu">
            <div v-if="markdown && markdownArtifact" class="list-group list-group-flush mb-2">
              <div class="list-group-item px-0 py-2">
                <div class="d-flex justify-content-between align-items-center gap-3">
                  <div class="flex-grow-1 min-w-0">
                    <div class="fw-medium text-truncate" :title="t('portal.detail.artifactMarkdown')">{{ t('portal.detail.artifactMarkdown') }}</div>
                    <div class="small text-body-secondary text-truncate" :title="markdownArtifact.filename">{{ markdownArtifact.filename }}</div>
                  </div>
                  <a
                    class="btn btn-outline-primary btn-sm flex-shrink-0"
                    :href="markdownDownloadUrl"
                    download="result.md"
                    @click="closeDownloadMenu"
                  >
                    <i class="bi bi-download me-1"></i>{{ t('portal.detail.downloadMarkdown') }}
                  </a>
                </div>
              </div>
            </div>
            <div v-if="mainDeliverables.length || imageDeliverables.length" class="list-group list-group-flush">
              <div v-for="item in mainDeliverables" :key="item.download_key" class="list-group-item px-0 py-2">
                <div class="d-flex justify-content-between align-items-center gap-3">
                  <div class="flex-grow-1 min-w-0">
                    <div class="fw-medium text-truncate" :title="artifactLabel(item)">{{ artifactLabel(item) }}</div>
                    <div class="small text-body-secondary text-truncate" :title="item.filename">{{ item.filename }}</div>
                  </div>
                  <a class="btn btn-outline-primary btn-sm flex-shrink-0" :href="downloadUrl(item)" :download="item.filename" @click="closeDownloadMenu">
                    <i class="bi bi-download me-1"></i>{{ t('portal.detail.download') }}
                  </a>
                </div>
              </div>
              <details v-if="imageDeliverables.length" class="portal-image-group">
                <summary class="list-group-item px-0 py-2 fw-medium">
                  {{ t('portal.detail.imageResources', { count: imageDeliverables.length }) }}
                </summary>
                <div class="list-group list-group-flush">
                  <div v-for="item in imageDeliverables" :key="item.download_key" class="list-group-item px-0 py-2">
                    <div class="d-flex justify-content-between align-items-center gap-3">
                      <div class="flex-grow-1 min-w-0">
                        <div class="fw-medium text-truncate" :title="artifactLabel(item)">{{ artifactLabel(item) }}</div>
                        <div class="small text-body-secondary text-truncate" :title="item.filename">{{ item.filename }}</div>
                      </div>
                      <a class="btn btn-outline-primary btn-sm flex-shrink-0" :href="downloadUrl(item)" :download="item.filename" @click="closeDownloadMenu">
                        <i class="bi bi-download me-1"></i>{{ t('portal.detail.download') }}
                      </a>
                    </div>
                  </div>
                </div>
              </details>
            </div>
            <div v-if="!deliverables.length" class="mk-empty py-4">
              <i class="bi bi-folder2-open mk-empty-icon"></i>
              <h3 class="mk-empty-title">{{ t('portal.detail.noDownloadsTitle') }}</h3>
              <p class="mk-empty-description mb-0">{{ t('portal.detail.noDownloadsDescription') }}</p>
            </div>
          </div>
        </details>
      </div>
    </header>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="task?.error" class="alert alert-warning">{{ task.error }}</div>
    <div v-if="loading && !task" class="text-center text-body-secondary py-5">{{ t('portal.tasks.loading') }}</div>
    <div v-else-if="task" class="card">
      <div class="card-body p-4 p-lg-5">
        <div class="mb-3">
          <h2 class="fs-5 fw-semibold mb-1">{{ t('portal.detail.resultTitle') }}</h2>
          <p class="small text-body-secondary mb-0">{{ t('portal.detail.resultSubtitle') }}</p>
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
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import { useI18n } from 'vue-i18n'
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

const props = defineProps<{
  taskId: string
  showBackButton?: boolean
}>()
defineEmits<{
  back: []
}>()

const { t } = useI18n()
const task = ref<TaskStatus | null>(null)
const deliverables = ref<DeliverableItem[]>([])
const markdown = ref('')
const loading = ref(false)
const resultLoading = ref(false)
const error = ref('')
const downloadMenu = ref<HTMLDetailsElement | null>(null)
let pollTimer = 0
let requestSequence = 0
let loadingTaskId = ''
const markdownParser = new MarkdownIt({ html: true, linkify: true, breaks: true })
const taskName = computed(() => {
  return task.value?.input_filename || t('portal.detail.taskFallback', { taskId: props.taskId })
})
const imageDeliverables = computed(() => deliverables.value.filter(isImageDeliverable))
const renderedMarkdown = computed(() => renderMarkdown(markdown.value))
const markdownArtifact = computed(() => deliverables.value.find((item) => /\.md$/i.test(item.filename)) || deliverables.value.find((item) => item.is_default))
const markdownDownloadUrl = computed(() => markdownArtifact.value ? downloadUrl(markdownArtifact.value) : '')
const mainDeliverables = computed(() => deliverables.value.filter((item) => {
  if (isImageDeliverable(item)) return false
  return !(markdown.value && markdownArtifact.value?.download_key === item.download_key)
}))

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
  return `/api/portal/tasks/${encodeURIComponent(props.taskId)}/deliverables/download?download_key=${encodeURIComponent(item.download_key)}`
}

function closeDownloadMenu() {
  if (downloadMenu.value) downloadMenu.value.open = false
}

function isImageDeliverable(item: DeliverableItem) {
  const key = item.download_key.replace(/\\/g, '/')
  return /(?:^|\/)images\//i.test(key) && /\.(?:avif|bmp|gif|jpe?g|png|svg|tiff?|webp)$/i.test(key)
}

function artifactLabel(item: DeliverableItem) {
  const keys = [item.artifact_type, item.name]
    .filter((value): value is string => Boolean(value))
    .map((value) => value.trim().toLowerCase())

  if (keys.some((key) => key.startsWith('images/')) || isImageDeliverable(item)) {
    return t('portal.detail.artifactImages')
  }

  const labels: Record<string, string> = {
    markdown: 'portal.detail.artifactMarkdown',
    middle_json: 'portal.detail.artifactMiddleJson',
    content_list: 'portal.detail.artifactContentList',
    content_list_v2: 'portal.detail.artifactContentListV2',
    model_json: 'portal.detail.artifactModelJson',
  }
  for (const key of keys) {
    const basename = key.split('/').pop() || key
    const normalized = basename.replace(/\.[^.]+$/, '').replace(/[\s.-]+/g, '_')
    if (labels[normalized]) return t(labels[normalized])
  }
  return item.name
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
  if (!props.taskId) return
  const requestedTaskId = props.taskId
  if (loading.value && loadingTaskId === requestedTaskId) return
  const sequence = ++requestSequence
  loadingTaskId = requestedTaskId
  loading.value = true
  error.value = ''
  if (task.value?.task_id !== requestedTaskId) {
    task.value = null
    deliverables.value = []
    markdown.value = ''
    resultLoading.value = false
  }
  try {
    const loadedTask = await apiFetch<TaskStatus>(`/api/portal/tasks/${encodeURIComponent(requestedTaskId)}`)
    if (sequence !== requestSequence) return
    task.value = loadedTask
    if (loadedTask.status === 'completed') {
      resultLoading.value = true
      const [result, listed] = await Promise.all([
        apiFetch<PortalTaskResult>(`/api/portal/tasks/${encodeURIComponent(requestedTaskId)}/result`),
        apiFetch<DeliverablesResponse>(`/api/portal/tasks/${encodeURIComponent(requestedTaskId)}/deliverables`),
      ])
      if (sequence !== requestSequence) return
      markdown.value = result.postprocessed_markdown || result.markdown || ''
      deliverables.value = listed.artifacts || []
    }
  } catch (err) {
    if (sequence !== requestSequence) return
    error.value = err instanceof ApiError && err.status === 404
      ? t('portal.detail.notFound')
      : err instanceof ApiError ? err.message : t('portal.detail.loadFailed')
  } finally {
    if (sequence === requestSequence) {
      loading.value = false
      loadingTaskId = ''
      resultLoading.value = false
    }
  }
}

watch(() => props.taskId, () => void load())

onMounted(() => {
  void load()
  pollTimer = window.setInterval(() => {
    if (task.value?.status === 'pending' || task.value?.status === 'processing') void load()
  }, 5000)
})

onBeforeUnmount(() => {
  requestSequence += 1
  window.clearInterval(pollTimer)
})
</script>

<style scoped>
.portal-detail-panel {
  min-width: 0;
}

.portal-task-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem 1rem;
  margin-bottom: 1.25rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--mk-border);
  border-radius: var(--mk-radius-md);
  background: var(--mk-surface);
}

.portal-task-meta,
.portal-task-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  min-width: 0;
}

.portal-task-meta {
  flex: 1 1 auto;
}

.portal-task-name {
  flex: 1 1 16rem;
  min-width: 0;
  max-width: min(48vw, 36rem);
  overflow: hidden;
  margin: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.portal-task-submitted {
  flex: 0 0 auto;
}

.portal-task-progress {
  display: flex;
  flex: 0 1 20rem;
  align-items: center;
  gap: 0.5rem;
  min-width: min(100%, 13rem);
}

.portal-task-progress > span:first-child {
  max-width: 12rem;
}

.portal-task-actions {
  flex: 0 0 auto;
  margin-left: auto;
}

.portal-download-dropdown {
  position: relative;
}

.portal-download-dropdown > summary {
  display: block;
  list-style: none;
  cursor: pointer;
}

.portal-download-dropdown > summary::-webkit-details-marker {
  display: none;
}

.portal-download-menu {
  position: absolute;
  z-index: 1020;
  top: calc(100% + 0.4rem);
  right: 0;
  width: min(30rem, calc(100vw - 3rem));
  max-height: min(70vh, 34rem);
  overflow: auto;
  padding: 0.5rem 1rem;
  border: 1px solid var(--mk-border);
  border-radius: var(--mk-radius-md);
  background: var(--mk-surface);
  box-shadow: 0 0.5rem 1.25rem rgb(20 35 45 / 16%);
}

.portal-download-menu .list-group-item {
  background: transparent;
}

.portal-download-menu .mk-empty {
  min-height: 8rem;
}

.portal-markdown {
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
