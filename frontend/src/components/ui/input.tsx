import * as React from "react"
import { cn } from "@/lib/utils"

/**
 * Fine-border-bottom form field (DESIGN.md Components → Form Fields):
 * 1px #bfbfbf bottom border, thickens to 2px #000 on focus.
 * Placeholders in #8c8c8c. No full box border.
 */
const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  function Input({ className, ...props }, ref) {
    return (
      <input
        ref={ref}
        data-slot="input"
        className={cn(
          "field-fine-border w-full bg-transparent px-0 py-2 font-mono text-sm text-ink-900 placeholder:text-ink-600",
          className,
        )}
        {...props}
      />
    )
  },
)

export { Input }
