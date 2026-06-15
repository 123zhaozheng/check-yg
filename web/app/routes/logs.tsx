import { Card, CardContent } from "~/components/ui/card"
import { ScrollText } from "lucide-react"

export default function LogsPage() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">日志</h1>
        <p className="text-sm text-muted-foreground mt-1">
          查看系统操作日志与审计追踪记录
        </p>
      </div>

      <Card className="bg-card border-border">
        <CardContent className="p-8 text-center">
          <ScrollText className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-foreground mb-2">日志查看</h3>
          <p className="text-sm text-muted-foreground">
            日志功能将在后续版本中提供
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
