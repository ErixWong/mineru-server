<template>
  <div class="min-vh-100 d-flex flex-column bg-body-tertiary">
    <nav class="navbar navbar-dark bg-dark py-3">
      <div class="container-xl px-3 px-lg-4 gap-3">
        <RouterLink class="navbar-brand d-flex align-items-center gap-2 fw-semibold mb-0" :to="{ name: 'portal-home' }">
          <i class="bi bi-file-earmark-richtext fs-4 text-info"></i>
          <span>MinerU 文档解析</span>
        </RouterLink>
        <div class="d-flex align-items-center gap-2 ms-auto">
          <span class="navbar-text small text-break d-none d-sm-inline">{{ displayName }}</span>
          <button class="btn btn-outline-light btn-sm" type="button" @click="logout">退出</button>
        </div>
      </div>
    </nav>

    <div class="bg-body border-bottom">
      <nav class="container-xl px-3 px-lg-4" aria-label="用户导航">
        <ul class="nav nav-underline flex-nowrap gap-2 overflow-auto">
          <li class="nav-item"><RouterLink class="nav-link text-nowrap" :to="{ name: 'portal-home' }">首页</RouterLink></li>
          <li class="nav-item"><RouterLink class="nav-link text-nowrap" :to="{ name: 'portal-new-task' }">新建解析</RouterLink></li>
          <li class="nav-item"><RouterLink class="nav-link text-nowrap" :to="{ name: 'portal-tasks' }">我的任务</RouterLink></li>
          <li class="nav-item"><RouterLink class="nav-link text-nowrap" :to="{ name: 'portal-ledger' }">额度明细</RouterLink></li>
        </ul>
      </nav>
    </div>

    <main class="container-xl px-3 px-lg-4 py-4 py-lg-5 flex-grow-1">
      <div v-if="error" class="alert alert-danger">{{ error }}</div>
      <RouterView />
    </main>
    <footer class="container-xl px-3 px-lg-4 pb-4 text-body-secondary small">安全、便捷地提取文档中的文字与结构</footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, apiFetch } from '../lib/api'
import { useAuthStore } from '../stores/auth'
import { usePortalStore } from '../stores/portal'

const router = useRouter()
const auth = useAuthStore()
const portal = usePortalStore()
const error = ref('')
const displayName = computed(() => portal.profile?.display_name || auth.user?.display_name || auth.user?.username || '')

onMounted(async () => {
  try {
    await portal.loadProfile()
  } catch (caught) {
    if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
      try {
        await auth.refresh()
      } catch {
        error.value = '登录状态验证失败，请重新登录。'
      }
    } else {
      error.value = caught instanceof Error ? caught.message : '暂时无法读取账户信息。'
    }
  }
})

async function logout() {
  try {
    await apiFetch('/api/admin/logout', { method: 'POST' })
  } catch (err) {
    error.value = err instanceof Error ? `退出失败：${err.message}` : '退出失败，请检查网络后重试。'
    return
  }
  auth.clear()
  portal.clear()
  await router.push({ name: 'login' })
}
</script>
