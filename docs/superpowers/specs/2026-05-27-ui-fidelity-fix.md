# UI Fidelity Fix — Exact Autogen-Studio Replication

**Date**: 2026-05-27
**Status**: Approved
**Reference**: `ref/autogen-main/python/packages/autogen-studio/frontend/`

## Goal

Achieve 99% visual fidelity with autogen-studio by copying source files exactly, then making minimal modifications (3 types: Link import, nav items, remove auth).

## Files to Copy Exactly

| # | Source (autogen-studio) | Target (our frontend) | Modifications |
|---|---|---|---|
| 1 | `tailwind.config.js` | `tailwind.config.js` | None |
| 2 | `src/styles/global.css` | `src/index.css` | None |
| 3 | `src/components/layout.tsx` | `src/components/layout.tsx` | Gatsby Link → react-router-dom, remove auth/ProtectedRoute, add our Routes |
| 4 | `src/components/sidebar.tsx` | `src/components/sidebar.tsx` | Gatsby Link → react-router-dom, replace nav items (2 items: 课题管理, 对话) |
| 5 | `src/components/contentheader.tsx` | `src/components/contentheader.tsx` | Gatsby Link → react-router-dom |
| 6 | `src/components/footer.tsx` | `src/components/footer.tsx` | Change text to "Research Map Agent", remove version fetch |
| 7 | `src/components/icons.tsx` | `src/components/icons.tsx` | None |
| 8 | `src/hooks/provider.tsx` | `src/hooks/provider.tsx` | Remove auth context, keep dark mode only |
| 9 | `src/hooks/store.ts` | `src/hooks/store.ts` | Copy from autogen, extend with workspace/session/chat stores |

## Fixes to Our Custom Pages

- `WorkspacePage.tsx` — use correct autogen `bg-primary`/`text-primary`/`border-secondary` classes
- `ChatPage.tsx` + sub-components — use autogen classes
- `SettingsPage.tsx` — use autogen classes
- `MindMapPanel.tsx` — use autogen classes

## What Stays Unchanged

- Backend API (already correct)
- Chat dialog design (user-designed, not from autogen)
