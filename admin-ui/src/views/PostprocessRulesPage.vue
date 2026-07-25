<template>
  <AdminLayout>
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <div>
        <h3 class="mb-1">{{ t('postprocess.title') }}</h3>
        <div class="text-muted small">{{ t('postprocess.subtitle') }}</div>
      </div>
      <button v-if="activeTab === 'plans'" class="btn btn-primary" :disabled="actions.length === 0" @click="openPlanCreate">{{ t('postprocess.createPlan') }}</button>
      <button v-else class="btn btn-primary" @click="openActionCreate">{{ t('postprocess.createAction') }}</button>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="success" class="alert alert-success">{{ success }}</div>

    <ul class="nav nav-tabs mb-3">
      <li class="nav-item">
        <button class="nav-link" :class="{ active: activeTab === 'plans' }" @click="activeTab = 'plans'">{{ t('postprocess.plans') }}</button>
      </li>
      <li class="nav-item">
        <button class="nav-link" :class="{ active: activeTab === 'actions' }" @click="activeTab = 'actions'">{{ t('postprocess.actions') }}</button>
      </li>
    </ul>

    <!-- ========== 方案 tab ========== -->
    <div v-if="activeTab === 'plans'" class="card shadow-sm">
      <div class="card-body">
        <div v-if="loading" class="text-muted">{{ t('postprocess.loading') }}</div>
        <div v-else-if="actions.length === 0" class="text-muted">{{ t('postprocess.needActionsFirst') }}</div>
        <div v-else-if="plans.length === 0" class="text-muted">{{ t('postprocess.noData_plans') }}</div>
        <div v-else class="table-responsive">
          <table class="table align-middle mb-0">
            <thead>
              <tr>
                <th>{{ t('postprocess.planColumns.title') }}</th>
                <th>{{ t('postprocess.planColumns.pipeline') }}</th>
                <th>{{ t('postprocess.planColumns.status') }}</th>
                <th>{{ t('postprocess.planColumns.updatedAt') }}</th>
                <th class="text-end">{{ t('postprocess.planColumns.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="plan in plans" :key="plan.plan_id">
                <td class="fw-semibold">
                  {{ plan.title }}
                  <div v-if="plan.description" class="small text-muted fw-normal">{{ plan.description }}</div>
                </td>
                <td class="small">
                  <span v-for="(step, index) in plan.steps" :key="index">
                    <span class="badge text-bg-light border">{{ index + 1 }}. {{ actionName(step.action_id) }}<template v-if="step.output_filename"> &rarr; {{ step.output_filename }}</template></span>
                    <span v-if="index < plan.steps.length - 1" class="mx-1 text-muted">&rarr;</span>
                  </span>
                </td>
                <td>
                  <span class="badge" :class="Boolean(plan.enabled) ? 'text-bg-success' : 'text-bg-secondary'">
                    {{ Boolean(plan.enabled) ? t('postprocess.enabled') : t('postprocess.disabled') }}
                  </span>
                </td>
                <td class="small text-muted">{{ formatDate(plan.updated_at || plan.created_at) }}</td>
                <td>
                  <div class="btn-group btn-group-sm d-flex justify-content-end">
                    <button class="btn btn-outline-primary" @click="openPlanEdit(plan)">{{ t('common.edit') }}</button>
                    <button class="btn btn-outline-danger" @click="removePlan(plan.plan_id)">{{ t('common.delete') }}</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ========== 动作 tab ========== -->
    <div v-else class="card shadow-sm">
      <div class="card-body">
        <div v-if="loading" class="text-muted">{{ t('postprocess.loading') }}</div>
        <div v-else-if="actions.length === 0" class="text-muted">{{ t('postprocess.noData_actions') }}</div>
        <div v-else class="table-responsive">
          <table class="table align-middle mb-0">
            <thead>
              <tr>
                <th>{{ t('postprocess.actionColumns.name') }}</th>
                <th>{{ t('postprocess.actionColumns.outputFilename') }}</th>
                <th>{{ t('postprocess.actionColumns.prompt') }}</th>
                <th>{{ t('postprocess.actionColumns.status') }}</th>
                <th>{{ t('postprocess.actionColumns.updatedAt') }}</th>
                <th class="text-end">{{ t('postprocess.actionColumns.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="action in actions" :key="action.action_id">
                <td class="fw-semibold">{{ action.name }}</td>
                <td class="small font-monospace">{{ action.config.output_filename || '-' }}</td>
                <td class="small text-break">{{ truncate(action.config.prompt || '', 80) }}</td>
                <td>
                  <span class="badge" :class="Boolean(action.enabled) ? 'text-bg-success' : 'text-bg-secondary'">
                    {{ Boolean(action.enabled) ? t('postprocess.enabled') : t('postprocess.disabled') }}
                  </span>
                </td>
                <td class="small text-muted">{{ formatDate(action.updated_at || action.created_at) }}</td>
                <td>
                  <div class="btn-group btn-group-sm d-flex justify-content-end">
                    <button class="btn btn-outline-primary" @click="openActionEdit(action)">{{ t('common.edit') }}</button>
                    <button class="btn btn-outline-danger" @click="removeAction(action.action_id)">{{ t('common.delete') }}</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ========== 方案编辑 modal ========== -->
    <div v-if="showPlanModal" class="modal fade show d-block" tabindex="-1" aria-modal="true">
      <div class="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ editingPlanId ? t('postprocess.editPlan') : t('postprocess.createPlan') }}</h5>
            <button type="button" class="btn-close" :aria-label="t('common.close')" @click="closePlanModal"></button>
          </div>
          <div class="modal-body">
            <form class="row g-3" @submit.prevent="submitPlan">
              <div class="col-12 col-md-6">
                <label class="form-label">{{ t('postprocess.planForm.title') }}</label>
                <input v-model="planForm.title" class="form-control" maxlength="120" required />
              </div>
              <div class="col-12 col-md-6">
                <label class="form-label">{{ t('postprocess.planForm.description') }}</label>
                <input v-model="planForm.description" class="form-control" maxlength="200" />
              </div>
              <div class="col-12">
                <label class="form-label">{{ t('postprocess.planForm.stepsHint') }}</label>
                <div v-for="(step, index) in planForm.steps" :key="index" class="d-flex align-items-center gap-2 mb-2">
                  <span class="badge text-bg-secondary flex-shrink-0">{{ index + 1 }}</span>
                  <select v-model="step.action_id" class="form-select" required>
                    <option value="" disabled>{{ t('postprocess.planForm.selectAction') }}</option>
                    <option v-for="action in enabledActions" :key="action.action_id" :value="action.action_id">{{ action.name }}</option>
                  </select>
                  <input v-model="step.output_filename" class="form-control" :placeholder="t('postprocess.planForm.outputOverride')" />
                  <div class="btn-group btn-group-sm flex-shrink-0">
                    <button type="button" class="btn btn-outline-secondary" :disabled="index === 0" :title="t('postprocess.planForm.moveUp')" @click="moveStep(index, -1)">&uarr;</button>
                    <button type="button" class="btn btn-outline-secondary" :disabled="index === planForm.steps.length - 1" :title="t('postprocess.planForm.moveDown')" @click="moveStep(index, 1)">&darr;</button>
                    <button type="button" class="btn btn-outline-danger" :disabled="planForm.steps.length <= 1" :title="t('postprocess.planForm.removeStep')" @click="planForm.steps.splice(index, 1)">&times;</button>
                  </div>
                </div>
                <button type="button" class="btn btn-outline-primary btn-sm" @click="planForm.steps.push({ action_id: '', output_filename: '' })">{{ t('postprocess.planForm.addStep') }}</button>
              </div>
              <div class="col-12">
                <div class="form-check form-switch">
                  <input id="plan-enabled" v-model="planForm.enabled" class="form-check-input" type="checkbox" />
                  <label class="form-check-label" for="plan-enabled">{{ t('postprocess.planForm.enable') }}</label>
                </div>
              </div>
              <div class="col-12 d-flex justify-content-end gap-2">
                <button type="button" class="btn btn-outline-secondary" @click="closePlanModal">{{ t('common.cancel') }}</button>
                <button class="btn btn-primary" :disabled="submitting">{{ submitting ? t('common.submitting') : t('common.save') }}</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
    <div v-if="showPlanModal" class="modal-backdrop fade show"></div>

    <!-- ========== 动作编辑 modal ========== -->
    <div v-if="showActionModal" class="modal fade show d-block" tabindex="-1" aria-modal="true">
      <div class="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ editingActionId ? t('postprocess.editAction') : t('postprocess.createAction') }}</h5>
            <button type="button" class="btn-close" :aria-label="t('common.close')" @click="closeActionModal"></button>
          </div>
          <div class="modal-body">
            <form class="row g-3" @submit.prevent="submitAction">
              <div class="col-12">
                <label class="form-label">{{ t('postprocess.actionForm.name') }}</label>
                <input v-model="actionForm.name" class="form-control" maxlength="120" required />
              </div>
              <div class="col-12">
                <label class="form-label">{{ t('postprocess.actionForm.prompt') }}</label>
                <textarea v-model="actionForm.prompt" class="form-control" rows="10" required></textarea>
              </div>
              <div class="col-12 col-md-6">
                <label class="form-label">{{ t('postprocess.actionForm.outputFilename') }}</label>
                <input v-model="actionForm.output_filename" class="form-control" placeholder="postprocessed.md" required />
                <div class="form-text">{{ t('postprocess.actionForm.outputHint') }}</div>
              </div>
              <div class="col-12 col-md-6">
                <label class="form-label">{{ t('postprocess.actionForm.contextSize') }}</label>
                <input v-model.number="actionForm.context_size" type="number" min="4096" class="form-control" :placeholder="t('postprocess.actionForm.defaultPlaceholder', { defaultValue: defaultContextSize })" />
                <div class="form-text">{{ t('postprocess.actionForm.contextSizeHint') }}</div>
              </div>
              <div class="col-12">
                <div class="form-check form-switch">
                  <input id="action-enabled" v-model="actionForm.enabled" class="form-check-input" type="checkbox" />
                  <label class="form-check-label" for="action-enabled">{{ t('postprocess.actionForm.enable') }}</label>
                </div>
              </div>
              <div class="col-12 d-flex justify-content-end gap-2">
                <button type="button" class="btn btn-outline-secondary" @click="closeActionModal">{{ t('common.cancel') }}</button>
                <button class="btn btn-primary" :disabled="submitting">{{ submitting ? t('common.submitting') : t('common.save') }}</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
    <div v-if="showActionModal" class="modal-backdrop fade show"></div>
  </AdminLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import type {
  PostprocessActionItem,
  PostprocessActionListResponse,
  PostprocessPlanItem,
  PostprocessPlanListResponse,
} from '../types'

const { t } = useI18n()

const activeTab = ref<'plans' | 'actions'>('plans')
const plans = ref<PostprocessPlanItem[]>([])
const actions = ref<PostprocessActionItem[]>([])
const loading = ref(false)
const submitting = ref(false)
const showPlanModal = ref(false)
const showActionModal = ref(false)
const editingPlanId = ref('')
const editingActionId = ref('')
const defaultContextSize = ref(131072)
const error = ref('')
const success = ref('')

const planForm = reactive({
  title: '',
  description: '',
  steps: [{ action_id: '', output_filename: '' }] as { action_id: string; output_filename: string }[],
  enabled: true,
})
const actionForm = reactive({
  name: '',
  prompt: '',
  output_filename: 'postprocessed.md',
  context_size: null as number | null,
  enabled: true,
})

const enabledActions = computed(() => actions.value.filter((action) => Boolean(action.enabled)))

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : '-'
}

function truncate(value: string, max: number) {
  return value.length > max ? value.slice(0, max) + '\u2026' : value
}

function actionName(actionId: string) {
  return actions.value.find((action) => action.action_id === actionId)?.name || actionId
}

function moveStep(index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= planForm.steps.length) return
  const [item] = planForm.steps.splice(index, 1)
  planForm.steps.splice(target, 0, item)
}

// ========== 数据加载 ==========

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [plansPayload, actionsPayload] = await Promise.all([
      apiFetch<PostprocessPlanListResponse>('/api/admin/postprocess-plans'),
      apiFetch<PostprocessActionListResponse>('/api/admin/postprocess-actions'),
    ])
    plans.value = plansPayload.items
    actions.value = actionsPayload.items
    defaultContextSize.value = plansPayload.default_context_size
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.loadFailed')
  } finally {
    loading.value = false
  }
}

// ========== 方案编辑 ==========

function resetPlanForm() {
  planForm.title = ''
  planForm.description = ''
  planForm.steps = [{ action_id: '', output_filename: '' }]
  planForm.enabled = true
  editingPlanId.value = ''
}

function openPlanCreate() {
  resetPlanForm()
  error.value = ''
  success.value = ''
  showPlanModal.value = true
}

function openPlanEdit(plan: PostprocessPlanItem) {
  editingPlanId.value = plan.plan_id
  planForm.title = plan.title
  planForm.description = plan.description || ''
  planForm.steps = plan.steps.map((step) => ({
    action_id: step.action_id,
    output_filename: step.output_filename || '',
  }))
  planForm.enabled = Boolean(plan.enabled)
  error.value = ''
  success.value = ''
  showPlanModal.value = true
}

function closePlanModal() {
  if (submitting.value) return
  showPlanModal.value = false
  resetPlanForm()
}

async function submitPlan() {
  submitting.value = true
  error.value = ''
  success.value = ''
  try {
    const payload = {
      title: planForm.title,
      description: planForm.description || null,
      steps: planForm.steps.map((step) => ({
        action_id: step.action_id,
        output_filename: step.output_filename.trim() || null,
      })),
      enabled: planForm.enabled,
    }
    if (editingPlanId.value) {
      await apiFetch('/api/admin/postprocess-plans/' + encodeURIComponent(editingPlanId.value), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      success.value = t('postprocess.planUpdated')
    } else {
      await apiFetch('/api/admin/postprocess-plans', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      success.value = t('postprocess.planSaved')
    }
    showPlanModal.value = false
    resetPlanForm()
    await loadAll()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.saveFailed')
  } finally {
    submitting.value = false
  }
}

async function removePlan(planId: string) {
  if (!window.confirm(t('postprocess.deletePlanConfirm'))) return
  error.value = ''
  success.value = ''
  try {
    await apiFetch('/api/admin/postprocess-plans/' + encodeURIComponent(planId), { method: 'DELETE' })
    success.value = t('postprocess.planDeleted')
    await loadAll()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.deleteFailed')
  }
}

// ========== 动作编辑 ==========

function resetActionForm() {
  actionForm.name = ''
  actionForm.prompt = ''
  actionForm.output_filename = 'postprocessed.md'
  actionForm.context_size = null
  actionForm.enabled = true
  editingActionId.value = ''
}

function openActionCreate() {
  resetActionForm()
  error.value = ''
  success.value = ''
  showActionModal.value = true
}

function openActionEdit(action: PostprocessActionItem) {
  editingActionId.value = action.action_id
  actionForm.name = action.name
  actionForm.prompt = action.config.prompt || ''
  actionForm.output_filename = action.config.output_filename || 'postprocessed.md'
  actionForm.context_size = action.config.context_size ?? null
  actionForm.enabled = Boolean(action.enabled)
  error.value = ''
  success.value = ''
  showActionModal.value = true
}

function closeActionModal() {
  if (submitting.value) return
  showActionModal.value = false
  resetActionForm()
}

async function submitAction() {
  submitting.value = true
  error.value = ''
  success.value = ''
  try {
    const payload = {
      name: actionForm.name,
      prompt: actionForm.prompt,
      output_filename: actionForm.output_filename,
      context_size: actionForm.context_size || null,
      enabled: actionForm.enabled,
    }
    if (editingActionId.value) {
      await apiFetch('/api/admin/postprocess-actions/' + encodeURIComponent(editingActionId.value), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      success.value = t('postprocess.actionUpdated')
    } else {
      await apiFetch('/api/admin/postprocess-actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      success.value = t('postprocess.actionSaved')
    }
    showActionModal.value = false
    resetActionForm()
    await loadAll()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.saveFailed')
  } finally {
    submitting.value = false
  }
}

async function removeAction(actionId: string) {
  if (!window.confirm(t('postprocess.deleteActionConfirm'))) return
  error.value = ''
  success.value = ''
  try {
    await apiFetch('/api/admin/postprocess-actions/' + encodeURIComponent(actionId), { method: 'DELETE' })
    success.value = t('postprocess.actionDeleted')
    await loadAll()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('common.deleteFailed')
  }
}

onMounted(() => {
  loadAll()
})
</script>
