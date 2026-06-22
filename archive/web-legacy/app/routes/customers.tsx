import { useEffect, useState } from "react"
import { Card, CardContent } from "~/components/ui/card"
import { Button } from "~/components/ui/button"
import { Input } from "~/components/ui/input"
import { Label } from "~/components/ui/label"
import { Textarea } from "~/components/ui/textarea"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog"
import { api } from "~/lib/api"
import { toast } from "sonner"
import {
  Users,
  Upload,
  Plus,
  Search,
  ChevronLeft,
  ChevronRight,
  Building2,
} from "lucide-react"

interface CustomerListItem {
  id: number
  name: string
  owner_id: number
  row_count: number
  created_at: string
}

export default function CustomersPage() {
  const [lists, setLists] = useState<CustomerListItem[]>([])
  const [total, setTotal] = useState(0)
  const [searchTerm, setSearchTerm] = useState("")
  const [currentPage, setCurrentPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ name: "", customersText: "" })
  const pageSize = 20

  async function fetchData() {
    setLoading(true)
    try {
      const params: Record<string, string> = {
        page: String(currentPage),
        page_size: String(pageSize),
      }
      if (searchTerm) params.search = searchTerm

      const res = await api.get<{ items: CustomerListItem[]; total: number }>("/api/customers/lists", params)
      setLists(res.items)
      setTotal(res.total)
    } catch {
      toast.error("客户名单加载失败")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [currentPage, searchTerm])

  function parseCustomerNames(text: string) {
    const seen = new Set<string>()
    return text
      .split(/[\n,，;；\t]+/)
      .map((item) => item.trim())
      .filter((item) => {
        if (!item || seen.has(item)) return false
        seen.add(item)
        return true
      })
  }

  async function handleCreateList() {
    const name = form.name.trim()
    const items = parseCustomerNames(form.customersText)
    if (!name) {
      toast.error("请输入名单名称")
      return
    }
    if (items.length === 0) {
      toast.error("请至少输入一个客户名称")
      return
    }

    setSaving(true)
    try {
      await api.post<CustomerListItem>("/api/customers/lists", { name, items })
      toast.success(`已创建名单，共 ${items.length} 名客户`)
      setCreateOpen(false)
      setForm({ name: "", customersText: "" })
      setCurrentPage(1)
      await fetchData()
    } catch {
      toast.error("客户名单创建失败")
    } finally {
      setSaving(false)
    }
  }

  async function handleImportFile(file: File | undefined) {
    if (!file) return
    const text = await file.text()
    setForm({
      name: form.name || file.name.replace(/\.[^.]+$/, ""),
      customersText: text,
    })
    setCreateOpen(true)
  }

  const totalPages = Math.ceil(total / pageSize) || 1
  const parsedCount = parseCustomerNames(form.customersText).length

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">客户名单</h1>
          <p className="text-sm text-muted-foreground mt-1">
            构建可复用的审计客户资产，用于流水匹配和报告分析
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <label>
              <input
                type="file"
                accept=".txt,.csv"
                className="hidden"
                onChange={(event) => {
                  handleImportFile(event.target.files?.[0])
                  event.target.value = ""
                }}
              />
              <Upload className="w-4 h-4 mr-2" />
              导入名单
            </label>
          </Button>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="w-4 h-4 mr-2" />
            新建名单
          </Button>
        </div>
      </div>

      <Card className="bg-card border-border">
        <CardContent className="p-4">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="搜索名单名称..."
              value={searchTerm}
              onChange={(event) => {
                setSearchTerm(event.target.value)
                setCurrentPage(1)
              }}
              className="pl-9"
            />
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
          加载中...
        </div>
      ) : lists.length === 0 ? (
        <Card className="bg-card border-border">
          <CardContent className="p-12 text-center">
            <Users className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-foreground mb-2">暂无客户名单</h3>
            <p className="text-sm text-muted-foreground mb-4">创建第一个客户名单开始使用</p>
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="w-4 h-4 mr-2" />
              新建名单
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {lists.map((list) => (
            <Card key={list.id} className="bg-card border-border hover:border-primary/50 transition-colors">
              <CardContent className="p-5">
                <div className="flex items-start gap-3 mb-4">
                  <div className="w-10 h-10 rounded-lg bg-surface-container-high flex items-center justify-center">
                    <Building2 className="w-5 h-5 text-foreground" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-foreground">{list.name}</h3>
                    <div className="text-xs text-muted-foreground mt-1">
                      创建于 {new Date(list.created_at).toLocaleDateString("zh-CN")}
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">客户总数</span>
                    <span className="font-semibold text-foreground">
                      {list.row_count.toLocaleString()} 名客户
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t border-border">
                    <span>所有者 ID: {list.owner_id}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          <Card
            className="bg-card border-border border-dashed transition-colors hover:border-primary/50 cursor-pointer"
            onClick={() => setCreateOpen(true)}
          >
            <CardContent className="p-5 flex flex-col items-center justify-center h-full min-h-[200px]">
              <div className="w-12 h-12 rounded-full bg-surface-container-high flex items-center justify-center mb-3">
                <Plus className="w-6 h-6 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground">新建客户名单</p>
            </CardContent>
          </Card>
        </div>
      )}

      {total > 0 && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-muted-foreground">
            共 {total} 个名单
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => i + 1).map((page) => (
              <Button
                key={page}
                variant={page === currentPage ? "default" : "outline"}
                size="icon"
                onClick={() => setCurrentPage(page)}
                className="w-8 h-8"
              >
                {page}
              </Button>
            ))}
            <Button
              variant="outline"
              size="icon"
              onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage === totalPages}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>新建客户名单</DialogTitle>
            <DialogDescription>
              每行输入一个客户名称，也可以用逗号、分号或制表符分隔；保存时会自动去重。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>名单名称</Label>
              <Input
                value={form.name}
                onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="例如：6月重点客户名单"
              />
            </div>
            <div className="space-y-2">
              <Label>客户名称</Label>
              <Textarea
                value={form.customersText}
                onChange={(event) => setForm((prev) => ({ ...prev, customersText: event.target.value }))}
                placeholder={"张三\n李四\n王五"}
                className="min-h-48"
              />
              <p className="text-xs text-muted-foreground">
                当前识别 {parsedCount} 名客户。
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} disabled={saving}>
              取消
            </Button>
            <Button onClick={handleCreateList} disabled={saving}>
              {saving ? "保存中..." : "保存名单"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
