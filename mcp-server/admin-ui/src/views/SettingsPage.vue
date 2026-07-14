<template>
  <AdminLayout>
    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="success" class="alert alert-success">{{ success }}</div>

    <div class="card page-card mb-3">
      <div class="card-body">
        <h5 class="card-title">修改密码</h5>
        <form class="row g-3" @submit.prevent="changePassword">
          <div class="col-md-4"><label class="form-label">当前密码</label><input v-model="form.old_password" class="form-control" type="password" required /></div>
          <div class="col-md-4"><label class="form-label">新密码</label><input v-model="form.new_password" class="form-control" type="password" required /></div>
          <div class="col-md-4"><label class="form-label">确认新密码</label><input v-model="confirmPassword" class="form-control" type="password" required /></div>
          <div class="col-12"><button class="btn btn-primary" :disabled="submitting">{{ submitting ? '提交中...' : '修改密码' }}</button></div>
        </form>
      </div>
    </div>

    <div class="card page-card mb-3">
      <div class="card-body">
        <h5 class="card-title">管理员安全</h5>
        <div v-if="settings" class="table-wrap">
          <table class="table table-sm mb-0">
            <tbody>
              <tr><th>用户名</th><td>{{ settings.admin_security.default_username }}</td></tr>
              <tr><th>密码状态</th><td>
                <span v-if="settings.admin_security.default_password_in_use" class="badge text-bg-warning">仍在使用默认密码</span>
                <span v-else class="badge text-bg-success">已修改</span>
              </td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="card page-card">
      <div class="card-body">
        <h5 class="card-title">全局运行配置</h5>
        <div v-if="settings" class="table-wrap">
          <table class="table table-sm mb-0">
            <tbody>
              <tr><th>最大并发数</th><td>{{ settings.max_concurrent }}</td></tr>
              <tr><th>配置来源</th><td>{{ settings.max_concurrent_source }}</td></tr>
              <tr><th>说明</th><td>{{ settings.max_concurrent_note }}</td></tr>
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
import AdminLayout from '../layouts/AdminLayout.vue'
import { apiFetch, ApiError } from '../lib/api'
import { useAuthStore } from '../stores/auth'
import type { RuntimeSettingsResponse } from '../types'

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
    error.value = '两次输入的密码不一致'
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
    success.value = '密码修改成功'
    auth.clear()
    window.setTimeout(() => {
      router.push({ name: 'login' })
    }, 800)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '修改密码失败'
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  try {
    await loadSettings()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载失败'
  }
})
</script>
