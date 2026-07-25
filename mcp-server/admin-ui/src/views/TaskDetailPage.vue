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
            <div class="mt-3 d-flex flex-wrap gap-2">
              <a v-if="task.status === 'completed'" class="btn btn-outline-primary btn-sm" :href="`/api/admin/tasks/${task.task_id}/source?name=${encodeURIComponent(task.input_filename)}`" target="_blank">{{ t('taskDetail.downloadSource') }}</a>
              <button class="btn btn-primary btn-sm" type="button" @click="openCloneModal">{{ t('taskDetail.cloneTask') }}</button>
            </div>
          </div></div>
        </div>
        <div class="col-lg-6">
          <div class="card page-card h-100"><div class="card-body">
            <div class="d-flex justify-content-between align-items-center mb-2">
              <h5 class="card-title mb-0">{{ t('taskDetail.deliverables') }}</h5>
              <div class="d-flex align-items-center gap-2">
                <span v-if="deliverables.length > 0" class="small text-muted">{{ t('taskDetail.deliverableCount', { count: deliverables.length }) }}</span>
                <a v-if="deliverables.length > 0" class="btn btn-outline-primary btn-sm" :href="archiveUrl" target="_blank">{{ t('taskDetail.downloadArchive') }}</a>
              </div>
            </div>
            <div v-if="deliverables.length === 0" class="text-muted">{{ t('taskDetail.noDeliverables') }}</div>
            <div v-else class="accordion" id="deliverables-accordion">
              <div v-for="group in deliverableGroups" :key="group.key" class="accordion-item">
                <h2 class="accordion-header">
                  <button class="accordion-button py-2" type="button" :class="{ collapsed: !group.open }" data-bs-toggle="collapse" :data-bs-target="`#deliverables-${group.key}`">
                    <span class="fw-semibold">{{ group.label }}</span>
                    <span class="badge text-bg-light border ms-2">{{ group.items.length }}</span>
                  </button>
                </h2>
                <div :id="`deliverables-${group.key}`" class="accordion-collapse collapse" :class="{ show: group.open }" data-bs-parent="#deliverables-accordion">
                  <div class="accordion-body py-2">
                    <div v-for="item in group.items" :key="item.download_key" class="d-flex justify-content-between align-items-start gap-3 py-2 border-bottom">
                      <div class="flex-grow-1 overflow-hidden">
                        <button v-if="isPreviewable(item)" type="button" class="btn btn-link px-0 py-0 text-start text-break" @click="openPreview(item)">{{ item.filename }}</button>
                        <a v-else :href="downloadUrl(item)" target="_blank" class="text-break">{{ item.filename }}</a>
                        <div class="small text-muted">
                          {{ item.artifact_type || item.role || t('taskDetail.typeAttachment') }}
                        </div>
                      </div>
                      <div class="d-flex flex-column align-items-end gap-2 flex-shrink-0">
                        <span class="text-muted small">{{ formatSize(item.size) }}</span>
                        <a class="btn btn-outline-secondary btn-sm" :href="downloadUrl(item)" target="_blank">{{ t('common.download') }}</a>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div></div>
        </div>
      </div>

      <div v-if="diagnostics" class="card page-card mb-3"><div class="card-body">
        <div class="d-flex justify-content-between align-items-center gap-2 mb-2">
          <h5 class="card-title mb-0">{{ t('taskDetail.diagnostics') }}</h5>
          <span class="badge" :class="errorCategoryClass(diagnostics.error.category)">{{ errorCategoryLabel(diagnostics.error.category) }}</span>
        </div>
        <div class="row g-3">
          <div class="col-lg-4">
            <h6>{{ t('taskDetail.requestParams') }}</h6>
            <table class="table table-sm mb-0">
              <tbody>
                <tr><th>{{ t('taskDetail.backend') }}</th><td>{{ diagnostics.request.backend || '-' }}</td></tr>
                <tr><th>{{ t('tasks.language') }}</th><td>{{ diagnostics.request.lang || '-' }}</td></tr>
                <tr><th>{{ t('taskDetail.pageRange') }}</th><td>{{ diagnostics.request.start_page_id }} - {{ diagnostics.request.end_page_id }}</td></tr>
                <tr><th>{{ t('taskDetail.recognition') }}</th><td>{{ recognitionSummary }}</td></tr>
                <tr><th>{{ t('taskDetail.remoteVlm') }}</th><td>{{ diagnostics.request.server_url_configured ? t('common.enable') : t('common.disable') }}</td></tr>
                <tr><th>{{ t('taskDetail.postprocess') }}</th><td>{{ diagnostics.request.enable_postprocess ? t('common.enable') : t('common.disable') }}</td></tr>
              </tbody>
            </table>
          </div>
          <div class="col-lg-4">
            <h6>{{ t('taskDetail.durationBreakdown') }}</h6>
            <table class="table table-sm mb-0">
              <tbody>
                <tr><th>{{ t('taskDetail.queueDuration') }}</th><td>{{ formatDuration(diagnostics.durations.queue_seconds) }}</td></tr>
                <tr><th>{{ t('taskDetail.parseDuration') }}</th><td>{{ formatDuration(diagnostics.durations.parse_seconds) }}</td></tr>
                <tr><th>{{ t('taskDetail.postprocessDuration') }}</th><td>{{ formatDuration(diagnostics.durations.postprocess_seconds) }}</td></tr>
                <tr><th>{{ t('taskDetail.totalDuration') }}</th><td>{{ formatDuration(diagnostics.durations.total_seconds) }}</td></tr>
              </tbody>
            </table>
          </div>
          <div class="col-lg-4">
            <h6>{{ t('taskDetail.diagnosticSummary') }}</h6>
            <div class="small text-muted mb-2">{{ diagnostics.error.suggestion }}</div>
            <div v-if="diagnostics.output_validation" class="small">
              <div>{{ t('taskDetail.requiredMissing') }}: {{ diagnostics.output_validation.required_missing?.join(', ') || '-' }}</div>
              <div>{{ t('taskDetail.recommendedMissing') }}: {{ diagnostics.output_validation.recommended_missing?.join(', ') || '-' }}</div>
            </div>
            <div v-if="diagnostics.logs.length > 0" class="mt-2">
              <div class="fw-semibold small">{{ t('taskDetail.recentLogs') }}</div>
              <div v-for="(log, index) in diagnostics.logs.slice(-3)" :key="index" class="small text-break">
                <span class="badge text-bg-light border">{{ log.level }}</span>
                {{ log.message }}
              </div>
            </div>
          </div>
        </div>
      </div></div>

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
          <div v-if="task.status === 'failed'" class="d-flex flex-column gap-2 flex-shrink-0">
            <button class="btn btn-primary" type="button" @click="openCloneModal">{{ t('taskDetail.cloneAndEdit') }}</button>
            <button
              class="btn btn-outline-danger"
              :disabled="reprocessing"
              @click="reprocess"
            >{{ reprocessing ? t('taskDetail.reprocessing') : t('taskDetail.reprocess') }}</button>
          </div>
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

      <div v-if="cloneModal.visible" class="modal fade show d-block" tabindex="-1" aria-modal="true">
        <div class="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
          <div class="modal-content">
            <div class="modal-header">
              <div>
                <h5 class="modal-title">{{ t('taskDetail.cloneModal.title') }}</h5>
                <div class="small text-muted">{{ t('taskDetail.cloneModal.subtitle') }}</div>
              </div>
              <button type="button" class="btn-close" :aria-label="t('common.close')" @click="closeCloneModal"></button>
            </div>
            <div class="modal-body">
              <div v-if="cloneModal.error" class="alert alert-danger">{{ cloneModal.error }}</div>
              <div class="row g-3">
                <div class="col-md-6">
                  <label class="form-label">{{ t('taskDetail.backend') }}</label>
                  <select v-model="cloneModal.backend" class="form-select">
                    <option v-for="option in backendOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                  </select>
                </div>
                <div class="col-md-6">
                  <label class="form-label">{{ t('tasks.language') }}</label>
                  <select v-model="cloneModal.lang" class="form-select">
                    <option value="ch">中文</option>
                    <option value="en">English</option>
                    <option value="japan">日本語</option>
                    <option value="korean">한국어</option>
                  </select>
                </div>
                <div class="col-md-6">
                  <label class="form-label">{{ t('taskDetail.cloneModal.startPage') }}</label>
                  <input v-model.number="cloneModal.startPageId" type="number" min="0" class="form-control" />
                </div>
                <div class="col-md-6">
                  <label class="form-label">{{ t('taskDetail.cloneModal.endPage') }}</label>
                  <input v-model.number="cloneModal.endPageId" type="number" min="0" class="form-control" />
                </div>
                <div class="col-md-6">
                  <label class="form-label">{{ t('taskDetail.recognition') }}</label>
                  <div class="d-flex flex-column gap-2">
                    <label class="form-check">
                      <input v-model="cloneModal.formulaEnable" class="form-check-input" type="checkbox" />
                      <span class="form-check-label">{{ t('taskDetail.formula') }}</span>
                    </label>
                    <label class="form-check">
                      <input v-model="cloneModal.tableEnable" class="form-check-input" type="checkbox" />
                      <span class="form-check-label">{{ t('taskDetail.table') }}</span>
                    </label>
                    <label class="form-check">
                      <input v-model="cloneModal.imageAnalysis" class="form-check-input" type="checkbox" />
                      <span class="form-check-label">{{ t('taskDetail.imageAnalysis') }}</span>
                    </label>
                  </div>
                </div>
                <div class="col-md-6">
                  <label class="form-label">{{ t('taskDetail.cloneModal.callerMode') }}</label>
                  <select v-model="cloneModal.callerMode" class="form-select">
                    <option value="inherit">{{ t('taskDetail.cloneModal.inheritCaller') }}</option>
                    <option value="unassigned">{{ t('taskDetail.cloneModal.unassignedCaller') }}</option>
                    <option value="specific">{{ t('taskDetail.cloneModal.specificCaller') }}</option>
                  </select>
                  <select v-if="cloneModal.callerMode === 'specific'" v-model="cloneModal.callerId" class="form-select mt-2">
                    <option value="" disabled>{{ t('taskDetail.cloneModal.selectCaller') }}</option>
                    <option v-for="caller in callers" :key="caller.caller_id" :value="caller.caller_id">{{ caller.name }}</option>
                  </select>
                </div>
                <div class="col-md-6">
                  <label class="form-check mt-2">
                    <input v-model="cloneModal.enablePostprocess" class="form-check-input" type="checkbox" />
                    <span class="form-check-label">{{ t('taskDetail.cloneModal.enablePostprocess') }}</span>
                  </label>
                </div>
                <div class="col-md-6">
                  <label class="form-label">{{ t('taskDetail.cloneModal.postprocessPlan') }}</label>
                  <select v-model="cloneModal.postprocessRuleId" class="form-select" :disabled="!cloneModal.enablePostprocess">
                    <option value="">{{ t('tasks.selectPlan') }}</option>
                    <option v-for="plan in plans" :key="plan.plan_id" :value="plan.plan_id">{{ plan.title }}</option>
                  </select>
                </div>
                <div class="col-md-6">
                  <label class="form-label">{{ t('taskDetail.cloneModal.contextSize') }}</label>
                  <input v-model.number="cloneModal.postprocessContextSize" type="number" min="4096" class="form-control" :disabled="!cloneModal.enablePostprocess" />
                </div>
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-outline-secondary" :disabled="cloneModal.submitting" @click="closeCloneModal">{{ t('common.cancel') }}</button>
              <button
                class="btn btn-primary"
                :disabled="cloneModal.submitting || (cloneModal.callerMode === 'specific' && !cloneModal.callerId)"
                @click="submitClone"
              >{{ cloneModal.submitting ? t('taskDetail.cloneModal.submitting') : t('taskDetail.cloneModal.submit') }}</button>
            </div>
          </div>
        </div>
      </div>
      <div v-if="cloneModal.visible" class="modal-backdrop fade show"></div>
    </template>
  </AdminLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import { useRoute, useRouter } from 'vue-router'
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
  TaskDiagnosticsResponse,
  TaskDetail,
  TaskCloneResponse,
} from '../types'

const { t } = useI18n()

const route = useRoute()
const router = useRouter()
const task = ref<TaskDetail | null>(null)
const diagnostics = ref<TaskDiagnosticsResponse | null>(null)
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
const cloneModal = reactive({
  visible: false,
  submitting: false,
  error: '',
  backend: 'pipeline',
  lang: 'ch',
  formulaEnable: true,
  tableEnable: true,
  imageAnalysis: true,
  startPageId: 0,
  endPageId: 99999,
  callerMode: 'inherit' as 'inherit' | 'unassigned' | 'specific',
  callerId: '',
  enablePostprocess: false,
  postprocessRuleId: '',
  postprocessContextSize: null as number | null,
})
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

const backendOptions = [
  { value: 'pipeline', label: 'pipeline' },
  { value: 'hybrid-http-client', label: 'hybrid-http-client' },
  { value: 'vlm-http-client', label: 'vlm-http-client' },
  { value: 'vlm-auto-engine', label: 'vlm-auto-engine' },
  { value: 'hybrid-auto-engine', label: 'hybrid-auto-engine' },
]

const archiveUrl = computed(() => {
  const taskId = task.value?.task_id ?? ''
  return `/api/admin/tasks/${encodeURIComponent(taskId)}/deliverables/archive`
})

const deliverableGroups = computed(() => {
  const groups = [
    { key: 'markdown', label: t('taskDetail.groupMarkdown'), items: [] as DeliverableItem[], open: true },
    { key: 'json', label: t('taskDetail.groupJson'), items: [] as DeliverableItem[], open: false },
    { key: 'images', label: t('taskDetail.groupImages'), items: [] as DeliverableItem[], open: false },
    { key: 'other', label: t('taskDetail.groupOther'), items: [] as DeliverableItem[], open: false },
  ]
  for (const item of deliverables.value) {
    const type = item.artifact_type || ''
    if (type.includes('markdown')) {
      groups[0].items.push(item)
    } else if (['middle_json', 'model_json', 'content_list', 'content_list_v2'].includes(type) || type.includes('json') || item.filename.toLowerCase().endsWith('.json')) {
      groups[1].items.push(item)
    } else if (isImageFile(item)) {
      groups[2].items.push(item)
    } else {
      groups[3].items.push(item)
    }
  }
  return groups.filter((group) => group.items.length > 0)
})

const recognitionSummary = computed(() => {
  if (!diagnostics.value) return '-'
  const items = []
  if (diagnostics.value.request.formula_enable) items.push(t('taskDetail.formula'))
  if (diagnostics.value.request.table_enable) items.push(t('taskDetail.table'))
  if (diagnostics.value.request.image_analysis) items.push(t('taskDetail.imageAnalysis'))
  return items.length ? items.join(' / ') : '-'
})

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : ''
}

function formatDuration(value?: number | null) {
  if (value === null || value === undefined) return '-'
  if (value < 60) return t('dashboard.seconds', { value: value.toFixed(1) })
  return t('dashboard.minutes', { value: (value / 60).toFixed(1) })
}

function formatSize(value?: number | null) {
  return value ? `${(value / 1024).toFixed(1)} KB` : '-'
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

function errorCategoryLabel(category: string) {
  const known = ['none', 'validation', 'backend_config', 'timeout', 'postprocess_error', 'mineru_error', 'system_error']
  return known.includes(category) ? t(`taskDetail.errorCategory.${category}`) : category
}

function errorCategoryClass(category: string) {
  switch (category) {
    case 'none':
      return 'text-bg-success'
    case 'validation':
    case 'backend_config':
      return 'text-bg-warning'
    case 'timeout':
    case 'postprocess_error':
    case 'mineru_error':
    case 'system_error':
      return 'text-bg-danger'
    default:
      return 'text-bg-secondary'
  }
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
  } else if (event.key === 'Escape' && cloneModal.visible) {
    closeCloneModal()
  } else if (event.key === 'Escape' && triggerModal.visible) {
    closeTriggerModal()
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

watch(() => route.params.taskId, () => {
  resetPreview()
  callerEdit.visible = false
  triggerModal.visible = false
  cloneModal.visible = false
  void load()
})

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
    diagnostics.value = await apiFetch<TaskDiagnosticsResponse>('/api/admin/tasks/' + encodeURIComponent(taskId) + '/diagnostics')
    if (task.value.status === 'completed') {
      const payload = await apiFetch<DeliverablesResponse>('/api/admin/tasks/' + encodeURIComponent(taskId) + '/deliverables')
      deliverables.value = payload.artifacts.filter((item) => item.available !== false && item.download_key)
      if (loadedTaskId.value !== taskId) {
        deliverablePage.value = 1
      }
    } else {
      deliverables.value = []
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

function openCloneModal() {
  const request = diagnostics.value?.request
  cloneModal.visible = true
  cloneModal.error = ''
  cloneModal.backend = request?.backend || task.value?.backend || 'pipeline'
  cloneModal.lang = request?.lang || 'ch'
  cloneModal.formulaEnable = request?.formula_enable ?? true
  cloneModal.tableEnable = request?.table_enable ?? true
  cloneModal.imageAnalysis = request?.image_analysis ?? true
  cloneModal.startPageId = request?.start_page_id ?? 0
  cloneModal.endPageId = request?.end_page_id ?? 99999
  cloneModal.callerMode = task.value?.caller_id ? 'inherit' : 'unassigned'
  cloneModal.callerId = task.value?.caller_id || callers.value[0]?.caller_id || ''
  cloneModal.enablePostprocess = request?.enable_postprocess ?? false
  cloneModal.postprocessRuleId = request?.postprocess_rule_id || ''
  cloneModal.postprocessContextSize = request?.postprocess_context_size ?? null
}

function closeCloneModal() {
  if (cloneModal.submitting) return
  cloneModal.visible = false
}

async function submitClone() {
  const taskId = task.value?.task_id
  if (!taskId) return
  cloneModal.submitting = true
  cloneModal.error = ''
  const body: Record<string, unknown> = {
    backend: cloneModal.backend,
    lang: cloneModal.lang,
    formula_enable: cloneModal.formulaEnable,
    table_enable: cloneModal.tableEnable,
    image_analysis: cloneModal.imageAnalysis,
    start_page_id: cloneModal.startPageId,
    end_page_id: cloneModal.endPageId,
    enable_postprocess: cloneModal.enablePostprocess,
    postprocess_rule_id: cloneModal.enablePostprocess ? cloneModal.postprocessRuleId || null : null,
    postprocess_context_size: cloneModal.enablePostprocess ? cloneModal.postprocessContextSize : null,
  }
  if (cloneModal.callerMode === 'inherit') {
    body.inherit_caller = true
  } else if (cloneModal.callerMode === 'specific') {
    body.inherit_caller = false
    body.caller_id = cloneModal.callerId
  } else {
    body.inherit_caller = false
    body.caller_id = null
  }

  try {
    const payload = await apiFetch<TaskCloneResponse>('/api/admin/tasks/' + encodeURIComponent(taskId) + '/clone', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    cloneModal.visible = false
    await router.push('/tasks/' + encodeURIComponent(payload.task_id))
  } catch (err) {
    cloneModal.error = err instanceof ApiError ? err.message : t('taskDetail.cloneModal.cloneFailed')
  } finally {
    cloneModal.submitting = false
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
