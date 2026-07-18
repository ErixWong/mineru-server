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
                <tr><th>状态</th><td>{{ statusLabel(task.status) }}</td></tr>
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
              <li v-for="item in deliverables" :key="item.download_key" class="list-group-item d-flex justify-content-between align-items-start gap-3 px-0">
                <div class="flex-grow-1 overflow-hidden">
                  <button v-if="isPreviewable(item)" type="button" class="btn btn-link px-0 py-0 text-start text-break" @click="openPreview(item)">{{ item.filename }}</button>
                  <a v-else :href="downloadUrl(item)" target="_blank" class="text-break">{{ item.filename }}</a>
                  <div class="small text-muted">
                    {{ item.artifact_type || item.role || '附件' }}
                  </div>
                </div>
                <div class="d-flex flex-column align-items-end gap-2 flex-shrink-0">
                  <span class="text-muted small">{{ item.size ? `${(item.size / 1024).toFixed(1)} KB` : '-' }}</span>
                  <div class="d-flex gap-2">
                    <a class="btn btn-outline-secondary btn-sm" :href="downloadUrl(item)" target="_blank">下载</a>
                  </div>
                </div>
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
        <div class="d-flex justify-content-between align-items-center gap-2 mb-3">
          <h5 class="card-title mb-0">解析结果</h5>
          <div class="btn-group btn-group-sm" role="group" aria-label="result view mode">
            <button type="button" class="btn" :class="resultView === 'rendered' ? 'btn-primary' : 'btn-outline-primary'" @click="resultView = 'rendered'">渲染</button>
            <button type="button" class="btn" :class="resultView === 'raw' ? 'btn-primary' : 'btn-outline-primary'" @click="resultView = 'raw'">原文</button>
          </div>
        </div>
        <div v-if="resultView === 'rendered'" class="overflow-auto">
          <div class="result-markdown" @click="handleRenderedResultClick" v-html="renderedResultHtml"></div>
        </div>
        <pre v-else class="result-block mb-0">{{ task.result_raw }}</pre>
      </div></div>

      <div v-if="preview.visible" class="modal fade show d-block" tabindex="-1" role="dialog" aria-modal="true" aria-labelledby="deliverable-preview-title">
        <div class="modal-dialog modal-xl modal-dialog-centered modal-dialog-scrollable">
          <div class="modal-content">
            <div class="modal-header">
              <div>
                <h5 id="deliverable-preview-title" class="modal-title">{{ preview.item?.filename }}</h5>
                <div class="small text-muted">{{ preview.item?.artifact_type || preview.item?.role || '附件预览' }}</div>
              </div>
              <button type="button" class="btn-close" aria-label="关闭" @click="closePreview"></button>
            </div>
            <div class="modal-body">
              <div v-if="preview.loading" class="text-muted">加载预览中...</div>
              <div v-else-if="preview.error" class="alert alert-danger mb-0">{{ preview.error }}</div>
              <div v-else-if="preview.kind === 'image'" class="text-center">
                <img :src="preview.imageSrc" :alt="preview.item?.filename || 'image preview'" class="img-fluid rounded border" />
              </div>
              <pre v-else-if="preview.kind === 'json'" class="result-block mb-0">{{ preview.jsonContent }}</pre>
            </div>
            <div class="modal-footer">
              <a v-if="preview.item" class="btn btn-outline-secondary" :href="downloadUrl(preview.item)" target="_blank">下载</a>
              <button type="button" class="btn btn-primary" @click="closePreview">关闭</button>
            </div>
          </div>
        </div>
      </div>
      <div v-if="preview.visible" class="modal-backdrop fade show"></div>
    </template>
  </AdminLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import { useRoute } from 'vue-router'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import type { DeliverableItem, DeliverablesResponse, TaskDetail } from '../types'

const route = useRoute()
const task = ref<TaskDetail | null>(null)
const deliverables = ref<DeliverableItem[]>([])
const loading = ref(false)
const error = ref('')
const resultView = ref<'rendered' | 'raw'>('rendered')
const preview = reactive({
  visible: false,
  loading: false,
  error: '',
  kind: '' as '' | 'image' | 'json',
  item: null as DeliverableItem | null,
  imageSrc: '',
  jsonContent: '',
})
const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : ''
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

function downloadUrl(item: DeliverableItem) {
  const taskId = task.value?.task_id ?? ''
  return `/api/admin/tasks/${encodeURIComponent(taskId)}/deliverables/download?download_key=${encodeURIComponent(item.download_key)}`
}

function previewUrl(item: DeliverableItem) {
  return `${downloadUrl(item)}&inline=true`
}

function isImageFile(item: DeliverableItem) {
  const filename = item.filename.toLowerCase()
  return ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'].some((suffix) => filename.endsWith(suffix))
}

function isJsonFile(item: DeliverableItem) {
  const filename = item.filename.toLowerCase()
  return filename.endsWith('.json') || item.artifact_type?.includes('json') === true
}

function isPreviewable(item: DeliverableItem) {
  return isImageFile(item) || isJsonFile(item)
}

function findDeliverableByMarkdownPath(markdownPath: string) {
  const normalized = markdownPath.trim().replace(/^\.\//, '').replace(/\\/g, '/').toLowerCase()
  const filename = normalized.split('/').pop() ?? normalized

  return deliverables.value.find((item) => {
    const key = item.download_key?.replace(/\\/g, '/').toLowerCase() ?? ''
    const name = item.filename.toLowerCase()
    return key === normalized || key.endsWith('/' + filename) || name === filename
  }) ?? null
}

function resolveMarkdownImageUrl(markdownPath: string) {
  const item = findDeliverableByMarkdownPath(markdownPath)
  return item ? previewUrl(item) : markdownPath
}

const renderedResultHtml = computed(() => {
  const source = task.value?.result_raw ?? ''
  if (!source) return ''

  const rendered = markdown.render(source)
  const rewritten = rendered
    .replace(/<img\s+([^>]*?)src="([^"]+)"([^>]*?)>/gi, (_match: string, before: string, src: string, after: string) => {
      const item = findDeliverableByMarkdownPath(src)
      const resolved = item ? previewUrl(item) : src
      const existingClassMatch = `${before} ${after}`.match(/class="([^"]*)"/i)
      const existingClasses = existingClassMatch?.[1]?.trim() ?? ''
      const mergedClasses = ['img-fluid', 'rounded', 'border', 'my-2', existingClasses].filter(Boolean).join(' ')
      const downloadKeyAttr = item?.download_key ? ` data-download-key="${item.download_key}"` : ''
      return `<img ${before}src="${resolved}"${after} class="${mergedClasses}"${downloadKeyAttr}>`
    })
    .replace(/<a\s+href="([^"]+)"/gi, '<a target="_blank" rel="noreferrer" href="$1"')

  return DOMPurify.sanitize(rewritten, {
    ADD_ATTR: ['target', 'rel'],
  })
})

function handleRenderedResultClick(event: MouseEvent) {
  const target = event.target
  if (!(target instanceof HTMLElement)) return

  const image = target.closest('img[data-download-key]')
  if (!(image instanceof HTMLImageElement)) return

  const downloadKey = image.dataset.downloadKey
  if (!downloadKey) return

  const item = deliverables.value.find((deliverable) => deliverable.download_key === downloadKey)
  if (!item || !isImageFile(item)) return

  event.preventDefault()
  openPreview(item)
}

function resetPreview() {
  preview.visible = false
  preview.loading = false
  preview.error = ''
  preview.kind = ''
  preview.item = null
  preview.imageSrc = ''
  preview.jsonContent = ''
}

function closePreview() {
  resetPreview()
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && preview.visible) {
    closePreview()
  }
}

async function openPreview(item: DeliverableItem) {
  preview.visible = true
  preview.loading = true
  preview.error = ''
  preview.item = item
  preview.imageSrc = ''
  preview.jsonContent = ''

  try {
    if (isImageFile(item)) {
      preview.kind = 'image'
      preview.imageSrc = previewUrl(item)
      return
    }

    if (isJsonFile(item)) {
      preview.kind = 'json'
      const payload = await apiFetch<string>(previewUrl(item))
      try {
        preview.jsonContent = JSON.stringify(JSON.parse(payload), null, 2)
      } catch {
        preview.jsonContent = payload
      }
      return
    }

    preview.error = '当前附件类型暂不支持预览'
  } catch (err) {
    preview.error = err instanceof ApiError ? err.message : '预览加载失败'
  } finally {
    preview.loading = false
  }
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
onMounted(() => window.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', handleKeydown))
</script>
