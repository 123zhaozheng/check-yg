import { createFileRoute } from "@tanstack/react-router"
import { PageHeader } from "@/components/layout/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"

/**
 * 设置 /settings (docs §D1).
 * Placeholder — S8 wires account / review params / channels / integrations tabs.
 */
export const Route = createFileRoute("/__authenticated/settings")({
  component: SettingsPage,
})

function SettingsPage() {
  return (
    <>
      <PageHeader
        title="设置"
        description="系统级配置：账户、审查参数、渠道与解析、集成与模型。"
        actions={<Button size="sm">保存</Button>}
      />

      <Card>
        <CardContent className="p-6">
          <h2 className="font-sans text-lg font-semibold text-ink-900">
            渠道与解析
          </h2>
          <p className="mt-1 text-sm text-ink-700">
            各渠道启用状态、MinerU/解析后端配置（地址、超时、重试）。
          </p>
          <div className="mt-6 space-y-6">
            <div>
              <label
                htmlFor="mineru-url"
                className="text-xs font-bold uppercase tracking-widest text-ink-600"
              >
                MinerU 服务地址
              </label>
              <Input
                id="mineru-url"
                defaultValue="http://localhost:8001"
                className="mt-2"
              />
            </div>
            <div>
              <label
                htmlFor="mineru-timeout"
                className="text-xs font-bold uppercase tracking-widest text-ink-600"
              >
                超时（秒）
              </label>
              <Input
                id="mineru-timeout"
                type="number"
                defaultValue="120"
                className="mt-2"
              />
            </div>
          </div>
        </CardContent>
      </Card>
    </>
  )
}
