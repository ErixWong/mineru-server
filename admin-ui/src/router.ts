import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { resolveLocale, setLocale, getLocale } from './i18n'
import LoginPage from './views/LoginPage.vue'
import ChangePasswordPage from './views/ChangePasswordPage.vue'
import DashboardPage from './views/DashboardPage.vue'
import CallersPage from './views/CallersPage.vue'
import TasksPage from './views/TasksPage.vue'
import TaskDetailPage from './views/TaskDetailPage.vue'
import SettingsPage from './views/SettingsPage.vue'
import PostprocessRulesPage from './views/PostprocessRulesPage.vue'
const router = createRouter({
  history: createWebHistory('/admin/'),
  routes: [
    { path: '/login', name: 'login', component: LoginPage, meta: { guestOnly: true } },
    { path: '/change-password', name: 'change-password', component: ChangePasswordPage },
    { path: '/', name: 'dashboard', component: DashboardPage, meta: { requiresAuth: true, requiresAdmin: true } },
    { path: '/callers', name: 'callers', component: CallersPage, meta: { requiresAuth: true, requiresAdmin: true } },
    { path: '/tasks', name: 'tasks', component: TasksPage, meta: { requiresAuth: true, requiresAdmin: true } },
    { path: '/tasks/:taskId', name: 'task-detail', component: TaskDetailPage, meta: { requiresAuth: true, requiresAdmin: true } },
    { path: '/postprocess-rules', name: 'postprocess-rules', component: PostprocessRulesPage, meta: { requiresAuth: true, requiresAdmin: true } },
    { path: '/settings', name: 'settings', component: SettingsPage, meta: { requiresAuth: true, requiresAdmin: true } },
    {
      path: '/portal',
      component: () => import('./layouts/PortalLayout.vue'),
      meta: { requiresAuth: true, requiresPortal: true },
      children: [
        { path: '', name: 'portal-home', component: () => import('./views/PortalHomePage.vue') },
        { path: 'new-task', name: 'portal-new-task', component: () => import('./views/PortalNewTaskPage.vue') },
        { path: 'tasks', name: 'portal-tasks', component: () => import('./views/PortalTasksPage.vue') },
        { path: 'tasks/:taskId', name: 'portal-task-detail', component: () => import('./views/PortalTaskDetailPage.vue') },
        { path: 'ledger', name: 'portal-ledger', component: () => import('./views/PortalLedgerPage.vue') },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.loaded) {
    await auth.refresh()
  }

  // Sync locale from server preference whenever a user is logged in.
  // Runs on first login and every navigation; setLocale is idempotent.
  if (auth.user) {
    const resolved = resolveLocale(auth.user.locale)
    if (getLocale() !== resolved) {
      setLocale(resolved)
    }
  }

  if (to.meta.guestOnly && auth.user) {
    if (auth.user.must_change_password) return { name: 'change-password' }
    return auth.user.role === 'user' ? { name: 'portal-home' } : { name: 'dashboard' }
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

  if (to.meta.requiresAdmin && auth.user?.role !== 'admin') {
    return { name: 'portal-home' }
  }

  if (to.meta.requiresPortal && auth.user?.role !== 'user') {
    return { name: 'dashboard' }
  }

  return true
})

export default router
