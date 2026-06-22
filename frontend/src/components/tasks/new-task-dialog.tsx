import * as React from "react"
import { useNavigate } from "@tanstack/react-router"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { ApiError, extractErrorDetail, type TaskCreatePayload } from "@/lib/api"
import { useCreateTask } from "@/hooks/use-tasks"
import { cn } from "@/lib/utils"

/**
 * 新建任务弹窗 (docs §B3).
 *
 * Monochrome Dialog: 基础信息 (任务名 / 被审查员工工号+姓名 / 部门 / 审查期间起止 /
 * 任务说明) + 审查范围 (预期渠道勾选). Footer = 取消 (描边) + 创建并进入 (黑底主按钮).
 *
 * 提交成功后 invalidate tasks 列表 + 跳 `/tasks/{id}/import` (任务详情数据导入 Tab).
 * 错误态 = 深灰底白字小条 (呼应 S1 login 错误态，禁红).
 */

const CHANNEL_OPTIONS = [
  { key: "bank", label: "银行" },
  { key: "pay", label: "支付" },
  { key: "wealth", label: "理财" },
  { key: "securities", label: "证券" },
  { key: "other", label: "其他" },
] as const

interface NewTaskDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function NewTaskDialog({ open, onOpenChange }: NewTaskDialogProps) {
  const navigate = useNavigate()
  const createTask = useCreateTask()

  const [title, setTitle] = React.useState("")
  const [employeeId, setEmployeeId] = React.useState("")
  const [employeeName, setEmployeeName] = React.useState("")
  const [department, setDepartment] = React.useState("")
  const [auditStart, setAuditStart] = React.useState("")
  const [auditEnd, setAuditEnd] = React.useState("")
  const [description, setDescription] = React.useState("")
  const [channels, setChannels] = React.useState<Record<string, boolean>>({})
  const [error, setError] = React.useState<string | null>(null)

  // Reset the form whenever the dialog opens.
  React.useEffect(() => {
    if (open) {
      setTitle("")
      setEmployeeId("")
      setEmployeeName("")
      setDepartment("")
      setAuditStart("")
      setAuditEnd("")
      setDescription("")
      setChannels({})
      setError(null)
    }
  }, [open])

  function toggleChannel(key: string) {
    setChannels((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim()) {
      setError("请填写任务名称。")
      return
    }
    setError(null)

    const payload: TaskCreatePayload = {
      title: title.trim(),
      description: description.trim() || undefined,
      employee_name: employeeName.trim() || undefined,
      employee_id: employeeId.trim() || undefined,
      department: department.trim() || undefined,
      audit_start: auditStart ? `${auditStart}T00:00:00` : undefined,
      audit_end: auditEnd ? `${auditEnd}T00:00:00` : undefined,
      expected_channels: (() => {
        const selected = CHANNEL_OPTIONS.filter((opt) => channels[opt.key]).map(
          (opt) => opt.label,
        )
        return selected.length ? selected : undefined
      })(),
    }

    try {
      const task = await createTask.mutateAsync(payload)
      onOpenChange(false)
      void navigate({ to: `/tasks/${task.id}/import` })
    } catch (err) {
      if (err instanceof ApiError) {
        setError(extractErrorDetail(err.data) ?? "创建任务失败，请稍后重试。")
      } else {
        setError("创建任务失败，请稍后重试。")
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader>
        <DialogTitle>新建审查任务</DialogTitle>
        <DialogClose onOpenChange={onOpenChange} />
      </DialogHeader>

      <form onSubmit={handleSubmit}>
        <DialogBody className="max-h-[70vh] overflow-y-auto scroll-thin">
          {/* 基础信息 */}
          <fieldset className="mb-6 flex flex-col gap-5">
            <legend className="mb-1 font-sans text-xs font-bold uppercase tracking-widest text-ink-600">
              基础信息
            </legend>
            <Field label="任务名称" required>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="例：2026-06 张某某流水审查"
                required
                autoFocus
              />
            </Field>
            <div className="grid grid-cols-2 gap-5">
              <Field label="被审查员工工号">
                <Input
                  value={employeeId}
                  onChange={(e) => setEmployeeId(e.target.value)}
                  placeholder="例：ZS-0421"
                />
              </Field>
              <Field label="被审查员工姓名">
                <Input
                  value={employeeName}
                  onChange={(e) => setEmployeeName(e.target.value)}
                  placeholder="员工姓名"
                />
              </Field>
            </div>
            <Field label="所属部门">
              <Input
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                placeholder="例：财务部"
              />
            </Field>
            <div className="grid grid-cols-2 gap-5">
              <Field label="审查期间起">
                <input
                  type="date"
                  value={auditStart}
                  onChange={(e) => setAuditStart(e.target.value)}
                  className="field-fine-border w-full bg-transparent px-0 py-2 font-mono text-sm text-ink-900"
                />
              </Field>
              <Field label="审查期间止">
                <input
                  type="date"
                  value={auditEnd}
                  onChange={(e) => setAuditEnd(e.target.value)}
                  className="field-fine-border w-full bg-transparent px-0 py-2 font-mono text-sm text-ink-900"
                />
              </Field>
            </div>
            <Field label="任务说明">
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="本次审查的重点、范围说明…"
                rows={3}
                className="field-fine-border w-full resize-none bg-transparent px-0 py-2 font-sans text-sm text-ink-900 placeholder:text-ink-600"
              />
            </Field>
          </fieldset>

          {/* 审查范围 */}
          <fieldset className="flex flex-col gap-3">
            <legend className="mb-1 font-sans text-xs font-bold uppercase tracking-widest text-ink-600">
              审查范围 · 预期渠道
            </legend>
            <p className="text-xs text-ink-600">
              仅作为预期参考，实际以数据导入为准。
            </p>
            <div className="flex flex-wrap gap-2">
              {CHANNEL_OPTIONS.map((opt) => {
                const checked = !!channels[opt.key]
                return (
                  <button
                    key={opt.key}
                    type="button"
                    onClick={() => toggleChannel(opt.key)}
                    className={cn(
                      "rounded-[var(--radius-DEFAULT)] border px-3 py-1.5 text-sm transition-colors",
                      checked
                        ? "border-ink-900 bg-ink-900 text-ink-100"
                        : "border-ink-400 bg-transparent text-ink-800 hover:border-ink-700",
                    )}
                  >
                    {opt.label}
                  </button>
                )
              })}
            </div>
          </fieldset>

          {error && (
            <p
              role="alert"
              className="mt-5 rounded-[var(--radius-DEFAULT)] bg-ink-800 px-3 py-2 font-mono text-xs font-semibold text-ink-100"
            >
              {error}
            </p>
          )}
        </DialogBody>

        <DialogFooter>
          <Button
            type="button"
            variant="secondary"
            onClick={() => onOpenChange(false)}
            disabled={createTask.isPending}
          >
            取消
          </Button>
          <Button type="submit" disabled={createTask.isPending}>
            {createTask.isPending ? "创建中…" : "创建并进入"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  )
}

/** Labeled form field with a fine-border-bottom input slot. */
function Field({
  label,
  required,
  children,
}: {
  label: string
  required?: boolean
  children: React.ReactNode
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-ink-700">
        {label}
        {required && <span className="text-ink-900"> *</span>}
      </span>
      {children}
    </label>
  )
}
