// TinyAssets onboarding app — SPA.
// Talks to the backend ONLY through the same-origin /mcp proxy using the
// canonical MCP handles. The universe's reply is rendered verbatim; the app
// never composes its voice.
"use strict";

// --------------------------------------------------------------------------- //
// MCP client (JSON-RPC over the local /mcp proxy)
// --------------------------------------------------------------------------- //

const MCP = {
  sessionId: null,
  nextId: 1,

  // Parse an MCP streamable-http body: either JSON or an SSE `data:` frame.
  _parseBody(text) {
    const t = (text || "").trim();
    if (!t) throw new Error("empty MCP response");
    if (t.startsWith("{") || t.startsWith("[")) return JSON.parse(t);
    for (const line of t.split(/\r?\n/)) {
      const s = line.trim();
      if (s.startsWith("data:")) {
        const payload = s.slice(5).trim();
        if (payload) return JSON.parse(payload);
      }
    }
    throw new Error("no JSON or SSE frame in MCP response");
  },

  async _rpc(method, params, { expectResult = true } = {}) {
    const frame = { jsonrpc: "2.0", method, params: params || {} };
    if (expectResult) frame.id = this.nextId++;
    const headers = { "Content-Type": "application/json" };
    if (this.sessionId) headers["mcp-session-id"] = this.sessionId;

    const resp = await fetch("/mcp", {
      method: "POST",
      headers,
      body: JSON.stringify(frame),
    });

    if (resp.status === 401) {
      const err = new Error("authentication_required");
      err.authRequired = true;
      throw err;
    }
    const sid = resp.headers.get("mcp-session-id");
    if (sid) this.sessionId = sid;

    if (!expectResult) return null; // notification: no body to parse
    const body = await resp.text();
    const rpc = this._parseBody(body);
    if (rpc.error) {
      const err = new Error(rpc.error.message || "MCP error");
      err.rpc = rpc.error;
      throw err;
    }
    return rpc.result;
  },

  async ensureInit() {
    if (this.sessionId) return;
    await this._rpc("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "tinyassets-onboarding-app", version: "1.0" },
    });
    await this._rpc("notifications/initialized", {}, { expectResult: false });
  },

  // Return the tool's decoded payload (structuredContent, else parsed text).
  async callTool(name, args) {
    await this.ensureInit();
    const result = await this._rpc("tools/call", { name, arguments: args || {} });
    if (result && typeof result.structuredContent === "object" && result.structuredContent) {
      return result.structuredContent;
    }
    const block = (result && result.content || []).find(
      (c) => c && c.type === "text" && typeof c.text === "string"
    );
    if (block) {
      try {
        return JSON.parse(block.text);
      } catch (_e) {
        return { reply: block.text };
      }
    }
    return {};
  },

  converse(message) {
    return this.callTool("converse", { message });
  },
  getStatus() {
    return this.callTool("get_status", {});
  },
  connectLLM(service, materialB64) {
    return this.callTool("write_graph", {
      target: "connection",
      operation: "connect_llm",
      payload_json: JSON.stringify({ service, auth_material_b64: materialB64 }),
    });
  },
};

// --------------------------------------------------------------------------- //
// DOM helpers + view state
// --------------------------------------------------------------------------- //

const $ = (id) => document.getElementById(id);
const views = { signin: $("view-signin"), chat: $("view-chat"), connect: $("view-connect") };

function showView(name) {
  for (const [key, el] of Object.entries(views)) el.hidden = key !== name;
}

let hasMessages = false;
let statusTimer = null;

function appendMessage(role, text, extraNode) {
  if (!hasMessages) {
    $("thread-empty").remove();
    hasMessages = true;
  }
  const thread = $("thread");
  const el = document.createElement("div");
  el.className = `msg msg--${role}`;
  if (role !== "system") {
    const label = document.createElement("span");
    label.className = "msg-role";
    label.textContent = role === "universe" ? "Universe" : "You";
    el.appendChild(label);
  }
  el.appendChild(document.createTextNode(text));
  if (extraNode) el.appendChild(extraNode);
  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
  return el;
}

function setStatusLine(text) {
  $("status-line").textContent = text || "";
}

// Render a converse payload. The universe's own `reply` is rendered VERBATIM.
function renderConversePayload(payload) {
  if (payload && typeof payload.reply === "string") {
    appendMessage("universe", payload.reply);
    return;
  }
  // No-engine / setup-required: the platform-authored honest note, plus a CTA.
  if (payload && payload.status === "held" && payload.reason === "setup_required") {
    const cta = document.createElement("div");
    cta.className = "setup-cta";
    const btn = document.createElement("button");
    btn.className = "btn btn--ghost";
    btn.textContent = "Connect your subscription";
    btn.addEventListener("click", () => showConnect());
    cta.appendChild(btn);
    appendMessage("universe", payload.note || "This universe has no engine yet.", cta);
    return;
  }
  if (payload && payload.error) {
    appendMessage("system", payload.error);
    return;
  }
  appendMessage("system", "Your universe returned an unexpected response.");
}

// --------------------------------------------------------------------------- //
// Actions
// --------------------------------------------------------------------------- //

async function sendTurn(message) {
  appendMessage("founder", message);
  const input = $("composer-input");
  input.value = "";
  input.style.height = "auto";
  $("btn-send").disabled = true;
  setStatusLine("Your universe is thinking...");
  try {
    const payload = await MCP.converse(message);
    renderConversePayload(payload);
    setStatusLine("");
  } catch (err) {
    if (err.authRequired) {
      setStatusLine("");
      return enterSignedOut();
    }
    appendMessage("system", `Couldn't reach your universe: ${err.message}`);
    setStatusLine("");
  } finally {
    $("btn-send").disabled = false;
  }
}

async function pollStatus() {
  try {
    const status = await MCP.getStatus();
    const dot = $("status-dot");
    const host = status.active_host;
    const alive = host && host !== "none" && host !== null;
    dot.className = "status-dot " + (alive ? "status-dot--ok" : "status-dot--warn");
    dot.title = alive ? `host: ${host}` : "no active host";
    const name =
      status.universe_name || status.universe || (status.universe_id ? status.universe_id : "");
    if (name) $("universe-name").textContent = name;
  } catch (err) {
    if (err.authRequired) return enterSignedOut();
    const dot = $("status-dot");
    dot.className = "status-dot status-dot--err";
    dot.title = "status unavailable";
  }
}

function startStatusHeartbeat() {
  pollStatus();
  clearInterval(statusTimer);
  statusTimer = setInterval(pollStatus, 30000);
}

function enterSignedIn() {
  showView("chat");
  startStatusHeartbeat();
  $("composer-input").focus();
}

function enterSignedOut() {
  clearInterval(statusTimer);
  MCP.sessionId = null;
  showView("signin");
}

function showConnect() {
  showView("connect");
  const box = $("connect-status");
  box.textContent =
    "The secure deposit form is served by the connector itself so your credential " +
    "never passes through chat. If it isn't deployed yet, the advanced deposit below " +
    "will show the connector's honest response.";
}

// --------------------------------------------------------------------------- //
// Wiring
// --------------------------------------------------------------------------- //

function autoGrow(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, window.innerHeight * 0.4) + "px";
}

function wire() {
  $("btn-signin").addEventListener("click", () => {
    window.location.href = "/auth/login";
  });

  $("btn-dev-token").addEventListener("click", async () => {
    const token = $("dev-token-input").value.trim();
    const errEl = $("dev-token-error");
    errEl.textContent = "";
    if (!token) {
      errEl.textContent = "Paste a token first.";
      return;
    }
    const resp = await fetch("/auth/manual-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: token }),
    });
    if (resp.ok) {
      $("dev-token-input").value = "";
      enterSignedIn();
    } else {
      errEl.textContent = "The app rejected that token.";
    }
  });

  $("composer").addEventListener("submit", (e) => {
    e.preventDefault();
    const message = $("composer-input").value.trim();
    if (message) sendTurn(message);
  });

  const input = $("composer-input");
  input.addEventListener("input", () => autoGrow(input));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      $("composer").requestSubmit();
    }
  });

  $("btn-connect").addEventListener("click", showConnect);
  $("btn-connect-back").addEventListener("click", () => showView("chat"));
  $("btn-signout").addEventListener("click", async () => {
    await fetch("/auth/logout", { method: "POST" });
    enterSignedOut();
  });

  $("btn-deposit").addEventListener("click", async () => {
    const service = $("connect-service").value;
    const material = $("connect-material").value.trim();
    const out = $("connect-result");
    out.hidden = false;
    if (!material) {
      out.textContent = "Enter your subscription credential first.";
      return;
    }
    out.textContent = "Depositing securely...";
    try {
      const b64 = btoa(unescape(encodeURIComponent(material)));
      const payload = await MCP.connectLLM(service, b64);
      $("connect-material").value = ""; // never keep the secret around
      out.textContent = JSON.stringify(payload, null, 2);
    } catch (err) {
      if (err.authRequired) return enterSignedOut();
      out.textContent = `Deposit failed: ${err.message}`;
    }
  });
}

async function boot() {
  wire();
  let session = { authenticated: false };
  try {
    session = await (await fetch("/api/session")).json();
  } catch (_e) {
    /* fall through to signed-out */
  }
  if (session.authenticated) {
    enterSignedIn();
  } else {
    enterSignedOut();
  }
}

boot();
