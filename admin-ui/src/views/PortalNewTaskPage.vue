<template>
  <section class="mx-auto" style="max-width: 900px">
    <div class="mb-4">
      <div class="small text-uppercase text-body-secondary fw-semibold mb-1">新建解析</div>
      <h1 class="fs-3 fw-semibold mb-1">上传文档</h1>
      <p class="text-body-secondary mb-0">支持 PDF 和常见图片格式，提交后可在任务详情查看结果。</p>
    </div>

    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
    <div class="card mb-4">
      <div class="card-body p-3 p-md-4">
        <div
          class="portal-upload-zone rounded-4 border border-2 border-dashed p-4 p-md-5 text-center"
          :class="{ 'portal-upload-zone-active': dragging }"
          role="button"
          tabindex="0"
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
          <i class="bi bi-cloud-arrow-up display-3 text-primary"></i>
          <h2 class="fs-5 fw-semibold mt-3 mb-2">{{ selectedFile ? '已选择文件' : '将文件拖到这里，或点击选择' }}</h2>
          <p class="text-body-secondary mb-0">支持 PDF、PNG、JPG、JPEG、TIFF、BMP</p>
          <div v-if="selectedFile" class="alert alert-light border text-start mt-4 mb-0">
            <div class="d-flex justify-content-between align-items-start gap-3">
              <div class="text-break">
                <div class="fw-semibold">{{ selectedFile.name }}</div>
                <div class="small text-body-secondary">{{ formatSize(selectedFile.size) }}</div>
              </div>
              <button class="btn btn-outline-secondary btn-sm flex-shrink-0" type="button" @click.stop="clearFile">更换文件</button>
            </div>
            <div v-if="readingPages" class="small text-body-secondary mt-2">正在读取文档页数…</div>
            <div v-else-if="estimatedPages !== null" class="small text-body-secondary mt-2">本次页码范围预计解析 {{ estimatedPages }} 页。</div>
            <div v-else-if="estimateError" class="small text-warning-emphasis mt-2">{{ estimateError }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="card mb-4">
      <div class="card-body p-4">
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-3">
          <div>
            <div class="small text-body-secondary">当前可用额度</div>
            <div class="fs-3 fw-semibold">
              {{ unlimited ? '不限量' : `${(profile?.quota_remaining_pages ?? 0).toLocaleString()} 页` }}
            </div>
          </div>
          <RouterLink class="btn btn-outline-secondary btn-sm" :to="{ name: 'portal-ledger' }">查看额度明细</RouterLink>
        </div>
        <div v-if="quotaInsufficient" class="alert alert-warning mt-3 mb-0" role="alert">
          <i class="bi bi-exclamation-circle-fill me-2"></i>
          额度不足：剩余 {{ profile?.quota_remaining_pages ?? 0 }} 页，本次预计需要 {{ estimatedPages ?? 1 }} 页。请补充额度或缩小页码范围后再试。
        </div>
        <div v-else-if="selectedFile && estimatedPages !== null && !unlimited" class="form-text mt-2">
          预计使用 {{ estimatedPages }} 页，提交后会按实际解析结果结算。
        </div>
      </div>
    </div>

    <div class="card mb-4">
      <div class="card-body p-4">
        <details>
          <summary class="fw-semibold text-primary">高级选项（可保持默认）</summary>
          <div class="row g-3 mt-1">
            <div class="col-md-6">
              <label class="form-label" for="portal-backend">解析方式</label>
              <select id="portal-backend" v-model="form.backend" class="form-select">
                <option value="">系统推荐</option>
                <option value="pipeline">标准识别</option>
                <option value="hybrid-http-client">增强识别</option>
                <option value="vlm-http-client">视觉模型识别</option>
                <option value="hybrid-auto-engine">本地增强识别</option>
                <option value="vlm-auto-engine">本地视觉模型</option>
              </select>
              <div class="form-text">不确定时请使用系统推荐。</div>
            </div>
            <div class="col-md-6">
              <label class="form-label" for="portal-language">文档语言</label>
              <select id="portal-language" v-model="form.lang" class="form-select">
                <option value="ch">中文（推荐）</option>
                <option value="en">英语</option>
                <option value="japan">日语</option>
                <option value="korean">韩语</option>
                <option value="fr">法语</option>
                <option value="de">德语</option>
              </select>
            </div>
            <div class="col-md-6">
              <label class="form-label" for="portal-start">起始页</label>
              <input id="portal-start" v-model.number="form.startPageId" class="form-control" type="number" min="0" />
              <div class="form-text">从第 0 页开始计数；默认处理全文。</div>
            </div>
            <div class="col-md-6">
              <label class="form-label" for="portal-end">结束页</label>
              <input id="portal-end" v-model.number="form.endPageId" class="form-control" type="number" min="0" />
            </div>
            <div class="col-12">
              <div class="fw-semibold mb-2">识别内容</div>
              <div class="d-flex flex-wrap gap-4">
                <label class="form-check">
                  <input v-model="form.formulaEnable" class="form-check-input" type="checkbox" />
                  <span class="form-check-label">识别公式</span>
                </label>
                <label class="form-check">
                  <input v-model="form.tableEnable" class="form-check-input" type="checkbox" />
                  <span class="form-check-label">识别表格</span>
                </label>
                <label class="form-check">
                  <input v-model="form.imageAnalysis" class="form-check-input" type="checkbox" />
                  <span class="form-check-label">分析图片内容</span>
                </label>
              </div>
            </div>
          </div>
        </details>
      </div>
    </div>

    <div v-if="rangeInvalid" class="alert alert-warning">结束页必须大于或等于起始页。</div>
    <div class="d-flex flex-wrap justify-content-end gap-2">
      <RouterLink class="btn btn-outline-secondary" :to="{ name: 'portal-home' }">返回首页</RouterLink>
      <button class="btn btn-primary btn-lg px-4" type="button" :disabled="!canSubmit" @click="submit">
        <span v-if="submitting" class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>
        {{ submitting ? '正在提交…' : '提交解析' }}
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { useRouter } from 'vue-router'
import { ApiError, apiFetch } from '../lib/api'
import { usePortalStore } from '../stores/portal'

const router = useRouter()
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
    error.value = '暂时无法读取额度信息，请刷新页面后重试。'
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
    error.value = '暂不支持该文件格式，请选择 PDF 或常见图片文件。'
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
    estimateError.value = '无法预估该 PDF 的页数，提交时仍会由系统校验额度。'
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
    return `额度不足：剩余 ${remaining} 页，本次需要 ${requested} 页。请补充额度或缩小页码范围后再试。`
  }
  return detail.message || '当前额度不足，请补充额度或缩小页码范围后重试。'
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
    error.value = err instanceof ApiError ? quotaErrorMessage(err) : '提交失败，请检查网络后重试。'
    if (err instanceof ApiError && err.payload?.detail?.error === 'QUOTA_EXCEEDED') {
      try {
        await portal.loadProfile()
      } catch {
        error.value += ' 额度信息更新失败，请刷新页面查看最新余额。'
      }
    }
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.portal-upload-zone {
  border-color: var(--bs-border-color) !important;
  background: var(--bs-tertiary-bg);
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.portal-upload-zone:hover,
.portal-upload-zone-active {
  border-color: var(--bs-primary) !important;
  background: var(--bs-primary-bg-subtle);
}

.border-dashed {
  border-style: dashed !important;
}
</style>
