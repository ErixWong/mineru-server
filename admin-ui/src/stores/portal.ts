import { defineStore } from 'pinia'
import { apiFetch } from '../lib/api'
import type { PortalProfile } from '../types'

export const usePortalStore = defineStore('portal', {
  state: () => ({
    profile: null as PortalProfile | null,
    loading: false,
  }),
  actions: {
    async loadProfile() {
      this.loading = true
      try {
        this.profile = await apiFetch<PortalProfile>('/api/portal/me')
      } finally {
        this.loading = false
      }
    },
    clear() {
      this.profile = null
      this.loading = false
    },
  },
})
