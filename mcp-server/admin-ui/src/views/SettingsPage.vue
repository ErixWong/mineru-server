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
        <div v-if="settings" class="table-wrap">
          <table class="table table-sm mb-0">
            <tbody>
              <tr><th>{{ t('settings.maxConcurrent') }}</th><td>{{ settings.max_concurrent }}</td></tr>
              <tr><th>{{ t('settings.configSource') }}</th><td>{{ settings.max_concurrent_source }}</td></tr>
              <tr><th>{{ t('settings.description') }}</th><td>{{ settings.max_concurrent_note }}</td></tr>
            </tbody>
          </table>
        </div>
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
const confirmPassword = ref('')
const form = reactive({ old_password: '', new_password: '' })

async function loadSettings() {
  settings.value = await apiFetch<RuntimeSettingsResponse>('/api/admin/settings/runtime')
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

onMounted(async () => {
  try {
    await loadSettings()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('settings.loadFailed')
  }
})
</script>
