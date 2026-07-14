<template>
  <div class="app-shell d-flex flex-column">
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
      <div class="container-fluid px-4">
        <RouterLink class="navbar-brand" to="/">MinerU Admin Console</RouterLink>
        <div class="navbar-nav flex-row gap-3 ms-auto align-items-center">
          <span class="navbar-text">{{ username }}</span>
          <button class="btn btn-outline-light btn-sm" @click="logout">退出</button>
        </div>
      </div>
    </nav>

    <div class="container py-4 flex-grow-1">
      <div v-if="error" class="alert alert-danger">{{ error }}</div>
      <ul class="nav nav-tabs mb-4">
        <li class="nav-item"><RouterLink class="nav-link" to="/">仪表盘</RouterLink></li>
        <li class="nav-item"><RouterLink class="nav-link" to="/callers">调用方</RouterLink></li>
        <li class="nav-item"><RouterLink class="nav-link" to="/tasks">任务与交付</RouterLink></li>
        <li class="nav-item"><RouterLink class="nav-link" to="/settings">系统设置</RouterLink></li>
      </ul>
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch, ApiError } from '../lib/api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const username = computed(() => auth.user?.username ?? '')
const error = ref('')

async function logout() {
  error.value = ''
  try {
    await apiFetch('/api/admin/logout', { method: 'POST' })
    auth.clear()
    router.push({ name: 'login' })
  } catch (err) {
    const message = err instanceof ApiError ? err.message : '退出失败'
    error.value = `${message}。将强制回到登录页以清理本地状态。`
    auth.clear()
    window.setTimeout(() => {
      router.push({ name: 'login' })
    }, 800)
  }
}
</script>

<style scoped>
.router-link-active.nav-link {
  color: var(--bs-primary);
}
</style>
