import React from "react"
import ReactDOM from "react-dom/client"
import { RouterProvider, createRouter } from "@tanstack/react-router"
import { QueryClientProvider } from "@tanstack/react-query"

import { queryClient } from "@/lib/query-client"
import { routeTree } from "@/routeTree.gen"

import "@/styles/global.css"

/** TanStack Router instance — cookie auth context carries the QueryClient. */
const router = createRouter({
  routeTree,
  defaultPreload: "intent",
  context: { queryClient },
  defaultNotFoundComponent: undefined,
})

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

const rootEl = document.getElementById("root")
if (!rootEl) {
  throw new Error("Root element #root not found")
}

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>,
)
