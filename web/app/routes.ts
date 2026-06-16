import {
  type RouteConfig,
  index,
  route,
} from "@react-router/dev/routes"

export default [
  route("login", "routes/login.tsx"),
  route("", "routes/_app.tsx", [
    index("routes/home.tsx"),
    route("dashboard", "routes/dashboard.tsx"),
    route("tasks", "routes/tasks.tsx"),
    route("customers", "routes/customers.tsx"),
    route("analytics", "routes/analytics.tsx"),
    route("settings", "routes/settings.tsx"),
    route("templates", "routes/templates.tsx"),
    route("prompts", "routes/prompts.tsx"),
    route("logs", "routes/logs.tsx"),
  ]),
] satisfies RouteConfig
