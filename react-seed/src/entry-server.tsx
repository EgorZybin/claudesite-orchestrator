/**
 * SSR entry point — loaded by the renderer service (Node).
 *
 * Renderer protocol:
 *   import { render } from "<built bundle>/entry-server.js";
 *   const html = render(props);
 *   // splice html into index.html template's <!--app-html--> marker
 */
import { renderToString } from "react-dom/server";
import { App } from "./App";
import type { RenderProps } from "./types";
import "./index.css";

export function render(props: RenderProps): { html: string; head: string } {
  const html = renderToString(<App {...props} />);
  // Per-page <head> additions (JSON-LD, og:image, etc) are emitted by
  // page components into a global; in v1 we keep <head> static via the
  // index.html template and just splice <title>/description from props.
  const head = "";
  return { html, head };
}
