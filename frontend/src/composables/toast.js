import { reactive } from 'vue'

export const toasts = reactive([])
let nextId = 1

export function useToast() {
  function push(message, type = 'success') {
    const id = nextId++
    toasts.push({ id, message, type })
    setTimeout(() => {
      const index = toasts.findIndex((item) => item.id === id)
      if (index !== -1) toasts.splice(index, 1)
    }, 3200)
  }
  return { success: (message) => push(message), error: (message) => push(message, 'error') }
}

