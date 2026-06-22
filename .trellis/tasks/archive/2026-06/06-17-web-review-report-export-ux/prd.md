# Complete Review Report Export Frontend Workflow

## Goal

Expose the existing backend review, report, Excel export, bundle export, and download capabilities in the React UI so a user can complete the audit workflow end to end after extraction finishes.

## Problem

The backend already exposes review/report/export APIs, but the frontend task page only supports extraction controls. A completed task has no obvious next action, which makes the web app feel like a demo despite having backend services.

## Scope

- Add completed-task actions in `web/app/routes/tasks.tsx` or a task detail view:
  - Run review.
  - Choose customer list when needed.
  - Generate report.
  - Export Excel.
  - Export skill bundle ZIP.
  - Download generated artifacts.
- Add API client helpers/types if useful, without duplicating request logic unnecessarily.
- Show actionable loading states and error messages for each step.
- Avoid fake metrics or placeholder success states; every button must call a backend API or be hidden.
- Keep current task create/start/pause/resume/cancel flows working.

## Reference Files

- `backend/app/routers/reviews.py`
- `backend/app/routers/reports.py`
- `backend/app/routers/exports.py`
- `backend/app/schemas/review.py`
- `web/app/routes/tasks.tsx`
- `web/app/routes/customers.tsx`
- `web/app/lib/api.ts`

## Acceptance Criteria

- From a completed task, user can run review using a selected customer list.
- User can generate a report and download it.
- User can export Excel and bundle ZIP and download both.
- Buttons are never inert; disabled states explain the missing prerequisite, such as no customer list.
- Frontend typecheck passes.
- Add focused frontend/API tests if the project has a test pattern; otherwise verify manually and document the tested paths.

## Out of Scope

- Redesigning analytics/dashboard pages.
- Reworking backend review/report/export algorithms unless a blocking API bug is found.
