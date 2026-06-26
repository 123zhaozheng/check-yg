import * as React from "react"
import { createFileRoute } from "@tanstack/react-router"
import { Download, Upload } from "lucide-react"

import { PageHeader } from "@/components/layout/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import {
  ApiError,
  extractErrorDetail,
  type KeywordCardListItem,
  type KeywordCardUpsertBody,
  type KeywordImportStats,
  type KeywordRiskLevel,
} from "@/lib/api"
import { useCurrentUser } from "@/hooks/use-current-user"
import {
  useCreateKeywordCard,
  useDeleteKeywordCard,
  useExportKeywordLibrary,
  useImportKeywordLibrary,
  useKeywordCard,
  useKeywordCards,
  useUpdateKeywordCard,
} from "@/hooks/use-keyword-library"

/**
 * 关键词库 /keyword-library (06-23-tab).
 *
 * 全局关键词卡片管理页（单色对齐 settings 模型卡 tab）:
 * - 卡片表格：卡片名 / 词数 / 风险等级 / 备注 / 操作（编辑/删除）。
 * - 顶部：导入 excel（上传 dialog） + 导出 excel + 新建卡片（admin 可见）。
 * - 新建/编辑 dialog：卡片名 + 风险等级（高/中/低 select）+ 备注 + 关键词列表（可增删的 term 输入行）。
 * - 导入 dialog：文件选择 + 上传 + 导入结果统计展示。
 * - admin gating（useCurrentUser role===admin）；非 admin 能看列表/导出但不能改。
 *
 * 单色 ink tokens，无 radix。命中片段高亮用粗体/下划线不用彩色。
 */
export const Route = createFileRoute("/__authenticated/keyword-library")({
  component: KeywordLibraryPage,
})

const RISK_OPTIONS: KeywordRiskLevel[] = ["高", "中", "低"]

function KeywordLibraryPage() {
  const { user } = useCurrentUser()
  const isAdmin = user?.role === "admin"

  return (
    <>
      <PageHeader title="关键词库" />
      <KeywordCardsCard isAdmin={isAdmin} />
    </>
  )
}

/** 卡片管理：列表 table + 导入/导出 + 新建/编辑/删除. */
function KeywordCardsCard({ isAdmin }: { isAdmin: boolean }) {
  const cardsQuery = useKeywordCards()
  const deleteCard = useDeleteKeywordCard()
  const exportLib = useExportKeywordLibrary()
  const [editing, setEditing] = React.useState<KeywordCardListItem | null>(null)
  const [creating, setCreating] = React.useState(false)
  const [importing, setImporting] = React.useState(false)
  const [viewingTerms, setViewingTerms] = React.useState<KeywordCardListItem | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  const cards = cardsQuery.data ?? []

  async function handleDelete(card: KeywordCardListItem) {
    setError(null)
    try {
      await deleteCard.mutateAsync(card.id)
    } catch (err) {
      setError(extractDetail(err) ?? "删除失败")
    }
  }

  async function handleExport() {
    setError(null)
    try {
      await exportLib.mutateAsync()
    } catch (err) {
      setError(extractDetail(err) ?? "导出失败")
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-sans text-base font-bold text-ink-900">关键词卡片</h2>
          </div>
          <div className="flex items-center gap-2">
            {isAdmin && (
              <Button variant="secondary" size="sm" onClick={() => setImporting(true)}>
                <Upload className="size-4" />
                导入 excel
              </Button>
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={handleExport}
              disabled={exportLib.isPending}
            >
              <Download className="size-4" />
              导出 excel
            </Button>
            {isAdmin && (
              <Button size="sm" onClick={() => setCreating(true)}>
                新建卡片
              </Button>
            )}
          </div>
        </div>

        {cardsQuery.isLoading && (
          <p className="text-sm text-ink-600">加载中…</p>
        )}
        {cardsQuery.isError && (
          <p className="text-sm text-ink-600">关键词卡片加载失败，请稍后重试。</p>
        )}

        {cards.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-ink-400 text-left">
                  <Th>卡片名</Th>
                  <Th>词数</Th>
                  <Th>风险等级</Th>
                  <Th>备注</Th>
                  {isAdmin && <Th>操作</Th>}
                </tr>
              </thead>
              <tbody>
                {cards.map((c) => (
                  <tr key={c.id} className="border-b border-ink-300">
                    <Td className="font-medium text-ink-900">
                      <button
                        onClick={() => setViewingTerms(c)}
                        className="text-left underline decoration-ink-400 underline-offset-2 hover:text-ink-700 hover:decoration-ink-900"
                        title="点击查看/管理关键词列表"
                      >
                        {c.name}
                      </button>
                    </Td>
                    <Td className="font-mono text-xs">{c.term_count}</Td>
                    <Td>
                      <RiskBadge level={c.risk_level} />
                    </Td>
                    <Td className="text-ink-700">{c.note || "—"}</Td>
                    {isAdmin && (
                      <Td>
                        <div className="flex gap-2">
                          <Button
                            variant="tertiary"
                            size="sm"
                            onClick={() => setEditing(c)}
                          >
                            编辑
                          </Button>
                          <Button
                            variant="tertiary"
                            size="sm"
                            onClick={() => handleDelete(c)}
                            disabled={deleteCard.isPending}
                          >
                            删除
                          </Button>
                        </div>
                      </Td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!cardsQuery.isLoading && cards.length === 0 && (
          <p className="text-sm text-ink-600">
            暂无关键词卡片，{isAdmin ? "点击「新建卡片」或「导入 excel」添加。" : "请联系 admin 添加。"}
          </p>
        )}

        {error && <p className="font-mono text-xs font-bold text-ink-900">{error}</p>}

        {creating && (
          <KeywordCardDialog mode="create" onClose={() => setCreating(false)} />
        )}
        {editing && (
          <KeywordCardDialog
            mode="edit"
            initial={editing}
            onClose={() => setEditing(null)}
          />
        )}
        {importing && (
          <ImportDialog onClose={() => setImporting(false)} />
        )}
        {viewingTerms && (
          <KeywordTermsDialog
            card={viewingTerms}
            isAdmin={isAdmin}
            onClose={() => setViewingTerms(null)}
          />
        )}
      </CardContent>
    </Card>
  )
}

/** 风险等级标 — 灰阶双编码（高=黑底白字方块 / 中=深灰 / 低=浅灰，单色禁彩色）. */
function RiskBadge({ level }: { level: KeywordRiskLevel }) {
  const styles: Record<KeywordRiskLevel, string> = {
    高: "bg-ink-900 text-ink-100 rounded-none",
    中: "bg-ink-700 text-ink-100 rounded-[var(--radius-DEFAULT)]",
    低: "bg-ink-300 text-ink-700 rounded-[var(--radius-full)]",
  }
  return (
    <span
      className={cn(
        "inline-flex h-5 min-w-8 items-center justify-center px-1.5 font-sans text-[11px] font-bold",
        styles[level],
      )}
    >
      {level}
    </span>
  )
}

/** 卡片新建/编辑对话框.
 *
 * 编辑模式只改卡片名/风险等级/备注——关键词列表已移到独立的「关键词列表」大弹窗
 * （点卡片名打开，KeywordTermsDialog），编辑 dialog 不再展示/改动 terms，避免两处
 * 都改 terms 互相覆盖。编辑保存时 terms 传空数组（后端空数组=不改动现有词）。
 * 新建模式仍在此处一并录入初始关键词。
 */
function KeywordCardDialog({
  mode,
  initial,
  onClose,
}: {
  mode: "create" | "edit"
  initial?: KeywordCardListItem
  onClose: () => void
}) {
  const createCard = useCreateKeywordCard()
  const updateCard = useUpdateKeywordCard()
  const [name, setName] = React.useState(initial?.name ?? "")
  const [riskLevel, setRiskLevel] = React.useState<KeywordRiskLevel>(
    initial?.risk_level ?? "中",
  )
  const [note, setNote] = React.useState(initial?.note ?? "")
  const [terms, setTerms] = React.useState<string[]>([""])
  const [error, setError] = React.useState<string | null>(null)

  function setTerm(idx: number, value: string) {
    setTerms((prev) => prev.map((t, i) => (i === idx ? value : t)))
  }

  function addTerm() {
    setTerms((prev) => [...prev, ""])
  }

  function removeTerm(idx: number) {
    setTerms((prev) => prev.filter((_, i) => i !== idx))
  }

  async function handleSave() {
    setError(null)
    const cleanName = name.trim()
    if (!cleanName) {
      setError("卡片名称不能为空")
      return
    }
    const cleanTerms = terms.map((t) => t.trim()).filter(Boolean)
    const body: KeywordCardUpsertBody = {
      name: cleanName,
      risk_level: riskLevel,
      note: note.trim() || null,
    }
    if (mode === "create") {
      // 新建：带初始 terms。
      body.terms = cleanTerms
    }
    try {
      if (mode === "create") {
        await createCard.mutateAsync(body)
      } else if (initial) {
        // 编辑：不传 terms（后端 None=不改现有词，由 KeywordTermsDialog 管理）。
        await updateCard.mutateAsync({ id: initial.id, body })
      }
      onClose()
    } catch (err) {
      setError(extractDetail(err) ?? "保存失败")
    }
  }

  const pending = createCard.isPending || updateCard.isPending

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} className="max-w-2xl">
      <DialogHeader>
        <DialogTitle>{mode === "create" ? "新建关键词卡片" : "编辑关键词卡片"}</DialogTitle>
        <DialogClose onOpenChange={(o) => !o && onClose()} />
      </DialogHeader>
      <DialogBody className="max-h-[60vh] overflow-y-auto">
        <div className="flex flex-col gap-4">
          {mode === "edit" && (
            <p className="rounded-[var(--radius-DEFAULT)] bg-ink-200 p-2 text-[11px] text-ink-700">
              提示：此处只改卡片名/风险等级/备注。关键词列表请点表格中的卡片名，在弹出的「关键词列表」中增删。
            </p>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                卡片名称
              </label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                风险等级
              </label>
              <select
                value={riskLevel}
                onChange={(e) => setRiskLevel(e.target.value as KeywordRiskLevel)}
                className="rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 px-2 py-2 font-sans text-sm text-ink-900 focus:border-ink-900 focus:outline-none"
              >
                {RISK_OPTIONS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
              备注
            </label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="可选" />
          </div>
          {mode === "create" && (
            <div className="flex flex-col gap-1">
              <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                关键词列表
              </label>
              <div className="flex flex-col gap-2">
                {terms.map((term, idx) => (
                  <div key={idx} className="flex items-center gap-2">
                    <Input
                      value={term}
                      onChange={(e) => setTerm(idx, e.target.value)}
                      placeholder={`关键词 ${idx + 1}`}
                    />
                    <Button
                      variant="tertiary"
                      size="sm"
                      onClick={() => removeTerm(idx)}
                      disabled={terms.length === 1}
                    >
                      删除
                    </Button>
                  </div>
                ))}
                <Button variant="secondary" size="sm" onClick={addTerm} className="self-start">
                  + 添加关键词
                </Button>
              </div>
            </div>
          )}
        </div>
        {error && <p className="mt-4 font-mono text-xs font-bold text-ink-900">{error}</p>}
      </DialogBody>
      <DialogFooter>
        <Button variant="tertiary" onClick={onClose}>
          取消
        </Button>
        <Button onClick={handleSave} disabled={pending}>
          {pending ? "保存中…" : "保存"}
        </Button>
      </DialogFooter>
    </Dialog>
  )
}

/**
 * 关键词列表大弹窗 —— 点卡片名打开，展示该卡片的所有关键词，可增/删/改（admin）。
 * 非 admin 只读。保存时用 PUT 卡片（terms 全量替换），卡片名/风险/备注保持原值。
 */
function KeywordTermsDialog({
  card,
  isAdmin,
  onClose,
}: {
  card: KeywordCardListItem
  isAdmin: boolean
  onClose: () => void
}) {
  const cardDetailQuery = useKeywordCard(card.id)
  const updateCard = useUpdateKeywordCard()
  const [terms, setTerms] = React.useState<string[]>([])
  const [loaded, setLoaded] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [savedMsg, setSavedMsg] = React.useState<string | null>(null)

  // 拉到详情后初始化本地 terms 编辑态（仅在首次加载时，避免覆盖用户编辑）。
  React.useEffect(() => {
    if (!loaded && cardDetailQuery.data) {
      setTerms(cardDetailQuery.data.terms.map((t) => t.term))
      setLoaded(true)
    }
  }, [cardDetailQuery.data, loaded])

  function setTerm(idx: number, value: string) {
    setTerms((prev) => prev.map((t, i) => (i === idx ? value : t)))
  }

  function addTerm() {
    setTerms((prev) => [...prev, ""])
  }

  function removeTerm(idx: number) {
    setTerms((prev) => prev.filter((_, i) => i !== idx))
  }

  async function handleSave() {
    setError(null)
    setSavedMsg(null)
    const cleanTerms = terms.map((t) => t.trim()).filter(Boolean)
    try {
      // PUT 全量替换 terms，卡片名/风险/备注保持原值。
      await updateCard.mutateAsync({
        id: card.id,
        body: {
          name: card.name,
          risk_level: card.risk_level,
          note: card.note ?? null,
          terms: cleanTerms,
        },
      })
      setSavedMsg("关键词列表已保存")
    } catch (err) {
      setError(extractDetail(err) ?? "保存失败")
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} className="max-w-3xl">
      <DialogHeader>
        <DialogTitle>
          关键词列表 · {card.name}
          <span className="ml-2 font-normal text-ink-600">
            （风险等级 {card.risk_level}{card.note ? ` · ${card.note}` : ""}）
          </span>
        </DialogTitle>
        <DialogClose onOpenChange={(o) => !o && onClose()} />
      </DialogHeader>
      <DialogBody className="max-h-[65vh] overflow-y-auto">
        {cardDetailQuery.isLoading && (
          <p className="text-sm text-ink-600">加载中…</p>
        )}
        {cardDetailQuery.isError && (
          <p className="text-sm text-ink-600">关键词加载失败，请稍后重试。</p>
        )}
        {loaded && (
          <div className="flex flex-col gap-2">
            {terms.length === 0 && (
              <p className="text-sm text-ink-600">
                暂无关键词，{isAdmin ? "点击下方「添加关键词」录入。" : "请联系 admin 录入。"}
              </p>
            )}
            {terms.map((term, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <Input
                  value={term}
                  onChange={(e) => setTerm(idx, e.target.value)}
                  placeholder={`关键词 ${idx + 1}`}
                  disabled={!isAdmin}
                />
                {isAdmin && (
                  <Button
                    variant="tertiary"
                    size="sm"
                    onClick={() => removeTerm(idx)}
                  >
                    删除
                  </Button>
                )}
              </div>
            ))}
            {isAdmin && (
              <Button variant="secondary" size="sm" onClick={addTerm} className="self-start">
                + 添加关键词
              </Button>
            )}
          </div>
        )}
        {error && <p className="mt-4 font-mono text-xs font-bold text-ink-900">{error}</p>}
        {savedMsg && <p className="mt-4 font-mono text-xs text-ink-700">{savedMsg}</p>}
      </DialogBody>
      <DialogFooter>
        <Button variant="tertiary" onClick={onClose}>
          关闭
        </Button>
        {isAdmin && (
          <Button onClick={handleSave} disabled={updateCard.isPending || !loaded}>
            {updateCard.isPending ? "保存中…" : "保存关键词列表"}
          </Button>
        )}
      </DialogFooter>
    </Dialog>
  )
}

/** 导入 excel 对话框 — 文件选择 + 上传 + 统计展示. */
function ImportDialog({ onClose }: { onClose: () => void }) {
  const importMut = useImportKeywordLibrary()
  const [file, setFile] = React.useState<File | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [stats, setStats] = React.useState<KeywordImportStats | null>(null)

  async function handleImport() {
    setError(null)
    setStats(null)
    if (!file) {
      setError("请先选择 excel 文件")
      return
    }
    try {
      const result = await importMut.mutateAsync(file)
      setStats(result)
    } catch (err) {
      setError(extractDetail(err) ?? "导入失败")
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} className="max-w-lg">
      <DialogHeader>
        <DialogTitle>导入关键词 excel</DialogTitle>
        <DialogClose onOpenChange={(o) => !o && onClose()} />
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <p className="text-xs text-ink-600">
          表头规范：<span className="font-mono">卡片名称,关键词,风险等级,备注</span>。
        </p>
        <input
          type="file"
          accept=".xlsx,.xls"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-sm text-ink-700"
        />
        {stats && (
          <div className="rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-200 p-3">
            <p className="text-xs font-bold uppercase tracking-widest text-ink-700">
              导入结果
            </p>
            <ul className="mt-2 space-y-1 font-mono text-xs text-ink-900">
              <li>新建卡片：{stats.created_cards}</li>
              <li>追加卡片：{stats.appended_cards}</li>
              <li>新增词：{stats.new_terms}</li>
              <li>跳过重复词：{stats.skipped_terms}</li>
              <li>拒绝行：{stats.rejected_rows}</li>
            </ul>
          </div>
        )}
        {error && <p className="font-mono text-xs font-bold text-ink-900">{error}</p>}
      </DialogBody>
      <DialogFooter>
        <Button variant="tertiary" onClick={onClose}>
          {stats ? "关闭" : "取消"}
        </Button>
        {!stats && (
          <Button onClick={handleImport} disabled={importMut.isPending}>
            {importMut.isPending ? "导入中…" : "上传导入"}
          </Button>
        )}
      </DialogFooter>
    </Dialog>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-2 py-2 text-xs font-bold uppercase tracking-widest text-ink-600">
      {children}
    </th>
  )
}

function Td({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return <td className={cn("px-2 py-2 text-ink-900", className)}>{children}</td>
}

/** Extract a human-readable error detail from an ApiError or generic error. */
function extractDetail(err: unknown): string | undefined {
  if (err instanceof ApiError) return extractErrorDetail(err.data)
  if (err instanceof Error) return err.message
  return undefined
}
