<template>
  <AdminLayout>
    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="success" class="alert alert-success">{{ success }}</div>

    <div class="card page-card mb-3">
      <div class="card-body">
        <div class="settings-card-header">
          <h5 class="card-title mb-0">{{ t('settings.changePassword') }}</h5>
          <span
            v-if="settings?.admin_security.default_password_in_use"
            class="badge text-bg-danger"
          >
            {{ t('settings.usingDefault') }}
          </span>
        </div>
        <form class="row g-3" @submit.prevent="changePassword">
          <div class="col-md-4"><label class="form-label">{{ t('settings.currentPassword') }}</label><input v-model="form.old_password" class="form-control form-control-sm" type="password" required /></div>
          <div class="col-md-4"><label class="form-label">{{ t('settings.newPassword') }}</label><input v-model="form.new_password" class="form-control form-control-sm" type="password" required /></div>
          <div class="col-md-4"><label class="form-label">{{ t('settings.confirmPassword') }}</label><input v-model="confirmPassword" class="form-control form-control-sm" type="password" required /></div>
          <div class="col-12"><button class="btn btn-primary btn-sm" :disabled="submitting">{{ submitting ? t('settings.changing') : t('settings.changeButton') }}</button></div>
        </form>
      </div>
    </div>

    <section class="runtime-page">
      <div class="runtime-page-header">
        <div>
          <h5 class="mb-1">{{ t('settings.runtimeConfig') }}</h5>
          <p class="text-muted small mb-0">{{ t('settings.runtimeConfigIntro') }}</p>
        </div>
        <span class="runtime-note">{{ t('settings.sensitiveHint') }}</span>
      </div>

      <form v-if="settings" class="runtime-form" @submit.prevent="saveRuntimeSettings">
        <section class="runtime-panel">
          <div class="runtime-panel-heading">
              <h6>{{ t('settings.routingSection') }}</h6>
              <p>{{ t('settings.routingSectionHelp') }}</p>
            </div>
            <div class="row g-3">
              <div class="col-md-6 col-xl-4">
                <label class="form-label">{{ t('settings.defaultBackend') }}</label>
                <select v-model="runtimeForm.default_backend" class="form-select form-select-sm">
                  <option v-for="backend in settings.valid_backends" :key="backend" :value="backend">{{ backend }}</option>
                </select>
                <div class="runtime-field-meta">
                  <span>{{ sourceLabel('default_backend') }}</span>
                </div>
              </div>
            </div>
        </section>

        <section class="runtime-panel">
          <div class="runtime-panel-heading">
              <h6>{{ t('settings.vlmSection') }}</h6>
              <p>{{ t('settings.vlmSectionHelp') }}</p>
            </div>
            <div class="row g-3">
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.vlmBaseUrl') }}</label>
                <input v-model="runtimeForm.vlm_base_url" class="form-control form-control-sm" placeholder="https://api.openai.com/v1" />
                <div class="runtime-field-meta">
                  <span>{{ sourceLabel('vlm_base_url') }}</span>
                </div>
              </div>
              <div class="col-md-3">
                <label class="form-label">{{ t('settings.vlmModel') }}</label>
                <input v-model="runtimeForm.vlm_model" class="form-control form-control-sm" placeholder="gpt-4o" />
                <div class="runtime-field-meta">
                  <span>{{ sourceLabel('vlm_model') }}</span>
                </div>
              </div>
              <div class="col-md-3">
                <label class="form-label">{{ t('settings.vlmApiKey') }}</label>
                <input v-model="secretForm.vlm_api_key" class="form-control form-control-sm" type="password" autocomplete="new-password" :placeholder="secretPlaceholder('vlm_api_key')" />
                <div class="runtime-field-meta">
                  <span>{{ secretStatus('vlm_api_key') }}</span>
                </div>
              </div>
              <div class="col-md-3">
                <label class="form-label">{{ t('settings.vlmMaxConcurrency') }}</label>
                <input v-model.number="runtimeForm.vlm_max_concurrency" class="form-control form-control-sm" type="number" min="1" max="100" />
                <div class="runtime-field-meta">
                  <span>{{ sourceLabel('vlm_max_concurrency') }}</span>
                  <span class="runtime-effect-badge">{{ t('settings.restartRequired') }}</span>
                </div>
              </div>
            </div>
        </section>

        <section class="runtime-panel">
          <div class="runtime-panel-heading">
              <h6>{{ t('settings.titleSection') }}</h6>
              <p>{{ t('settings.titleSectionHelp') }}</p>
            </div>
            <div class="row g-3">
              <div class="col-md-6">
                <label class="form-label">{{ t('settings.titleBaseUrl') }}</label>
                <input v-model="runtimeForm.title_base_url" class="form-control form-control-sm" placeholder="https://api.openai.com/v1" />
                <div class="runtime-field-meta">
                  <span>{{ sourceLabel('title_base_url') }}</span>
                </div>
              </div>
              <div class="col-md-3">
                <label class="form-label">{{ t('settings.titleModel') }}</label>
                <input v-model="runtimeForm.title_model" class="form-control form-control-sm" placeholder="gpt-4o-mini" />
                <div class="runtime-field-meta">
                  <span>{{ sourceLabel('title_model') }}</span>
                </div>
              </div>
              <div class="col-md-3">
                <label class="form-label">{{ t('settings.titleApiKey') }}</label>
                <input v-model="secretForm.title_api_key" class="form-control form-control-sm" type="password" autocomplete="new-password" :placeholder="secretPlaceholder('title_api_key')" />
                <div class="runtime-field-meta">
                  <span>{{ secretStatus('title_api_key') }}</span>
                </div>
              </div>
              <div class="col-md-3">
                <label class="form-label">{{ t('settings.postprocessContextSize') }}</label>
                <input v-model.number="runtimeForm.postprocess_context_size" class="form-control form-control-sm" type="number" min="4096" step="1024" />
                <div class="runtime-field-meta">
                  <span>{{ sourceLabel('postprocess_context_size') }}</span>
                </div>
              </div>
              <div class="col-md-3">
                <label class="form-label">{{ t('settings.postprocessMaxConcurrent') }}</label>
                <input v-model.number="runtimeForm.postprocess_max_concurrent" class="form-control form-control-sm" type="number" min="1" max="32" />
                <div class="runtime-field-meta">
                  <span>{{ sourceLabel('postprocess_max_concurrent') }}</span>
                  <span class="runtime-effect-badge">{{ t('settings.restartRequired') }}</span>
                </div>
              </div>
            </div>
        </section>

        <section class="runtime-panel">
          <div class="runtime-panel-heading">
              <h6>{{ t('settings.schedulerSection') }}</h6>
              <p>{{ t('settings.schedulerSectionHelp') }}</p>
            </div>
            <div class="row g-3">
              <div class="col-md-3">
                <label class="form-label">{{ t('settings.maxConcurrent') }}</label>
                <input v-model.number="runtimeForm.max_concurrent" class="form-control form-control-sm" type="number" min="1" max="100" />
                <div class="runtime-field-meta">
                  <span>{{ sourceLabel('max_concurrent') }}</span>
                  <span class="runtime-effect-badge">{{ t('settings.restartRequired') }}</span>
                </div>
              </div>
              <div class="col-md-3">
                <label class="form-label">{{ t('settings.taskTimeout') }}</label>
                <input v-model.number="runtimeForm.task_timeout" class="form-control form-control-sm" type="number" min="1" />
                <div class="runtime-field-meta">
                  <span>{{ sourceLabel('task_timeout') }}</span>
                </div>
              </div>
              <div class="col-md-3">
                <label class="form-label">{{ t('settings.retryLimit') }}</label>
                <input v-model.number="runtimeForm.retry_limit" class="form-control form-control-sm" type="number" min="0" max="100" />
                <div class="runtime-field-meta">
                  <span>{{ sourceLabel('retry_limit') }}</span>
                </div>
              </div>
              <div class="col-md-3">
                <label class="form-label">{{ t('settings.cleanupDays') }}</label>
                <input v-model.number="runtimeForm.cleanup_days" class="form-control form-control-sm" type="number" min="1" />
                <div class="runtime-field-meta">
                  <span>{{ sourceLabel('cleanup_days') }}</span>
                </div>
              </div>
            </div>
        </section>

        <div class="runtime-actions">
          <button class="btn btn-primary btn-sm" :disabled="savingRuntime">{{ savingRuntime ? t('settings.saving') : t('settings.saveRuntime') }}</button>
          <span class="text-muted small">{{ settings.max_concurrent_note }}</span>
        </div>
      </form>
    </section>
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

<style scoped>
.settings-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.runtime-page {
  margin-top: 1rem;
}

.runtime-page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.runtime-page-header h5 {
  color: #212529;
  font-weight: 700;
}

.runtime-note {
  flex: 0 0 auto;
  max-width: 20rem;
  padding: 0.375rem 0.625rem;
  border: 1px solid #d7dde5;
  border-radius: 6px;
  color: #495057;
  background: #f8f9fa;
  font-size: 0.8125rem;
  line-height: 1.35;
}

.runtime-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.runtime-panel {
  padding: 1rem;
  border: 1px solid #dfe5ec;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 0.125rem 0.25rem rgba(15, 23, 42, 0.04);
}

.runtime-panel-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #eef1f4;
}

.runtime-panel-heading h6 {
  margin: 0;
  color: #212529;
  font-size: 1rem;
  font-weight: 700;
}

.runtime-panel-heading p {
  max-width: 42rem;
  margin: 0;
  color: #6c757d;
  font-size: 0.8125rem;
  line-height: 1.4;
  text-align: right;
}

.runtime-field-meta {
  display: flex;
  min-height: 1.25rem;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.25rem;
  color: #6c757d;
  font-size: 0.8125rem;
  line-height: 1.35;
}

.runtime-field-meta > span:first-child {
  min-width: 0;
  overflow-wrap: anywhere;
}

.runtime-effect-badge {
  flex: 0 0 auto;
  padding: 0.0625rem 0.375rem;
  border: 1px solid #f1c36d;
  border-radius: 999px;
  color: #7a4c00;
  background: #fff7e6;
  font-size: 0.75rem;
  line-height: 1.3;
}

.runtime-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.875rem 1rem;
  border: 1px solid #dfe5ec;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 0.125rem 0.25rem rgba(15, 23, 42, 0.04);
}

@media (max-width: 767.98px) {
  .runtime-page-header,
  .runtime-panel-heading,
  .runtime-actions {
    display: block;
  }

  .runtime-note {
    max-width: none;
    margin-top: 0.75rem;
  }

  .runtime-panel-heading p {
    margin-top: 0.25rem;
    text-align: left;
  }

  .runtime-actions .btn {
    margin-bottom: 0.75rem;
  }
}
</style>
