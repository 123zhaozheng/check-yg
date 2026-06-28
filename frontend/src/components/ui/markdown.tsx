import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { cn } from "@/lib/utils"

/**
 * Markdown 渲染（单色设计系统）.
 *
 * AI 追问气泡 + 维度详情 detail_text 都用：AI 回复天然带 Markdown（标题/列表/
 * 加粗/代码/表格），纯 ``whitespace-pre-wrap`` 会丢结构、表格挤成一团。
 *
 * 单色硬底线（docs §C4 / global.css）：禁红黄绿，全 ink-* 灰阶；排版紧凑适配窄气泡。
 * remark-gfm 启用表格 / 删除线 / 任务列表 / 自动链接。
 *
 * 样式全走 Tailwind 任意变体（``[&_p]:``），不引 typography 插件，零额外依赖。
 */
export function Markdown({
  children,
  className,
}: {
  children: string
  className?: string
}) {
  return (
    <div
      className={cn(
        // 正文：ink-900，紧凑行距，元素间小间距.
        "text-sm leading-relaxed text-ink-900",
        "[&_p]:my-1.5 first:[&_p]:mt-0 last:[&_p]:mb-0",
        // 标题.
        "[&_h1]:mt-2 [&_h1]:mb-1.5 [&_h1]:text-base [&_h1]:font-bold",
        "[&_h2]:mt-2 [&_h2]:mb-1.5 [&_h2]:text-sm [&_h2]:font-bold",
        "[&_h3]:mt-1.5 [&_h3]:mb-1 [&_h3]:text-sm [&_h3]:font-semibold",
        "[&_h4]:mt-1.5 [&_h4]:mb-1 [&_h4]:text-sm [&_h4]:font-semibold",
        // 强调 / 删除线.
        "[&_strong]:font-semibold",
        "[&_em]:italic",
        "[&_del]:text-ink-600 [&_del]:line-through",
        // 列表（pl-5 = 1.25rem，避开非标准 4.5 间距）.
        "[&_ul]:my-1.5 [&_ul]:list-disc [&_ul]:pl-5",
        "[&_ol]:my-1.5 [&_ol]:list-decimal [&_ol]:pl-5",
        "[&_li]:my-0.5 [&_li]:marker:text-ink-700",
        "[&_li>p]:my-0",
        // 任务列表项：去项目符号.
        "[&_li:has(>input)]:list-none [&_li:has(>input)]:pl-0",
        "[&_input[type=checkbox]]:mr-1.5 [&_input[type=checkbox]]:align-middle",
        // 链接.
        "[&_a]:font-medium [&_a]:text-ink-900 [&_a]:underline [&_a]:underline-offset-2",
        "[&_a]:hover:text-ink-700",
        // 内联代码.
        "[&_code]:rounded-[var(--radius-DEFAULT)] [&_code]:bg-ink-300 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.85em]",
        // 代码块.
        "[&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-[var(--radius-lg)] [&_pre]:bg-ink-300 [&_pre]:p-2.5",
        "[&_pre_code]:block [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-[0.85em]",
        // 引用.
        "[&_blockquote]:my-1.5 [&_blockquote]:border-l-2 [&_blockquote]:border-ink-500 [&_blockquote]:pl-2.5 [&_blockquote]:text-ink-700",
        "[&_blockquote>p]:my-0",
        // 表格（窄气泡用 text-xs）.
        "[&_table]:my-2 [&_table]:block [&_table]:w-full [&_table]:overflow-x-auto [&_table]:border-collapse [&_table]:text-xs",
        "[&_th]:border [&_th]:border-ink-400 [&_th]:bg-ink-200 [&_th]:px-1.5 [&_th]:py-1 [&_th]:text-left [&_th]:font-semibold",
        "[&_td]:border [&_td]:border-ink-400 [&_td]:px-1.5 [&_td]:py-1 [&_td]:align-top",
        // 分隔线.
        "[&_hr]:my-2 [&_hr]:border-ink-400",
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  )
}
