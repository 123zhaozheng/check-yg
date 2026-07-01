import * as React from "react"

import type { FlowRecordItem } from "@/lib/api"

/**
 * 原始↔标准对照（双栏）——清洗页就地展开 + 流水号弹窗共用的对比块.
 *
 * 从 ``routes/.../clean.tsx`` 抽出，两处调用方零行为差异：
 * - 清洗页：行展开，不包滚动容器（自然撑高）。
 * - 弹窗：``scrollable`` 为 true 时两栏各自 ``max-h-[60vh] overflow-y-auto``，
 *   原始 20+ cells 滚、标准化字段固定，弹窗不撑成竖长条。
 *
 * 原始 cells from ``row.raw_payload.cells``；标准 from the row's fields.
 * Differences highlighted with bg-ink-200 (light gray), never a colored diff.
 */
export function RawVsStandardCompare({
  row,
  scrollable = false,
}: {
  row: FlowRecordItem
  scrollable?: boolean
}) {
  const rawCells = row.raw_payload?.cells ?? []
  const standardFields: { label: string; value: string }[] = [
    { label: "交易时间", value: row.transaction_time ?? "" },
    { label: "交易对手", value: row.counterparty_name ?? "" },
    { label: "对手账号", value: row.counterparty_account ?? "" },
    { label: "金额", value: row.amount ?? "" },
    { label: "余额", value: row.balance ?? "" },
    { label: "原始金额", value: row.raw_amount ?? "" },
    { label: "摘要", value: row.summary ?? "" },
    { label: "收支类型", value: row.transaction_type ?? "" },
  ]

  // 弹窗态：每栏套独立滚动容器；清洗页展开态直接渲染（不滚）。
  // 组件自身不带外层 padding——调用方控制（清洗页行展开 / 弹窗 DialogBody 各自管），
  // 这样两处 padding 互不影响，抽出后清洗页视觉零变化。
  const panelClass = scrollable ? "max-h-[60vh] overflow-y-auto scroll-thin" : ""

  return (
    <div className="flex gap-6 font-sans text-sm">
      {/* Original raw */}
      <div className={`flex-1 ${panelClass}`}>
        <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-ink-700">
          原始数据（来源：{row.channel || "未知渠道"}）
        </div>
        <div className="grid grid-cols-[120px_1fr] gap-x-4 gap-y-1.5 font-mono text-xs">
          {rawCells.map((cell, idx) => (
            <React.Fragment key={idx}>
              <div className="text-ink-700">单元格 {idx + 1}:</div>
              <div className="bg-ink-200 px-1.5 py-0.5 text-ink-900">
                {cell || "（空）"}
              </div>
            </React.Fragment>
          ))}
          {rawCells.length === 0 && (
            <div className="col-span-2 text-ink-700">无原始数据</div>
          )}
        </div>
      </div>
      {/* Standard */}
      <div className={`flex-1 border-l border-ink-400 pl-6 ${panelClass}`}>
        <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-ink-900">
          标准化（已应用 schema）
        </div>
        <div className="grid grid-cols-[120px_1fr] gap-x-4 gap-y-1.5 font-mono text-xs">
          {standardFields.map((f) => (
            <React.Fragment key={f.label}>
              <div className="text-ink-700">{f.label}:</div>
              <div className="border border-ink-400 bg-ink-100 px-1.5 py-0.5 font-bold text-ink-900">
                {f.value || "（空）"}
              </div>
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  )
}
