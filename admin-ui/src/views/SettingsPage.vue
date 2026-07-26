<template>
  <AdminLayout>
    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="success" class="alert alert-success">{{ success }}</div>

    <div class="card page-card mb-3">
      <div class="card-body">
        <h5 class="card-title">{{ t('settings.changePassword') }}</h5>
        <form class="row g-3" @submit.prevent="changePassword">
          <div class="col-md-4"><label class="form-label">{{ t('settings.currentPassword') }}</label><input v-model="form.old_password" class="form-control" type="password" required /></div>
          <div class="col-md-4"><label class="form-label">{{ t('settings.newPassword') }}</label><input v-model="form.new_password" class="form-control" type="password" required /></div>
          <div class="col-md-4"><label class="form-label">{{ t('settings.confirmPassword') }}</label><input v-model="confirmPassword" class="form-control" type="password" required /></div>
          <div class="col-12"><button class="btn btn-primary" :disabled="submitting">{{ submitting ? t('settings.changing') : t('settings.changeButton') }}</button></div>
        </form>
      </div>
    </div>

    <div class="card page-card mb-3">
      <div class="card-body">
        <h5 class="card-title">{{ t('settings.adminSecurity') }}</h5>
        <div v-if="settings" class="table-wrap">
          <table class="table table-sm mb-0">
            <tbody>
              <tr><th>{{ t('settings.username') }}</th><td>{{ settings.admin_security.default_username }}</td></tr>
              <tr><th>{{ t('settings.passwordStatus') }}</th><td>
                <span v-if="settings.admin_security.default_password_in_use" class="badge text-bg-warning">{{ t('settings.usingDefault') }}</span>
                <span v-else class="badge text-bg-success">{{ t('settings.modified') }}</span>
              </td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="card page-card">
      <div class="card-body">
        <h5 class="card-title">{{ t('settings.runtimeConfig') }}</h5>
        <form v-if="settings" class="row g-3" @submit.prevent="saveRuntimeSettings">
          <div class="col-md-4">
            <label class="form-label">{{ t('settings.defaultBackend') }}</label>
            <select v-model="runtimeForm.default_backend" class="form-select">
              <option v-for="backend in settings.valid_backends" :key="backend" :value="backend">{{ backend }}</option>
            </select>
            <div class="form-text">{{ sourceLabel('default_backend') }}</div>
          </div>

          <div class="col-md-8">
            <label class="form-label">{{ t('settings.vlmBaseUrl') }}</label>
            <input v-model="runtimeForm.vlm_base_url" class="form-control" placeholder="https://api.openai.com/v1" />
            <div class="form-text">{{ sourceLabel('vlm_base_url') }}</div>
          </div>
          <div class="col-md-4">
            <label class="form-label">{{ t('settings.vlmModel') }}</label>
            <input v-model="runtimeForm.vlm_model" class="form-control" placeholder="gpt-4o" />
            <div class="form-text">{{ sourceLabel('vlm_model') }}</div>
          </div>
          <div class="col-md-4">
            <label class="form-label">{{ t('settings.vlmApiKey') }}</label>
            <input v-model="secretForm.vlm_api_key" class="form-control" type="password" autocomplete="new-password" :placeholder="secretPlaceholder('vlm_api_key')" />
            <div class="form-text">{{ secretStatus('vlm_api_key') }}</div>
          </div>
          <div class="col-md-4">
            <label class="form-label">{{ t('settings.vlmMaxConcurrency') }}</label>
            <input v-model.number="runtimeForm.vlm_max_concurrency" class="form-control" type="number" min="1" max="100" />
            <div class="form-text text-warning">{{ t('settings.restartRequired') }}</div>
          </div>

          <div class="col-md-8">
            <label class="form-label">{{ t('settings.titleBaseUrl') }}</label>
            <input v-model="runtimeForm.title_base_url" class="form-control" placeholder="https://api.openai.com/v1" />
            <div class="form-text">{{ sourceLabel('title_base_url') }}</div>
          </div>
          <div class="col-md-4">
            <label class="form-label">{{ t('settings.titleModel') }}</label>
            <input v-model="runtimeForm.title_model" class="form-control" placeholder="gpt-4o-mini" />
            <div class="form-text">{{ sourceLabel('title_model') }}</div>
          </div>
          <div class="col-md-4">
            <label class="form-label">{{ t('settings.titleApiKey') }}</label>
            <input v-model="secretForm.title_api_key" class="form-control" type="password" autocomplete="new-password" :placeholder="secretPlaceholder('title_api_key')" />
            <div class="form-text">{{ secretStatus('title_api_key') }}</div>
          </div>
          <div class="col-md-4">
            <label class="form-label">{{ t('settings.postprocessContextSize') }}</label>
            <input v-model.number="runtimeForm.postprocess_context_size" class="form-control" type="number" min="4096" step="1024" />
            <div class="form-text">{{ sourceLabel('postprocess_context_size') }}</div>
          </div>
          <div class="col-md-4">
            <label class="form-label">{{ t('settings.postprocessMaxConcurrent') }}</label>
            <input v-model.number="runtimeForm.postprocess_max_concurrent" class="form-control" type="number" min="1" max="32" />
            <div class="form-text text-warning">{{ t('settings.restartRequired') }}</div>
          </div>

          <div class="col-md-3">
            <label class="form-label">{{ t('settings.maxConcurrent') }}</label>
            <input v-model.number="runtimeForm.max_concurrent" class="form-control" type="number" min="1" max="100" />
            <div class="form-text text-warning">{{ t('settings.restartRequired') }}</div>
          </div>
          <div class="col-md-3">
            <label class="form-label">{{ t('settings.taskTimeout') }}</label>
            <input v-model.number="runtimeForm.task_timeout" class="form-control" type="number" min="1" />
            <div class="form-text">{{ sourceLabel('task_timeout') }}</div>
          </div>
          <div class="col-md-3">
            <label class="form-label">{{ t('settings.retryLimit') }}</label>
            <input v-model.number="runtimeForm.retry_limit" class="form-control" type="number" min="0" max="100" />
            <div class="form-text">{{ sourceLabel('retry_limit') }}</div>
          </div>
          <div class="col-md-3">
            <label class="form-label">{{ t('settings.cleanupDays') }}</label>
            <input v-model.number="runtimeForm.cleanup_days" class="form-control" type="number" min="1" />
            <div class="form-text">{{ sourceLabel('cleanup_days') }}</div>
          </div>

          <div class="col-12">
            <button class="btn btn-primary" :disabled="savingRuntime">{{ savingRuntime ? t('settings.saving') : t('settings.saveRuntime') }}</button>
            <span class="text-muted small ms-3">{{ settings.max_concurrent_note }}</span>
          </div>
        </form>
      </div>
    </div>
  </AdminLayout>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import { useAuthStore } from '../stores/auth'
import type { RuntimeSettingsResponse } from '../types'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const settings = ref<RuntimeSettingsResponse | null>(null)
const error = ref('')
const success = ref('')
const submitting = ref(false)
const savingRuntime = ref(false)
const confirmPassword = ref('')
const form = reactive({ old_password: '', new_password: '' })
const runtimeForm = reactive({
  default_backend: '',
  vlm_base_url: '',
  vlm_model: '',
  vlm_max_concurrency: 2,
  title_base_url: '',
  title_model: '',
  postprocess_context_size: 131072,
  postprocess_max_concurrent: 2,
  max_concurrent: 3,
  task_timeout: 3600,
  retry_limit: 3,
  cleanup_days: 300,
})
const secretForm = reactive({ vlm_api_key: '', title_api_key: '' })

async function loadSettings() {
  settings.value = await apiFetch<RuntimeSettingsResponse>('/api/admin/settings/runtime')
  Object.assign(runtimeForm, settings.value.config)
  secretForm.vlm_api_key = ''
  secretForm.title_api_key = ''
}

function sourceLabel(key: string) {
  const source = settings.value?.sources?.[key] || 'environment'
  return source === 'database' ? t('settings.sourceDatabase') : t('settings.sourceEnvironment')
}

function secretPlaceholder(key: string) {
  const secret = settings.value?.secrets?.[key]
  return secret?.configured ? t('settings.keepExistingSecret') : t('settings.notConfigured')
}

function secretStatus(key: string) {
  const secret = settings.value?.secrets?.[key]
  if (!secret?.configured) return t('settings.notConfigured')
  const masked = `${secret.prefix || ''}...${secret.suffix || ''}`
  const source = secret.source === 'database' ? t('settings.sourceDatabase') : t('settings.sourceEnvironment')
  return t('settings.secretConfigured', { masked, source })
}

async function changePassword() {
  if (form.new_password !== confirmPassword.value) {
    error.value = t('settings.mismatch')
    return
  }
  submitting.value = true
  error.value = ''
  success.value = ''
  try {
    await apiFetch('/api/admin/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    form.old_password = ''
    form.new_password = ''
    confirmPassword.value = ''
    success.value = t('settings.success')
    auth.clear()
    window.setTimeout(() => {
      router.push({ name: 'login' })
    }, 800)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('settings.changeFailed')
  } finally {
    submitting.value = false
  }
}

async function saveRuntimeSettings() {
  savingRuntime.value = true
  error.value = ''
  success.value = ''
  try {
    const payload: Record<string, unknown> = { ...runtimeForm }
    if (secretForm.vlm_api_key.trim()) payload.vlm_api_key = secretForm.vlm_api_key.trim()
    if (secretForm.title_api_key.trim()) payload.title_api_key = secretForm.title_api_key.trim()
    settings.value = await apiFetch<RuntimeSettingsResponse>('/api/admin/settings/runtime', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    Object.assign(runtimeForm, settings.value.config)
    secretForm.vlm_api_key = ''
    secretForm.title_api_key = ''
    success.value = t('settings.runtimeSaved')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('settings.runtimeSaveFailed')
  } finally {
    savingRuntime.value = false
  }
}

onMounted(async () => {
  try {
    await loadSettings()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('settings.loadFailed')
  }
})
</script>
