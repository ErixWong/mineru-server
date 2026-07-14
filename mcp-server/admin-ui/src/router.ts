import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'
import LoginPage from './views/LoginPage.vue'
import ChangePasswordPage from './views/ChangePasswordPage.vue'
import DashboardPage from './views/DashboardPage.vue'
import CallersPage from './views/CallersPage.vue'
import TasksPage from './views/TasksPage.vue'
import TaskDetailPage from './views/TaskDetailPage.vue'
import SettingsPage from './views/SettingsPage.vue'

const router = createRouter({
  history: createWebHistory('/admin/'),
  routes: [
    { path: '/login', name: 'login', component: LoginPage, meta: { guestOnly: true } },
    { path: '/change-password', name: 'change-password', component: ChangePasswordPage },
    { path: '/', name: 'dashboard', component: DashboardPage, meta: { requiresAuth: true } },
    { path: '/callers', name: 'callers', component: CallersPage, meta: { requiresAuth: true } },
    { path: '/tasks', name: 'tasks', component: TasksPage, meta: { requiresAuth: true } },
    { path: '/tasks/:taskId', name: 'task-detail', component: TaskDetailPage, meta: { requiresAuth: true } },
    { path: '/settings', name: 'settings', component: SettingsPage, meta: { requiresAuth: true } },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.loaded) {
    await auth.refresh()
  }

  if (to.meta.guestOnly && auth.user) {
    return auth.user.must_change_password ? { name: 'change-password' } : { name: 'dashboard' }
  }

  if (to.name === 'change-password') {
    if (!auth.user) {
      return { name: 'login' }
    }
    return true
  }

  if (to.meta.requiresAuth && !auth.user) {
    return { name: 'login' }
  }

  if (auth.user?.must_change_password && to.name !== 'change-password') {
    return { name: 'change-password' }
  }

  return true
})

export default router
