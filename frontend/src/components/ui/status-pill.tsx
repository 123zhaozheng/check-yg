import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

/**
 * Status capsule (DESIGN.md Components → Status Capsules).
 * Grayscale pill — the ONLY shape allowed to use full pill radius.
 * Progression by luminance, never by hue.
 *
 *   pending      — #f0f0f0 bg, #595959 text   (待解析 / 待开始)
 *   in-progress  — #bfbfbf bg, #ffffff text   (解析中 / 进行中)
 *   done         — #1f1f1f bg, #ffffff text   (完成 / 深灰实心)
 *   reported     — #000000 bg, #ffffff text   (报告/定稿, 最强)
 *   failed       — #000000 bg, #ffffff text, bold + 2px black border (失败/高风险)
 */
const statusPillVariants = cva(
  "inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-full)] px-3 py-0.5 font-sans text-xs font-medium whitespace-nowrap leading-5",
  {
    variants: {
      tone: {
        pending: "bg-ink-300 text-ink-700",
        "in-progress": "bg-ink-500 text-ink-100",
        done: "bg-ink-800 text-ink-100",
        reported: "bg-ink-900 text-ink-100",
        failed:
          "bg-ink-900 text-ink-100 font-bold border-2 border-ink-900 px-2.5",
      },
    },
    defaultVariants: {
      tone: "pending",
    },
  },
)

export interface StatusPillProps
  extends React.ComponentProps<"span">,
    VariantProps<typeof statusPillVariants> {}

function StatusPill({ className, tone, children, ...props }: StatusPillProps) {
  return (
    <span
      data-slot="status-pill"
      data-tone={tone}
      className={cn(statusPillVariants({ tone }), className)}
      {...props}
    >
      {children}
    </span>
  )
}

export { StatusPill, statusPillVariants }
