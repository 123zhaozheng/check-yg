import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import { Badge } from "~/components/ui/badge"
import {
  BarChart3,
  FileText,
  Database,
  DollarSign,
  Users,
  TrendingUp,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  CheckCircle2,
  Zap,
} from "lucide-react"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
} from "recharts"

// Mock data
const dailyTrend = [
  { date: "2/12", value: 45 },
  { date: "2/13", value: 52 },
  { date: "2/14", value: 48 },
  { date: "2/15", value: 61 },
  { date: "2/16", value: 55 },
  { date: "2/17", value: 67 },
  { date: "2/18", value: 72 },
  { date: "2/19", value: 68 },
  { date: "2/20", value: 75 },
  { date: "2/21", value: 82 },
  { date: "2/22", value: 78 },
  { date: "2/23", value: 85 },
  { date: "2/24", value: 90 },
  { date: "2/25", value: 88 },
  { date: "2/26", value: 95 },
  { date: "2/27", value: 92 },
  { date: "2/28", value: 98 },
  { date: "3/1", value: 105 },
  { date: "3/2", value: 102 },
  { date: "3/3", value: 110 },
  { date: "3/4", value: 108 },
  { date: "3/5", value: 115 },
  { date: "3/6", value: 112 },
  { date: "3/7", value: 120 },
  { date: "3/8", value: 118 },
  { date: "3/9", value: 125 },
  { date: "3/10", value: 122 },
  { date: "3/11", value: 130 },
  { date: "3/12", value: 128 },
]

const topCustomers = [
  { name: "某大型央企集团", amount: "¥2,340,000", change: "+12%", trend: "up" as const },
  { name: "某金融机构", amount: "¥1,890,000", change: "+8%", trend: "up" as const },
  { name: "某上市公司", amount: "¥1,560,000", change: "-3%", trend: "down" as const },
  { name: "某外资企业", amount: "¥1,230,000", change: "+15%", trend: "up" as const },
  { name: "某贸易公司", amount: "¥980,000", change: "+5%", trend: "up" as const },
]

const processingTypes = [
  { name: "PDF解析", value: 45, color: "#bec6e0" },
  { name: "Excel解析", value: 30, color: "#10B981" },
  { name: "Word解析", value: 15, color: "#F59E0B" },
  { name: "HTML解析", value: 10, color: "#EF4444" },
]

const avgProcessingTime = [
  { date: "2/12", time: 2.1 },
  { date: "2/19", time: 1.9 },
  { date: "2/26", time: 1.7 },
  { date: "3/4", time: 1.5 },
  { date: "3/11", time: 1.3 },
]

const aiInsights = [
  {
    title: "处理效率提升",
    description: "本月平均处理时间较上月缩短 18%",
    icon: TrendingUp,
    color: "text-success",
  },
  {
    title: "高风险客户增加",
    description: "本周新增 3 个高风险客户标记",
    icon: AlertTriangle,
    color: "text-destructive",
  },
  {
    title: "自动化率提升",
    description: "AI 自动分类准确率达 94.2%",
    icon: Zap,
    color: "text-warning",
  },
]

export default function AnalyticsPage() {
  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-foreground">数据分析</h1>
        <p className="text-sm text-muted-foreground mt-1">
          全局数据概览与趋势分析
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-card border-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <FileText className="w-5 h-5 text-muted-foreground" />
              <span className="text-xs font-medium text-success flex items-center gap-1">
                <ArrowUpRight className="w-3 h-3" />
                +12%
              </span>
            </div>
            <div className="text-2xl font-bold text-foreground mb-1">12,908</div>
            <div className="text-xs text-muted-foreground">总文档数</div>
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <Database className="w-5 h-5 text-muted-foreground" />
              <span className="text-xs font-medium text-success flex items-center gap-1">
                <ArrowUpRight className="w-3 h-3" />
                +8%
              </span>
            </div>
            <div className="text-2xl font-bold text-foreground mb-1">894,031</div>
            <div className="text-xs text-muted-foreground">总记录数</div>
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <DollarSign className="w-5 h-5 text-muted-foreground" />
              <span className="text-xs font-medium text-success flex items-center gap-1">
                <ArrowUpRight className="w-3 h-3" />
                +15%
              </span>
            </div>
            <div className="text-2xl font-bold text-foreground mb-1">¥42.18M</div>
            <div className="text-xs text-muted-foreground">总金额</div>
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <Users className="w-5 h-5 text-muted-foreground" />
              <span className="text-xs font-medium text-destructive flex items-center gap-1">
                <ArrowDownRight className="w-3 h-3" />
                -2%
              </span>
            </div>
            <div className="text-2xl font-bold text-warning mb-1">284</div>
            <div className="text-xs text-muted-foreground">总客户数</div>
          </CardContent>
        </Card>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Daily Trend Chart */}
        <Card className="lg:col-span-2 bg-card border-border">
          <CardHeader className="pb-4">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base font-semibold">每日处理趋势</CardTitle>
                <p className="text-xs text-muted-foreground mt-1">
                  最近 30 天文档处理量变化趋势
                </p>
              </div>
              <Badge variant="outline" className="text-xs">
                最近 30 天
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={dailyTrend}>
                  <defs>
                    <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#bec6e0" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#bec6e0" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
                  <XAxis dataKey="date" stroke="#8e9193" fontSize={10} />
                  <YAxis stroke="#8e9193" fontSize={10} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#1c1b1b",
                      border: "1px solid #444749",
                      borderRadius: "8px",
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#bec6e0"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#colorValue)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Processing Types */}
        <Card className="bg-card border-border">
          <CardHeader className="pb-4">
            <CardTitle className="text-base font-semibold">处理类型分布</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[200px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={processingTypes}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    {processingTypes.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#1c1b1b",
                      border: "1px solid #444749",
                      borderRadius: "8px",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-2 mt-4">
              {processingTypes.map((type) => (
                <div key={type.name} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: type.color }}
                    />
                    <span className="text-foreground">{type.name}</span>
                  </div>
                  <span className="text-muted-foreground">{type.value}%</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Second Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Top Customers */}
        <Card className="lg:col-span-2 bg-card border-border">
          <CardHeader className="flex flex-row items-center justify-between pb-4">
            <CardTitle className="text-base font-semibold">客户参考 Top 10</CardTitle>
            <Badge variant="outline" className="text-xs">
              按金额排序
            </Badge>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {topCustomers.map((customer, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-3 rounded-lg bg-surface-container-low hover:bg-surface-container transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center text-xs font-bold text-primary">
                      {index + 1}
                    </div>
                    <div>
                      <div className="text-sm font-medium text-foreground">{customer.name}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-sm text-foreground">{customer.amount}</span>
                    <span
                      className={`text-xs font-medium flex items-center gap-1 ${
                        customer.trend === "up" ? "text-success" : "text-destructive"
                      }`}
                    >
                      {customer.trend === "up" ? (
                        <ArrowUpRight className="w-3 h-3" />
                      ) : (
                        <ArrowDownRight className="w-3 h-3" />
                      )}
                      {customer.change}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Avg Processing Time */}
        <Card className="bg-card border-border">
          <CardHeader className="pb-4">
            <CardTitle className="text-base font-semibold">平均处理时间</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">单位: 小时</p>
          </CardHeader>
          <CardContent>
            <div className="h-[200px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={avgProcessingTime}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
                  <XAxis dataKey="date" stroke="#8e9193" fontSize={10} />
                  <YAxis stroke="#8e9193" fontSize={10} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#1c1b1b",
                      border: "1px solid #444749",
                      borderRadius: "8px",
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="time"
                    stroke="#10B981"
                    strokeWidth={2}
                    dot={{ fill: "#10B981", r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* AI Insights */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between pb-4">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-warning" />
            <CardTitle className="text-base font-semibold">AI 洞察</CardTitle>
          </div>
          <Badge variant="outline" className="text-xs">
            自动生成
          </Badge>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {aiInsights.map((insight, index) => (
              <div
                key={index}
                className="p-4 rounded-lg bg-surface-container-low border border-border"
              >
                <div className="flex items-start gap-3">
                  <insight.icon className={`w-5 h-5 ${insight.color} shrink-0 mt-0.5`} />
                  <div>
                    <div className="text-sm font-medium text-foreground mb-1">
                      {insight.title}
                    </div>
                    <div className="text-xs text-muted-foreground">{insight.description}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
