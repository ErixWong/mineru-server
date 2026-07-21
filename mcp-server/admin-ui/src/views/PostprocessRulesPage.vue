<template>
  <AdminLayout>
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <div>
        <h3 class="mb-1">后处理方案</h3>
        <div class="text-muted small">方案（Plan）由若干动作（Action）组成流水线，步骤串联执行：上一步的输出是下一步的输入</div>
      </div>
      <button v-if="activeTab === 'plans'" class="btn btn-primary" :disabled="actions.length === 0" @click="openPlanCreate">新增方案</button>
      <button v-else class="btn btn-primary" @click="openActionCreate">新增动作</button>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="success" class="alert alert-success">{{ success }}</div>

    <ul class="nav nav-tabs mb-3">
      <li class="nav-item">
        <button class="nav-link" :class="{ active: activeTab === 'plans' }" @click="activeTab = 'plans'">方案</button>
      </li>
      <li class="nav-item">
        <button class="nav-link" :class="{ active: activeTab === 'actions' }" @click="activeTab = 'actions'">动作</button>
      </li>
    </ul>

    <!-- ========== 方案 tab ========== -->
    <div v-if="activeTab === 'plans'" class="card shadow-sm">
      <div class="card-body">
        <div v-if="loading" class="text-muted">加载中...</div>
        <div v-else-if="actions.length === 0" class="text-muted">请先在「动作」页创建至少一个动作，再组装方案</div>
        <div v-else-if="plans.length === 0" class="text-muted">暂无方案</div>
        <div v-else class="table-responsive">
          <table class="table align-middle mb-0">
            <thead>
              <tr>
                <th>标题</th>
                <th>流水线步骤</th>
                <th>状态</th>
                <th>更新时间</th>
                <th class="text-end">操作</th>
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
                    <span class="badge text-bg-light border">{{ index + 1 }}. {{ actionName(step.action_id) }}<template v-if="step.output_filename"> → {{ step.output_filename }}</template></span>
                    <span v-if="index < plan.steps.length - 1" class="mx-1 text-muted">→</span>
                  </span>
                </td>
                <td>
                  <span class="badge" :class="Boolean(plan.enabled) ? 'text-bg-success' : 'text-bg-secondary'">
                    {{ Boolean(plan.enabled) ? '启用' : '停用' }}
                  </span>
                </td>
                <td class="small text-muted">{{ formatDate(plan.updated_at || plan.created_at) }}</td>
                <td>
                  <div class="btn-group btn-group-sm d-flex justify-content-end">
                    <button class="btn btn-outline-primary" @click="openPlanEdit(plan)">编辑</button>
                    <button class="btn btn-outline-danger" @click="removePlan(plan.plan_id)">删除</button>
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
        <div v-if="loading" class="text-muted">加载中...</div>
        <div v-else-if="actions.length === 0" class="text-muted">暂无动作</div>
        <div v-else class="table-responsive">
          <table class="table align-middle mb-0">
            <thead>
              <tr>
                <th>名称</th>
                <th>输出文件名</th>
                <th>提示词</th>
                <th>状态</th>
                <th>更新时间</th>
                <th class="text-end">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="action in actions" :key="action.action_id">
                <td class="fw-semibold">{{ action.name }}</td>
                <td class="small font-monospace">{{ action.config.output_filename || '-' }}</td>
                <td class="small text-break">{{ truncate(action.config.prompt || '', 80) }}</td>
                <td>
                  <span class="badge" :class="Boolean(action.enabled) ? 'text-bg-success' : 'text-bg-secondary'">
                    {{ Boolean(action.enabled) ? '启用' : '停用' }}
                  </span>
                </td>
                <td class="small text-muted">{{ formatDate(action.updated_at || action.created_at) }}</td>
                <td>
                  <div class="btn-group btn-group-sm d-flex justify-content-end">
                    <button class="btn btn-outline-primary" @click="openActionEdit(action)">编辑</button>
                    <button class="btn btn-outline-danger" @click="removeAction(action.action_id)">删除</button>
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
            <h5 class="modal-title">{{ editingPlanId ? '编辑方案' : '新增方案' }}</h5>
            <button type="button" class="btn-close" aria-label="关闭" @click="closePlanModal"></button>
          </div>
          <div class="modal-body">
            <form class="row g-3" @submit.prevent="submitPlan">
              <div class="col-12 col-md-6">
                <label class="form-label">标题</label>
                <input v-model="planForm.title" class="form-control" maxlength="120" required />
              </div>
              <div class="col-12 col-md-6">
                <label class="form-label">描述（可选）</label>
                <input v-model="planForm.description" class="form-control" maxlength="200" />
              </div>
              <div class="col-12">
                <label class="form-label">流水线步骤（按顺序执行，上一步输出作为下一步输入）</label>
                <div v-for="(step, index) in planForm.steps" :key="index" class="d-flex align-items-center gap-2 mb-2">
                  <span class="badge text-bg-secondary flex-shrink-0">{{ index + 1 }}</span>
                  <select v-model="step.action_id" class="form-select" required>
                    <option value="" disabled>选择动作</option>
                    <option v-for="action in enabledActions" :key="action.action_id" :value="action.action_id">{{ action.name }}</option>
                  </select>
                  <input v-model="step.output_filename" class="form-control" placeholder="输出文件名覆盖（可选）" />
                  <div class="btn-group btn-group-sm flex-shrink-0">
                    <button type="button" class="btn btn-outline-secondary" :disabled="index === 0" title="上移" @click="moveStep(index, -1)">↑</button>
                    <button type="button" class="btn btn-outline-secondary" :disabled="index === planForm.steps.length - 1" title="下移" @click="moveStep(index, 1)">↓</button>
                    <button type="button" class="btn btn-outline-danger" :disabled="planForm.steps.length <= 1" title="删除步骤" @click="planForm.steps.splice(index, 1)">×</button>
                  </div>
                </div>
                <button type="button" class="btn btn-outline-primary btn-sm" @click="planForm.steps.push({ action_id: '', output_filename: '' })">添加步骤</button>
              </div>
              <div class="col-12">
                <div class="form-check form-switch">
                  <input id="plan-enabled" v-model="planForm.enabled" class="form-check-input" type="checkbox" />
                  <label class="form-check-label" for="plan-enabled">启用该方案</label>
                </div>
              </div>
              <div class="col-12 d-flex justify-content-end gap-2">
                <button type="button" class="btn btn-outline-secondary" @click="closePlanModal">取消</button>
                <button class="btn btn-primary" :disabled="submitting">{{ submitting ? '提交中...' : '保存' }}</button>
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
            <h5 class="modal-title">{{ editingActionId ? '编辑动作' : '新增动作' }}</h5>
            <button type="button" class="btn-close" aria-label="关闭" @click="closeActionModal"></button>
          </div>
          <div class="modal-body">
            <form class="row g-3" @submit.prevent="submitAction">
              <div class="col-12">
                <label class="form-label">名称</label>
                <input v-model="actionForm.name" class="form-control" maxlength="120" required />
              </div>
              <div class="col-12">
                <label class="form-label">提示词</label>
                <textarea v-model="actionForm.prompt" class="form-control" rows="10" required></textarea>
              </div>
              <div class="col-12 col-md-6">
                <label class="form-label">输出文件名</label>
                <input v-model="actionForm.output_filename" class="form-control" placeholder="postprocessed.md" required />
                <div class="form-text">该步骤产物的文件名（.md），重跑时同名覆盖。</div>
              </div>
              <div class="col-12 col-md-6">
                <label class="form-label">分片字符预算（可选）</label>
                <input v-model.number="actionForm.context_size" type="number" min="4096" class="form-control" :placeholder="`默认 ${defaultContextSize}`" />
                <div class="form-text">留空则使用全局默认值，应显著低于模型上下文窗口。</div>
              </div>
              <div class="col-12">
                <div class="form-check form-switch">
                  <input id="action-enabled" v-model="actionForm.enabled" class="form-check-input" type="checkbox" />
                  <label class="form-check-label" for="action-enabled">启用该动作</label>
                </div>
              </div>
              <div class="col-12 d-flex justify-content-end gap-2">
                <button type="button" class="btn btn-outline-secondary" @click="closeActionModal">取消</button>
                <button class="btn btn-primary" :disabled="submitting">{{ submitting ? '提交中...' : '保存' }}</button>
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
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import type {
  PostprocessActionItem,
  PostprocessActionListResponse,
  PostprocessPlanItem,
  PostprocessPlanListResponse,
} from '../types'

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
  return value.length > max ? value.slice(0, max) + '…' : value
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
    error.value = err instanceof ApiError ? err.message : '加载失败'
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
      success.value = '方案已更新'
    } else {
      await apiFetch('/api/admin/postprocess-plans', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      success.value = '方案已创建'
    }
    showPlanModal.value = false
    resetPlanForm()
    await loadAll()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '保存失败'
  } finally {
    submitting.value = false
  }
}

async function removePlan(planId: string) {
  if (!window.confirm('确定删除该后处理方案吗？')) return
  error.value = ''
  success.value = ''
  try {
    await apiFetch('/api/admin/postprocess-plans/' + encodeURIComponent(planId), { method: 'DELETE' })
    success.value = '方案已删除'
    await loadAll()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
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
      success.value = '动作已更新'
    } else {
      await apiFetch('/api/admin/postprocess-actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      success.value = '动作已创建'
    }
    showActionModal.value = false
    resetActionForm()
    await loadAll()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '保存失败'
  } finally {
    submitting.value = false
  }
}

async function removeAction(actionId: string) {
  if (!window.confirm('确定删除该动作吗？被方案引用的动作无法删除。')) return
  error.value = ''
  success.value = ''
  try {
    await apiFetch('/api/admin/postprocess-actions/' + encodeURIComponent(actionId), { method: 'DELETE' })
    success.value = '动作已删除'
    await loadAll()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  }
}

onMounted(() => {
  loadAll()
})
</script>
