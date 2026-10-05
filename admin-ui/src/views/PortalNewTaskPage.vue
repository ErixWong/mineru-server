<template>
  <section class="mx-auto" style="max-width: 900px">
    <div class="mb-4">
      <div class="small text-uppercase text-body-secondary fw-semibold mb-1">{{ t('portal.newTask.eyebrow') }}</div>
      <h1 class="fs-3 fw-semibold mb-1">{{ t('portal.newTask.title') }}</h1>
      <p class="text-body-secondary mb-0">{{ t('portal.newTask.subtitle') }}</p>
    </div>

    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
    <div class="card mb-4">
      <div class="card-body p-3 p-md-4">
        <div
          class="mk-upload-zone p-4 p-md-5 text-center"
          :class="{ 'mk-upload-zone-active': dragging }"
          role="button"
          tabindex="0"
          :aria-label="t('portal.newTask.uploadAria')"
          @click="fileInput?.click()"
          @keydown.enter.prevent="fileInput?.click()"
          @dragenter.prevent="dragging = true"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
        >
          <input
            ref="fileInput"
            class="visually-hidden"
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp,application/pdf,image/*"
            @change="onFileChange"
          />
          <span class="mk-upload-icon"><i class="bi bi-cloud-arrow-up"></i></span>
          <h2 class="fs-4 fw-semibold mt-3 mb-2">{{ selectedFile ? t('portal.newTask.fileSelected') : t('portal.newTask.dropPrompt') }}</h2>
          <div class="mk-format-list mt-2" :aria-label="t('portal.newTask.formatsAria')">
            <span><i class="bi bi-filetype-pdf"></i>{{ t('portal.newTask.formatPdf') }}</span>
            <span><i class="bi bi-file-earmark-image"></i>{{ t('portal.newTask.formatImages') }}</span>
          </div>
          <div v-if="selectedFile" class="alert alert-light border text-start mt-4 mb-0">
            <div class="d-flex justify-content-between align-items-start gap-3">
              <div class="text-break">
                <div class="fw-semibold">{{ selectedFile.name }}</div>
                <div class="small text-body-secondary">{{ formatSize(selectedFile.size) }}</div>
              </div>
              <button class="btn btn-outline-secondary btn-sm flex-shrink-0" type="button" @click.stop="clearFile">{{ t('portal.newTask.changeFile') }}</button>
            </div>
            <div v-if="readingPages" class="small text-body-secondary mt-2">{{ t('portal.newTask.readingPages') }}</div>
            <div v-else-if="estimatedPages !== null" class="small text-body-secondary mt-2">{{ t('portal.newTask.estimatedPages', { pages: estimatedPages }) }}</div>
            <div v-else-if="estimateError" class="small text-warning-emphasis mt-2">{{ estimateError }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="mk-quota-strip d-flex flex-wrap align-items-center gap-3 px-3 px-md-4 py-3 mb-4">
      <i class="bi bi-layers text-primary fs-5"></i>
      <div>
        <div class="small text-body-secondary">{{ t('portal.newTask.quotaLabel') }}</div>
        <div class="mk-quota-value">
          {{ unlimited ? t('portal.newTask.unlimited') : `${(profile?.quota_remaining_pages ?? 0).toLocaleString()} ${t('portal.newTask.pageUnit')}` }}
        </div>
      </div>
      <div class="ms-auto">
        <RouterLink class="btn btn-outline-secondary btn-sm" :to="{ name: 'portal-ledger' }">{{ t('portal.newTask.quotaLink') }}</RouterLink>
      </div>
    </div>
    <div v-if="quotaInsufficient" class="alert alert-warning mb-4" role="alert">
      <i class="bi bi-exclamation-circle-fill me-2"></i>
      {{ t('portal.newTask.quotaInsufficient', { remaining: profile?.quota_remaining_pages ?? 0, estimated: estimatedPages ?? 1 }) }}
    </div>
    <div v-else-if="selectedFile && estimatedPages !== null && !unlimited" class="form-text mb-4">
      {{ t('portal.newTask.quotaEstimate', { pages: estimatedPages }) }}
    </div>

    <div class="card mb-4">
      <div class="card-body p-4">
        <details>
          <summary class="fw-semibold text-primary">{{ t('portal.newTask.advanced') }}</summary>
          <p class="small text-body-secondary mt-3 mb-0">{{ t('portal.newTask.advancedHint') }}</p>
          <div class="row g-3 mt-1">
            <div class="col-md-6">
              <label class="form-label" for="portal-backend">{{ t('portal.newTask.backendLabel') }}</label>
              <select id="portal-backend" v-model="form.backend" class="form-select">
                <option value="">{{ t('portal.newTask.backendDefault') }}</option>
                <option value="pipeline">{{ t('portal.newTask.backendPipeline') }}</option>
                <option value="hybrid-http-client">{{ t('portal.newTask.backendHybridRemote') }}</option>
                <option value="vlm-http-client">{{ t('portal.newTask.backendVlmRemote') }}</option>
                <option value="hybrid-auto-engine">{{ t('portal.newTask.backendHybridLocal') }}</option>
                <option value="vlm-auto-engine">{{ t('portal.newTask.backendVlmLocal') }}</option>
              </select>
              <div class="form-text">{{ t('portal.newTask.backendHint') }}</div>
            </div>
            <div class="col-md-6">
              <label class="form-label" for="portal-language">{{ t('portal.newTask.languageLabel') }}</label>
              <select id="portal-language" v-model="form.lang" class="form-select">
                <option value="ch">{{ t('portal.newTask.languageChinese') }}</option>
                <option value="en">{{ t('portal.newTask.languageEnglish') }}</option>
                <option value="japan">{{ t('portal.newTask.languageJapanese') }}</option>
                <option value="korean">{{ t('portal.newTask.languageKorean') }}</option>
                <option value="fr">{{ t('portal.newTask.languageFrench') }}</option>
                <option value="de">{{ t('portal.newTask.languageGerman') }}</option>
              </select>
            </div>
            <div class="col-md-6">
              <label class="form-label" for="portal-start">{{ t('portal.newTask.startPage') }}</label>
              <input id="portal-start" v-model.number="form.startPageId" class="form-control" type="number" min="0" />
              <div class="form-text">{{ t('portal.newTask.startPageHint') }}</div>
            </div>
            <div class="col-md-6">
              <label class="form-label" for="portal-end">{{ t('portal.newTask.endPage') }}</label>
              <input id="portal-end" v-model.number="form.endPageId" class="form-control" type="number" min="0" />
            </div>
            <div class="col-12">
              <div class="fw-semibold mb-2">{{ t('portal.newTask.recognitionOptions') }}</div>
              <div class="d-flex flex-wrap gap-4">
                <label class="form-check">
                  <input v-model="form.formulaEnable" class="form-check-input" type="checkbox" />
                  <span class="form-check-label">{{ t('portal.newTask.formula') }}</span>
                </label>
                <label class="form-check">
                  <input v-model="form.tableEnable" class="form-check-input" type="checkbox" />
                  <span class="form-check-label">{{ t('portal.newTask.table') }}</span>
                </label>
                <label class="form-check">
                  <input v-model="form.imageAnalysis" class="form-check-input" type="checkbox" />
                  <span class="form-check-label">{{ t('portal.newTask.imageAnalysis') }}</span>
                </label>
              </div>
            </div>
          </div>
        </details>
      </div>
    </div>

    <div v-if="rangeInvalid" class="alert alert-warning">{{ t('portal.newTask.invalidPageRange') }}</div>
    <div class="d-flex flex-wrap justify-content-end gap-2">
      <RouterLink class="btn btn-outline-secondary" :to="{ name: 'portal-home' }">{{ t('portal.newTask.backHome') }}</RouterLink>
      <button class="btn btn-primary btn-lg px-4" type="button" :disabled="!canSubmit" @click="submit">
        <span v-if="submitting" class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>
        {{ submitting ? t('portal.newTask.submitting') : t('portal.newTask.submit') }}
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ApiError, apiFetch } from '../lib/api'
import { usePortalStore } from '../stores/portal'

const router = useRouter()
const { t } = useI18n()
const portal = usePortalStore()
const profile = computed(() => portal.profile)
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const pageCount = ref<number | null>(null)
const readingPages = ref(false)
const estimateError = ref('')
const submitting = ref(false)
const dragging = ref(false)
const error = ref('')
const form = reactive({
  backend: '',
  lang: 'ch',
  formulaEnable: true,
  tableEnable: true,
  imageAnalysis: true,
  startPageId: 0,
  endPageId: 99999,
})
const unlimited = computed(() => profile.value?.quota_total_pages === null)
const estimatedPages = computed(() => {
  if (!selectedFile.value || pageCount.value === null) return null
  const start = Math.max(0, form.startPageId || 0)
  const end = Math.max(-1, form.endPageId ?? 99999)
  if (end < start) return 0
  if (selectedFile.value.name.toLowerCase().endsWith('.pdf')) {
    return Math.max(0, Math.min(end, pageCount.value - 1) - start + 1)
  }
  return start <= 0 && end >= 0 ? 1 : 0
})
const rangeInvalid = computed(() => form.startPageId < 0 || form.endPageId < form.startPageId)
const quotaInsufficient = computed(() => {
  if (unlimited.value) return false
  const remaining = profile.value?.quota_remaining_pages ?? 0
  if (remaining <= 0) return true
  return estimatedPages.value !== null && estimatedPages.value > remaining
})
const canSubmit = computed(() => Boolean(
  selectedFile.value
  && !submitting.value
  && !readingPages.value
  && !rangeInvalid.value
  && !quotaInsufficient.value
  && (unlimited.value || estimatedPages.value !== null || (profile.value?.quota_remaining_pages ?? 0) > 0),
))

onMounted(async () => {
  try {
    await portal.loadProfile()
  } catch {
    error.value = t('portal.newTask.profileFailed')
  }
})

function acceptedFile(file: File) {
  return /\.(pdf|png|jpe?g|tiff|bmp)$/i.test(file.name)
}

async function chooseFile(file?: File) {
  error.value = ''
  estimateError.value = ''
  pageCount.value = null
  if (!file) return
  if (!acceptedFile(file)) {
    selectedFile.value = null
    error.value = t('portal.newTask.unsupportedFile')
    return
  }
  selectedFile.value = file
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    pageCount.value = 1
    return
  }

  readingPages.value = true
  try {
    const data = new Uint8Array(await file.arrayBuffer())
    const { GlobalWorkerOptions, getDocument } = await import('pdfjs-dist')
    GlobalWorkerOptions.workerSrc = pdfWorkerUrl
    const document = await getDocument({ data, isEvalSupported: false }).promise
    pageCount.value = document.numPages
    await document.destroy()
  } catch {
    estimateError.value = t('portal.newTask.estimateFailed')
  } finally {
    readingPages.value = false
  }
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  void chooseFile(input.files?.[0])
}

function onDrop(event: DragEvent) {
  dragging.value = false
  void chooseFile(event.dataTransfer?.files[0])
}

function clearFile() {
  selectedFile.value = null
  pageCount.value = null
  estimateError.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

function formatSize(size: number) {
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function quotaErrorMessage(err: ApiError) {
  const detail = err.payload?.detail
  if (detail?.error !== 'QUOTA_EXCEEDED') return err.message
  const remaining = detail.detail?.remaining_pages
  const requested = detail.detail?.requested_pages
  if (typeof remaining === 'number' && typeof requested === 'number') {
    return t('portal.newTask.quotaExceeded', { remaining, requested })
  }
  return detail.message || t('portal.newTask.quotaExceededFallback')
}

async function submit() {
  if (!selectedFile.value || !canSubmit.value) return
  submitting.value = true
  error.value = ''
  const body = new FormData()
  body.append('file', selectedFile.value)
  if (form.backend) body.append('backend', form.backend)
  body.append('lang', form.lang)
  body.append('formula_enable', String(form.formulaEnable))
  body.append('table_enable', String(form.tableEnable))
  body.append('image_analysis', String(form.imageAnalysis))
  body.append('start_page_id', String(form.startPageId))
  body.append('end_page_id', String(form.endPageId))
  try {
    const result = await apiFetch<{ task_id: string }>('/api/portal/tasks', { method: 'POST', body })
    await portal.loadProfile()
    await router.push({ name: 'portal-task-detail', params: { taskId: result.task_id } })
  } catch (err) {
    error.value = err instanceof ApiError ? quotaErrorMessage(err) : t('portal.newTask.submitFailed')
    if (err instanceof ApiError && err.payload?.detail?.error === 'QUOTA_EXCEEDED') {
      try {
        await portal.loadProfile()
      } catch {
        error.value += ` ${t('portal.newTask.profileRefreshFailed')}`
      }
    }
  } finally {
    submitting.value = false
  }
}
</script>
