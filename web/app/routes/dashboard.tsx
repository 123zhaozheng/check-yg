import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Progress } from "~/components/ui/progress"
import {
  ClipboardList,
  TrendingUp,
  Calendar,
  Users,
  AlertTriangle,
  ArrowUpRight,
  Clock,
  CheckCircle2,
} from "lucide-react"

// Mock data - will be replaced with API calls
const stats = [
  { label: "总任务数", value: "124", change: "+12%", icon: ClipboardList, trend: "up" },
  { label: "活跃任务", value: "18", change: "+3", icon: TrendingUp, trend: "up" },
  { label: "本月完成", value: "86", change: "较上月 +15%", icon: Calendar, trend: "up" },
  { label: "总客户数", value: "852", change: "+28", icon: Users, trend: "up" },
  { label: "待处理", value: "7", change: "紧急", icon: AlertTriangle, trend: "down" },
]

const recentTasks = [
  { id: "T-2024-001", customer: "张三科技有限公司", status: "进行中", priority: "高", time: "2小时前" },
  { id: "T-2024-002", customer: "李四贸易公司", status: "待审核", priority: "中", time: "5小时前" },
  { id: "T-2024-003", customer: "王五实业集团", status: "已完成", priority: "低", time: "1天前" },
  { id: "T-2024-004", customer: "赵六投资有限公司", status: "进行中", priority: "高", time: "1天前" },
  { id: "T-2024-005", customer: "孙七 Manufacturing", status: "待处理", priority: "紧急", time: "2天前" },
]

const auditProgress = [
  { name: "Q1 2024 审计", progress: 85, status: "进行中" },
  { name: "年度合规检查", progress: 60, status: "进行中" },
  { name: "客户风险评估", progress: 100, status: "已完成" },
]

const priorities = [
  { id: "P-001", title: "高风险客户复审", deadline: "2024-03-15", status: "紧急" },
  { id: "P-002", title: "季度报告提交", deadline: "2024-03-20", status: "重要" },
  { id: "P-003", title: "新客户尽职调查", deadline: "2024-03-25", status: "普通" },
]

export default function Dashboard() {
  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">早上好，管理员</h1>
          <p className="text-sm text-muted-foreground mt-1">2024年3月12日，星期二</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">
            <Calendar className="w-4 h-4 mr-2" />
            本周工作计划
          </Button>
          <Button size="sm">查看审计报告</Button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        {stats.map((stat, index) => (
          <Card key={index} className="bg-card border-border">
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-3">
                <stat.icon className="w-5 h-5 text-muted-foreground" />
                <span
                  className={`text-xs font-medium ${
                    stat.trend === "up" ? "text-success" : "text-destructive"
                  }`}
                >
                  {stat.change}
                </span>
              </div>
              <div className="text-2xl font-bold text-foreground mb-1">{stat.value}</div>
              <div className="text-xs text-muted-foreground">{stat.label}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Tasks */}
        <Card className="lg:col-span-2 bg-card border-border">
          <CardHeader className="flex flex-row items-center justify-between pb-4">
            <CardTitle className="text-base font-semibold">最近任务</CardTitle>
            <Button variant="ghost" size="sm" className="text-xs">
              查看全部
              <ArrowUpRight className="w-3 h-3 ml-1" />
            </Button>
          </CardHeader>
          <CardContent>
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
                      <div className="text-sm font-medium text-foreground">{task.customer}</div>
                      <div className="text-xs text-muted-foreground">{task.id}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge
                      variant={
                        task.status === "已完成"
                          ? "secondary"
                          : task.status === "进行中"
                          ? "default"
                          : task.status === "待审核"
                          ? "outline"
                          : "destructive"
                      }
                      className="text-xs"
                    >
                      {task.status}
                    </Badge>
                    <Badge
                      variant={
                        task.priority === "紧急"
                          ? "destructive"
                          : task.priority === "高"
                          ? "default"
                          : task.priority === "中"
                          ? "outline"
                          : "secondary"
                      }
                      className="text-xs"
                    >
                      {task.priority}
                    </Badge>
                    <span className="text-xs text-muted-foreground flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {task.time}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Audit Progress */}
        <Card className="bg-card border-border">
          <CardHeader className="pb-4">
            <CardTitle className="text-base font-semibold">审计进度</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {auditProgress.map((item, index) => (
              <div key={index} className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-foreground">{item.name}</span>
                  <span className="text-muted-foreground">{item.progress}%</span>
                </div>
                <Progress value={item.progress} className="h-2" />
                <div className="text-xs text-muted-foreground">{item.status}</div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Priorities */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between pb-4">
          <CardTitle className="text-base font-semibold">审计优先级</CardTitle>
          <Button variant="ghost" size="sm" className="text-xs">
            管理优先级
            <ArrowUpRight className="w-3 h-3 ml-1" />
          </Button>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {priorities.map((priority) => (
              <div
                key={priority.id}
                className="p-4 rounded-lg bg-surface-container-low border border-border"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="text-sm font-medium text-foreground">{priority.title}</div>
                  <Badge
                    variant={
                      priority.status === "紧急"
                        ? "destructive"
                        : priority.status === "重要"
                        ? "default"
                        : "secondary"
                    }
                    className="text-xs"
                  >
                    {priority.status}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground flex items-center gap-1">
                  <Calendar className="w-3 h-3" />
                  截止: {priority.deadline}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
