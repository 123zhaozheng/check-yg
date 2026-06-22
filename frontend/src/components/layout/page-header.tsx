import * as React from "react"
import { cn } from "@/lib/utils"

/** Page header: H1 title + optional description + right-aligned actions. */
function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string
  description?: string
  actions?: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-2 pb-6 md:flex-row md:items-end md:justify-between",
        className,
      )}
    >
      <div className="min-w-0">
        <h1 className="font-sans text-2xl font-bold leading-tight tracking-tight text-ink-900">
          {title}
        </h1>
        {description && (
          <p className="mt-1 text-sm text-ink-700">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

export { PageHeader }
