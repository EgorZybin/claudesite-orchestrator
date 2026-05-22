/**
 * Client entry — hydrates the SSR-rendered HTML.
 *
 * Reads `window.__SSR_PROPS__` (injected by the renderer service into the
 * page <script> tag) to get the same props the server used. Without this
 * the React tree would re-render with default props and tear off the SSR
 * HTML, breaking interactivity in Radix primitives (Accordion/Tabs/Sheet).
 */
import { hydrateRoot } from "react-dom/client";
import { App } from "./App";
import type { RenderProps } from "./types";
import "./index.css";

declare global {
  interface Window {
    __SSR_PROPS__?: RenderProps;
  }
}

const props = window.__SSR_PROPS__;
const root = document.getElementById("root");

if (props && root) {
  hydrateRoot(root, <App {...props} />);
} else {
  // Dev fallback — no SSR yet, render a placeholder.
  console.warn("No __SSR_PROPS__ — hydration skipped.");
}
