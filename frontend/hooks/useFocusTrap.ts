import { useEffect } from "react"

export function useFocusTrap(containerRef: React.RefObject<HTMLElement | null>, active: boolean) {
  useEffect(() => {
    if (!active) return
    const container = containerRef.current
    if (!container) return

    const focusableSelectors = [
      "a",
      "button",
      "input",
      "textarea",
      "select",
      "[tabindex]:not([tabindex='-1'])",
    ]

    const getFocusable = () =>
      Array.from(container.querySelectorAll<HTMLElement>(focusableSelectors.join(",")))

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return

      const focusables = getFocusable()
      if (focusables.length === 0) return

      const first = focusables[0]
      const last = focusables[focusables.length - 1]

      if (e.shiftKey) {
        if (document.activeElement === first) {
          last.focus()
          e.preventDefault()
        }
      } else {
        if (document.activeElement === last) {
          first.focus()
          e.preventDefault()
        }
      }
    }

    container.addEventListener("keydown", handleKeyDown)

    return () => {
      container.removeEventListener("keydown", handleKeyDown)
    }
  }, [active, containerRef])
}
