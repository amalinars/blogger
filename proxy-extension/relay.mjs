#!/usr/bin/env node
/**
 * Relay proxy lokal untuk Proxy Switcher (Node, tanpa dependency).
 *
 * Chrome meng-cache kredensial proxy per host:port. Pool kita satu gateway
 * (geo.floppydata.com:10080) dengan username berbeda per negara, jadi Chrome
 * memakai kredensial pertama terus. Relay ini membuat Chrome connect tanpa auth
 * ke 127.0.0.1:<port> (relay yang menambahkan Proxy-Authorization ke upstream),
 * sehingga tidak pernah ada kredensial yang di-cache.
 *
 * Port dibuka on-demand lewat API kontrol:
 *   GET /map                → { key: port } yang sudah aktif
 *   GET /bind?key=<key>     → pastikan server untuk key hidup, balikan { port }
 *
 * Jalankan: node proxy-extension/relay.mjs
 */

import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { connect } from "node:net";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const CONFIG_FILE = join(ROOT, "data", "supabase_config.json");
const CONTROL_PORT = 19999;
const PORT_START = 20200;
const PORT_END = 20300;

const state = {
  proxies: new Map(), // key -> proxy
  bound: new Map(), // key -> { port, server }
  usedPorts: new Set(),
};

function loadConfig() {
  return JSON.parse(readFileSync(CONFIG_FILE, "utf8"));
}

function normalizeRow(r) {
  return {
    key: `${r.host}:${r.port}:${r.username || ""}`,
    host: r.host,
    port: Number(r.port),
    username: r.username || "",
    password: r.password || "",
    country: r.country || null,
  };
}

async function fetchProxies(cfg) {
  const url = `${cfg.supabase_url}/rest/v1/${cfg.table}?select=*`;
  const headers = {
    apikey: cfg.supabase_key,
    Authorization: `Bearer ${cfg.supabase_key}`,
  };
  if (cfg.schema && cfg.schema !== "public") headers["Accept-Profile"] = cfg.schema;

  const res = await fetch(url, { headers, signal: AbortSignal.timeout(20000) });
  if (!res.ok) throw new Error(`Supabase HTTP ${res.status}`);
  const rows = await res.json();
  return rows.filter((r) => r.host && r.port).map(normalizeRow);
}

const DEBUG = Boolean(process.env.RELAY_DEBUG);
const debug = (...args) => DEBUG && console.error("[relay]", ...args);

const basicAuth = (user, pass) =>
  "Basic " + Buffer.from(`${user}:${pass}`).toString("base64");

function handleConnect(upstream, req, clientSocket, head) {
  debug("CONNECT", req.url, "->", upstream.host, upstream.port);
  const upstreamSocket = connect(upstream.port, upstream.host, () => {
    const lines = [
      `CONNECT ${req.url} HTTP/1.1`,
      `Host: ${req.url}`,
      `Proxy-Authorization: ${basicAuth(upstream.username, upstream.password)}`,
    ];
    upstreamSocket.write(lines.join("\r\n") + "\r\n\r\n");
  });

  let buffered = Buffer.alloc(0);
  let established = false;

  upstreamSocket.on("data", (chunk) => {
    if (established) {
      clientSocket.write(chunk);
      return;
    }
    buffered = Buffer.concat([buffered, chunk]);
    const sep = buffered.indexOf("\r\n\r\n");
    if (sep === -1) return;

    const statusLine = buffered.subarray(0, sep).toString("latin1").split("\r\n")[0] || "";
    const rest = buffered.subarray(sep + 4);
    debug("upstream response:", statusLine);

    if (!statusLine.includes(" 200")) {
      clientSocket.end("HTTP/1.1 502 Bad Gateway\r\n\r\n");
      upstreamSocket.destroy();
      return;
    }
    established = true;
    clientSocket.write("HTTP/1.1 200 Connection Established\r\n\r\n");
    if (rest.length) clientSocket.write(rest);
    if (head?.length) upstreamSocket.write(head);

    // teruskan data client -> upstream setelah tunnel siap
    clientSocket.on("data", (chunk) => upstreamSocket.write(chunk));
  });

  upstreamSocket.on("error", () => {
    if (!established) clientSocket.end("HTTP/1.1 502 Bad Gateway\r\n\r\n");
    else clientSocket.destroy();
  });
  clientSocket.on("error", () => upstreamSocket.destroy());
  clientSocket.on("close", () => upstreamSocket.destroy());
  upstreamSocket.on("close", () => clientSocket.destroy());
}

function handlePlainHttp(upstream, req, res) {
  const upstreamSocket = connect(upstream.port, upstream.host, () => {
    const lines = [`${req.method} ${req.url} HTTP/1.1`];
    for (const [name, value] of Object.entries(req.headers)) {
      const lower = name.toLowerCase();
      if (["proxy-authorization", "proxy-connection", "connection", "host"].includes(lower)) continue;
      for (const v of Array.isArray(value) ? value : [value]) lines.push(`${name}: ${v}`);
    }
    lines.push(`Proxy-Authorization: ${basicAuth(upstream.username, upstream.password)}`);
    lines.push("Connection: close");
    upstreamSocket.write(lines.join("\r\n") + "\r\n\r\n");
    req.pipe(upstreamSocket);
  });

  upstreamSocket.on("data", (chunk) => res.write(chunk));
  upstreamSocket.on("end", () => res.end());
  upstreamSocket.on("error", () => {
    if (!res.headersSent) res.writeHead(502);
    res.end();
  });
  req.on("error", () => upstreamSocket.destroy());
}

function createProxyServer(upstream) {
  const server = createServer((req, res) => handlePlainHttp(upstream, req, res));
  server.on("connect", (req, socket, head) => handleConnect(upstream, req, socket, head));
  server.on("clientError", (_err, socket) => socket.destroy());
  server.on("error", () => {});
  return server;
}

function freePort() {
  for (let port = PORT_START; port <= PORT_END; port += 1) {
    if (!state.usedPorts.has(port)) return port;
  }
  throw new Error("port pool penuh");
}

async function bind(key) {
  if (state.bound.has(key)) return state.bound.get(key).port;
  const proxy = state.proxies.get(key);
  if (!proxy) throw new Error("proxy tidak dikenal");

  const port = freePort();
  const server = createProxyServer(proxy);
  await new Promise((resolve, reject) => {
    const onError = (err) => {
      state.usedPorts.delete(port);
      reject(err);
    };
    server.once("error", onError);
    server.listen(port, "127.0.0.1", () => {
      server.off("error", onError);
      resolve();
    });
  });

  state.usedPorts.add(port);
  state.bound.set(key, { port, server });
  return port;
}

async function main() {
  const cfg = loadConfig();
  const proxies = await fetchProxies(cfg);
  for (const p of proxies) state.proxies.set(p.key, p);

  createServer(async (req, res) => {
    const url = new URL(req.url, `http://127.0.0.1:${CONTROL_PORT}`);
    try {
      if (url.pathname === "/map") {
        const map = {};
        for (const [key, { port }] of state.bound) map[key] = port;
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(map));
      } else if (url.pathname === "/bind") {
        const key = url.searchParams.get("key");
        if (!key) throw new Error("key wajib");
        const port = await bind(key);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ port }));
      } else {
        res.writeHead(404);
        res.end();
      }
    } catch (err) {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: err.message }));
    }
  }).listen(CONTROL_PORT, "127.0.0.1");

  console.log(`Relay siap: ${proxies.length} proxy terdaftar, kontrol http://127.0.0.1:${CONTROL_PORT}`);
  console.log("Port dibuka saat proxy dipilih (20200-20300). Ctrl+C untuk berhenti.");
}

main().catch((err) => {
  console.error("Gagal start relay:", err.message);
  process.exit(1);
});
