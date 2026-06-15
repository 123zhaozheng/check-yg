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
import { api } from "~/lib/api"
import {
  Search,
  Plus,
  Filter,
  ChevronLeft,
  ChevronRight,
  MoreHorizontal,
  Clock,
  CheckCircle2,
  AlertCircle,
  XCircle,
  FileText,
  Pause,
} from "lucide-react"

interface TaskItem {
  id: number
  title: string
  description: string | null
  status: string
  owner_id: number
  created_at: string
  completed_at: string | null
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
  const pageSize = 20

  useEffect(() => {
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
        // API error
      } finally {
        setLoading(false)
      }
    }
    fetchTasks()
  }, [currentPage, statusFilter, searchTerm])

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
        <Button>
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
            <Button variant="outline" size="icon">
              <Filter className="w-4 h-4" />
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
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <MoreHorizontal className="w-4 h-4" />
                        </Button>
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
    </div>
  )
}
