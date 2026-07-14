import { defineStore } from 'pinia'
import { fetchCurrentAdmin, ApiError } from '../lib/api'
import type { AdminMe } from '../types'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as AdminMe | null,
    loaded: false,
  }),
  actions: {
    async refresh() {
      try {
        this.user = await fetchCurrentAdmin()
      } catch (error) {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          this.user = null
        } else {
          throw error
        }
      } finally {
        this.loaded = true
      }
    },
    clear() {
      this.user = null
      this.loaded = true
    },
  },
})
