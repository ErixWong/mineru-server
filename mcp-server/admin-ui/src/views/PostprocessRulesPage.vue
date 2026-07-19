<template>
  <AdminLayout>
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <div>
        <h3 class="mb-1">后处理方案</h3>
        <div class="text-muted small">用于任务完成后的 markdown 后处理；超长文档按每分片 {{ defaultContextSize }} 字符的原文预算切片多轮调用（应显著低于模型实际窗口，为 prompt 与输出预留空间）</div>
      </div>
      <button class="btn btn-primary" @click="openCreate">新增方案</button>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="success" class="alert alert-success">{{ success }}</div>

    <div class="card shadow-sm">
      <div class="card-body">
        <div v-if="loading" class="text-muted">加载中...</div>
        <div v-else-if="rules.length === 0" class="text-muted">暂无方案</div>
        <div v-else class="table-responsive">
          <table class="table align-middle mb-0">
            <thead>
              <tr>
                <th>标题</th>
                <th>输出文件名</th>
                <th>提示词</th>
                <th>状态</th>
                <th>更新时间</th>
                <th class="text-end">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rule in rules" :key="rule.rule_id">
                <td class="fw-semibold">{{ rule.title }}</td>
                <td class="small font-monospace">{{ rule.output_filename }}</td>
                <td class="small text-break">{{ rule.prompt }}</td>
                <td>
                  <span class="badge" :class="Boolean(rule.enabled) ? 'text-bg-success' : 'text-bg-secondary'">
                    {{ Boolean(rule.enabled) ? '启用' : '停用' }}
                  </span>
                </td>
                <td class="small text-muted">{{ formatDate(rule.updated_at || rule.created_at) }}</td>
                <td>
                  <div class="btn-group btn-group-sm d-flex justify-content-end">
                    <button class="btn btn-outline-primary" @click="openEdit(rule)">编辑</button>
                    <button class="btn btn-outline-danger" @click="removeRule(rule.rule_id)">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div v-if="showModal" class="modal fade show d-block" tabindex="-1" aria-modal="true">
      <div class="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ editingId ? '编辑方案' : '新增方案' }}</h5>
            <button type="button" class="btn-close" aria-label="关闭" @click="closeModal"></button>
          </div>
          <div class="modal-body">
            <form class="row g-3" @submit.prevent="submitRule">
              <div class="col-12">
                <label class="form-label">标题</label>
                <input v-model="form.title" class="form-control" maxlength="120" required />
              </div>
              <div class="col-12">
                <label class="form-label">提示词</label>
                <textarea v-model="form.prompt" class="form-control" rows="12" required></textarea>
              </div>
              <div class="col-12 col-md-6">
                <label class="form-label">输出文件名</label>
                <input v-model="form.output_filename" class="form-control" placeholder="postprocessed.md" required />
                <div class="form-text">用于固定后处理交付物下载文件名。</div>
              </div>
              <div class="col-12">
                <div class="form-check form-switch">
                  <input id="rule-enabled" v-model="form.enabled" class="form-check-input" type="checkbox" />
                  <label class="form-check-label" for="rule-enabled">启用该方案</label>
                </div>
              </div>
              <div class="col-12 d-flex justify-content-end gap-2">
                <button type="button" class="btn btn-outline-secondary" @click="closeModal">取消</button>
                <button class="btn btn-primary" :disabled="submitting">{{ submitting ? '提交中...' : '保存' }}</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
    <div v-if="showModal" class="modal-backdrop fade show"></div>
  </AdminLayout>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import type { PostprocessRuleItem, PostprocessRuleListResponse } from '../types'

const rules = ref<PostprocessRuleItem[]>([])
const loading = ref(false)
const submitting = ref(false)
const showModal = ref(false)
const editingId = ref('')
const defaultContextSize = ref(131072)
const error = ref('')
const success = ref('')
const form = reactive({ title: '', prompt: '', output_filename: 'postprocessed.md', enabled: true })

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : '-'
}

function resetForm() {
  form.title = ''
  form.prompt = ''
  form.output_filename = 'postprocessed.md'
  form.enabled = true
  editingId.value = ''
}

function openCreate() {
  resetForm()
  error.value = ''
  success.value = ''
  showModal.value = true
}

function openEdit(rule: PostprocessRuleItem) {
  editingId.value = rule.rule_id
  form.title = rule.title
  form.prompt = rule.prompt
  form.output_filename = rule.output_filename
  form.enabled = Boolean(rule.enabled)
  error.value = ''
  success.value = ''
  showModal.value = true
}

function closeModal() {
  if (submitting.value) return
  showModal.value = false
  resetForm()
}

async function loadRules() {
  loading.value = true
  error.value = ''
  try {
    const payload = await apiFetch<PostprocessRuleListResponse>('/api/admin/postprocess-rules')
    rules.value = payload.items
    defaultContextSize.value = payload.default_context_size
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function submitRule() {
  submitting.value = true
  error.value = ''
  success.value = ''
  try {
    const payload = { title: form.title, prompt: form.prompt, output_filename: form.output_filename, enabled: form.enabled }
    if (editingId.value) {
      await apiFetch('/api/admin/postprocess-rules/' + encodeURIComponent(editingId.value), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      success.value = '方案已更新'
    } else {
      await apiFetch('/api/admin/postprocess-rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      success.value = '方案已创建'
    }
    showModal.value = false
    resetForm()
    await loadRules()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '保存失败'
  } finally {
    submitting.value = false
  }
}

async function removeRule(ruleId: string) {
  if (!window.confirm('确定删除该后处理方案吗？')) return
  error.value = ''
  success.value = ''
  try {
    await apiFetch('/api/admin/postprocess-rules/' + encodeURIComponent(ruleId), { method: 'DELETE' })
    success.value = '方案已删除'
    await loadRules()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  }
}

onMounted(() => {
  loadRules()
})
</script>
