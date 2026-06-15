import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "~/components/ui/card"
import { Button } from "~/components/ui/button"
import { Input } from "~/components/ui/input"
import { Label } from "~/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import { api } from "~/lib/api"
import { toast } from "sonner"
import {
  Settings,
  Cpu,
  Shield,
  Eye,
  EyeOff,
  TestTube,
  Save,
  CheckCircle2,
  Info,
  Server,
  Key,
} from "lucide-react"

type SettingsTab = "basic" | "ai" | "security"

interface SettingItem {
  key: string
  value: string
  category: string
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("basic")
  const [showApiKey, setShowApiKey] = useState(false)
  const [saving, setSaving] = useState(false)

  // Form state
  const [mineruMode, setMineruMode] = useState("fast")
  const [mineruConcurrency, setMineruConcurrency] = useState("16")
  const [mineruEndpoint, setMineruEndpoint] = useState("")
  const [llmBaseUrl, setLlmBaseUrl] = useState("")
  const [llmModelName, setLlmModelName] = useState("")
  const [llmApiKey, setLlmApiKey] = useState("")

  useEffect(() => {
    async function fetchSettings() {
      try {
        const settings = await api.get<SettingItem[]>("/api/settings/")
        const map: Record<string, string> = {}
        settings.forEach((s) => { map[s.key] = s.value })

        setMineruMode(map["mineru.mode"] || "fast")
        setMineruConcurrency(map["mineru.max_concurrency"] || "16")
        setMineruEndpoint(map["mineru.api_endpoint"] || "")
        setLlmBaseUrl(map["llm.base_url"] || "")
        setLlmModelName(map["llm.model_name"] || "")
        setLlmApiKey(map["llm.api_key"] || "")
      } catch {
        // Settings not available yet
      }
    }
    fetchSettings()
  }, [])

  async function saveSetting(key: string, value: string) {
    try {
      await api.put(`/api/settings/${key}`, { value })
    } catch {
      toast.error(`保存 ${key} 失败`)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await Promise.all([
        saveSetting("mineru.mode", mineruMode),
        saveSetting("mineru.max_concurrency", mineruConcurrency),
        saveSetting("mineru.api_endpoint", mineruEndpoint),
        saveSetting("llm.base_url", llmBaseUrl),
        saveSetting("llm.model_name", llmModelName),
        saveSetting("llm.api_key", llmApiKey),
      ])
      toast.success("设置已保存")
    } catch {
      toast.error("保存失败")
    } finally {
      setSaving(false)
    }
  }

  const handleTestConnection = () => {
    toast.info("测试连接功能开发中")
  }

  const tabs = [
    { id: "basic" as const, label: "基础", icon: Settings },
    { id: "ai" as const, label: "AI", icon: Cpu },
    { id: "security" as const, label: "安全", icon: Shield },
  ]

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-foreground">设置</h1>
        <p className="text-sm text-muted-foreground mt-1">
          配置系统参数、AI 模型和安全选项
        </p>
      </div>

      <div className="flex gap-6">
        {/* Sidebar Tabs */}
        <div className="w-48 shrink-0 space-y-1">
          <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3 px-3">
            设置分类
          </div>
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                activeTab === tab.id
                  ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 space-y-6">
          {activeTab === "basic" && (
            <>
              {/* MinerU Config */}
              <Card className="bg-card border-border">
                <CardHeader>
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-surface-container-high flex items-center justify-center">
                      <Server className="w-5 h-5 text-foreground" />
                    </div>
                    <div>
                      <CardTitle className="text-base">MinerU 配置</CardTitle>
                      <CardDescription className="text-xs">
                        管理核心解析引擎的数据提取模式与连接端点
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">解析模式 (Mode)</Label>
                      <Select value={mineruMode} onValueChange={setMineruMode}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="fast">Fast (快速解析)</SelectItem>
                          <SelectItem value="precise">Precise (精确解析)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">最大并发数</Label>
                      <Input
                        type="number"
                        value={mineruConcurrency}
                        onChange={(e) => setMineruConcurrency(e.target.value)}
                        className="bg-surface-container-low"
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">API 端点 (URL)</Label>
                    <div className="relative">
                      <Server className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        value={mineruEndpoint}
                        onChange={(e) => setMineruEndpoint(e.target.value)}
                        className="pl-9 bg-surface-container-low"
                        placeholder="https://mineru.api.check-yg.com/v1"
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* LLM Config */}
              <Card className="bg-card border-border">
                <CardHeader>
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-surface-container-high flex items-center justify-center">
                      <Cpu className="w-5 h-5 text-foreground" />
                    </div>
                    <div>
                      <CardTitle className="text-base">LLM 大语言模型配置</CardTitle>
                      <CardDescription className="text-xs">
                        配置审计自动化的推理核心及验证身份
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">基础 URL (Base URL)</Label>
                      <Input
                        value={llmBaseUrl}
                        onChange={(e) => setLlmBaseUrl(e.target.value)}
                        className="bg-surface-container-low"
                        placeholder="https://api.openai.com/v1"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">模型名称 (Model Name)</Label>
                      <Input
                        value={llmModelName}
                        onChange={(e) => setLlmModelName(e.target.value)}
                        className="bg-surface-container-low"
                        placeholder="gpt-4-turbo-preview"
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">API 密钥 (API Key)</Label>
                    <div className="relative">
                      <Key className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        type={showApiKey ? "text" : "password"}
                        value={llmApiKey}
                        onChange={(e) => setLlmApiKey(e.target.value)}
                        className="pl-9 pr-10 bg-surface-container-low"
                        placeholder="sk-..."
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                      >
                        {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                    <p className="text-[10px] text-muted-foreground">
                      密钥在传输中已加密，仅用于授权请求。
                    </p>
                  </div>
                </CardContent>
              </Card>

              {/* Action Buttons */}
              <div className="flex items-center gap-3 pt-4 border-t border-border">
                <div className="ml-auto flex gap-2">
                  <Button variant="outline" onClick={handleTestConnection}>
                    <TestTube className="w-4 h-4 mr-2" />
                    测试连接
                  </Button>
                  <Button onClick={handleSave} disabled={saving}>
                    <Save className="w-4 h-4 mr-2" />
                    {saving ? "保存中..." : "保存设置"}
                  </Button>
                </div>
              </div>
            </>
          )}

          {activeTab === "ai" && (
            <Card className="bg-card border-border">
              <CardContent className="p-8 text-center">
                <Cpu className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-foreground mb-2">AI 配置</h3>
                <p className="text-sm text-muted-foreground">
                  AI 相关配置将在后续版本中提供
                </p>
              </CardContent>
            </Card>
          )}

          {activeTab === "security" && (
            <Card className="bg-card border-border">
              <CardContent className="p-8 text-center">
                <Shield className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-foreground mb-2">安全配置</h3>
                <p className="text-sm text-muted-foreground">
                  安全相关配置将在后续版本中提供
                </p>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Assistant Panel */}
        <div className="w-64 shrink-0 hidden lg:block">
          <Card className="bg-card border-border sticky top-6">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Info className="w-4 h-4 text-warning" />
                <CardTitle className="text-sm">配置助手</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <h4 className="text-xs font-semibold text-foreground mb-1">关于 MinerU</h4>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  MinerU 是我们自研的高性能 PDF 解析框架。建议在处理含有大量表格的审计报告时开启 Precise 模式。
                </p>
              </div>
              <div className="h-px bg-border" />
              <div>
                <h4 className="text-xs font-semibold text-foreground mb-1">模型建议</h4>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  建议使用上下文窗口大于 128k 的模型，以确保长篇审计报告的逻辑连贯性。
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
