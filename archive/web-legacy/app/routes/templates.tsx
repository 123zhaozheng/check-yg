import { Card, CardContent } from "~/components/ui/card"
import { FileText } from "lucide-react"

export default function TemplatesPage() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">模板</h1>
        <p className="text-sm text-muted-foreground mt-1">
          管理审计报告模板与导出格式
        </p>
      </div>

      <Card className="bg-card border-border">
        <CardContent className="p-8 text-center">
          <FileText className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-foreground mb-2">模板管理</h3>
          <p className="text-sm text-muted-foreground">
            模板功能将在后续版本中提供
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
