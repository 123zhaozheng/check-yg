import * as React from "react"
import { createFileRoute, useParams } from "@tanstack/react-router"
import { Check, FileText, GripVertical, RefreshCw } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { ReportAnnotationItem, ReportChapterItem } from "@/lib/api"
import {
  useAddAnnotation,
  useFinalizeReport,
  useGenerateReport,
  usePatchChapter,
  usePatchAnnotation,
  useRegenerateChapter,
  useRegenerateReport,
  useReorderChapters,
  useReport,
} from "@/hooks/use-report"

/**
 * 审查报告 /tasks/:id/report (docs §C5).
 *
 * Monochrome 三栏报告页（黑白年报排版，单色原则）:
 * - 顶部控制条: 保存草稿描边 + 提交定稿黑底主按钮 + 重新生成全报告描边 +
 *   "已定稿"灰阶标签（定稿后只读水印）.
 * - 左·报告大纲: 8 章目录，点击跳转，可拖拽排序（HTML5 drag），选中黑底高亮.
 * - 中·报告正文: 章节粗体大字 + 规整排版（Markdown 轻量渲染）;
 *   异常条目卡片块嵌入（标题/金额/AI结论/关联记录入口）;
 *   行内编辑点段落 → textarea 细虚线框 → blur 保存 PATCH;
 *   每章「重新生成本章」描边次按钮.
 * - 右·复核批注栏: 批注列表（批注人+时间+文本+解决状态灰阶，左细灰竖线 +
 *   浅灰底块，禁彩色高亮）+ 新建批注（选章节+输入）+ 切 resolved.
 *
 * 定稿后整页只读，写操作后端 409. 不删减精神：定稿只改 Report.status 软态.
 */
export const Route = createFileRoute("/__authenticated/tasks/$id/report")({
  component: ReportPage,
})

function ReportPage() {
  const { id } = useParams({ from: "/__authenticated/tasks/$id/report" })
  const taskId = Number(id)

  const reportQuery = useReport(taskId)
  const generateReport = useGenerateReport(taskId)
  const regenerateReport = useRegenerateReport(taskId)
  const finalizeReport = useFinalizeReport(taskId)

  const report = reportQuery.data
  const isFinal = report?.status === "final"
  const isGenerating = report?.status === "generating"
  const isFailed = report?.status === "failed"
  const chapters = React.useMemo(
    () =>
      [...(report?.chapters ?? [])].sort(
        (a, b) => a.order_index - b.order_index,
      ),
    [report?.chapters],
  )

  const [activeChapterId, setActiveChapterId] = React.useState<number | null>(
    null,
  )
  // Sync the active chapter to the first chapter once the report loads.
  React.useEffect(() => {
    if (chapters.length && activeChapterId == null) {
      setActiveChapterId(chapters[0].id)
    }
  }, [chapters, activeChapterId])

  return (
    <div className="flex flex-col gap-4">
      {/* Top control bar */}
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
          <div className="flex items-center gap-3">
            <FileText className="size-5 text-ink-700" />
            <div>
              <h2 className="font-sans text-lg font-bold text-ink-900">
                审查报告
              </h2>
              <p className="font-mono text-xs text-ink-600">
                {report
                  ? `报告 #${report.id} · ${reportStatusLabel(report.status)}`
                  : "尚未生成报告"}
              </p>
            </div>
            {isFinal && (
              <span className="rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-200 px-2 py-0.5 font-mono text-xs font-bold uppercase tracking-wider text-ink-500">
                已定稿
              </span>
            )}
            {isGenerating && (
              <span className="rounded-[var(--radius-DEFAULT)] border border-ink-500 bg-ink-200 px-2 py-0.5 font-mono text-xs font-bold text-ink-700">
                生成中
              </span>
            )}
            {isFailed && (
              <span className="rounded-[var(--radius-DEFAULT)] border border-ink-900 bg-ink-900 px-2 py-0.5 font-mono text-xs font-bold text-ink-100">
                生成失败
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {!report && (
              <Button
                size="sm"
                onClick={() => generateReport.mutate()}
                disabled={generateReport.isPending}
              >
                {generateReport.isPending ? "生成中…" : "生成报告"}
              </Button>
            )}
            {report && !isFinal && (
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => regenerateReport.mutate(report.id)}
                  disabled={regenerateReport.isPending || isGenerating}
                >
                  <RefreshCw className="size-4" />
                  {isGenerating
                    ? "后台生成中…"
                    : regenerateReport.isPending
                      ? "重生成中…"
                      : "重新生成全报告"}
                </Button>
                <Button
                  size="sm"
                  onClick={() => finalizeReport.mutate(report.id)}
                  disabled={finalizeReport.isPending || isGenerating}
                >
                  {finalizeReport.isPending ? "定稿中…" : "提交定稿"}
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {!report && !reportQuery.isLoading && (
        <Card>
          <CardContent className="p-10 text-center">
            <p className="text-sm text-ink-600">
              尚未生成报告。点击上方「生成报告」基于清洗标准化记录与 AI 分析发现汇总审查报告。
            </p>
          </CardContent>
        </Card>
      )}

      {reportQuery.isLoading && (
        <Card>
          <CardContent className="p-10 text-center text-sm text-ink-600">
            加载中…
          </CardContent>
        </Card>
      )}

      {report && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[200px_1fr_300px]">
          {/* Left: outline */}
          <ReportOutline
            taskId={taskId}
            chapters={chapters}
            activeChapterId={activeChapterId}
            isFinal={isFinal}
            isGenerating={Boolean(isGenerating)}
            onSelect={setActiveChapterId}
          />

          {/* Middle: report body */}
          <ReportBody
            taskId={taskId}
            reportId={report.id}
            chapters={chapters}
            isFinal={isFinal}
            activeChapterId={activeChapterId}
            isGenerating={Boolean(isGenerating)}
          />

          {/* Right: annotations */}
          <AnnotationPanel
            taskId={taskId}
            reportId={report.id}
            chapters={chapters}
            annotations={report.annotations ?? []}
            isFinal={isFinal}
            isGenerating={Boolean(isGenerating)}
          />
        </div>
      )}

      {isFinal && (
        // "已定稿" 水印式灰阶标签（固定在页面右上，仅 final 显示）
        <div
          aria-hidden
          className="pointer-events-none fixed right-6 top-24 rotate-12 select-none rounded-[var(--radius-DEFAULT)] border-2 border-ink-400 px-4 py-1 font-sans text-sm font-bold uppercase tracking-widest text-ink-500"
        >
          已定稿
        </div>
      )}
    </div>
  )
}

/** Left column: chapter outline with drag-to-reorder and jump-to. */
function ReportOutline({
  taskId,
  chapters,
  activeChapterId,
  isFinal,
  isGenerating,
  onSelect,
}: {
  taskId: number
  chapters: ReportChapterItem[]
  activeChapterId: number | null
  isFinal: boolean
  isGenerating: boolean
  onSelect: (id: number) => void
}) {
  const reorder = useReorderChapters(taskId)
  const [dragId, setDragId] = React.useState<number | null>(null)
  const [overId, setOverId] = React.useState<number | null>(null)

  function handleDrop() {
    if (dragId == null || overId == null || dragId === overId) {
      setDragId(null)
      setOverId(null)
      return
    }
    const ordered = chapters.map((c) => c.id)
    const from = ordered.indexOf(dragId)
    const to = ordered.indexOf(overId)
    if (from === -1 || to === -1) {
      setDragId(null)
      setOverId(null)
      return
    }
    ordered.splice(from, 1)
    ordered.splice(to, 0, dragId)
    const reportId = chapters[0]?.report_id
    if (reportId != null) {
      reorder.mutate({
        reportId,
        items: ordered.map((cid, idx) => ({ chapter_id: cid, order_index: idx })),
      })
    }
    setDragId(null)
    setOverId(null)
  }

  return (
    <Card className="h-fit">
      <CardContent className="p-3">
        <p className="mb-2 px-2 font-sans text-xs font-bold uppercase tracking-widest text-ink-600">
          报告大纲
        </p>
        <ul className="flex flex-col gap-0.5">
          {chapters.map((c, idx) => {
            const active = c.id === activeChapterId
            return (
              <li
                key={c.id}
                draggable={!isFinal && !isGenerating}
                onDragStart={() => setDragId(c.id)}
                onDragOver={(e) => {
                  e.preventDefault()
                  setOverId(c.id)
                }}
                onDragEnd={handleDrop}
                onDrop={handleDrop}
              >
                <button
                  onClick={() => onSelect(c.id)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-[var(--radius-DEFAULT)] px-2 py-1.5 text-left font-sans text-sm transition-colors",
                    active
                      ? "bg-ink-900 font-bold text-ink-100"
                      : "text-ink-800 hover:bg-ink-300",
                    overId === c.id && dragId !== c.id && "ring-1 ring-ink-700",
                  )}
                >
                  {!isFinal && !isGenerating && (
                    <GripVertical className="size-3.5 shrink-0 text-ink-600" />
                  )}
                  <span className="font-mono text-xs text-ink-600">
                    {String(idx + 1).padStart(2, "0")}
                  </span>
                  <span className="truncate">{c.title}</span>
                </button>
              </li>
            )
          })}
        </ul>
        {!isFinal && !isGenerating && (
          <p className="mt-2 px-2 font-mono text-[10px] text-ink-600">
            拖拽章节排序
          </p>
        )}
      </CardContent>
    </Card>
  )
}

/** Middle column: the chaptered report body with inline editing. */
function ReportBody({
  taskId,
  reportId,
  chapters,
  isFinal,
  activeChapterId,
  isGenerating,
}: {
  taskId: number
  reportId: number
  chapters: ReportChapterItem[]
  isFinal: boolean
  activeChapterId: number | null
  isGenerating: boolean
}) {
  const sectionRefs = React.useRef<Record<number, HTMLDivElement | null>>({})

  // Jump to the active chapter when it changes.
  React.useEffect(() => {
    if (activeChapterId == null) return
    const el = sectionRefs.current[activeChapterId]
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" })
  }, [activeChapterId])

  return (
    <Card>
      <CardContent className="max-h-[calc(100vh-220px)] overflow-y-auto scroll-thin p-8">
        <article className="mx-auto max-w-3xl">
          {chapters.map((c, idx) => (
            <ChapterSection
              key={c.id}
              ref={(el) => {
                sectionRefs.current[c.id] = el
              }}
              taskId={taskId}
              reportId={reportId}
              chapter={c}
              index={idx}
              isFinal={isFinal}
              isGenerating={isGenerating}
            />
          ))}
        </article>
      </CardContent>
    </Card>
  )
}

/** One chapter section with title + rendered content + inline edit + regenerate. */
const ChapterSection = React.forwardRef<
  HTMLDivElement,
  {
    taskId: number
    reportId: number
    chapter: ReportChapterItem
    index: number
    isFinal: boolean
    isGenerating: boolean
  }
>(function ChapterSection(
  { taskId, reportId, chapter, index, isFinal, isGenerating },
  ref,
) {
  const patchChapter = usePatchChapter(taskId)
  const regenerateChapter = useRegenerateChapter(taskId)

  const [editing, setEditing] = React.useState(false)
  const [draft, setDraft] = React.useState(chapter.content)

  React.useEffect(() => {
    if (!editing) setDraft(chapter.content)
  }, [chapter.content, editing])

  function save() {
    if (draft !== chapter.content) {
      patchChapter.mutate({ reportId, chapterId: chapter.id, body: { content: draft } })
    }
    setEditing(false)
  }

  const hasContent = chapter.content.trim().length > 0

  return (
    <section
      ref={ref}
      className={cn(
        "mb-10 scroll-mt-4 border-b border-ink-300 pb-8 last:border-b-0",
      )}
    >
      <header className="mb-4 flex items-start justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-sm font-bold text-ink-600">
            {String(index + 1).padStart(2, "0")}
          </span>
          <h2 className="font-sans text-2xl font-bold text-ink-900">
            {chapter.title}
          </h2>
        </div>
        {!isFinal && !isGenerating && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() =>
              regenerateChapter.mutate({ reportId, chapterId: chapter.id })
            }
            disabled={regenerateChapter.isPending}
          >
            <RefreshCw className="size-4" />
            {regenerateChapter.isPending ? "重生成中…" : "重新生成本章"}
          </Button>
        )}
      </header>

      {editing ? (
        <div className="rounded-[var(--radius-DEFAULT)] border border-dashed border-ink-500 p-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={save}
            autoFocus
            rows={Math.max(6, draft.split("\n").length + 1)}
            className="w-full resize-y border-none bg-transparent p-2 font-sans text-sm leading-7 text-ink-900 focus:outline-none"
          />
          <div className="flex justify-end gap-2 px-2 pb-1">
            <Button variant="secondary" size="sm" onClick={() => setEditing(false)}>
              取消
            </Button>
            <Button size="sm" onClick={save}>
              保存
            </Button>
          </div>
        </div>
      ) : (
        <div
          onClick={() => !isFinal && hasContent && setEditing(true)}
          className={cn(
            "cursor-text rounded-[var(--radius-DEFAULT)] p-1 transition-colors",
            !isFinal && hasContent && "hover:bg-ink-200",
          )}
        >
          {hasContent ? (
            <MarkdownContent content={chapter.content} />
          ) : (
            <div className="rounded-[var(--radius-DEFAULT)] border border-dashed border-ink-400 bg-ink-200 px-4 py-5 font-sans text-sm text-ink-600">
              {isGenerating ? "生成中…" : "暂无内容。"}
            </div>
          )}
        </div>
      )}
    </section>
  )
})

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => (
          <h2 className="mb-3 mt-2 font-sans text-xl font-bold text-ink-900">
            {children}
          </h2>
        ),
        h2: ({ children }) => (
          <h3 className="mb-2 mt-4 font-sans text-lg font-bold text-ink-900">
            {children}
          </h3>
        ),
        h3: ({ children }) => (
          <h4 className="mb-2 mt-4 font-sans text-base font-bold text-ink-900">
            {children}
          </h4>
        ),
        p: ({ children }) => (
          <p className="mb-3 font-sans text-sm leading-7 text-ink-800">
            {children}
          </p>
        ),
        strong: ({ children }) => (
          <strong className="font-bold text-ink-900">{children}</strong>
        ),
        ul: ({ children }) => (
          <ul className="mb-3 ml-5 list-disc space-y-1 font-sans text-sm leading-7 text-ink-800">
            {children}
          </ul>
        ),
        ol: ({ children }) => (
          <ol className="mb-3 ml-5 list-decimal space-y-1 font-sans text-sm leading-7 text-ink-800">
            {children}
          </ol>
        ),
        blockquote: ({ children }) => {
          const text = markdownText(children)
          if (text.trim().startsWith("finding:")) {
            return <FindingCard line={text.trim().slice(8).trim()} />
          }
          return (
            <blockquote className="mb-4 border-l-2 border-ink-400 bg-ink-200 px-4 py-2 font-sans text-sm leading-7 text-ink-700">
              {children}
            </blockquote>
          )
        },
        table: ({ children }) => (
          <div className="mb-4 overflow-x-auto">
            <table className="w-full border-collapse font-sans text-xs text-ink-800">
              {children}
            </table>
          </div>
        ),
        th: ({ children }) => (
          <th className="border border-ink-400 bg-ink-300 px-2 py-1.5 text-left font-bold text-ink-900">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="border border-ink-300 px-2 py-1.5 align-top">
            {children}
          </td>
        ),
        code: ({ children }) => (
          <code className="rounded-[var(--radius-DEFAULT)] bg-ink-200 px-1 font-mono text-xs text-ink-900">
            {children}
          </code>
        ),
        hr: () => <hr className="my-4 border-ink-300" />,
      }}
    >
      {content}
    </ReactMarkdown>
  )
}

function markdownText(node: React.ReactNode): string {
  if (node == null || typeof node === "boolean") return ""
  if (typeof node === "string" || typeof node === "number") return String(node)
  if (Array.isArray(node)) return node.map(markdownText).join("")
  if (React.isValidElement<{ children?: React.ReactNode }>(node)) {
    return markdownText(node.props.children)
  }
  return ""
}

/** Anomaly finding card embedded in the report body (single-color). */
function FindingCard({ line }: { line: string }) {
  // Format: "**{type}** | 金额 {amount} | 对手 {counterparty} | {description}"
  const parts = line.split("|").map((s) => s.trim())
  const title = parts[0]?.replace(/^\*\*|\*\*$/g, "") ?? "异常发现"
  const fields = parts.slice(1)
  return (
    <div className="mb-4 rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-200 p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="size-2.5 shrink-0 bg-ink-900" />
        <h4 className="font-sans text-base font-bold text-ink-900">{title}</h4>
      </div>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-1 font-mono text-xs text-ink-700 sm:grid-cols-2">
        {fields.map((f, i) => {
          const [k, ...rest] = f.split(/\s+/)
          return (
            <div key={i} className="flex gap-1">
              <dt className="font-bold text-ink-900">{k}</dt>
              <dd>{rest.join(" ")}</dd>
            </div>
          )
        })}
      </dl>
      <p className="mt-2 border-t border-ink-400 pt-2 font-sans text-xs text-ink-600">
        详见关联记录
      </p>
    </div>
  )
}

/** Right column: review annotations. Left thin gray bar + light gray block. */
function AnnotationPanel({
  taskId,
  reportId,
  chapters,
  annotations,
  isFinal,
  isGenerating,
}: {
  taskId: number
  reportId: number
  chapters: ReportChapterItem[]
  annotations: ReportAnnotationItem[]
  isFinal: boolean
  isGenerating: boolean
}) {
  const addAnnotation = useAddAnnotation(taskId)
  const toggleAnnotation = usePatchAnnotation(taskId)

  const [newChapterId, setNewChapterId] = React.useState<number | "">("")
  const [newContent, setNewContent] = React.useState("")

  React.useEffect(() => {
    if (newChapterId === "" && chapters.length) setNewChapterId(chapters[0].id)
  }, [chapters, newChapterId])

  function submit() {
    if (!newContent.trim()) return
    addAnnotation.mutate({
      reportId,
      body: {
        chapter_id: newChapterId === "" ? null : Number(newChapterId),
        content: newContent.trim(),
      },
    })
    setNewContent("")
  }

  const sorted = [...annotations].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )

  const chapterTitle = (cid: number | null | undefined) =>
    chapters.find((c) => c.id === cid)?.title ?? "报告级"

  return (
    <Card className="h-fit">
      <CardContent className="p-3">
        <p className="mb-3 px-1 font-sans text-xs font-bold uppercase tracking-widest text-ink-600">
          复核批注 · {sorted.length}
        </p>

        <ul className="flex flex-col gap-2">
          {sorted.length === 0 && (
            <li className="px-1 py-4 text-center font-sans text-xs text-ink-600">
              暂无批注。
            </li>
          )}
          {sorted.map((a) => (
            <li
              key={a.id}
              className="border-l-2 border-ink-500 bg-ink-200 px-3 py-2"
            >
              <div className="mb-1 flex items-center justify-between">
                <span className="font-sans text-xs font-bold text-ink-900">
                  {a.author}
                </span>
                <span className="font-mono text-[10px] text-ink-600">
                  {formatDateTime(a.created_at)}
                </span>
              </div>
              <p className="mb-1 font-sans text-xs text-ink-700">
                <span className="font-mono text-ink-600">
                  [{chapterTitle(a.chapter_id)}]
                </span>
              </p>
              <p className="mb-2 whitespace-pre-wrap font-sans text-xs leading-5 text-ink-900">
                {a.content}
              </p>
              <button
                onClick={() => toggleAnnotation.mutate({ reportId, annotationId: a.id })}
                disabled={isFinal}
                className={cn(
                  "inline-flex items-center gap-1 rounded-[var(--radius-DEFAULT)] border px-2 py-0.5 font-mono text-[10px] transition-colors disabled:opacity-50",
                  a.resolved
                    ? "border-ink-700 bg-ink-700 text-ink-100"
                    : "border-ink-400 bg-transparent text-ink-700 hover:border-ink-700",
                )}
              >
                <Check className="size-3" />
                {a.resolved ? "已解决" : "待解决"}
              </button>
            </li>
          ))}
        </ul>

        {!isFinal && !isGenerating && (
          <div className="mt-3 flex flex-col gap-2 border-t border-ink-300 pt-3">
            <p className="px-1 font-sans text-xs font-bold text-ink-700">
              新建批注
            </p>
            <select
              value={newChapterId}
              onChange={(e) => setNewChapterId(Number(e.target.value))}
              className="rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 px-2 py-1.5 font-sans text-xs text-ink-900 focus:border-ink-900 focus:outline-none"
            >
              {chapters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
            <textarea
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              placeholder="批注内容…"
              rows={3}
              className="resize-none rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 px-2 py-1.5 font-sans text-xs text-ink-900 placeholder:text-ink-600 focus:border-ink-900 focus:outline-none"
            />
            <Button
              size="sm"
              onClick={submit}
              disabled={addAnnotation.isPending || !newContent.trim()}
            >
              {addAnnotation.isPending ? "提交中…" : "添加批注"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function reportStatusLabel(status: string): string {
  switch (status) {
    case "generating":
      return "生成中"
    case "generated":
      return "已生成"
    case "failed":
      return "生成失败"
    case "final":
      return "已定稿"
    default:
      return "草稿"
  }
}

/** Format ISO datetime as "YYYY-MM-DD HH:mm". */
function formatDateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
