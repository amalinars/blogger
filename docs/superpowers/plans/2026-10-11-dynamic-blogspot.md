# Dynamic Next.js Blogspot (Chronicle) Implementation Plan

> **For agentic workers:** Dynamic full-stack English editorial blog platform built with Next.js (FE + BE unified), zero slop, high-craft editorial design, SQLite/file-backed persistent storage, and interactive CMS studio.

**Goal:** Build a feature-complete, dynamic blogspot publication named "Chronicle" with rich reader views, dynamic search/filters, claps, comments, archive, and CMS studio for publishing and managing posts.

**Tech Stack:**
- Framework: Next.js 16 (App Router) + React 19 + TypeScript
- Styling: Tailwind CSS v4 + Custom Editorial Tokens (Serif headlines, Parchment/Ink palettes)
- Storage: Persistent JSON database with atomic writes (`src/lib/db.ts`)
- Libraries: `lucide-react`, `canvas-confetti`, `marked`
- Quality: Visual excellence, responsive, zero-slop typography and interactions.

---

### Task 1: Core Data Models, Types, and Database Layer
- Files: `src/lib/types.ts`, `src/lib/db.ts`, `src/lib/seed-data.ts`
- Functions: CRUD for posts, comments, categories, archives, stats, claps, views.

### Task 2: API Endpoints (Backend in Next.js App Router)
- Files:
  - `src/app/api/posts/route.ts` (GET all with filters, POST create)
  - `src/app/api/posts/[id]/route.ts` (GET by slug/id, PUT update, DELETE)
  - `src/app/api/posts/[id]/clap/route.ts` (POST clap)
  - `src/app/api/posts/[id]/comments/route.ts` (GET comments, POST comment)
  - `src/app/api/seed/route.ts` (POST reset/seed)
  - `src/app/api/stats/route.ts` (GET analytics)

### Task 3: Design System, Layout, and Fonts
- Files: `src/app/layout.tsx`, `src/app/globals.css`, `src/components/Navbar.tsx`, `src/components/Footer.tsx`
- Setup: Google Fonts (Newsreader serif + Plus Jakarta Sans + JetBrains Mono), warm parchment & obsidian dark themes, masthead navigation.

### Task 4: Home Page & Reader Components
- Files:
  - `src/app/page.tsx`
  - `src/components/HeroPost.tsx`
  - `src/components/PostCard.tsx`
  - `src/components/FilterBar.tsx`
  - `src/components/Sidebar.tsx`
  - `src/components/NewsletterModal.tsx`

### Task 5: Single Post Reader Page (`/post/[slug]`)
- Files:
  - `src/app/post/[slug]/page.tsx`
  - `src/components/ReadingProgressBar.tsx`
  - `src/components/ClapButton.tsx`
  - `src/components/BookmarkButton.tsx`
  - `src/components/ShareButton.tsx`
  - `src/components/TableOfContents.tsx`
  - `src/components/CommentsSection.tsx`

### Task 6: Taxonomy & Archive Pages
- Files:
  - `src/app/category/[slug]/page.tsx`
  - `src/app/tag/[tag]/page.tsx`
  - `src/app/archive/page.tsx`

### Task 7: Admin Studio / CMS (`/studio` or `/admin`)
- Files:
  - `src/app/studio/page.tsx`
  - `src/components/studio/PostList.tsx`
  - `src/components/studio/PostEditor.tsx`
  - `src/components/studio/AnalyticsView.tsx`

### Task 8: Verification & Visual Polish (Browser Subagent Loop)
- Launch `npm run dev` in background
- Open browser subagent:
  - Verify homepage render, hero post, category filtering, search
  - Verify post detail view, reading progress, clap confetti, comment submission
  - Verify studio editor: create new post, edit post, delete post, view updates
  - Verify dark/light theme switching
  - Fix any visual or functional flaws detected during verification.
