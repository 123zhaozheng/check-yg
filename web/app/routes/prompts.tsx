import { Card, CardContent } from "~/components/ui/card"
import { MessageSquare } from "lucide-react"

export default function PromptsPage() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">提示词</h1>
        <p className="text-sm text-muted-foreground mt-1">
          管理 AI 审计提示词与指令模板
        </p>
      </div>

      <Card className="bg-card border-border">
        <CardContent className="p-8 text-center">
          <MessageSquare className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-foreground mb-2">提示词管理</h3>
          <p className="text-sm text-muted-foreground">
            提示词功能将在后续版本中提供
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
