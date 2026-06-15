import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Progress } from "~/components/ui/progress"
import { api } from "~/lib/api"
import {
  ClipboardList,
  TrendingUp,
  Calendar,
  Users,
  AlertTriangle,
  ArrowUpRight,
  Clock,
} from "lucide-react"

interface TaskItem {
  id: number
  title: string
  status: string
  owner_id: number
  created_at: string
}

interface DashboardStats {
  totalTasks: number
  activeTasks: number
  completedThisMonth: number
  totalCustomers: number
  pending: number
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats>({
    totalTasks: 0,
    activeTasks: 0,
    completedThisMonth: 0,
    totalCustomers: 0,
    pending: 0,
  })
  const [recentTasks, setRecentTasks] = useState<TaskItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchData() {
      try {
        // Fetch tasks
        const tasksRes = await api.get<{ items: TaskItem[]; total: number }>("/api/tasks/?page=1&page_size=5")
        setRecentTasks(tasksRes.items)
        setStats((prev) => ({ ...prev, totalTasks: tasksRes.total }))

        // Count by status
        const activeRes = await api.get<{ total: number }>("/api/tasks/?page=1&page_size=1&status_filter=running")
        const pendingRes = await api.get<{ total: number }>("/api/tasks/?page=1&page_size=1&status_filter=draft")
        const completedRes = await api.get<{ total: number }>("/api/tasks/?page=1&page_size=1&status_filter=completed")

        setStats((prev) => ({
          ...prev,
          activeTasks: activeRes.total,
          pending: pendingRes.total,
          completedThisMonth: completedRes.total,
        }))
      } catch {
        // API not ready, use defaults
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  const statusLabel: Record<string, string> = {
    draft: "草稿",
    running: "进行中",
    paused: "已暂停",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
  }

  const statusVariant = (status: string): "default" | "secondary" | "destructive" | "outline" => {
    if (status === "completed") return "secondary"
    if (status === "running") return "default"
    if (status === "failed") return "destructive"
    return "outline"
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-sm text-muted-foreground">加载中...</div>
      </div>
    )
  }

  const statCards = [
    { label: "总任务数", value: stats.totalTasks, icon: ClipboardList },
    { label: "活跃任务", value: stats.activeTasks, icon: TrendingUp },
    { label: "已完成", value: stats.completedThisMonth, icon: Calendar },
    { label: "待处理", value: stats.pending, icon: AlertTriangle },
  ]

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">工作台</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {new Date().toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long" })}
          </p>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((stat, index) => (
          <Card key={index} className="bg-card border-border">
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-3">
                <stat.icon className="w-5 h-5 text-muted-foreground" />
              </div>
              <div className="text-2xl font-bold text-foreground mb-1">{stat.value}</div>
              <div className="text-xs text-muted-foreground">{stat.label}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Recent Tasks */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between pb-4">
          <CardTitle className="text-base font-semibold">最近任务</CardTitle>
          <Button variant="ghost" size="sm" className="text-xs" onClick={() => window.location.href = "/tasks"}>
            查看全部
            <ArrowUpRight className="w-3 h-3 ml-1" />
          </Button>
        </CardHeader>
        <CardContent>
          {recentTasks.length === 0 ? (
            <div className="text-center py-8 text-sm text-muted-foreground">
              暂无任务，去创建第一个任务吧
            </div>
          ) : (
            <div className="space-y-3">
              {recentTasks.map((task) => (
                <div
                  key={task.id}
                  className="flex items-center justify-between p-3 rounded-lg bg-surface-container-low hover:bg-surface-container transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                      <ClipboardList className="w-4 h-4 text-primary" />
                    </div>
                    <div>
                      <div className="text-sm font-medium text-foreground">{task.title}</div>
                      <div className="text-xs text-muted-foreground">ID: {task.id}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant={statusVariant(task.status)} className="text-xs">
                      {statusLabel[task.status] || task.status}
                    </Badge>
                    <span className="text-xs text-muted-foreground flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {new Date(task.created_at).toLocaleDateString("zh-CN")}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
