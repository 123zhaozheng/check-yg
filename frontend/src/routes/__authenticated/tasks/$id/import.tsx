import * as React from "react"
import { createFileRoute, useParams } from "@tanstack/react-router"
import {
  Eye,
  File,
  FileSpreadsheet,
  FileText,
  Play,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { DocumentItem, DocumentStatus } from "@/lib/api"
import {
  useDeleteDocument,
  useDocumentList,
  useUploadTaskDocuments,
} from "@/hooks/use-documents"
import { useStartExtraction, useTask } from "@/hooks/use-tasks"

/**
 * 数据导入 /tasks/:id/import (docs §C2).
 *
 * Left channel list (银行流水/支付渠道/证券交易/票据凭证/其他) with a black
 * active bar + per-channel file count badge. Right upload area: channel
 * title + 开始处理 primary button + large dashed dropzone + 选择文件 outline
 * button. Below: file table (文件名 / 类型 / 大小 / 解析状态胶囊 / 上传时间 /
 * 操作). TanStack Query polls the documents list every 2s while any doc is
 * pending/processing and stops once all are settled.
 *
 * Channel keys are the Chinese labels themselves, persisted verbatim as the
 * backend `channel` string (mirrors Task.expected_channels semantics).
 */
export const Route = createFileRoute("/__authenticated/tasks/$id/import")({
  component: ImportPage,
})

/** Channel key = Chinese label (stored verbatim as backend `channel`). */
const CHANNELS = [
  "银行流水",
  "支付渠道",
  "证券交易",
  "票据凭证",
  "其他",
] as const

/** File extensions the backend scanner actually accepts (no .csv — scanner
 *  does not support it). Frontend validation + dropzone copy align to this. */
const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".xls"]
const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(",")
const MAX_FILE_BYTES = 50 * 1024 * 1024 // 50 MB

function ImportPage() {
  const { id } = useParams({ from: "/__authenticated/tasks/$id/import" })
  const taskId = Number(id)

  const [selectedChannel, setSelectedChannel] = React.useState<string>(
    CHANNELS[0],
  )

  // Pull ALL documents (no channel filter) so per-channel badges can be
  // derived client-side via group-by — simpler than one query per channel.
  const allDocsQuery = useDocumentList(taskId, {})
  const allDocs = allDocsQuery.data?.items ?? []

  // Task detail — read status so the 开始处理 button is disabled while running.
  const taskQuery = useTask(taskId)
  const taskStatus = taskQuery.data?.status ?? "draft"

  // Filtered view for the currently selected channel.
  const channelQuery = useDocumentList(taskId, { channel: selectedChannel })
  const channelDocs = channelQuery.data?.items ?? []

  // Per-channel counts (exclude soft-deleted — backend default already hides
  // status=deleted, so items here are live documents only).
  const countsByChannel = React.useMemo(() => {
    const counts: Record<string, number> = {}
    for (const ch of CHANNELS) counts[ch] = 0
    for (const d of allDocs) {
      if (d.status === "deleted") continue
      const key = d.channel ?? "其他"
      counts[key] = (counts[key] ?? 0) + 1
    }
    return counts
  }, [allDocs])

  // 开始处理 is enabled only when there is at least one pending document and
  // the task is not already running. Running tasks auto-pick up new uploads via
  // the runner's batch loop, so the button is hidden then.
  const hasPending = allDocs.some((d) => d.status === "pending")
  const isRunning = taskStatus === "running"

  const upload = useUploadTaskDocuments(taskId)
  const deleteDoc = useDeleteDocument(taskId)
  const startExtraction = useStartExtraction(taskId)

  // Cache the original File objects by filename+size so a failed row's Retry
  // can re-upload the same file without a file picker round-trip.
  const fileCacheRef = React.useRef<Map<string, File>>(new Map())
  const rememberFiles = React.useCallback((files: File[]) => {
    for (const f of files) {
      fileCacheRef.current.set(cacheKey(f.name, f.size), f)
    }
  }, [])
  const lookupCachedFile = React.useCallback((filename: string, size: number) => {
    return fileCacheRef.current.get(cacheKey(filename, size))
  }, [])

  function handleUpload(files: File[]) {
    const valid = filterAccepted(files)
    if (valid.length === 0) return
    rememberFiles(valid)
    upload.mutate({ files: valid, channel: selectedChannel })
  }

  function handleRetry(doc: DocumentItem) {
    const size = doc.size_bytes ?? 0
    const cached = lookupCachedFile(doc.filename, size)
    if (!cached) {
      // No cached File (e.g. page reloaded) — fall back to the picker.
      hiddenInputRef.current?.click()
      return
    }
    upload.mutate({ files: [cached], channel: doc.channel ?? selectedChannel })
  }

  function handleDelete(docId: number) {
    deleteDoc.mutate(docId)
  }

  // Hidden <input type=file multiple> driven by both the dropzone click and
  // the 选择文件 button.
  const hiddenInputRef = React.useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = React.useState(false)

  function openPicker() {
    hiddenInputRef.current?.click()
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    handleUpload(files)
    // Reset so picking the same file twice still fires change.
    e.target.value = ""
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragging(false)
    const files = Array.from(e.dataTransfer.files)
    handleUpload(files)
  }

  function onDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    if (!isDragging) setIsDragging(true)
  }

  function onDragLeave(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragging(false)
  }

  const channelLabel = CHANNELS.find((c) => c === selectedChannel) ?? selectedChannel

  return (
    <div className="flex h-[calc(100vh-220px)] min-h-[420px] gap-4">
      {/* Left: channel list */}
      <aside className="flex w-64 flex-shrink-0 flex-col rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100">
        <div className="border-b border-ink-400 p-4">
          <h3 className="font-sans text-base font-semibold text-ink-900">
            数据渠道
          </h3>
        </div>
        <div className="scroll-thin flex-1 space-y-1 overflow-y-auto p-2">
          {CHANNELS.map((ch) => {
            const active = ch === selectedChannel
            const count = countsByChannel[ch] ?? 0
            return (
              <button
                key={ch}
                onClick={() => setSelectedChannel(ch)}
                className={cn(
                  "flex w-full items-center justify-between rounded-[var(--radius-DEFAULT)] px-3 py-2.5 text-left transition-colors",
                  active
                    ? "border-l-2 border-ink-900 bg-ink-300"
                    : "border-l-2 border-transparent hover:bg-ink-300",
                )}
              >
                <span
                  className={cn(
                    "font-sans text-sm",
                    active ? "font-medium text-ink-900" : "text-ink-700",
                  )}
                >
                  {ch}
                </span>
                <span
                  className={cn(
                    "rounded-[var(--radius-DEFAULT)] px-1.5 py-0.5 font-mono text-[11px]",
                    active
                      ? "bg-ink-400 text-ink-900"
                      : "border border-ink-400 bg-ink-200 text-ink-700",
                  )}
                >
                  {count}
                </span>
              </button>
            )
          })}
        </div>
      </aside>

      {/* Right: upload area + file table */}
      <section className="flex min-w-0 flex-1 flex-col rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100 p-6">
        {/* Header: channel title + 上传文件 + 开始处理 */}
        <div className="mb-5 flex items-center justify-between">
          <h3 className="font-sans text-lg font-semibold text-ink-900">
            {channelLabel} 上传
          </h3>
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={openPicker}>
              <Upload className="size-4" />
              上传文件
            </Button>
            {isRunning ? (
              <Button size="sm" disabled>
                <RefreshCw className="size-4 animate-spin" />
                处理中
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={() => startExtraction.mutate()}
                disabled={!hasPending || startExtraction.isPending}
              >
                <Play className="size-4" />
                开始处理
              </Button>
            )}
          </div>
        </div>

        {/* Dropzone */}
        <div
          role="button"
          tabIndex={0}
          onClick={openPicker}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              openPicker()
            }
          }}
          onDrop={onDrop}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          className={cn(
            "mb-6 flex cursor-pointer flex-col items-center justify-center border-2 border-dashed p-8 text-center transition-colors",
            isDragging
              ? "border-ink-900 bg-ink-300"
              : "border-ink-500 bg-ink-100 hover:border-ink-900 hover:bg-ink-200",
          )}
        >
          <Upload className="mb-3 size-8 text-ink-600" />
          <p className="font-sans text-base font-semibold text-ink-900">
            拖拽文件到此处
          </p>
          <p className="mt-1 text-sm text-ink-600">
            支持 PDF / Excel / Word，单文件最大 50MB
          </p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-4"
            onClick={(e) => {
              e.stopPropagation()
              openPicker()
            }}
          >
            选择文件
          </Button>
          <input
            ref={hiddenInputRef}
            type="file"
            multiple
            accept={ACCEPT_ATTR}
            className="hidden"
            onChange={onInputChange}
          />
        </div>

        {upload.isError && (
          <p className="mb-3 text-sm text-ink-900">
            上传失败：{(upload.error as Error)?.message ?? "请重试"}
          </p>
        )}
        {startExtraction.isError && (
          <p className="mb-3 text-sm text-ink-900">
            开始处理失败：{(startExtraction.error as Error)?.message ?? "请重试"}
          </p>
        )}

        {/* File table */}
        <div className="flex min-h-0 flex-1 flex-col rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100">
          {/* Header row */}
          <div className="grid grid-cols-[minmax(200px,2fr)_90px_90px_140px_120px_90px] items-center gap-3 border-b border-ink-400 bg-ink-200 p-3 text-xs font-bold uppercase tracking-wider text-ink-700">
            <div>文件名</div>
            <div>类型</div>
            <div className="text-right">大小</div>
            <div>解析状态</div>
            <div>上传时间</div>
            <div className="text-right">操作</div>
          </div>

          {/* Body */}
          <div className="scroll-thin flex-1 overflow-y-auto">
            {channelDocs.length === 0 && (
              <div className="px-4 py-10 text-center text-sm text-ink-600">
                暂无文件，拖拽或点击上传。
              </div>
            )}
            {channelDocs.map((doc) => (
              <FileRow
                key={doc.id}
                doc={doc}
                onRetry={() => handleRetry(doc)}
                onDelete={() => handleDelete(doc.id)}
              />
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}

/** One file row. Status capsule maps to a grayscale tone; Failed is the only
 *  "heavy" state — black bg + white bold uppercase + Retry.
 *
 *  The filename is wrapped in a `group relative` container so hovering it
 *  reveals an absolutely-positioned portrait card (纯 CSS group-hover, no
 *  radix/portal — Chrome 96/108 safe). Card shows the stage-1 portrait's core
 *  fields; when portrait is null (not yet generated / LLM failed) it shows a
 *  「画像待生成」 placeholder. */
function FileRow({
  doc,
  onRetry,
  onDelete,
}: {
  doc: DocumentItem
  onRetry: () => void
  onDelete: () => void
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-[minmax(200px,2fr)_90px_90px_140px_120px_90px] items-center gap-3 border-b border-ink-400 p-3 transition-colors hover:bg-ink-300",
        doc.status === "failed" && "bg-ink-300",
        doc.status === "pending" && "opacity-70",
      )}
    >
      {/* Filename + type icon + hover portrait card */}
      <div className="group relative flex min-w-0 items-center gap-2">
        <FileTypeIcon filename={doc.filename} className="size-4 flex-shrink-0 text-ink-600" />
        <span
          className={cn(
            "truncate font-sans text-sm text-ink-900",
            doc.status === "failed" && "font-semibold",
          )}
          title={doc.filename}
        >
          {doc.filename}
        </span>
        <PortraitCard portrait={doc.portrait ?? null} />
      </div>

      {/* Type */}
      <div className="font-mono text-xs text-ink-700">
        {typeLabel(doc.filename)}
      </div>

      {/* Size */}
      <div className="text-right font-mono text-xs text-ink-700">
        {formatBytes(doc.size_bytes ?? null)}
      </div>

      {/* Status capsule */}
      <div>
        <StatusCapsule status={doc.status} />
      </div>

      {/* Uploaded time */}
      <div className="font-mono text-xs text-ink-700">
        {formatDate(doc.created_at)}
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-2">
        {doc.status === "failed" ? (
          <Button variant="tertiary" size="sm" onClick={onRetry}>
            <RefreshCw className="size-3.5" />
            重试
          </Button>
        ) : (
          <>
            {/* View — noop in this slice (PRD: 跳详情/预览 留给后续切片). */}
            <button
              type="button"
              disabled
              className="text-ink-600 transition-colors hover:text-ink-900 disabled:opacity-50"
              aria-label="查看"
              title="查看（暂未开放）"
            >
              <Eye className="size-4" />
            </button>
            <button
              onClick={onDelete}
              className="text-ink-600 transition-colors hover:text-ink-900"
              aria-label="删除"
              title="删除"
            >
              <Trash2 className="size-4" />
            </button>
          </>
        )}
      </div>
    </div>
  )
}

/** 账户类型 → 中文标签（portrait.account_type 的 enum 值映射）. */
const ACCOUNT_TYPE_LABEL: Record<string, string> = {
  credit_card: "信用卡",
  debit_card: "储蓄卡",
  alipay: "支付宝",
  wechat: "微信",
  bank_general: "银行通用",
  unknown: "未知",
}

/** 收支规则 → 中文标签（portrait.amount_sign_rule 的 enum 值映射）. */
const AMOUNT_SIGN_RULE_LABEL: Record<string, string> = {
  pos_income: "正数=收入",
  pos_expense: "正数=支出",
  no_sign: "无符号",
  split_cols: "收支分列",
  unknown: "未知",
}

/**
 * 文档画像 hover 卡片（纯 CSS group-hover，文件名右下角弹出）.
 *
 * 渲染画像核心字段：账户类型/持有人/机构/对账期间/收支规则/表头属性。
 * key_observations 截断省略（hover 卡片只显核心，不堆观察列表）。
 * portrait 为 null（未生成 / LLM 失败）时显示「画像待生成」占位。
 * monochrome：9 级 ink token，不用红色；--shadow-popover 投影。
 */
function PortraitCard({
  portrait,
}: {
  portrait: Record<string, unknown> | null
}) {
  if (!portrait) {
    return (
      <div
        className="pointer-events-none absolute left-0 top-full z-50 mt-1 hidden w-56 rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100 p-3 text-xs text-ink-600 group-hover:block"
        style={{ boxShadow: "var(--shadow-popover)" }}
      >
        画像待生成
      </div>
    )
  }

  const rows: { label: string; value: string }[] = [
    {
      label: "账户类型",
      value: ACCOUNT_TYPE_LABEL[String(portrait.account_type ?? "unknown")] ?? "未知",
    },
    { label: "持有人", value: String(portrait.account_holder ?? "") || "—" },
    { label: "机构", value: String(portrait.institution ?? "") || "—" },
    { label: "对账期间", value: String(portrait.statement_period ?? "") || "—" },
    {
      label: "收支规则",
      value:
        AMOUNT_SIGN_RULE_LABEL[String(portrait.amount_sign_rule ?? "unknown")] ?? "未知",
    },
  ]
  const headerAttrs = Array.isArray(portrait.header_attributes)
    ? (portrait.header_attributes as unknown[]).map(String)
    : []

  return (
    <div
      className="pointer-events-none absolute left-0 top-full z-50 mt-1 hidden w-72 rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100 p-3 group-hover:block"
      style={{ boxShadow: "var(--shadow-popover)" }}
    >
      <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-ink-700">
        文档画像
      </div>
      <dl className="grid grid-cols-[80px_1fr] gap-x-3 gap-y-1.5 font-mono text-xs">
        {rows.map((r) => (
          <React.Fragment key={r.label}>
            <dt className="text-ink-700">{r.label}</dt>
            <dd className="truncate text-ink-900" title={r.value}>
              {r.value}
            </dd>
          </React.Fragment>
        ))}
      </dl>
      {headerAttrs.length > 0 && (
        <div className="mt-2 border-t border-ink-400 pt-2">
          <div className="mb-1 text-[11px] font-bold uppercase tracking-wider text-ink-700">
            表头
          </div>
          <div className="flex flex-wrap gap-1">
            {headerAttrs.slice(0, 8).map((h, i) => (
              <span
                key={i}
                className="rounded-[var(--radius-DEFAULT)] bg-ink-200 px-1.5 py-0.5 font-mono text-[11px] text-ink-900"
              >
                {h}
              </span>
            ))}
            {headerAttrs.length > 8 && (
              <span className="px-1 py-0.5 font-mono text-[11px] text-ink-700">
                +{headerAttrs.length - 8}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/** Grayscale status capsule. Pending=light, Parsing=mid + spinner, Done=deep,
 *  Failed=black bg white bold uppercase. Never colored. */
function StatusCapsule({ status }: { status: DocumentStatus }) {
  switch (status) {
    case "completed":
      return (
        <span className="inline-flex items-center rounded-[var(--radius-full)] bg-ink-800 px-2.5 py-0.5 text-xs font-medium text-ink-100">
          完成
        </span>
      )
    case "processing":
      return (
        <span className="inline-flex items-center gap-1.5 rounded-[var(--radius-full)] bg-ink-500 px-2.5 py-0.5 text-xs font-medium text-ink-100">
          <RefreshCw className="size-3 animate-spin" />
          解析中
        </span>
      )
    case "failed":
      return (
        <span className="inline-flex items-center rounded-none border-2 border-ink-900 bg-ink-900 px-2.5 py-0.5 text-xs font-bold uppercase tracking-wider text-ink-100">
          失败
        </span>
      )
    case "deleted":
      return (
        <span className="inline-flex items-center rounded-[var(--radius-full)] bg-ink-300 px-2.5 py-0.5 text-xs font-medium text-ink-600 line-through">
          已删除
        </span>
      )
    case "pending":
    default:
      return (
        <span className="inline-flex items-center rounded-[var(--radius-full)] border border-ink-400 bg-ink-300 px-2.5 py-0.5 text-xs font-medium text-ink-700">
          待解析
        </span>
      )
  }
}

/** Pick a monochrome file-type icon by extension. */
function FileTypeIcon({
  filename,
  className,
}: {
  filename: string
  className?: string
}) {
  const ext = filename.slice(filename.lastIndexOf(".")).toLowerCase()
  if (ext === ".pdf") return <FileText className={className} />
  if (ext === ".xlsx" || ext === ".xls") return <FileSpreadsheet className={className} />
  return <File className={className} />
}

/** ---- helpers ---- */

function cacheKey(filename: string, size: number): string {
  return `${filename}|${size}`
}

function filterAccepted(files: File[]): File[] {
  return files.filter((f) => {
    const dot = f.name.lastIndexOf(".")
    if (dot < 0) return false
    const ext = f.name.slice(dot).toLowerCase()
    return ACCEPTED_EXTENSIONS.includes(ext) && f.size <= MAX_FILE_BYTES
  })
}

function typeLabel(filename: string): string {
  const ext = filename.slice(filename.lastIndexOf(".") + 1).toUpperCase()
  return ext || "—"
}

function formatBytes(bytes: number | null): string {
  if (bytes == null) return "—"
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
