import * as React from "react"
import { cn } from "@/lib/utils"

/**
 * Empty state (docs §D2).
 *
 * 居中线框盾形/文件夹（1px 灰线 SVG stroke currentColor text-ink-500，不加填充）
 * + 一行标题 + 一行辅文灰说明 + 一个主 CTA 按钮. 单色原则：线框仅 1px 灰线，
 * 保持克制；任务列表空时复用.
 */
function EmptyState({
  title,
  description,
  action,
  icon = "shield",
  className,
}: {
  title: string
  description?: string
  action?: React.ReactNode
  icon?: "shield" | "folder"
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-4 px-6 py-16 text-center",
        className,
      )}
    >
      <div className="text-ink-500">
        {icon === "shield" ? <ShieldIcon /> : <FolderIcon />}
      </div>
      <div className="flex flex-col items-center gap-1.5">
        <h3 className="font-sans text-lg font-bold text-ink-900">{title}</h3>
        {description && (
          <p className="max-w-sm text-sm text-ink-600">{description}</p>
        )}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

/** 1px 灰线盾形 SVG（不加填充，单色原则）. */
function ShieldIcon() {
  return (
    <svg
      width="56"
      height="56"
      viewBox="0 0 56 56"
      fill="none"
      stroke="currentColor"
      strokeWidth="1"
      aria-hidden
    >
      <path d="M28 6 L48 14 V28 C48 39 39 47 28 50 C17 47 8 39 8 28 V14 Z" />
      <path d="M19 28 L26 35 L38 22" />
    </svg>
  )
}

/** 1px 灰线文件夹 SVG（不加填充，单色原则）. */
function FolderIcon() {
  return (
    <svg
      width="56"
      height="56"
      viewBox="0 0 56 56"
      fill="none"
      stroke="currentColor"
      strokeWidth="1"
      aria-hidden
    >
      <path d="M8 16 H22 L26 20 H48 V44 H8 Z" />
      <path d="M8 24 H48" />
    </svg>
  )
}

export { EmptyState }
