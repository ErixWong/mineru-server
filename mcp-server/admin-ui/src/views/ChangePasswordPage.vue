<template>
  <div class="container py-5" style="max-width: 480px">
    <div class="card page-card">
      <div class="card-body p-4">
        <h3 class="card-title mb-3">{{ t('password.title') }}</h3>
        <div v-if="error" class="alert alert-danger">{{ error }}</div>
        <div v-if="success" class="alert alert-success">{{ t('password.success') }}</div>
        <form @submit.prevent="submit">
          <div class="mb-3">
            <label class="form-label">{{ t('password.currentPassword') }}</label>
            <input v-model="form.old_password" class="form-control" type="password" required />
          </div>
          <div class="mb-3">
            <label class="form-label">{{ t('password.newPassword') }}</label>
            <input v-model="form.new_password" class="form-control" type="password" required />
          </div>
          <div class="mb-3">
            <label class="form-label">{{ t('password.confirmPassword') }}</label>
            <input v-model="confirmPassword" class="form-control" type="password" required />
          </div>
          <button class="btn btn-primary w-100" :disabled="submitting">
            {{ submitting ? t('password.changing') : t('password.changeButton') }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { apiFetch, ApiError } from '../lib/api'
import { useAuthStore } from '../stores/auth'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const submitting = ref(false)
const error = ref('')
const success = ref(false)
const confirmPassword = ref('')
const form = reactive({ old_password: '', new_password: '' })

async function submit() {
  if (form.new_password !== confirmPassword.value) {
    error.value = t('password.mismatch')
    return
  }
  submitting.value = true
  error.value = ''
  success.value = false
  try {
    await apiFetch('/api/admin/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    success.value = true
    auth.clear()
    setTimeout(() => router.push({ name: 'login' }), 800)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('password.changeFailed')
  } finally {
    submitting.value = false
  }
}
</script>
