import { useState } from "react"
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
import {
  Search,
  Plus,
  Filter,
  ChevronLeft,
  ChevronRight,
  Download,
  MoreHorizontal,
  FileText,
  Clock,
  CheckCircle2,
  AlertCircle,
  XCircle,
} from "lucide-react"

// Mock data
const mockTasks = [
  { id: "PTS-2023-001", customer: "2023年某公司财务审计", status: "已完成", priority: "高", created: "2023-11-24", updated: "14:20", documents: 24, amount: "1,560,000", progress: 100 },
  { id: "PTS-2023-002", customer: "某大型央企合规性审查", status: "进行中", priority: "中", created: "2023-11-25", updated: "17:30", documents: 156, amount: "8,320,000", progress: 65 },
  { id: "PTS-2023-003", customer: "外资企业年度审计", status: "待审核", priority: "低", created: "2023-11-26", updated: "09:15", documents: 89, amount: "4,200,000", progress: 80 },
  { id: "PTS-2023-004", customer: "金融机构风险评估", status: "已逾期", priority: "紧急", created: "2023-11-20", updated: "11:45", documents: 203, amount: "15,800,000", progress: 45 },
  { id: "PTS-2023-005", customer: "某集团合并报表审计", status: "进行中", priority: "高", created: "2023-11-27", updated: "16:00", documents: 67, amount: "3,450,000", progress: 30 },
  { id: "PTS-2023-006", customer: "上市公司年报审计", status: "已完成", priority: "中", created: "2023-11-18", updated: "10:30", documents: 145, amount: "9,870,000", progress: 100 },
  { id: "PTS-2023-007", customer: "中小企业税务审计", status: "待处理", priority: "低", created: "2023-11-28", updated: "14:20", documents: 34, amount: "1,230,000", progress: 0 },
  { id: "PTS-2023-008", customer: "跨境交易合规审查", status: "进行中", priority: "高", created: "2023-11-22", updated: "15:45", documents: 178, amount: "12,560,000", progress: 55 },
]

const statusConfig: Record<string, { variant: "default" | "secondary" | "destructive" | "outline"; icon: any }> = {
  "已完成": { variant: "secondary", icon: CheckCircle2 },
  "进行中": { variant: "default", icon: Clock },
  "待审核": { variant: "outline", icon: AlertCircle },
  "待处理": { variant: "outline", icon: FileText },
  "已逾期": { variant: "destructive", icon: XCircle },
}

const priorityConfig: Record<string, "destructive" | "default" | "secondary"> = {
  "紧急": "destructive",
  "高": "default",
  "中": "secondary",
  "低": "secondary",
}

export default function TasksPage() {
  const [searchTerm, setSearchTerm] = useState("")
  const [statusFilter, setStatusFilter] = useState("all")
  const [priorityFilter, setPriorityFilter] = useState("all")
  const [currentPage, setCurrentPage] = useState(1)
  const totalPages = 3

  const filteredTasks = mockTasks.filter((task) => {
    const matchesSearch = task.customer.toLowerCase().includes(searchTerm.toLowerCase()) ||
      task.id.toLowerCase().includes(searchTerm.toLowerCase())
    const matchesStatus = statusFilter === "all" || task.status === statusFilter
    const matchesPriority = priorityFilter === "all" || task.priority === priorityFilter
    return matchesSearch && matchesStatus && matchesPriority
  })

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
                placeholder="搜索任务编号或客户名称..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-9"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder="状态" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部状态</SelectItem>
                <SelectItem value="进行中">进行中</SelectItem>
                <SelectItem value="待审核">待审核</SelectItem>
                <SelectItem value="待处理">待处理</SelectItem>
                <SelectItem value="已完成">已完成</SelectItem>
                <SelectItem value="已逾期">已逾期</SelectItem>
              </SelectContent>
            </Select>
            <Select value={priorityFilter} onValueChange={setPriorityFilter}>
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder="优先级" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部优先级</SelectItem>
                <SelectItem value="紧急">紧急</SelectItem>
                <SelectItem value="高">高</SelectItem>
                <SelectItem value="中">中</SelectItem>
                <SelectItem value="低">低</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="outline" size="icon">
              <Filter className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="icon">
              <Download className="w-4 h-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card className="bg-card border-border">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[120px]">任务编号</TableHead>
                <TableHead>客户名称</TableHead>
                <TableHead className="w-[100px]">状态</TableHead>
                <TableHead className="w-[100px]">优先级</TableHead>
                <TableHead className="w-[120px]">创建时间</TableHead>
                <TableHead className="w-[80px]">文档数</TableHead>
                <TableHead className="w-[120px]">金额</TableHead>
                <TableHead className="w-[100px]">进度</TableHead>
                <TableHead className="w-[50px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredTasks.map((task) => {
                const status = statusConfig[task.status] || statusConfig["待处理"]
                const StatusIcon = status.icon
                return (
                  <TableRow key={task.id} className="hover:bg-surface-container-low/50">
                    <TableCell className="font-mono text-xs">{task.id}</TableCell>
                    <TableCell className="font-medium">{task.customer}</TableCell>
                    <TableCell>
                      <Badge variant={status.variant} className="gap-1">
                        <StatusIcon className="w-3 h-3" />
                        {task.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={priorityConfig[task.priority] || "secondary"}>
                        {task.priority}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {task.created}
                      <br />
                      {task.updated}
                    </TableCell>
                    <TableCell>{task.documents}</TableCell>
                    <TableCell className="font-mono">¥{task.amount}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-surface-container-low rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary rounded-full transition-all"
                            style={{ width: `${task.progress}%` }}
                          />
                        </div>
                        <span className="text-xs text-muted-foreground w-8">{task.progress}%</span>
                      </div>
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
        </CardContent>
      </Card>

      {/* Pagination & Summary */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          显示 1-{Math.min(8, filteredTasks.length)} 条，共 {filteredTasks.length} 条
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
          {[1, 2, 3].map((page) => (
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

      {/* Stats Summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-card border-border">
          <CardContent className="p-4">
            <div className="text-2xl font-bold text-foreground">1,482</div>
            <div className="text-xs text-muted-foreground mt-1">总任务数</div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="p-4">
            <div className="text-2xl font-bold text-foreground">12</div>
            <div className="text-xs text-muted-foreground mt-1">待处理</div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="p-4">
            <div className="text-2xl font-bold text-success">8.42%</div>
            <div className="text-xs text-muted-foreground mt-1">逾期率</div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="p-4">
            <div className="text-2xl font-bold text-foreground">342</div>
            <div className="text-xs text-muted-foreground mt-1">本月完成</div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
