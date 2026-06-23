import { createFileRoute, Link } from "@tanstack/react-router"
import { Button } from "@/components/ui/button"

/**
 * 404 / (docs §D3).
 * Large bold 404 + explanation + return-to-dashboard primary button +
 * go-back secondary button. Error in black/white — no red panic (单色原则).
 */
export const Route = createFileRoute("/$")({
  component: NotFoundPage,
})

function NotFoundPage() {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-6 bg-ink-200 px-6 text-center">
      <div className="font-sans text-8xl font-bold leading-none text-ink-900">
        404
      </div>
      <p className="max-w-md text-sm text-ink-700">
        未找到该页面。它可能已被移动、归档，或您没有访问权限。
      </p>
      <div className="flex items-center gap-3">
        <Button onClick={() => window.history.back()} variant="secondary">
          返回上一页
        </Button>
        <Link to="/">
          <Button>返回工作台</Button>
        </Link>
      </div>
    </div>
  )
}
