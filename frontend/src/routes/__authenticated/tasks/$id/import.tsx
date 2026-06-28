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
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"
import type { DocumentItem, DocumentStatus } from "@/lib/api"
import {
  useDeleteDocument,
  useDocument,
  useDocumentList,
  useUploadTaskDocuments,
} from "@/hooks/use-documents"
import { useStartExtraction, useTask } from "@/hooks/use-tasks"

/**
 * 数据导入 /tasks/:id/import (docs §C2).
 *
 * Single channel (银行流水) upload area: channel title + 开始处理 primary
 * button + large dashed dropzone + 选择文件 outline button. Below: file
 * table (文件名 / 类型 / 大小 / 解析状态胶囊 / 上传时间 / 操作). TanStack
 * Query polls the documents list every 2s while any doc is
 * pending/processing and stops once all are settled.
 *
 * Channel key is the Chinese label itself, persisted verbatim as the
 * backend `channel` string (mirrors Task.expected_channels semantics).
 */
export const Route = createFileRoute("/__authenticated/tasks/$id/import")({
  component: ImportPage,
})

/** Channel key = Chinese label (stored verbatim as backend `channel`). */
const CHANNEL = "银行流水"

/** File extensions the backend scanner actually accepts (no .csv — scanner
 *  does not support it). Frontend validation + dropzone copy align to this. */
const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".xls"]
const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(",")
const MAX_FILE_BYTES = 50 * 1024 * 1024 // 50 MB

function ImportPage() {
  const { id } = useParams({ from: "/__authenticated/tasks/$id/import" })
  const taskId = Number(id)

  const [portraitDocId, setPortraitDocId] = React.useState<number | null>(null)
  const [portraitRequestKey, setPortraitRequestKey] = React.useState(0)

  // Pull ALL documents (no channel filter) so the file list and hasPending
  // check work at the task level.
  const allDocsQuery = useDocumentList(taskId, {})
  const allDocs = allDocsQuery.data?.items ?? []

  // Task detail — read status so the 开始处理 button is disabled while running.
  const taskQuery = useTask(taskId)
  const taskStatus = taskQuery.data?.status ?? "draft"

  // Filtered view for the 银行流水 channel (derived from allDocs so we keep a
  // single query at the task level).
  const channelDocs = allDocs.filter(
    (d) => (d.channel ?? "其他") === CHANNEL,
  )

  // 开始处理 is enabled only when there is at least one pending document and
  // the task is not already running. Running tasks auto-pick up new uploads via
  // the runner's batch loop, so the button is hidden then.
  const hasPending = allDocs.some((d) => d.status === "pending")
  const isRunning = taskStatus === "running"

  const upload = useUploadTaskDocuments(taskId)
  const deleteDoc = useDeleteDocument(taskId)
  const startExtraction = useStartExtraction(taskId)
  const portraitQuery = useDocument(taskId, portraitDocId)

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
    upload.mutate({ files: valid, channel: CHANNEL })
  }

  function handleRetry(doc: DocumentItem) {
    const size = doc.size_bytes ?? 0
    const cached = lookupCachedFile(doc.filename, size)
    if (!cached) {
      // No cached File (e.g. page reloaded) — fall back to the picker.
      hiddenInputRef.current?.click()
      return
    }
    upload.mutate({ files: [cached], channel: doc.channel ?? CHANNEL })
  }

  function handleDelete(docId: number) {
    deleteDoc.mutate(docId)
  }

  function handleViewPortrait(docId: number) {
    setPortraitDocId(docId)
    setPortraitRequestKey((v) => v + 1)
  }

  React.useEffect(() => {
    if (portraitDocId === null) return
    void portraitQuery.refetch()
    // Refetch on every open/click, even if TanStack Query has a cached value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [portraitRequestKey])

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

  return (
    <div className="flex h-[calc(100vh-220px)] min-h-[420px] flex-col">
      {/* Upload area + file table */}
      <section className="flex min-h-0 flex-1 flex-col rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100 p-6">
        {/* Header: channel title + 上传文件 + 开始处理 */}
        <div className="mb-5 flex items-center justify-between">
          <h3 className="font-sans text-lg font-semibold text-ink-900">
            银行流水上传
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
                onViewPortrait={() => handleViewPortrait(doc.id)}
                onRetry={() => handleRetry(doc)}
                onDelete={() => handleDelete(doc.id)}
              />
            ))}
          </div>
        </div>
      </section>
      <PortraitDialog
        open={portraitDocId !== null}
        document={portraitQuery.data ?? null}
        isLoading={portraitQuery.isFetching || portraitQuery.data === undefined}
        isError={portraitQuery.isError}
        onOpenChange={(open) => {
          if (!open) setPortraitDocId(null)
        }}
      />
    </div>
  )
}

/** One file row. Status capsule maps to a grayscale tone; Failed is the only
 *  "heavy" state — black bg + white bold uppercase + Retry. */
function FileRow({
  doc,
  onViewPortrait,
  onRetry,
  onDelete,
}: {
  doc: DocumentItem
  onViewPortrait: () => void
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
      {/* Filename + type icon */}
      <div className="flex min-w-0 items-center gap-2">
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
            <button
              type="button"
              onClick={onViewPortrait}
              className="text-ink-600 transition-colors hover:text-ink-900 focus-visible:outline-2 focus-visible:outline-ink-800 focus-visible:outline-offset-2"
              aria-label="查看文档画像"
              title="查看文档画像"
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
 * 文档画像详情弹框。
 *
 * 渲染画像核心字段：账户类型/持有人/机构/对账期间/收支规则/表头属性。
 * portrait 为 null（未生成 / LLM 失败）时显示「画像待生成」占位。
 */
function PortraitDialog({
  open,
  document,
  isLoading,
  isError,
  onOpenChange,
}: {
  open: boolean
  document: DocumentItem | null
  isLoading: boolean
  isError: boolean
  onOpenChange: (open: boolean) => void
}) {
  const portrait = document?.portrait ?? null

  return (
    <Dialog open={open} onOpenChange={onOpenChange} className="max-w-3xl">
      <DialogHeader>
        <DialogTitle>文档画像</DialogTitle>
        <DialogClose onOpenChange={onOpenChange} />
      </DialogHeader>
      <DialogBody className="max-h-[70vh] overflow-y-auto">
        <div className="mb-4 min-w-0">
          <div className="truncate font-sans text-sm font-semibold text-ink-900">
            {document?.filename ?? "正在读取文档..."}
          </div>
          <div className="mt-1 font-mono text-xs text-ink-700">
            {isLoading ? "正在刷新画像..." : "点击小眼睛时读取的最新画像"}
          </div>
        </div>

        {isLoading ? (
          <div className="border border-ink-400 bg-ink-200 p-4 text-sm text-ink-700">
            正在读取最新文档画像...
          </div>
        ) : isError ? (
          <div className="border border-ink-400 bg-ink-200 p-4 text-sm text-ink-800">
            画像读取失败，请稍后重试。
          </div>
        ) : (
          <PortraitContent portrait={portrait} />
        )}
      </DialogBody>
    </Dialog>
  )
}

function PortraitContent({
  portrait,
}: {
  portrait: Record<string, unknown> | null
}) {
  if (!portrait) {
    return (
      <div className="border border-ink-400 bg-ink-200 p-4 text-sm text-ink-700">
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
  const columnMapping = Array.isArray(portrait.column_mapping)
    ? (portrait.column_mapping as unknown[]).map(String)
    : []
  const observations = Array.isArray(portrait.key_observations)
    ? (portrait.key_observations as unknown[]).map(String)
    : []

  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-[96px_1fr] gap-x-4 gap-y-2 font-mono text-sm">
        {rows.map((r) => (
          <React.Fragment key={r.label}>
            <dt className="text-ink-700">{r.label}</dt>
            <dd className="min-w-0 break-words text-ink-900" title={r.value}>
              {r.value}
            </dd>
          </React.Fragment>
        ))}
      </dl>
      {(headerAttrs.length > 0 || columnMapping.length > 0) && (
        <div className="border-t border-ink-400 pt-4">
          <div className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-700">
            表头
          </div>
          <div className="overflow-hidden border border-ink-400">
            <div className="grid grid-cols-[1fr_1fr] bg-ink-200 px-3 py-2 font-sans text-xs font-semibold text-ink-800">
              <div>原始表头</div>
              <div>标准字段</div>
            </div>
            {(headerAttrs.length > 0 ? headerAttrs : columnMapping).map((h, i) => (
              <div
                key={`${h}-${i}`}
                className="grid grid-cols-[1fr_1fr] border-t border-ink-400 px-3 py-2 font-mono text-xs text-ink-900"
              >
                <div className="min-w-0 break-words">
                  {headerAttrs[i] ?? "—"}
                </div>
                <div className="min-w-0 break-words">
                  {columnMapping[i] ?? "—"}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {observations.length > 0 && (
        <div className="border-t border-ink-400 pt-4">
          <div className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-700">
            关键观察
          </div>
          <ul className="space-y-1.5 font-sans text-sm text-ink-900">
            {observations.map((item, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-2 size-1.5 shrink-0 rounded-[var(--radius-full)] bg-ink-700" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
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
