import * as React from "react"
import { createFileRoute, useParams } from "@tanstack/react-router"
import { Download, Eye } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Toggle } from "@/components/ui/toggle"
import { cn } from "@/lib/utils"
import {
  type DataExportFormat,
  type ExportListItem,
  type ExportScope,
  type ReportExportFormat,
} from "@/lib/api"
import {
  triggerExportDownload,
  useExportData,
  useExportHistory,
  useExportPreview,
  useExportReport,
} from "@/hooks/use-exports"

/**
 * 导出 /tasks/:id/export (docs §C6).
 *
 * Monochrome 导出页（单色原则）:
 * - 报告导出卡: 格式 segmented (PDF/Word/HTML 灰阶) + 含批注 toggle (灰阶:
 *   关浅灰 / 开黑底白圆) + 导出主按钮 → POST export/report.
 * - 数据导出卡: 范围 segmented (原始/标准化/异常) + 格式 segmented (Excel/CSV)
 *   + 导出主按钮 → POST export/data.
 * - 预览: 每组「预览」描边按钮 → GET export/preview，单色渲染报告前几章 /
 *   数据前几行（卡片展开）.
 * - 导出历史列表: 表格 (格式/范围/时间/重新下载描边按钮) → GET exports.
 *   不删减精神: 历史产物文件保留可重新下载.
 *
 * toggle 灰阶组件 (components/ui/toggle.tsx): 关 bg-ink-300 / 开 bg-ink-900.
 */
export const Route = createFileRoute("/__authenticated/tasks/$id/export")({
  component: ExportPage,
})

const REPORT_FORMATS: { key: ReportExportFormat; label: string }[] = [
  { key: "pdf", label: "PDF" },
  { key: "docx", label: "Word" },
  { key: "html", label: "HTML" },
]

const DATA_SCOPES: { key: "raw" | "standard" | "findings"; label: string }[] = [
  { key: "raw", label: "原始数据" },
  { key: "standard", label: "标准化数据" },
  { key: "findings", label: "异常记录" },
]

const DATA_FORMATS: { key: DataExportFormat; label: string }[] = [
  { key: "excel", label: "Excel" },
  { key: "csv", label: "CSV" },
]

function ExportPage() {
  const { id } = useParams({ from: "/__authenticated/tasks/$id/export" })
  const taskId = Number(id)

  const historyQuery = useExportHistory(taskId)
  const exportReport = useExportReport(taskId)
  const exportData = useExportData(taskId)

  const [reportFormat, setReportFormat] = React.useState<ReportExportFormat>("pdf")
  const [includeAnnotations, setIncludeAnnotations] = React.useState(false)
  const [dataScope, setDataScope] = React.useState<"raw" | "standard" | "findings">("standard")
  const [dataFormat, setDataFormat] = React.useState<DataExportFormat>("excel")

  const history = historyQuery.data ?? []

  function handleExportReport() {
    exportReport.mutate({
      format: reportFormat,
      include_annotations: includeAnnotations,
    })
  }

  function handleExportData() {
    exportData.mutate({ scope: dataScope, format: dataFormat })
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="p-4">
          <h2 className="font-sans text-lg font-bold text-ink-900">导出</h2>
          <p className="mt-1 text-sm text-ink-700">
            将报告与原始/标准化数据导出为多种格式，供归档与线下流转。
          </p>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 报告导出 */}
        <Card>
          <CardContent className="flex flex-col gap-4 p-6">
            <div>
              <h3 className="font-sans text-base font-bold text-ink-900">报告导出</h3>
              <p className="mt-1 text-xs text-ink-600">
                基于当前章节化审查报告生成 PDF / Word / HTML。
              </p>
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                格式
              </label>
              <SegmentedControl
                options={REPORT_FORMATS}
                value={reportFormat}
                onChange={setReportFormat}
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-ink-900">含批注附录</p>
                <p className="text-xs text-ink-600">将复核批注作为附录一并导出</p>
              </div>
              <Toggle
                checked={includeAnnotations}
                onCheckedChange={setIncludeAnnotations}
                aria-label="含批注附录"
              />
            </div>

            <div className="flex items-center gap-2">
              <PreviewButton taskId={taskId} scope="report" />
              <Button
                onClick={handleExportReport}
                disabled={exportReport.isPending}
              >
                <Download className="size-4" />
                {exportReport.isPending ? "导出中…" : "导出报告"}
              </Button>
              {exportReport.isError && (
                <span className="font-mono text-xs text-ink-700">
                  导出失败（请先生成报告）
                </span>
              )}
            </div>
          </CardContent>
        </Card>

        {/* 数据导出 */}
        <Card>
          <CardContent className="flex flex-col gap-4 p-6">
            <div>
              <h3 className="font-sans text-base font-bold text-ink-900">数据导出</h3>
              <p className="mt-1 text-xs text-ink-600">
                导出原始/标准化流水或异常记录为 Excel / CSV。
              </p>
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                范围
              </label>
              <SegmentedControl
                options={DATA_SCOPES}
                value={dataScope}
                onChange={setDataScope}
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                格式
              </label>
              <SegmentedControl
                options={DATA_FORMATS}
                value={dataFormat}
                onChange={setDataFormat}
              />
            </div>

            <div className="flex items-center gap-2">
              <PreviewButton taskId={taskId} scope={dataScope} />
              <Button
                onClick={handleExportData}
                disabled={exportData.isPending}
              >
                <Download className="size-4" />
                {exportData.isPending ? "导出中…" : "导出数据"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 导出历史 */}
      <Card>
        <CardContent className="p-0">
          <div className="border-b border-ink-400 px-6 py-4">
            <h3 className="font-sans text-base font-bold text-ink-900">导出历史</h3>
            <p className="mt-1 text-xs text-ink-600">
              历史产物文件保留，可随时重新下载。
            </p>
          </div>
          <table className="w-full border-collapse text-left">
            <thead className="border-b border-ink-400 bg-ink-200 text-xs font-bold uppercase tracking-wider text-ink-700">
              <tr>
                <th className="px-4 py-3 font-bold">格式</th>
                <th className="px-4 py-3 font-bold">范围</th>
                <th className="px-4 py-3 font-bold">生成时间</th>
                <th className="px-4 py-3 text-right font-bold">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-400 text-sm text-ink-900">
              {historyQuery.isLoading && (
                <tr>
                  <td colSpan={4} className="px-4 py-10 text-center text-ink-600">
                    加载中…
                  </td>
                </tr>
              )}
              {!historyQuery.isLoading && history.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-10 text-center text-ink-600">
                    暂无导出记录。
                  </td>
                </tr>
              )}
              {history.map((item) => (
                <ExportHistoryRow key={item.id} item={item} />
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  )
}

/** 灰阶 segmented 单选（选中黑底白字，未选中描边）. */
function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { key: T; label: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div className="inline-flex rounded-[var(--radius-DEFAULT)] border border-ink-400 p-0.5">
      {options.map((opt) => (
        <button
          key={opt.key}
          type="button"
          onClick={() => onChange(opt.key)}
          className={cn(
            "px-3 py-1.5 font-sans text-xs font-medium transition-colors",
            value === opt.key
              ? "bg-ink-900 text-ink-100"
              : "text-ink-700 hover:bg-ink-300",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

/** 预览按钮 + 展开式预览卡片（单色渲染）. */
function PreviewButton({
  taskId,
  scope,
}: {
  taskId: number
  scope: ExportScope
}) {
  const [open, setOpen] = React.useState(false)
  const previewQuery = useExportPreview(taskId, scope)

  return (
    <>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setOpen((v) => !v)}
        disabled={open}
      >
        <Eye className="size-4" />
        预览
      </Button>
      {open && (
        <PreviewModal
          scope={scope}
          sample={previewQuery.data?.sample}
          annotationCount={previewQuery.data?.annotation_count ?? null}
          isLoading={previewQuery.isLoading}
          isError={previewQuery.isError}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}

/** 预览弹层（单色渲染报告前几章 / 数据前几行）. */
function PreviewModal({
  scope,
  sample,
  annotationCount,
  isLoading,
  isError,
  onClose,
}: {
  scope: ExportScope
  sample: unknown
  annotationCount: number | null
  isLoading: boolean
  isError: boolean
  onClose: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-6"
      onClick={onClose}
    >
      <div
        className="card-surface max-h-[80vh] w-full max-w-2xl overflow-y-auto scroll-thin"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-ink-400 px-6 py-4">
          <div>
            <h3 className="font-sans text-base font-bold text-ink-900">
              导出预览 · {scopeLabel(scope)}
            </h3>
            <p className="mt-0.5 font-mono text-xs text-ink-600">
              {scope === "report"
                ? `前 2 章 + 批注 ${annotationCount ?? 0} 条`
                : "前 20 行取样"}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            关闭
          </Button>
        </div>
        <div className="px-6 py-4">
          {isLoading && (
            <p className="py-8 text-center text-sm text-ink-600">加载中…</p>
          )}
          {isError && (
            <p className="py-8 text-center text-sm text-ink-600">
              预览加载失败（报告请先生成）。
            </p>
          )}
          {!isLoading && !isError && scope === "report" && (
            <ReportSampleRender sample={sample} />
          )}
          {!isLoading && !isError && scope !== "report" && (
            <DataSampleRender sample={sample} />
          )}
        </div>
      </div>
    </div>
  )
}

/** 报告预览：前 2 章 content 文本（单色年报排版）. */
function ReportSampleRender({ sample }: { sample: unknown }) {
  const chapters = (sample as { title: string; content: string }[] | undefined) ?? []
  if (chapters.length === 0) {
    return <p className="py-8 text-center text-sm text-ink-600">暂无章节数据。</p>
  }
  return (
    <div className="flex flex-col gap-6">
      {chapters.map((c, i) => (
        <div key={i} className="border-b border-ink-300 pb-4 last:border-b-0">
          <h4 className="mb-2 font-sans text-base font-bold text-ink-900">
            {c.title}
          </h4>
          <pre className="whitespace-pre-wrap font-sans text-sm leading-6 text-ink-800">
            {c.content}
          </pre>
        </div>
      ))}
    </div>
  )
}

/** 数据预览：前 20 行 JSON（等宽字体，单色表格）. */
function DataSampleRender({ sample }: { sample: unknown }) {
  const rows = (sample as Record<string, unknown>[] | undefined) ?? []
  if (rows.length === 0) {
    return <p className="py-8 text-center text-sm text-ink-600">暂无数据。</p>
  }
  const headers = Object.keys(rows[0])
  return (
    <div className="overflow-x-auto scroll-thin">
      <table className="w-full border-collapse text-left font-mono text-xs">
        <thead className="border-b border-ink-400 text-ink-700">
          <tr>
            {headers.map((h) => (
              <th key={h} className="px-3 py-2 font-bold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-300 text-ink-900">
          {rows.map((row, i) => (
            <tr key={i}>
              {headers.map((h) => (
                <td key={h} className="px-3 py-2">
                  {formatCell(row[h])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** 导出历史行：格式 / 范围 / 时间 / 重新下载. */
function ExportHistoryRow({ item }: { item: ExportListItem }) {
  const [downloading, setDownloading] = React.useState(false)

  async function handleDownload() {
    setDownloading(true)
    try {
      await triggerExportDownload(item.id)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <tr className="transition-colors hover:bg-ink-300">
      <td className="px-4 py-3 font-medium text-ink-900">
        {formatLabel(item.format)}
      </td>
      <td className="px-4 py-3 text-xs text-ink-700">
        {item.scope ? scopeLabel(item.scope) : "—"}
      </td>
      <td className="px-4 py-3 font-mono text-xs text-ink-700">
        {formatDate(item.created_at)}
      </td>
      <td className="px-4 py-3 text-right">
        <Button
          variant="secondary"
          size="sm"
          onClick={handleDownload}
          disabled={downloading}
        >
          {downloading ? "下载中…" : "重新下载"}
        </Button>
      </td>
    </tr>
  )
}

/** Map scope → 中文 label. */
function scopeLabel(scope: ExportScope): string {
  switch (scope) {
    case "report":
      return "报告"
    case "raw":
      return "原始数据"
    case "standard":
      return "标准化数据"
    case "findings":
      return "异常记录"
    default:
      return scope
  }
}

/** Map format → 中文 label. */
function formatLabel(fmt: string): string {
  switch (fmt) {
    case "pdf":
      return "PDF"
    case "docx":
      return "Word"
    case "html":
      return "HTML"
    case "excel":
      return "Excel"
    case "csv":
      return "CSV"
    case "bundle":
      return "ZIP 包"
    default:
      return fmt
  }
}

/** Format a cell value for the preview table. */
function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

/** Format an ISO datetime as "YYYY-MM-DD HH:mm". */
function formatDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
