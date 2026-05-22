/**
 * Type contract between the orchestrator (Python) and the React app.
 * MUST mirror `app/schemas/site_content.py` exactly. Field names match
 * the Pydantic models; nothing is repackaged on the server side.
 */

export type PageType =
  | "home"
  | "services"
  | "service"
  | "blog_index"
  | "blog_post"
  | "about"
  | "contacts"
  | string; // open enum — Claude may extend

/**
 * Per-site identity as resolved by the orchestrator into the render
 * context (mirrors `SimpleNamespace` built in `api/routes/public.py`).
 */
export interface Site {
  brand: string;
  language: string;
  industry: string;
  tagline: string | null;
}

export interface NavItem {
  label: string;
  href: string;
  current: boolean;
}

export interface PageSummary {
  slug: string;
  title: string;
  page_type: PageType;
  href: string;
  nav_label: string | null;
  sort_order: number;
  seo_description: string;
  hero_title: string | null;
  hero_subtitle: string | null;
  hero_image: string | null;
}

/** Semantic content blocks — discriminated union by `kind`. */
export type ContentBlock =
  | { kind: "heading"; level: 2 | 3 | 4; text: string }
  | { kind: "paragraph"; markdown: string }
  | {
      kind: "image";
      src: string;
      alt: string;
      caption?: string;
      width?: number;
      height?: number;
    }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "quote"; text: string; attribution?: string }
  | { kind: "table"; headers: string[]; rows: string[][] }
  | { kind: "cta"; label: string; href: string; style: "primary" | "secondary" | "ghost" };

export interface Page {
  slug: string;
  page_type: PageType;
  title: string;
  seo_description: string;
  hero_title: string | null;
  hero_subtitle: string | null;
  hero_image: string | null;
  content_blocks: ContentBlock[];
  modules_used: string[];
}

/** Module data — open shape; per-kind structure documented in contracts/. */
export type ModuleData = Record<string, unknown>;

export type Modules = Record<string, ModuleData | null>;

export interface RenderProps {
  site: Site;
  page: Page;
  modules: Modules;
  nav: NavItem[];
  current_url: string;
  pages_in_site: PageSummary[];
}
