import * as React from "react"
import { cn } from "@/lib/utils"

/**
 * Monochrome toggle (docs §C6 导出 toggle / §D1 设置 boolean 项).
 *
 * 灰阶 toggle（单色原则，禁彩色）：
 * - 关：浅灰底 (bg-ink-300) + 灰圆 (bg-ink-100 border-ink-500).
 * - 开：黑底白圆 (bg-ink-900 + bg-ink-100).
 * 不使用彩色开关。focus 用深灰外框（无蓝色 ring）.
 */
const Toggle = React.forwardRef<
  HTMLButtonElement,
  {
    checked: boolean
    onCheckedChange: (checked: boolean) => void
    disabled?: boolean
    "aria-label"?: string
    className?: string
  }
>(function Toggle(
  { checked, onCheckedChange, disabled, className, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-[var(--radius-full)] transition-colors focus-visible:outline-2 focus-visible:outline-ink-800 focus-visible:outline-offset-2 disabled:opacity-50",
        checked ? "bg-ink-900" : "bg-ink-300",
        className,
      )}
      {...rest}
    >
      <span
        className={cn(
          "inline-block size-3.5 rounded-[var(--radius-full)] transition-transform",
          checked
            ? "translate-x-[18px] bg-ink-100"
            : "translate-x-[3px] border border-ink-500 bg-ink-100",
        )}
      />
    </button>
  )
})

export { Toggle }
