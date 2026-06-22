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
  Eye,
  EyeOff,
  TestTube,
  Save,
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
  const [mineruMode, setMineruMode] = useState("local")
  const [mineruUrl, setMineruUrl] = useState("")
  const [mineruPublicUrl, setMineruPublicUrl] = useState("")
  const [mineruPublicApiKey, setMineruPublicApiKey] = useState("")
  const [mineruTimeout, setMineruTimeout] = useState("300")
  const [llmBaseUrl, setLlmBaseUrl] = useState("")
  const [llmModelName, setLlmModelName] = useState("")
  const [llmApiKey, setLlmApiKey] = useState("")

  useEffect(() => {
    async function fetchSettings() {
      try {
        const settings = await api.get<SettingItem[]>("/api/settings/")
        const map: Record<string, string> = {}
        settings.forEach((s) => { map[s.key] = s.value })

        setMineruMode(map["mineru.mode"] || "local")
        setMineruUrl(map["mineru.url"] || "")
        setMineruPublicUrl(map["mineru.public_url"] || "")
        setMineruPublicApiKey(map["mineru.public_api_key"] || "")
        setMineruTimeout(map["mineru.timeout"] || "300")
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
        saveSetting("mineru.url", mineruUrl),
        saveSetting("mineru.public_url", mineruPublicUrl),
        saveSetting("mineru.public_api_key", mineruPublicApiKey),
        saveSetting("mineru.timeout", mineruTimeout),
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

  const handleTestConnection = async () => {
    const result = await api.post<{ ok: boolean; message: string }>("/api/settings/test-connection")
    if (result.ok) {
      toast.success(result.message || "连接测试通过")
    } else {
      toast.error(result.message || "连接测试失败")
    }
  }

  const tabs = [
    { id: "basic" as const, label: "基础", icon: Settings },
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
                      <Label className="text-xs text-muted-foreground">部署模式 (Mode)</Label>
                      <Select value={mineruMode} onValueChange={setMineruMode}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="local">Local (自托管服务)</SelectItem>
                          <SelectItem value="public">Public (公网 Agent)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">请求超时 (秒)</Label>
                      <Input
                        type="number"
                        value={mineruTimeout}
                        onChange={(e) => setMineruTimeout(e.target.value)}
                        className="bg-surface-container-low"
                        placeholder="300"
                      />
                    </div>
                  </div>
                  {mineruMode === "local" ? (
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">MinerU 服务地址 (URL)</Label>
                      <div className="relative">
                        <Server className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                          value={mineruUrl}
                          onChange={(e) => setMineruUrl(e.target.value)}
                          className="pl-9 bg-surface-container-low"
                          placeholder="http://localhost:8000"
                        />
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="space-y-2">
                        <Label className="text-xs text-muted-foreground">公网 Agent 地址 (Public URL)</Label>
                        <Input
                          value={mineruPublicUrl}
                          onChange={(e) => setMineruPublicUrl(e.target.value)}
                          className="bg-surface-container-low"
                          placeholder="https://mineru.net/api/v1/agent"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs text-muted-foreground">公网 API 密钥 (API Key)</Label>
                        <div className="relative">
                          <Key className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                          <Input
                            type={showApiKey ? "text" : "password"}
                            value={mineruPublicApiKey}
                            onChange={(e) => setMineruPublicApiKey(e.target.value)}
                            className="pl-9 pr-10 bg-surface-container-low"
                            placeholder="公网 MinerU API Key"
                          />
                          <button
                            type="button"
                            onClick={() => setShowApiKey(!showApiKey)}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                          >
                            {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>
                    </>
                  )}
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
                  MinerU 是文档解析引擎。Local 模式连接自托管服务，Public 模式通过公网 Agent 调用，需配置 API 密钥。
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
