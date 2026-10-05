import type { AdminMe } from '../types'

export class ApiError extends Error {
  status: number
  payload: any

  constructor(status: number, payload: any, message?: string) {
    super(message ?? payload?.detail?.message ?? payload?.message ?? `HTTP ${status}`)
    this.status = status
    this.payload = payload
  }
}

let unauthorizedHandler: (() => void) | null = null
let unauthorizedRedirectPending = false

export function setUnauthorizedHandler(handler: () => void) {
  unauthorizedHandler = handler
}

function getCookie(name: string): string {
  const prefix = `${name}=`
  return document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length) ?? ''
}

function buildHeaders(init?: HeadersInit, method = 'GET'): Headers {
  const headers = new Headers(init)
  const upper = method.toUpperCase()
  if (![ 'GET', 'HEAD', 'OPTIONS' ].includes(upper)) {
    const csrf = getCookie('admin_csrf')
    if (csrf) {
      headers.set('X-CSRF-Token', csrf)
    }
  }
  return headers
}

export async function apiFetch<T>(input: string, init: RequestInit = {}): Promise<T> {
  const method = init.method ?? 'GET'
  const response = await fetch(input, {
    credentials: 'same-origin',
    ...init,
    headers: buildHeaders(init.headers, method),
  })

  const contentType = response.headers.get('content-type') ?? ''
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()

  const isLoginRequest = new URL(input, window.location.origin).pathname === '/api/admin/login'
  if (response.status === 401 && !isLoginRequest && !unauthorizedRedirectPending) {
    unauthorizedRedirectPending = true
    unauthorizedHandler?.()
  } else if (isLoginRequest && response.ok) {
    unauthorizedRedirectPending = false
  }

  if (!response.ok) {
    throw new ApiError(response.status, payload)
  }

  return payload as T
}

export async function fetchCurrentAdmin(): Promise<AdminMe> {
  return apiFetch<AdminMe>('/api/admin/me')
}
