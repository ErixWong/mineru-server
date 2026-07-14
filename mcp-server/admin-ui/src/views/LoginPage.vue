<template>
  <div class="container py-5" style="max-width: 420px">
    <div class="card page-card">
      <div class="card-body p-4">
        <h3 class="card-title mb-3">MinerU 管理控制台</h3>
        <p class="text-muted">请登录以继续</p>
        <div v-if="error" class="alert alert-danger">{{ error }}</div>
        <form @submit.prevent="submit">
          <div class="mb-3">
            <label class="form-label">用户名</label>
            <input v-model="form.username" class="form-control" required />
          </div>
          <div class="mb-3">
            <label class="form-label">密码</label>
            <input v-model="form.password" class="form-control" type="password" required />
          </div>
          <button class="btn btn-primary w-100" :disabled="submitting">
            {{ submitting ? '登录中...' : '登录' }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch, ApiError } from '../lib/api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const submitting = ref(false)
const error = ref('')
const form = reactive({ username: 'admin', password: '' })

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    const result = await apiFetch<{ success: boolean; must_change_password: boolean }>('/api/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    await auth.refresh()
    router.push(result.must_change_password ? { name: 'change-password' } : { name: 'dashboard' })
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '登录失败'
  } finally {
    submitting.value = false
  }
}
</script>
