import { useState } from "react"
import { Card, CardContent } from "~/components/ui/card"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import {
  Users,
  Upload,
  Plus,
  Filter,
  X,
  ChevronLeft,
  ChevronRight,
  Building2,
  AlertTriangle,
  FileText,
  Clock,
} from "lucide-react"

// Mock data
const mockCustomerLists = [
  {
    id: 1,
    name: "年度核心审计名单",
    tags: [{ label: "重点关注", variant: "default" as const }, { label: "2024年度", variant: "secondary" as const }],
    count: 1234,
    progress: 78,
    updatedBy: "张审计师",
    updatedAt: "2小时前",
    avatar: "Z",
  },
  {
    id: 2,
    name: "高风险违规名单",
    tags: [{ label: "黑名单", variant: "destructive" as const }],
    count: 412,
    progress: 45,
    updatedBy: "李合规",
    updatedAt: "昨天 14:20",
    avatar: "L",
  },
  {
    id: 3,
    name: "外资独资企业审计",
    tags: [{ label: "特殊标记", variant: "outline" as const }],
    count: 89,
    progress: 92,
    updatedBy: "王外资",
    updatedAt: "3天前",
    avatar: "W",
  },
  {
    id: 4,
    name: "临时待审名单",
    tags: [{ label: "草稿", variant: "secondary" as const }],
    count: 12,
    progress: 0,
    updatedBy: "未分配",
    updatedAt: "1周前",
    avatar: "U",
  },
]

export default function CustomersPage() {
  const [filters, setFilters] = useState<string[]>([])
  const [showActiveOnly, setShowActiveOnly] = useState(false)
  const [sortBy, setSortBy] = useState("updated")
  const [currentPage, setCurrentPage] = useState(1)
  const totalPages = 3

  const toggleFilter = (filter: string) => {
    setFilters((prev) =>
      prev.includes(filter) ? prev.filter((f) => f !== filter) : [...prev, filter]
    )
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">客户名单</h1>
          <p className="text-sm text-muted-foreground mt-1">
            构建可复用的审计客户资产
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">
            <Upload className="w-4 h-4 mr-2" />
            导入名单
          </Button>
          <Button>
            <Plus className="w-4 h-4 mr-2" />
            新建名单
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card className="bg-card border-border">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">筛选:</span>
            </div>
            {filters.map((filter) => (
              <Badge key={filter} variant="secondary" className="gap-1">
                {filter}
                <button onClick={() => toggleFilter(filter)}>
                  <X className="w-3 h-3" />
                </button>
              </Badge>
            ))}
            <Button
              variant={filters.includes("重点关注") ? "default" : "outline"}
              size="sm"
              onClick={() => toggleFilter("重点关注")}
            >
              重点关注
            </Button>
            <Button
              variant={filters.includes("黑名单") ? "destructive" : "outline"}
              size="sm"
              onClick={() => toggleFilter("黑名单")}
            >
              黑名单
            </Button>
            <label className="flex items-center gap-2 text-sm text-muted-foreground ml-auto">
              <input
                type="checkbox"
                checked={showActiveOnly}
                onChange={(e) => setShowActiveOnly(e.target.checked)}
                className="rounded border-border"
              />
              仅显示活跃
            </label>
            <Select value={sortBy} onValueChange={setSortBy}>
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder="排序" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="updated">按更新时间排序</SelectItem>
                <SelectItem value="name">按名称排序</SelectItem>
                <SelectItem value="count">按客户数排序</SelectItem>
              </SelectContent>
            </Select>
            <span className="text-xs text-muted-foreground">
              共找到 12 个名单
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Customer List Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {mockCustomerLists.map((list) => (
          <Card key={list.id} className="bg-card border-border hover:border-primary/50 transition-colors cursor-pointer">
            <CardContent className="p-5">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-surface-container-high flex items-center justify-center">
                    <Building2 className="w-5 h-5 text-foreground" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-foreground">{list.name}</h3>
                    <div className="flex gap-1 mt-1">
                      {list.tags.map((tag) => (
                        <Badge key={tag.label} variant={tag.variant} className="text-[10px]">
                          {tag.label}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">客户总数</span>
                  <span className="font-semibold text-foreground">
                    {list.count.toLocaleString()} 名客户
                  </span>
                </div>

                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">审计进度</span>
                    <span className="text-foreground">{list.progress}%</span>
                  </div>
                  <div className="h-1.5 bg-surface-container-low rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        list.progress === 100
                          ? "bg-success"
                          : list.progress > 50
                          ? "bg-primary"
                          : list.progress > 0
                          ? "bg-warning"
                          : "bg-muted"
                      }`}
                      style={{ width: `${list.progress}%` }}
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t border-border">
                  <div className="flex items-center gap-1">
                    <div className="w-5 h-5 rounded-full bg-secondary flex items-center justify-center text-[10px] font-medium text-secondary-foreground">
                      {list.avatar}
                    </div>
                    <span>{list.updatedBy}</span>
                  </div>
                  <span>更新于 {list.updatedAt}</span>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}

        {/* Create New Card */}
        <Card className="bg-card border-border border-dashed hover:border-primary/50 transition-colors cursor-pointer">
          <CardContent className="p-5 flex flex-col items-center justify-center h-full min-h-[200px]">
            <div className="w-12 h-12 rounded-full bg-surface-container-high flex items-center justify-center mb-3">
              <Plus className="w-6 h-6 text-muted-foreground" />
            </div>
            <p className="text-sm text-muted-foreground">创建新名单</p>
          </CardContent>
        </Card>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          显示 1-4 个名单，共 12 个
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
    </div>
  )
}
