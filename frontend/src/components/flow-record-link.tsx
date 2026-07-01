import * as React from "react"

import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { RawVsStandardCompare } from "@/components/flow-record-compare"
import { cn } from "@/lib/utils"
import { useFlowRecord } from "@/hooks/use-records"

/**
 * 可点击流水号 ``#521`` ——点击弹出 Dialog，左原始 cells / 右标准化字段（复用
 * ``RawVsStandardCompare``），让用户认清这是哪条流水（prd §二.3 / §二.4）.
 *
 * 触发器视觉按 ``variant`` 各自保留现有上下文样式（决策 6）：
 * - ``plain``（默认，关键词审查用）：纯文字（决策 6 保留现状）+ hover 加深 bg + 下划线（仅 hover）.
 * - ``chip``（AI 分析关联记录用）：保留现有 chip 样式 + hover 加深.
 * 单色硬底线：hover 反馈只用灰阶（bg-ink-300），cursor-pointer，禁彩色.
 *
 * 弹窗纯查看（无采纳/忽略，决策 5）；``max-w-3xl`` + 双栏各自 ``max-h-[60vh]`` 滚
 * 动（决策 4）；recordId 不存在显示「该流水记录不存在或已删除」.
 */
export function FlowRecordLink({
  taskId,
  recordId,
  variant = "plain",
}: {
  taskId: number
  recordId: number
  variant?: "plain" | "chip"
}) {
  const [open, setOpen] = React.useState(false)
  // recordId 非空恒真，传 null 仅是为了 hook 的 enabled 类型契约——这里 recordId 必到.
  const query = useFlowRecord(taskId, open ? recordId : null)

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="查看流水原始↔标准对照"
        className={cn(
          "cursor-pointer font-mono text-xs transition-colors",
          variant === "plain"
            ? "text-ink-700 hover:bg-ink-300 hover:text-ink-900 hover:underline hover:decoration-ink-400 hover:underline-offset-2"
            : "rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-200 px-2 py-0.5 text-ink-900 hover:bg-ink-300",
        )}
      >
        #{recordId}
      </button>
      <Dialog open={open} onOpenChange={setOpen} className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>流水详情 #{recordId}</DialogTitle>
          <DialogClose onOpenChange={setOpen} />
        </DialogHeader>
        <DialogBody>
          {query.isLoading && (
            <div className="py-10 text-center text-sm text-ink-700">加载中…</div>
          )}
          {query.isError && (
            <div className="py-10 text-center text-sm text-ink-700">
              该流水记录不存在或已删除
            </div>
          )}
          {query.data && (
            <RawVsStandardCompare row={query.data} scrollable />
          )}
        </DialogBody>
      </Dialog>
    </>
  )
}
