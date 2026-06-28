import { useEffect, useRef, useState } from "react"

export function ResponsiveChartContainer({
  children,
  height = 300,
}: {
  children: React.ReactNode
  height?: number | string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)

  useEffect(() => {
    if (!ref.current) return

    const el = ref.current

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setWidth(entry.contentRect.width)
      }
    })

    observer.observe(el)

    return () => observer.disconnect()
  }, [])

  return (
    <div ref={ref} className="w-full overflow-x-auto">
      <div style={{ width, height }}>
        {children}
      </div>
    </div>
  )
}
