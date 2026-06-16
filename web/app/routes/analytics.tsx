import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import { Badge } from "~/components/ui/badge"
import { api } from "~/lib/api"
import {
  BarChart3,
  CheckCircle2,
  Clock,
  FileText,
  Pause,
  XCircle,
} from "lucide-react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

interface TaskItem {
  id: number
  title: string
  status: string
  created_at: string
  completed_at: string | null
}

const statusMeta: Record<string, { label: string; icon: typeof FileText; color: string }> = {
  draft: { label: "草稿", icon: FileText, color: "#94a3b8" },
  running: { label: "进行中", icon: Clock, color: "#bec6e0" },
  paused: { label: "已暂停", icon: Pause, color: "#f59e0b" },
  completed: { label: "已完成", icon: CheckCircle2, color: "#10b981" },
  failed: { label: "失败", icon: XCircle, color: "#ef4444" },
  cancelled: { label: "已取消", icon: XCircle, color: "#64748b" },
}

export default function AnalyticsPage() {
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchData() {
      setLoading(true)
      try {
        const res = await api.get<{ items: TaskItem[]; total: number }>("/api/tasks/", {
          page: "1",
          page_size: "100",
        })
        setTasks(res.items)
        setTotal(res.total)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  const counts = tasks.reduce<Record<string, number>>((acc, task) => {
    acc[task.status] = (acc[task.status] || 0) + 1
    return acc
  }, {})

  const chartData = Object.entries(statusMeta).map(([status, meta]) => ({
    status,
    label: meta.label,
    value: counts[status] || 0,
    fill: meta.color,
  }))

  const completed = counts.completed || 0
  const running = counts.running || 0
  const failed = counts.failed || 0
  const completionRate = total > 0 ? Math.round((completed / total) * 100) : 0

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-sm text-muted-foreground">加载中...</div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">数据分析</h1>
        <p className="text-sm text-muted-foreground mt-1">
          基于当前后端任务数据的执行概览，不展示未接入的模拟金额或客户排行。
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "总任务数", value: total, icon: BarChart3 },
          { label: "进行中", value: running, icon: Clock },
          { label: "已完成", value: completed, icon: CheckCircle2 },
          { label: "失败", value: failed, icon: XCircle },
        ].map((stat) => (
          <Card key={stat.label} className="bg-card border-border">
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 bg-card border-border">
          <CardHeader className="pb-4">
            <CardTitle className="text-base font-semibold">任务状态分布</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
                  <XAxis dataKey="label" stroke="#8e9193" fontSize={10} />
                  <YAxis stroke="#8e9193" fontSize={10} allowDecimals={false} />
                  <Tooltip contentStyle={{ backgroundColor: "#1c1b1b", border: "1px solid #444749", borderRadius: "8px" }} />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardHeader className="pb-4">
            <CardTitle className="text-base font-semibold">完成率</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-4xl font-bold text-foreground">{completionRate}%</div>
            <p className="mt-2 text-sm text-muted-foreground">
              {completed} / {total} 个任务已完成
            </p>
            <div className="mt-6 space-y-2">
              {chartData.map((item) => (
                <div key={item.status} className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{item.label}</span>
                  <Badge variant="outline">{item.value}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="bg-card border-border">
        <CardHeader className="pb-4">
          <CardTitle className="text-base font-semibold">最近任务</CardTitle>
        </CardHeader>
        <CardContent>
          {tasks.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">暂无任务数据</div>
          ) : (
            <div className="space-y-3">
              {tasks.slice(0, 8).map((task) => {
                const meta = statusMeta[task.status] || statusMeta.draft
                return (
                  <div key={task.id} className="flex items-center justify-between rounded-lg bg-surface-container-low p-3">
                    <div>
                      <div className="text-sm font-medium text-foreground">{task.title}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {new Date(task.created_at).toLocaleString("zh-CN")}
                      </div>
                    </div>
                    <Badge variant={task.status === "failed" ? "destructive" : "outline"}>{meta.label}</Badge>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
