import { useEffect } from "react"

export function useDrawerRuntime(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose()
      }
    }

    const prev = document.body.style.overflow
    document.body.style.overflow = "hidden"

    window.addEventListener("keydown", onKeyDown)

    return () => {
      window.removeEventListener("keydown", onKeyDown)
      document.body.style.overflow = prev
    }
  }, [open, onClose])
}
