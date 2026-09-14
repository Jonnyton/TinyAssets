/* Declarative experience preview. No network, storage, or execution authority. */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.TinyExperience = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const forbidden = new Set([
    "credentials", "api_key", "access_token", "authorization", "private_key",
    "password", "secret", "bindings", "universe_id", "branch_id", "run_id",
    "conversation_id", "device_token", "conversations", "learned_memory"
  ]);
  const name = /^[a-z][a-z0-9_-]{0,63}$/;
  function fail(reason) { throw new Error(reason); }
  function clone(value) {
    const seen = new Set();
    function check(v) {
      if (v === null || typeof v === "string" || typeof v === "boolean") return;
      if (typeof v === "number" && Number.isFinite(v)) return;
      if (typeof v !== "object" || seen.has(v)) fail("Value must be acyclic JSON");
      if (!Array.isArray(v) && Object.getPrototypeOf(v) !== Object.prototype &&
          Object.getPrototypeOf(v) !== null) fail("Value must be plain JSON");
      seen.add(v);
      Object.values(v).forEach(check);
      seen.delete(v);
    }
    check(value);
    return JSON.parse(JSON.stringify(value));
  }
  function canonical(v) {
    if (Array.isArray(v)) return "[" + v.map(canonical).join(",") + "]";
    if (v && typeof v === "object") return "{" + Object.keys(v).sort().map(
      k => JSON.stringify(k) + ":" + canonical(v[k])).join(",") + "}";
    return JSON.stringify(v);
  }
  function freeze(v) {
    if (v && typeof v === "object") {
      Object.values(v).forEach(freeze);
      Object.freeze(v);
    }
    return v;
  }
  function inspect(definition) {
    const source = clone(definition);
    function publicOnly(v) {
      if (typeof v === "string" && /Bearer\s+|gh[pousr]_[A-Za-z0-9]+/.test(v))
        fail("Definition contains credential-shaped content");
      if (!v || typeof v !== "object") return;
      for (const [key, value] of Object.entries(v)) {
        if (forbidden.has(key.toLowerCase().replaceAll("-", "_")))
          fail("Definition contains private content");
        publicOnly(value);
      }
    }
    publicOnly(source);
    if (source.schema_version !== 1 || typeof source.name !== "string" ||
        !source.name.trim() || !source.components || Array.isArray(source.components) ||
        typeof source.components !== "object") fail("Expected native composition");
    const unsupported = [];
    for (const [id, component] of Object.entries(source.components)) {
      if (!name.test(id) || !component || typeof component !== "object" ||
          Array.isArray(component) || typeof component.kind !== "string")
        fail("Invalid component");
      if (!["experience.view", "experience.action"].includes(component.kind))
        unsupported.push(id);
    }
    return freeze({source, unsupported, executable: false});
  }
  function prepareIntent(definition, actionId, bindings) {
    const {source} = inspect(definition);
    if (!Object.hasOwn(source.components, actionId)) fail("Unknown action");
    const action = source.components[actionId];
    if (action.kind !== "experience.action" || action.operation !== "run_branch")
      fail("Unsupported typed operation");
    if (typeof action.target_role !== "string" || !name.test(action.target_role) ||
        !bindings || !Object.hasOwn(bindings, action.target_role))
      fail("Missing private target binding");
    const target = bindings[action.target_role];
    if (!target || typeof target.branchId !== "string" || !target.branchId.trim() ||
        !Number.isSafeInteger(target.revision) || target.revision < 0)
      fail("Invalid private target binding");
    if (!action.input || typeof action.input !== "object" || Array.isArray(action.input))
      fail("Action input must be an object");
    return freeze({
      operation: "run_branch", actionId, source: canonical(source),
      target: {branchId: target.branchId, revision: target.revision},
      input: clone(action.input), admission: "not_requested", retry: "unsupported"
    });
  }
  function revalidateIntent(prepared, definition, bindings) {
    // Client-side stale-intent guard, NOT authorization. The real handler must
    // independently derive actor/universe and revalidate target and authority.
    if (!prepared || typeof prepared.actionId !== "string") fail("Invalid prepared intent");
    const current = prepareIntent(definition, prepared.actionId, bindings);
    if (canonical(clone(prepared)) !== canonical(current))
      fail("Prepared intent is stale or changed; prepare it again");
    return current;
  }
  function recovery(outcome) {
    if (!outcome || outcome.kind !== "action" ||
        typeof outcome.actionId !== "string" || !outcome.actionId.trim())
      return freeze({automaticRetry: false, next: "check_canonical_history"});
    return freeze({automaticRetry: false, next: "inspect_action_outcome"});
  }
  function renderPreview(definition, container, options = {}) {
    const {source, unsupported} = inspect(definition);
    const doc = container.ownerDocument;
    const mode = options.mode === "phone" ? "phone" : "desktop";
    const fixtures = clone(options.fixtures === undefined ? [] : options.fixtures);
    if (!Array.isArray(fixtures) || fixtures.some(item => !item ||
        typeof item !== "object" || Array.isArray(item) ||
        typeof item.label !== "string" || typeof item.status !== "string"))
      fail("Fixtures must be an array of label/status objects");
    const fragment = doc.createDocumentFragment();
    function element(tag, text, parent) {
      const node = doc.createElement(tag);
      if (text !== undefined) node.textContent = String(text);
      parent.appendChild(node);
      return node;
    }
    element("h2", source.name, fragment);
    element("p", "Preview with fixture data. No actions are sent.", fragment);
    for (const [id, view] of Object.entries(source.components)) {
      if (view.kind !== "experience.view") continue;
      const layout = view.layouts && view.layouts[mode];
      if (!["board", "list"].includes(layout)) {
        element("p", "Unsupported layout: " + id, fragment);
        continue;
      }
      const section = element("section", undefined, fragment);
      element("h3", typeof view.title === "string" ? view.title : id, section);
      const list = element("ul", undefined, section);
      list.className = "experience-" + layout;
      for (const item of fixtures) {
        const row = element("li", undefined, list);
        element("strong", item.label, row);
        element("p", item.status, row);
      }
    }
    const status = element("p", "Choose an action to inspect its fixture intent.", fragment);
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    for (const [id, action] of Object.entries(source.components)) {
      if (action.kind !== "experience.action") continue;
      const button = element("button", typeof action.label === "string" ? action.label : id, fragment);
      button.type = "button";
      button.addEventListener("click", () => {
        try {
          const intent = prepareIntent(source, id, options.bindings || {});
          status.textContent = "Prepared " + intent.operation + " for fixture " +
            intent.target.branchId + ". No action was sent.";
        } catch (error) { status.textContent = error.message; }
      });
    }
    if (unsupported.length)
      element("p", "Preserved unsupported components: " + unsupported.join(", "), fragment);
    container.replaceChildren(fragment);
    return {mode, unsupported};
  }
  return Object.freeze({inspect, prepareIntent, revalidateIntent, recovery, renderPreview});
});
