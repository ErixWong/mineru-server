<template>
  <AdminLayout>
    <div class="mb-3">
      <RouterLink class="btn btn-link px-0" to="/tasks">&larr; {{ t('taskDetail.backToList') }}</RouterLink>
    </div>
    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="loading" class="text-muted">{{ t('taskDetail.loading') }}</div>
    <template v-else-if="task">
      <div class="row g-3 mb-3">
        <div class="col-lg-6">
          <div class="card page-card h-100"><div class="card-body">
            <h5 class="card-title">{{ t('taskDetail.title') }}</h5>
            <table class="table table-sm mb-0">
              <tbody>
                <tr><th>{{ t('taskDetail.taskId') }}</th><td class="monospace small">{{ task.task_id }}</td></tr>
                <tr><th>{{ t('taskDetail.status') }}</th><td>{{ statusLabel(task.status) }}</td></tr>
                <tr><th>{{ t('taskDetail.fileName') }}</th><td>{{ task.input_filename }}</td></tr>
                <tr><th>{{ t('taskDetail.backend') }}</th><td>{{ task.backend || '-' }}</td></tr>
                <tr>
                  <th>{{ t('taskDetail.caller') }}</th>
                  <td>
                    <div v-if="!callerEdit.visible" class="d-flex align-items-center gap-2">
                      <span>{{ task.caller_name || t('taskDetail.unassigned') }}</span>
                      <button class="btn btn-outline-primary btn-sm" @click="openCallerEdit">{{ t('taskDetail.modify') }}</button>
                    </div>
                    <div v-else class="d-flex align-items-center gap-2">
                      <select v-model="callerEdit.callerId" class="form-select form-select-sm" style="max-width: 220px;">
                        <option value="">{{ t('taskDetail.unassigned') }}</option>
                        <option v-for="caller in callers" :key="caller.caller_id" :value="caller.caller_id">{{ caller.name }}</option>
                      </select>
                      <button class="btn btn-primary btn-sm" :disabled="callerEdit.saving" @click="saveCaller">{{ callerEdit.saving ? t('taskDetail.saveing') : t('common.save') }}</button>
                      <button class="btn btn-outline-secondary btn-sm" :disabled="callerEdit.saving" @click="callerEdit.visible = false">{{ t('common.cancel') }}</button>
                    </div>
                    <div v-if="callerEdit.error" class="small text-danger mt-1">{{ callerEdit.error }}</div>
                  </td>
                </tr>
                <tr><th>{{ t('taskDetail.created') }}</th><td>{{ formatDate(task.created_at) }}</td></tr>
                <tr><th>{{ t('taskDetail.started') }}</th><td>{{ formatDate(task.started_at) || '-' }}</td></tr>
                <tr><th>{{ t('taskDetail.completed') }}</th><td>{{ formatDate(task.completed_at) || '-' }}</td></tr>
              </tbody>
            </table>
            <div v-if="task.status === 'completed'" class="mt-3">
              <a class="btn btn-outline-primary btn-sm" :href="`/api/admin/tasks/${task.task_id}/source?name=${encodeURIComponent(task.input_filename)}`" target="_blank">{{ t('taskDetail.downloadSource') }}</a>
            </div>
          </div></div>
        </div>
        <div class="col-lg-6">
          <div class="card page-card h-100"><div class="card-body">
            <div class="d-flex justify-content-between align-items-center mb-2">
              <h5 class="card-title mb-0">{{ t('taskDetail.deliverables') }}</h5>
              <span v-if="deliverables.length > 0" class="small text-muted">{{ t('taskDetail.deliverableCount', { count: deliverables.length }) }}</span>
            </div>
            <div v-if="deliverables.length === 0" class="text-muted">{{ t('taskDetail.noDeliverables') }}</div>
            <template v-else>
              <ul class="list-group list-group-flush">
                <li v-for="item in pagedDeliverables" :key="item.download_key" class="list-group-item d-flex justify-content-between align-items-start gap-3 px-0">
                  <div class="flex-grow-1 overflow-hidden">
                    <button v-if="isPreviewable(item)" type="button" class="btn btn-link px-0 py-0 text-start text-break" @click="openPreview(item)">{{ item.filename }}</button>
                    <a v-else :href="downloadUrl(item)" target="_blank" class="text-break">{{ item.filename }}</a>
                    <div class="small text-muted">
                      {{ item.artifact_type || item.role || t('taskDetail.typeAttachment') }}
                    </div>
                  </div>
                  <div class="d-flex flex-column align-items-end gap-2 flex-shrink-0">
                    <span class="text-muted small">{{ item.size ? `${(item.size / 1024).toFixed(1)} KB` : '-' }}</span>
                    <div class="d-flex gap-2">
                      <a class="btn btn-outline-secondary btn-sm" :href="downloadUrl(item)" target="_blank">{{ t('common.download') }}</a>
                    </div>
                  </div>
                </li>
              </ul>
              <nav v-if="deliverableTotalPages > 1" class="mt-2 d-flex justify-content-between align-items-center">
                <span class="small text-muted">{{ t('tasks.pagination_total', { total: 0, page: deliverablePage, totalPages: deliverableTotalPages }).replace(/0 \/ /, '') }}</span>
                <ul class="pagination pagination-sm mb-0">
                  <li class="page-item" :class="{ disabled: deliverablePage === 1 }">
                    <button class="page-link" :disabled="deliverablePage === 1" @click="deliverablePage--">&laquo;</button>
                  </li>
                  <li
                    v-for="item in deliverablePageItems"
                    :key="item.key"
                    class="page-item"
                    :class="{ active: item.page === deliverablePage, disabled: item.page === null }"
                  >
                    <span v-if="item.page === null" class="page-link">&hellip;</span>
                    <button v-else class="page-link" @click="deliverablePage = item.page">{{ item.page }}</button>
                  </li>
                  <li class="page-item" :class="{ disabled: deliverablePage === deliverableTotalPages }">
                    <button class="page-link" :disabled="deliverablePage === deliverableTotalPages" @click="deliverablePage++">&raquo;</button>
                  </li>
                </ul>
              </nav>
            </template>
          </div></div>
        </div>
      </div>

      <div class="card page-card mb-3"><div class="card-body">
        <div class="d-flex justify-content-between align-items-center gap-2 mb-2">
          <h5 class="card-title mb-0">{{ t('taskDetail.postprocess') }}</h5>
          <button
            v-if="task.status === 'completed'"
            class="btn btn-outline-primary btn-sm"
            :disabled="plans.length === 0"
            :title="plans.length === 0 ? t('taskDetail.noPlansAvailable') : ''"
            @click="openTriggerModal"
          >{{ t('taskDetail.triggerPostprocess') }}</button>
        </div>
        <div v-if="runs.length === 0" class="text-muted small">{{ t('taskDetail.noPostprocessRun') }}</div>
        <div v-else class="table-responsive">
          <table class="table table-sm align-middle mb-0">
            <thead>
              <tr>
                <th>{{ t('taskDetail.planTable.plan') }}</th>
                <th>{{ t('taskDetail.planTable.trigger') }}</th>
                <th>{{ t('taskDetail.planTable.status') }}</th>
                <th>{{ t('taskDetail.planTable.steps') }}</th>
                <th>{{ t('taskDetail.planTable.createdAt') }}</th>
                <th class="text-end">{{ t('taskDetail.planTable.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in runs" :key="run.run_id">
                <td class="small fw-semibold">{{ run.plan_title }}</td>
                <td><span class="badge text-bg-light border">{{ triggerSourceLabel(run.trigger_source) }}</span></td>
                <td>
                  <span class="badge" :class="postprocessBadgeClass(run.status)">{{ postprocessStatusLabel(run.status) }}</span>
                  <div v-if="run.error" class="small text-danger text-break">{{ run.error }}</div>
                </td>
                <td class="small">
                  <div v-for="(step, index) in run.steps" :key="index" class="d-flex align-items-center gap-1 mb-1">
                    <span class="badge" :class="postprocessBadgeClass(step.status)">{{ postprocessStatusLabel(step.status) }}</span>
                    <span>{{ step.name }}</span>
                    <span class="text-muted font-monospace">{{ step.output_filename }}</span>
                  </div>
                </td>
                <td class="small text-muted">{{ formatDate(run.created_at) }}</td>
                <td>
                  <div class="d-flex justify-content-end">
                    <button
                      v-if="run.status === 'pending' || run.status === 'running'"
                      class="btn btn-outline-danger btn-sm"
                      :disabled="cancellingRunId === run.run_id"
                      @click="cancelRun(run.run_id)"
                    >{{ cancellingRunId === run.run_id ? t('taskDetail.cancelling') : t('taskDetail.cancelRun') }}</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div></div>

      <div v-if="task.error" class="card page-card mb-3 border-danger"><div class="card-body">
        <div class="d-flex justify-content-between align-items-start gap-2">
          <div class="flex-grow-1">
            <h5 class="card-title text-danger">{{ t('taskDetail.errorTitle') }}</h5>
            <pre class="result-block mb-0">{{ task.error }}</pre>
          </div>
          <button
            v-if="task.status === 'failed'"
            class="btn btn-outline-danger flex-shrink-0"
            :disabled="reprocessing"
            @click="reprocess"
          >{{ reprocessing ? t('taskDetail.reprocessing') : t('taskDetail.reprocess') }}</button>
        </div>
      </div></div>

      <div v-if="task.result_raw" class="card page-card"><div class="card-body">
        <div class="d-flex justify-content-between align-items-center gap-2 mb-3">
          <h5 class="card-title mb-0">{{ t('taskDetail.result') }}</h5>
          <div class="btn-group btn-group-sm" role="group" :aria-label="t('taskDetail.result')">
            <button type="button" class="btn" :class="resultView === 'rendered' ? 'btn-primary' : 'btn-outline-primary'" @click="resultView = 'rendered'">{{ t('taskDetail.rendered') }}</button>
            <button type="button" class="btn" :class="resultView === 'raw' ? 'btn-primary' : 'btn-outline-primary'" @click="resultView = 'raw'">{{ t('taskDetail.raw') }}</button>
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
                <div class="small text-muted">{{ preview.item?.artifact_type || preview.item?.role || t('taskDetail.previewAttachment') }}</div>
              </div>
              <button type="button" class="btn-close" :aria-label="t('common.close')" @click="closePreview"></button>
            </div>
            <div class="modal-body">
              <div v-if="preview.loading" class="text-muted">{{ t('taskDetail.previewLoading') }}</div>
              <div v-else-if="preview.error" class="alert alert-danger mb-0">{{ preview.error }}</div>
              <div v-else-if="preview.kind === 'image'" class="text-center">
                <img :src="preview.imageSrc" :alt="preview.item?.filename || 'image preview'" class="img-fluid rounded border" />
              </div>
              <pre v-else-if="preview.kind === 'json'" class="result-block mb-0">{{ preview.jsonContent }}</pre>
              <div v-else-if="preview.kind === 'markdown'" class="result-markdown" @click="handleRenderedResultClick" v-html="previewMarkdownHtml"></div>
            </div>
            <div class="modal-footer">
              <a v-if="preview.item" class="btn btn-outline-secondary" :href="downloadUrl(preview.item)" target="_blank">{{ t('common.download') }}</a>
              <button type="button" class="btn btn-primary" @click="closePreview">{{ t('common.close') }}</button>
            </div>
          </div>
        </div>
      </div>
      <div v-if="preview.visible" class="modal-backdrop fade show"></div>

      <div v-if="triggerModal.visible" class="modal fade show d-block" tabindex="-1" aria-modal="true">
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">{{ t('taskDetail.triggerModal.title') }}</h5>
              <button type="button" class="btn-close" :aria-label="t('common.close')" @click="closeTriggerModal"></button>
            </div>
            <div class="modal-body">
              <div v-if="triggerModal.error" class="alert alert-danger">{{ triggerModal.error }}</div>
              <label class="form-label">{{ t('taskDetail.triggerModal.selectPlan') }}</label>
              <select v-model="triggerModal.planId" class="form-select">
                <option value="" disabled>{{ t('tasks.selectPlan') }}</option>
                <option v-for="plan in plans" :key="plan.plan_id" :value="plan.plan_id">
                  {{ plan.title }}（{{ plan.steps.length }} {{ t('taskDetail.triggerModal.planSteps') }}）
                </option>
              </select>
              <div class="form-text">{{ t('taskDetail.triggerModal.hint') }}</div>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-outline-secondary" @click="closeTriggerModal">{{ t('common.cancel') }}</button>
              <button
                class="btn btn-primary"
                :disabled="!triggerModal.planId || triggerModal.submitting"
                @click="submitTrigger"
              >{{ triggerModal.submitting ? t('taskDetail.triggerModal.triggering') : t('taskDetail.triggerModal.trigger') }}</button>
            </div>
          </div>
        </div>
      </div>
      <div v-if="triggerModal.visible" class="modal-backdrop fade show"></div>
    </template>
  </AdminLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import { postprocessBadgeClass, postprocessStatusLabel, triggerSourceLabel } from '../lib/postprocess'
import type {
  CallerItem,
  DeliverableItem,
  DeliverablesResponse,
  PostprocessPlanItem,
  PostprocessPlanListResponse,
  PostprocessRunItem,
  PostprocessRunListResponse,
  TaskDetail,
} from '../types'

const { t } = useI18n()

const route = useRoute()
const task = ref<TaskDetail | null>(null)
const deliverables = ref<DeliverableItem[]>([])
const DELIVERABLES_PAGE_SIZE = 5
const deliverablePage = ref(1)
const loadedTaskId = ref('')
const deliverableTotalPages = computed(() => Math.max(1, Math.ceil(deliverables.value.length / DELIVERABLES_PAGE_SIZE)))
const pagedDeliverables = computed(() => {
  const start = (deliverablePage.value - 1) * DELIVERABLES_PAGE_SIZE
  return deliverables.value.slice(start, start + DELIVERABLES_PAGE_SIZE)
})

interface DeliverablePageItem {
  key: string
  page: number | null
}

const deliverablePageItems = computed<DeliverablePageItem[]>(() => {
  const count = deliverableTotalPages.value
  const current = deliverablePage.value
  const pages = new Set<number>([1, count, current - 2, current - 1, current, current + 1, current + 2])
  const sorted = [...pages].filter((p) => p >= 1 && p <= count).sort((a, b) => a - b)
  const items: DeliverablePageItem[] = []
  let prev = 0
  for (const p of sorted) {
    if (p - prev > 1) items.push({ key: `gap-${p}`, page: null })
    items.push({ key: `p-${p}`, page: p })
    prev = p
  }
  return items
})

watch(deliverableTotalPages, (total) => {
  if (deliverablePage.value > total) {
    deliverablePage.value = total
  }
})
const runs = ref<PostprocessRunItem[]>([])
const plans = ref<PostprocessPlanItem[]>([])
const callers = ref<CallerItem[]>([])
const callerEdit = reactive({ visible: false, callerId: '', saving: false, error: '' })
const cancellingRunId = ref('')
const triggerModal = reactive({ visible: false, planId: '', submitting: false, error: '' })
const loading = ref(false)
const reprocessing = ref(false)
const error = ref('')
const resultView = ref<'rendered' | 'raw'>('rendered')
const preview = reactive({
  visible: false,
  loading: false,
  error: '',
  kind: '' as '' | 'image' | 'json' | 'markdown',
  item: null as DeliverableItem | null,
  imageSrc: '',
  jsonContent: '',
  markdownContent: '',
})
const markdown = new MarkdownIt({
  html: true,
  linkify: true,
  breaks: true,
})

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : ''
}

function statusLabel(status: string) {
  const key = `status.${status}`
  if (['pending', 'processing', 'completed', 'failed', 'cancelled'].includes(status)) {
    return t(key)
  }
  return status
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

function isMarkdownFile(item: DeliverableItem) {
  const filename = item.filename.toLowerCase()
  return filename.endsWith('.md') || item.artifact_type?.includes('markdown') === true
}

function isPreviewable(item: DeliverableItem) {
  return isImageFile(item) || isJsonFile(item) || isMarkdownFile(item)
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

function renderMarkdown(source: string) {
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
}

const renderedResultHtml = computed(() => {
  const source = task.value?.result_raw ?? ''
  return source ? renderMarkdown(source) : ''
})

const previewMarkdownHtml = computed(() => renderMarkdown(preview.markdownContent))

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
  preview.markdownContent = ''
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
  preview.markdownContent = ''

  try {
    if (isImageFile(item)) {
      preview.kind = 'image'
      preview.imageSrc = previewUrl(item)
      return
    }

    if (isMarkdownFile(item)) {
      preview.kind = 'markdown'
      preview.markdownContent = await apiFetch<string>(previewUrl(item))
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

    preview.error = t('taskDetail.typeUnsupported')
  } catch (err) {
    preview.error = err instanceof ApiError ? err.message : t('taskDetail.previewFailed')
  } finally {
    preview.loading = false
  }
}

let pollTimer: ReturnType<typeof setTimeout> | undefined
let pollCount = 0
const MAX_POLLS = 600

function isTerminalStatus(status: string) {
  return status === 'completed' || status === 'failed' || status === 'cancelled'
}

function hasActiveRun() {
  return runs.value.some((run) => run.status === 'pending' || run.status === 'running')
}

function schedulePolling() {
  if (pollTimer !== undefined) {
    clearTimeout(pollTimer)
    pollTimer = undefined
  }
  const taskActive = task.value && !isTerminalStatus(task.value.status)
  if (taskActive || hasActiveRun()) {
    if (pollCount >= MAX_POLLS) {
      error.value = t('taskDetail.pollTimeout')
      return
    }
    pollCount += 1
    pollTimer = setTimeout(() => {
      void load(true)
    }, 3000)
  }
}

async function load(silent = false) {
  if (!silent) {
    loading.value = true
    error.value = ''
    pollCount = 0
  }
  try {
    const taskId = String(route.params.taskId)
    task.value = await apiFetch<TaskDetail>('/api/admin/tasks/' + encodeURIComponent(taskId))
    runs.value = (await apiFetch<PostprocessRunListResponse>('/api/admin/tasks/' + encodeURIComponent(taskId) + '/postprocess-runs')).items
    if (task.value.status === 'completed') {
      const payload = await apiFetch<DeliverablesResponse>('/api/admin/tasks/' + encodeURIComponent(taskId) + '/deliverables')
      deliverables.value = payload.artifacts.filter((item) => item.available !== false && item.download_key)
      if (loadedTaskId.value !== taskId) {
        deliverablePage.value = 1
      }
    }
    loadedTaskId.value = taskId
    error.value = ''
  } catch (err) {
    if (!silent) {
      error.value = err instanceof ApiError ? err.message : t('taskDetail.loadingFailed')
    }
  } finally {
    loading.value = false
    schedulePolling()
  }
}

async function loadPlans() {
  try {
    const payload = await apiFetch<PostprocessPlanListResponse>('/api/admin/postprocess-plans?include_disabled=false')
    plans.value = payload.items
  } catch {
    plans.value = []
  }
}

async function loadCallers() {
  try {
    callers.value = await apiFetch<CallerItem[]>('/api/admin/callers?include_disabled=false')
  } catch {
    callers.value = []
  }
}

function openCallerEdit() {
  callerEdit.callerId = task.value?.caller_id || ''
  callerEdit.error = ''
  callerEdit.visible = true
}

async function saveCaller() {
  if (!task.value) return
  callerEdit.saving = true
  callerEdit.error = ''
  try {
    await apiFetch('/api/admin/tasks/' + encodeURIComponent(task.value.task_id) + '/caller', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ caller_id: callerEdit.callerId || null }),
    })
    callerEdit.visible = false
    await load(true)
  } catch (err) {
    callerEdit.error = err instanceof ApiError ? err.message : t('taskDetail.saveFailed')
  } finally {
    callerEdit.saving = false
  }
}

function openTriggerModal() {
  triggerModal.visible = true
  triggerModal.planId = ''
  triggerModal.error = ''
}

function closeTriggerModal() {
  if (triggerModal.submitting) return
  triggerModal.visible = false
}

async function submitTrigger() {
  if (!triggerModal.planId || !task.value) return
  triggerModal.submitting = true
  triggerModal.error = ''
  try {
    await apiFetch('/api/admin/tasks/' + encodeURIComponent(task.value.task_id) + '/postprocess-runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_id: triggerModal.planId }),
    })
    triggerModal.visible = false
    await load(true)
  } catch (err) {
    triggerModal.error = err instanceof ApiError ? err.message : t('taskDetail.triggerModal.triggerFailed')
  } finally {
    triggerModal.submitting = false
  }
}

async function reprocess() {
  reprocessing.value = true
  try {
    const taskId = task.value?.task_id
    if (!taskId) return
    await apiFetch('/api/admin/tasks/' + encodeURIComponent(taskId) + '/reprocess', { method: 'POST' })
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('taskDetail.reprocessFailed')
  } finally {
    reprocessing.value = false
  }
}

async function cancelRun(runId: string) {
  cancellingRunId.value = runId
  try {
    await apiFetch('/api/admin/postprocess-runs/' + encodeURIComponent(runId) + '/cancel', { method: 'POST' })
    await load(true)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('taskDetail.cancelFailed')
  } finally {
    cancellingRunId.value = ''
  }
}

onMounted(() => {
  void load()
  void loadPlans()
  void loadCallers()
})
onMounted(() => window.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  if (pollTimer !== undefined) {
    clearTimeout(pollTimer)
  }
})
</script>
