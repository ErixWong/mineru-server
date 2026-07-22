import { createI18n } from 'vue-i18n'
import zhCN from './messages/zh-CN.json'
import en from './messages/en.json'

export const SUPPORTED_LOCALES = ['zh-CN', 'en'] as const
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number]
export const DEFAULT_LOCALE: SupportedLocale = 'zh-CN'

const LOCALE_STORAGE_KEY = 'mineru-admin-locale'

function detectLocalLocale(): SupportedLocale {
  try {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY)
    if (stored && (SUPPORTED_LOCALES as readonly string[]).includes(stored)) {
      return stored as SupportedLocale
    }
  } catch { /* localStorage unavailable (SSR / test env) */ }
  try {
    const browser = navigator.language
    if (browser.startsWith('zh')) return 'zh-CN'
    if (browser.startsWith('en')) return 'en'
  } catch { /* navigator unavailable */ }
  return DEFAULT_LOCALE
}

// Initialize with best-guess locale immediately (localStorage > browser > zh-CN).
// The router guard will later override with server preference when auth loads.
export const i18n = createI18n({
  legacy: false,
  locale: detectLocalLocale(),
  fallbackLocale: 'zh-CN',
  messages: { 'zh-CN': zhCN, en },
})

/**
 * Resolve the effective locale.
 * Priority: server preference > localStorage > browser > default.
 * Call after auth is loaded to apply the server-stored user preference.
 */
export function resolveLocale(serverLocale?: string | null): SupportedLocale {
  if (serverLocale && (SUPPORTED_LOCALES as readonly string[]).includes(serverLocale)) {
    return serverLocale as SupportedLocale
  }
  return detectLocalLocale()
}

export function setLocale(locale: SupportedLocale) {
  i18n.global.locale.value = locale
  localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  document.documentElement.lang = locale
}

export function getLocale(): SupportedLocale {
  return i18n.global.locale.value as SupportedLocale
}
