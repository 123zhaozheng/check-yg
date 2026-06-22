import * as React from "react"
import { Card, CardContent } from "@/components/ui/card"

/**
 * Placeholder for a task-detail tab. Shows the tab title + one-line note so
 * routes are walkable during infra verification. Per-slice tasks replace this
 * with the real workflow UI.
 */
function TabPlaceholder({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children?: React.ReactNode
}) {
  return (
    <Card>
      <CardContent className="p-6">
        <h2 className="font-sans text-lg font-semibold text-ink-900">
          {title}
        </h2>
        <p className="mt-1 text-sm text-ink-700">{description}</p>
        {children && <div className="mt-4">{children}</div>}
      </CardContent>
    </Card>
  )
}

export { TabPlaceholder }
