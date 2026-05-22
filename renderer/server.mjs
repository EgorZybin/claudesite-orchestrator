/**
 * Claudesite Renderer Service
 *
 * Two endpoints:
 *   POST /build    — runs `vite build` (client + ssr) inside a site dir
 *   POST /render   — dynamic-imports the per-site SSR bundle, calls render(props),
 *                    splices into the client index.html template, returns HTML
 *
 * Architecture:
 *   - The seed package (react-seed/) is COPY'd into the image at /app/seed/
 *     with `node_modules` already installed.
 *   - Each site dir at /var/claudesite/sites/<id>/current/ gets a symlink
 *     `node_modules -> /app/seed/node_modules` before its first build.
 *   - Per-site src/ holds Claude-written pages/sections + the immutable seed
 *     primitives that were COPY'd from /app/seed/.
 *
 * Cache invalidation for SSR re-loads:
 *   Each successful /build bumps an in-memory version counter for that
 *   site_dir. /render appends `?bust=v{N}` to the dynamic-import URL so Node
 *   ESM treats it as a fresh module, picking up the new bundle.
 */
import Fastify from "fastify";
import { spawn } from "node:child_process";
import { readFile, lstat, symlink, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";

const SEED_DIR = process.env.SEED_DIR || "/app/seed";
const SEED_NODE_MODULES = path.join(SEED_DIR, "node_modules");
const VITE_BIN = path.join(SEED_NODE_MODULES, ".bin", "vite");
const PORT = parseInt(process.env.PORT || "8090", 10);
const HOST = process.env.HOST || "0.0.0.0";
const REQUEST_BODY_LIMIT = 4 * 1024 * 1024; // 4 MB — props with content_blocks can grow

// In-memory version tracker — bumped after each successful build to
// invalidate the Node ESM module cache for that site's SSR bundle.
const siteVersions = new Map();

function bumpVersion(siteDir) {
  const v = (siteVersions.get(siteDir) || 0) + 1;
  siteVersions.set(siteDir, v);
  return v;
}

function currentVersion(siteDir) {
  return siteVersions.get(siteDir) || 0;
}

const fastify = Fastify({
  logger: { level: process.env.LOG_LEVEL || "info" },
  bodyLimit: REQUEST_BODY_LIMIT,
});

// ---------------------------------------------------------------------------
// Filesystem helpers
// ---------------------------------------------------------------------------

async function pathExists(p) {
  try {
    await lstat(p);
    return true;
  } catch {
    return false;
  }
}

async function ensureNodeModulesLink(siteDir) {
  const link = path.join(siteDir, "node_modules");
  if (await pathExists(link)) return; // already linked or installed
  await mkdir(siteDir, { recursive: true });
  await symlink(SEED_NODE_MODULES, link, "dir");
}

// ---------------------------------------------------------------------------
// Vite invocation
// ---------------------------------------------------------------------------

function runVite(cwd, args) {
  return new Promise((resolve) => {
    const proc = spawn(VITE_BIN, args, {
      cwd,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, NODE_ENV: "production" },
    });
    const out = [];
    proc.stdout.on("data", (chunk) => out.push(chunk.toString()));
    proc.stderr.on("data", (chunk) => out.push(chunk.toString()));
    proc.on("close", (code) => resolve({ code: code ?? -1, log: out.join("") }));
    proc.on("error", (err) =>
      resolve({ code: -1, log: `spawn error: ${err.message}` }),
    );
  });
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

fastify.get("/health", async () => ({
  ok: true,
  seed_dir: SEED_DIR,
  seed_installed: existsSync(SEED_NODE_MODULES),
  tracked_sites: siteVersions.size,
}));

fastify.post("/build", async (request, reply) => {
  const { site_dir } = request.body ?? {};
  if (!site_dir || typeof site_dir !== "string") {
    return reply.code(400).send({ ok: false, error: "site_dir (string) required" });
  }
  if (!existsSync(site_dir)) {
    return reply.code(400).send({ ok: false, error: `site_dir not found: ${site_dir}` });
  }
  if (!existsSync(path.join(site_dir, "package.json"))) {
    return reply.code(400).send({
      ok: false,
      error: `site_dir missing package.json (seed not copied?): ${site_dir}`,
    });
  }

  const t0 = Date.now();
  try {
    await ensureNodeModulesLink(site_dir);
  } catch (e) {
    return reply.code(500).send({ ok: false, error: `symlink failed: ${e.message}` });
  }

  fastify.log.info({ site_dir }, "build_start");

  // Client first (produces .vite/manifest.json + index.html), then SSR bundle.
  const clientRes = await runVite(site_dir, ["build"]);
  if (clientRes.code !== 0) {
    fastify.log.warn({ site_dir, log: clientRes.log }, "build_client_failed");
    return reply.code(500).send({
      ok: false,
      stage: "client",
      code: clientRes.code,
      log: clientRes.log.slice(-4000),
    });
  }

  const ssrRes = await runVite(site_dir, ["build", "--ssr", "src/entry-server.tsx"]);
  if (ssrRes.code !== 0) {
    fastify.log.warn({ site_dir, log: ssrRes.log }, "build_ssr_failed");
    return reply.code(500).send({
      ok: false,
      stage: "ssr",
      code: ssrRes.code,
      log: ssrRes.log.slice(-4000),
    });
  }

  const version = bumpVersion(site_dir);
  const duration_ms = Date.now() - t0;
  fastify.log.info({ site_dir, duration_ms, version }, "build_ok");
  return {
    ok: true,
    duration_ms,
    version,
    client_log: clientRes.log.slice(-1500),
    ssr_log: ssrRes.log.slice(-1500),
  };
});

fastify.post("/render", async (request, reply) => {
  const { site_dir, props } = request.body ?? {};
  if (!site_dir || typeof site_dir !== "string") {
    return reply.code(400).send({ error: "site_dir (string) required" });
  }
  if (!props || typeof props !== "object") {
    return reply.code(400).send({ error: "props (object) required" });
  }

  const ssrEntry = path.join(site_dir, "dist/server/entry-server.js");
  const clientTemplate = path.join(site_dir, "dist/client/index.html");

  if (!existsSync(ssrEntry)) {
    return reply.code(503).send({
      error: `SSR bundle missing: ${ssrEntry} (build first via POST /build)`,
    });
  }
  if (!existsSync(clientTemplate)) {
    return reply.code(503).send({
      error: `client index.html missing: ${clientTemplate} (build first)`,
    });
  }

  const v = currentVersion(site_dir);
  let mod;
  try {
    // Bust Node ESM module cache by appending ?bust=v{N}.
    mod = await import(`file://${ssrEntry}?bust=v${v}`);
  } catch (e) {
    fastify.log.error({ err: e.stack }, "render_import_failed");
    return reply.code(500).send({ error: `import failed: ${e.message}` });
  }
  if (typeof mod.render !== "function") {
    return reply.code(500).send({
      error: "SSR bundle does not export render(props)",
    });
  }

  let rendered;
  try {
    rendered = mod.render(props);
  } catch (e) {
    fastify.log.error({ err: e.stack }, "render_exec_failed");
    return reply.code(500).send({ error: `render() threw: ${e.message}` });
  }

  if (typeof rendered?.html !== "string") {
    return reply.code(500).send({
      error: "render() did not return { html: string }",
    });
  }

  let template;
  try {
    template = await readFile(clientTemplate, "utf-8");
  } catch (e) {
    return reply.code(500).send({ error: `read template failed: ${e.message}` });
  }

  const ssrPropsScript =
    `<script>window.__SSR_PROPS__ = ${jsonForScript(props)};</script>`;
  const headInject = `${rendered.head || ""}\n${ssrPropsScript}`;

  const html = template
    .replace("<!--app-html-->", rendered.html)
    .replace(/<!--app-title-->/g, escapeHtml(props.page?.title || ""))
    .replace(
      /<!--app-description-->/g,
      escapeAttr(props.page?.seo_description || ""),
    )
    .replace(/<!--app-canonical-->/g, escapeAttr(props.current_url || ""))
    .replace(/<!--app-lang-->/g, escapeAttr(props.site?.language || "en"))
    .replace("<!--app-head-->", headInject);

  reply
    .header("X-Renderer-Version", String(v))
    .type("text/html; charset=utf-8")
    .send(html);
});

// ---------------------------------------------------------------------------
// Output escaping helpers
// ---------------------------------------------------------------------------

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

function jsonForScript(obj) {
  // Embed JSON inside <script>...</script>: escape `</script>` and U+2028/9
  // to prevent script-tag breakout and JSON-vs-JS-string corner cases.
  return JSON.stringify(obj)
    .replace(/</g, "\\u003c")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

fastify
  .listen({ port: PORT, host: HOST })
  .then(() => fastify.log.info({ port: PORT, host: HOST, seed_dir: SEED_DIR }, "renderer_ready"))
  .catch((err) => {
    fastify.log.error(err);
    process.exit(1);
  });
