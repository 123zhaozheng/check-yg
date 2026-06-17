import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Input } from "~/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { Textarea } from "~/components/ui/textarea"
import { Label } from "~/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "~/components/ui/dropdown-menu"
import { api, downloadFile } from "~/lib/api"
import { toast } from "sonner"
import {
  Search,
  Plus,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  MoreHorizontal,
  Clock,
  CheckCircle2,
  AlertCircle,
  XCircle,
  FileText,
  Pause,
  Play,
  Square,
  Download,
  FileSpreadsheet,
  FileArchive,
  ClipboardCheck,
} from "lucide-react"

interface TaskItem {
  id: number
  title: string
  description: string | null
  status: string
  owner_id: number
  config: {
    document_folder?: string | null
    batch_size?: number
    confidence_threshold?: number
  } | null
  created_at: string
  updated_at: string
  completed_at: string | null
}

interface CustomerListOption {
  id: number
  name: string
  row_count: number
}

interface ReviewSummary {
  id: number
  total_matches: number
}

interface ReportSummary {
  id: number
  content: string
}

interface ExportSummary {
  id: number
  format: string
}

const statusConfig: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline"; icon: any }> = {
  draft: { label: "草稿", variant: "outline", icon: FileText },
  running: { label: "进行中", variant: "default", icon: Clock },
  paused: { label: "已暂停", variant: "secondary", icon: Pause },
  completed: { label: "已完成", variant: "secondary", icon: CheckCircle2 },
  failed: { label: "失败", variant: "destructive", icon: XCircle },
  cancelled: { label: "已取消", variant: "outline", icon: AlertCircle },
}

export default function TasksPage() {
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [total, setTotal] = useState(0)
  const [searchTerm, setSearchTerm] = useState("")
  const [statusFilter, setStatusFilter] = useState("all")
  const [currentPage, setCurrentPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [actingTaskId, setActingTaskId] = useState<number | null>(null)
  const [form, setForm] = useState({
    title: "",
    description: "",
    document_folder: "",
    batch_size: "20",
    confidence_threshold: "70",
  })

  // Review / report / export workflow state for completed tasks.
  const [workflowTask, setWorkflowTask] = useState<TaskItem | null>(null)
  const [customerLists, setCustomerLists] = useState<CustomerListOption[]>([])
  const [selectedListId, setSelectedListId] = useState<string>("")
  const [review, setReview] = useState<ReviewSummary | null>(null)
  const [report, setReport] = useState<ReportSummary | null>(null)
  const [exports, setExports] = useState<ExportSummary[]>([])
  const [workflowBusy, setWorkflowBusy] = useState<string | null>(null)
  const pageSize = 20

  async function fetchTasks() {
    setLoading(true)
    try {
      const params: Record<string, string> = {
        page: String(currentPage),
        page_size: String(pageSize),
      }
      if (statusFilter !== "all") params.status_filter = statusFilter
      if (searchTerm) params.search = searchTerm

      const res = await api.get<{ items: TaskItem[]; total: number }>("/api/tasks/", params)
      setTasks(res.items)
      setTotal(res.total)
    } catch {
      toast.error("任务列表加载失败")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTasks()
  }, [currentPage, statusFilter, searchTerm])

  async function handleCreateTask() {
    const title = form.title.trim()
    if (!title) {
      toast.error("请输入任务名称")
      return
    }

    setSaving(true)
    try {
      const task = await api.post<TaskItem>("/api/tasks/", {
        title,
        description: form.description.trim() || undefined,
        document_folder: form.document_folder.trim() || undefined,
        batch_size: Number(form.batch_size) || 20,
        confidence_threshold: Number(form.confidence_threshold) || 70,
      })
      setCreateOpen(false)
      setForm({
        title: "",
        description: "",
        document_folder: "",
        batch_size: "20",
        confidence_threshold: "70",
      })
      toast.success("任务已创建")
      if (task.config?.document_folder) {
        await handleTaskAction(task.id, "start", {
          document_folder: task.config.document_folder,
          batch_size: task.config.batch_size || 20,
          confidence_threshold: task.config.confidence_threshold || 70,
        })
      } else {
        await fetchTasks()
      }
    } catch {
      toast.error("任务创建失败")
    } finally {
      setSaving(false)
    }
  }

  async function handleTaskAction(
    taskId: number,
    action: "start" | "pause" | "resume" | "cancel",
    body?: Record<string, unknown>
  ) {
    setActingTaskId(taskId)
    try {
      await api.post<TaskItem>(`/api/tasks/${taskId}/${action}`, body)
      const labels = {
        start: "任务已启动",
        pause: "任务已暂停",
        resume: "任务已继续",
        cancel: "任务已取消",
      }
      toast.success(labels[action])
      await fetchTasks()
    } catch {
      toast.error("任务操作失败")
    } finally {
      setActingTaskId(null)
    }
  }

  function openWorkflow(task: TaskItem) {
    setWorkflowTask(task)
    setReview(null)
    setReport(null)
    setExports([])
    setSelectedListId("")
    setCustomerLists([])
    fetchCustomerLists()
  }

  function closeWorkflow() {
    setWorkflowTask(null)
    setReview(null)
    setReport(null)
    setExports([])
    setSelectedListId("")
    setCustomerLists([])
  }

  async function fetchCustomerLists() {
    try {
      const res = await api.get<{ items: CustomerListOption[]; total: number }>(
        "/api/customers/lists",
        { page: "1", page_size: "100" }
      )
      setCustomerLists(res.items)
      if (res.items.length > 0) {
        setSelectedListId(String(res.items[0].id))
      }
    } catch {
      toast.error("客户名单加载失败")
    }
  }

  async function handleRunReview() {
    if (!workflowTask) return
    if (!selectedListId) {
      toast.error("请先选择客户名单")
      return
    }
    setWorkflowBusy("review")
    try {
      const res = await api.post<ReviewSummary>(
        `/api/tasks/${workflowTask.id}/review`,
        { customer_list_id: Number(selectedListId) }
      )
      setReview(res)
      setReport(null)
      setExports([])
      toast.success(`审查完成，命中 ${res.total_matches} 条匹配`)
    } catch {
      toast.error("审查失败")
    } finally {
      setWorkflowBusy(null)
    }
  }

  async function handleGenerateReport() {
    if (!workflowTask) return
    setWorkflowBusy("report")
    try {
      const res = await api.post<ReportSummary>(
        `/api/tasks/${workflowTask.id}/report`,
        review ? { review_id: review.id } : undefined
      )
      setReport(res)
      toast.success("报告已生成")
    } catch {
      toast.error("报告生成失败")
    } finally {
      setWorkflowBusy(null)
    }
  }

  async function handleExport(format: "excel" | "bundle") {
    if (!workflowTask) return
    setWorkflowBusy(`export-${format}`)
    try {
      const res = await api.post<ExportSummary>(
        `/api/tasks/${workflowTask.id}/export/${format}`,
        review ? { review_id: review.id } : undefined
      )
      setExports((prev) => [...prev, res])
      toast.success(format === "excel" ? "Excel 导出已生成" : "技能包已生成")
    } catch {
      toast.error("导出失败")
    } finally {
      setWorkflowBusy(null)
    }
  }

  async function handleDownloadReport() {
    if (!report) return
    try {
      await downloadFile(`/api/reports/${report.id}/download`, `report-${report.id}.md`)
    } catch {
      toast.error("报告下载失败")
    }
  }

  async function handleDownloadExport(exportId: number, format: string) {
    const ext = format === "excel" ? "xlsx" : "zip"
    try {
      await downloadFile(`/api/exports/${exportId}/download`, `export-${exportId}.${ext}`)
    } catch {
      toast.error("下载失败")
    }
  }

  const totalPages = Math.ceil(total / pageSize) || 1

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">审查任务</h1>
          <p className="text-sm text-muted-foreground mt-1">
            管理和跟踪所有审计任务的执行进度与审查状态。
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="w-4 h-4 mr-2" />
          创建新任务
        </Button>
      </div>

      {/* Filters */}
      <Card className="bg-card border-border">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="搜索任务名称..."
                value={searchTerm}
                onChange={(e) => { setSearchTerm(e.target.value); setCurrentPage(1) }}
                className="pl-9"
              />
            </div>
            <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setCurrentPage(1) }}>
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder="状态" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部状态</SelectItem>
                <SelectItem value="running">进行中</SelectItem>
                <SelectItem value="draft">草稿</SelectItem>
                <SelectItem value="paused">已暂停</SelectItem>
                <SelectItem value="completed">已完成</SelectItem>
                <SelectItem value="failed">失败</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="outline" size="icon" onClick={fetchTasks} title="刷新">
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card className="bg-card border-border">
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
              加载中...
            </div>
          ) : tasks.length === 0 ? (
            <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
              暂无任务数据
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[80px]">ID</TableHead>
                  <TableHead>任务名称</TableHead>
                  <TableHead className="w-[100px]">状态</TableHead>
                  <TableHead className="w-[140px]">创建时间</TableHead>
                  <TableHead className="w-[140px]">完成时间</TableHead>
                  <TableHead className="w-[50px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasks.map((task) => {
                  const cfg = statusConfig[task.status] || statusConfig.draft
                  const StatusIcon = cfg.icon
                  return (
                    <TableRow key={task.id} className="hover:bg-surface-container-low/50">
                      <TableCell className="font-mono text-xs">{task.id}</TableCell>
                      <TableCell>
                        <div className="font-medium">{task.title}</div>
                        {task.description && (
                          <div className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{task.description}</div>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant={cfg.variant} className="gap-1">
                          <StatusIcon className="w-3 h-3" />
                          {cfg.label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {new Date(task.created_at).toLocaleString("zh-CN")}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {task.completed_at ? new Date(task.completed_at).toLocaleString("zh-CN") : "-"}
                      </TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8" disabled={actingTaskId === task.id}>
                              <MoreHorizontal className="w-4 h-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-36">
                            {(task.status === "draft" || task.status === "failed" || task.status === "cancelled") && (
                              <DropdownMenuItem
                                onClick={() => handleTaskAction(task.id, "start", {
                                  document_folder: task.config?.document_folder,
                                  batch_size: task.config?.batch_size || 20,
                                  confidence_threshold: task.config?.confidence_threshold || 70,
                                })}
                                disabled={!task.config?.document_folder}
                              >
                                <Play className="w-4 h-4" />
                                启动
                              </DropdownMenuItem>
                            )}
                            {task.status === "running" && (
                              <DropdownMenuItem onClick={() => handleTaskAction(task.id, "pause")}>
                                <Pause className="w-4 h-4" />
                                暂停
                              </DropdownMenuItem>
                            )}
                            {task.status === "paused" && (
                              <DropdownMenuItem onClick={() => handleTaskAction(task.id, "resume")}>
                                <Play className="w-4 h-4" />
                                继续
                              </DropdownMenuItem>
                            )}
                            {(task.status === "running" || task.status === "paused") && (
                              <>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem variant="destructive" onClick={() => handleTaskAction(task.id, "cancel")}>
                                  <Square className="w-4 h-4" />
                                  取消
                                </DropdownMenuItem>
                              </>
                            )}
                            {task.status === "completed" && (
                              <>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem onClick={() => openWorkflow(task)}>
                                  <ClipboardCheck className="w-4 h-4" />
                                  审查 / 报告 / 导出
                                </DropdownMenuItem>
                              </>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {total > 0 && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-muted-foreground">
            共 {total} 条记录
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => i + 1).map((page) => (
              <Button
                key={page}
                variant={page === currentPage ? "default" : "outline"}
                size="icon"
                onClick={() => setCurrentPage(page)}
                className="w-8 h-8"
              >
                {page}
              </Button>
            ))}
            <Button
              variant="outline"
              size="icon"
              onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage === totalPages}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>创建审查任务</DialogTitle>
            <DialogDescription>
              填写后端可访问的文档目录。保存后如果目录已填写，会立即启动抽取。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>任务名称</Label>
              <Input
                value={form.title}
                onChange={(e) => setForm((prev) => ({ ...prev, title: e.target.value }))}
                placeholder="例如：6月员工客户流水审查"
              />
            </div>
            <div className="space-y-2">
              <Label>文档目录</Label>
              <Input
                value={form.document_folder}
                onChange={(e) => setForm((prev) => ({ ...prev, document_folder: e.target.value }))}
                placeholder="D:\\audit\\documents"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>批处理行数</Label>
                <Input
                  type="number"
                  min={1}
                  value={form.batch_size}
                  onChange={(e) => setForm((prev) => ({ ...prev, batch_size: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label>流水判定阈值</Label>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  value={form.confidence_threshold}
                  onChange={(e) => setForm((prev) => ({ ...prev, confidence_threshold: e.target.value }))}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>备注</Label>
              <Textarea
                value={form.description}
                onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
                placeholder="可选"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} disabled={saving}>
              取消
            </Button>
            <Button onClick={handleCreateTask} disabled={saving}>
              {saving ? "创建中..." : "创建并启动"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Review / Report / Export workflow */}
      <Dialog open={!!workflowTask} onOpenChange={(open) => { if (!open) closeWorkflow() }}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>审查、报告与导出</DialogTitle>
            <DialogDescription>
              任务 #{workflowTask?.id} — {workflowTask?.title}。依次完成审查、生成报告与导出产物。
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-5 max-h-[60vh] overflow-y-auto">
            {/* Step 1: Review */}
            <div className="space-y-3 rounded-lg border border-border p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ClipboardCheck className="w-4 h-4 text-foreground" />
                  <span className="font-medium text-sm">1. 审查匹配</span>
                </div>
                {review && (
                  <Badge variant="secondary" className="gap-1">
                    <CheckCircle2 className="w-3 h-3" />
                    命中 {review.total_matches} 条
                  </Badge>
                )}
              </div>
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">客户名单</Label>
                {customerLists.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    暂无客户名单，请先在“客户名单”页面创建。审查将使用系统默认名单。
                  </p>
                ) : (
                  <Select value={selectedListId} onValueChange={setSelectedListId}>
                    <SelectTrigger>
                      <SelectValue placeholder="选择客户名单" />
                    </SelectTrigger>
                    <SelectContent>
                      {customerLists.map((list) => (
                        <SelectItem key={list.id} value={String(list.id)}>
                          {list.name}（{list.row_count} 条）
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
              <Button
                onClick={handleRunReview}
                disabled={workflowBusy !== null}
              >
                {workflowBusy === "review" ? "审查中..." : review ? "重新审查" : "运行审查"}
              </Button>
            </div>

            {/* Step 2: Report */}
            <div className="space-y-3 rounded-lg border border-border p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-foreground" />
                  <span className="font-medium text-sm">2. 生成报告</span>
                </div>
                {report && (
                  <Badge variant="secondary" className="gap-1">
                    <CheckCircle2 className="w-3 h-3" />
                    报告 #{report.id}
                  </Badge>
                )}
              </div>
              <Button
                onClick={handleGenerateReport}
                disabled={workflowBusy !== null}
              >
                {workflowBusy === "report" ? "生成中..." : report ? "重新生成报告" : "生成报告"}
              </Button>
              {report && (
                <div className="space-y-2">
                  <div className="max-h-40 overflow-y-auto rounded bg-surface-container-low p-2 text-xs text-muted-foreground whitespace-pre-wrap">
                    {report.content || "（报告内容为空）"}
                  </div>
                  <Button variant="outline" size="sm" onClick={handleDownloadReport}>
                    <Download className="w-4 h-4 mr-2" />
                    下载报告 (.md)
                  </Button>
                </div>
              )}
            </div>

            {/* Step 3: Export */}
            <div className="space-y-3 rounded-lg border border-border p-4">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-4 h-4 text-foreground" />
                <span className="font-medium text-sm">3. 导出产物</span>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => handleExport("excel")}
                  disabled={workflowBusy !== null}
                >
                  <FileSpreadsheet className="w-4 h-4 mr-2" />
                  {workflowBusy === "export-excel" ? "导出中..." : "导出 Excel"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => handleExport("bundle")}
                  disabled={workflowBusy !== null}
                >
                  <FileArchive className="w-4 h-4 mr-2" />
                  {workflowBusy === "export-bundle" ? "打包中..." : "导出技能包 ZIP"}
                </Button>
              </div>
              {exports.length > 0 && (
                <div className="space-y-2">
                  {exports.map((exp) => (
                    <div
                      key={exp.id}
                      className="flex items-center justify-between rounded bg-surface-container-low p-2"
                    >
                      <span className="text-xs text-muted-foreground">
                        {exp.format === "excel" ? "Excel" : "技能包 ZIP"} #{exp.id}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDownloadExport(exp.id, exp.format)}
                      >
                        <Download className="w-4 h-4 mr-1" />
                        下载
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={closeWorkflow}>关闭</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
