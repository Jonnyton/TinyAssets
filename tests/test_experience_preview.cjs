"use strict";
const assert = require("node:assert/strict");
const {test} = require("node:test");
const experience = require("../tinyassets/onboarding/experience.js");

function fixture() {
  return {
    schema_version: 1, name: "My board",
    components: {
      board: {kind: "experience.view", title: "<img onerror=alert(1)>",
        layouts: {desktop: "board", phone: "list"}},
      start: {kind: "experience.action", operation: "run_branch", label: "Prepare",
        target_role: "worker", input: {value: 3}},
      future: {kind: "future.hologram", config: {preserved: true}}
    }
  };
}
const bindings = {worker: {branchId: "fixture-only", revision: 7}};

test("source preserves unknown components and stays inert", () => {
  const definition = fixture();
  const got = experience.inspect(definition);
  assert.deepEqual(got.source, definition);
  assert.deepEqual(got.unsupported, ["future"]);
  assert.equal(got.executable, false);
  definition.components.future.config.preserved = false;
  assert.equal(got.source.components.future.config.preserved, true);
  assert.ok(Object.isFrozen(got.source.components));
});
test("prepared action binds exact source, input, target and revision", () => {
  const definition = fixture();
  const intent = experience.prepareIntent(definition, "start", bindings);
  assert.equal(intent.admission, "not_requested");
  assert.deepEqual(intent.target, {branchId: "fixture-only", revision: 7});
  assert.deepEqual(experience.revalidateIntent(intent, definition, bindings), intent);
  for (const changed of [
    {worker: {branchId: "other", revision: 7}},
    {worker: {branchId: "fixture-only", revision: 8}}
  ]) assert.throws(() => experience.revalidateIntent(intent, definition, changed), /stale/);
  definition.components.start.input.value = 4;
  assert.throws(() => experience.revalidateIntent(intent, definition, bindings), /stale/);
  assert.deepEqual(intent.input, {value: 3});
});
test("no implicit conversation operation or retry", () => {
  const definition = fixture();
  definition.components.start.operation = "converse";
  assert.throws(() => experience.prepareIntent(definition, "start", bindings), /Unsupported/);
  assert.deepEqual(experience.recovery({kind: "conversation", actionId: "guess"}), {
    automaticRetry: false, next: "check_canonical_history"
  });
  for (const outcome of [undefined, {actionId: "a"}, {kind: "run", actionId: "a"},
    {kind: "action"}, {kind: "action", actionId: 1}, {kind: "action", actionId: " "}])
    assert.deepEqual(experience.recovery(outcome), {
      automaticRetry: false, next: "check_canonical_history"
    });
  assert.deepEqual(experience.recovery({kind: "action", actionId: "a"}), {
    automaticRetry: false, next: "inspect_action_outcome"
  });
});
test("absent or malformed bindings and tampered intent refuse", () => {
  for (const bad of [{}, {worker: {branchId: "x", revision: NaN}},
    {worker: {branchId: "", revision: 1}}])
    assert.throws(() => experience.prepareIntent(fixture(), "start", bad));
  const p = experience.prepareIntent(fixture(), "start", bindings);
  assert.throws(() => experience.revalidateIntent({...p, retry: "automatic"}, fixture(), bindings));
  assert.throws(() => experience.prepareIntent(fixture(), "toString", bindings));
});
test("private source and non-JSON data refuse with value-free errors", () => {
  const source = fixture();
  source.components.start.credentials = {password: "private-sentinel"};
  assert.throws(() => experience.inspect(source), error =>
    /private content/.test(error.message) && !error.message.includes("private-sentinel"));
  assert.throws(() => experience.inspect({...fixture(), extra: NaN}));
  assert.throws(() => experience.inspect({...fixture(), extra: undefined}));
  const cyclic = fixture(); cyclic.cycle = cyclic;
  assert.throws(() => experience.inspect(cyclic));
});


test("credential text vectors agree with the native Python validator", () => {
  const vectors = [
    "plain public note", "Bearer", "sk-short",
    "bEaReR abc.DEF-123", "GHP_abcdefghijklmnop", "xoxb-abcdefghijklmnop",
    "sk-abcdefghijklmnop", "eyJabcdefgh.abcdefgh.abcdefgh",
    "prefix ghp_abcdefghijklmnop suffix"
  ];
  const {spawnSync} = require("node:child_process");
  const python = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
  const result = spawnSync(python, ["-c", [
    "import json,sys",
    "from tinyassets.custom_agents import AgentValidationError, _check_secret_fields",
    "results=[]",
    "for value in json.load(sys.stdin):",
    "    try:",
    "        _check_secret_fields({'text': value})",
    "        results.append(True)",
    "    except AgentValidationError:",
    "        results.append(False)",
    "print(json.dumps(results))"
  ].join("\n")], {input: JSON.stringify(vectors), encoding: "utf8",
    cwd: require("node:path").resolve(__dirname, "..")});
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, result.stderr);
  const native = JSON.parse(result.stdout);
  assert.deepEqual(native, [true, true, true, false, false, false, false, false, false]);
  vectors.forEach((value, i) => {
    const source = fixture();
    source.components.future.config.text = value;
    if (native[i]) assert.doesNotThrow(() => experience.inspect(source));
    else assert.throws(() => experience.inspect(source),
      /^Error: Definition contains credential-shaped content$/);
  });
});

// This small DOM double checks interpretation and text sinks; it is NOT browser
// rendering evidence. The HTML fixture is the separately inspectable surface.
class Element {
  constructor(tag, doc) {
    this.tagName = tag; this.ownerDocument = doc; this.children = [];
    this.textContent = ""; this.attributes = {}; this.listeners = {};
  }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = children; }
  setAttribute(k, v) { this.attributes[k] = v; }
  addEventListener(k, v) { this.listeners[k] = v; }
  set innerHTML(_) { throw new Error("Executable HTML sink must not be used"); }
}
function documentFixture() {
  const doc = {createElement: tag => new Element(tag, doc),
    createDocumentFragment: () => new Element("fragment", doc)};
  return new Element("main", doc);
}
function walk(node) { return [node, ...node.children.flatMap(walk)]; }
test("malformed fixtures fail clearly before replacing the view", () => {
  const root = documentFixture();
  const original = new Element("p", root.ownerDocument);
  root.appendChild(original);
  for (const fixtures of [{}, null, false, "", [null], [1], [{label: "x"}]]) {
    assert.throws(() => experience.renderPreview(fixture(), root, {fixtures}),
      /^Error: Fixtures must be an array of label\/status objects$/);
    assert.equal(root.children[0], original);
  }
});
test("desktop and phone layouts keep literal text and inert action identity", () => {
  const root = documentFixture();
  const definition = fixture();
  for (const mode of ["desktop", "phone"]) {
    experience.renderPreview(definition, root, {mode, bindings,
      fixtures: [{label: "Same instance", status: "<script>untrusted</script>"}]});
    const nodes = walk(root);
    assert.equal(nodes.find(n => n.tagName === "ul").className,
      mode === "phone" ? "experience-list" : "experience-board");
    assert.ok(nodes.some(n => n.textContent === "<img onerror=alert(1)>"));
    assert.ok(nodes.some(n => n.textContent === "<script>untrusted</script>"));
    nodes.find(n => n.tagName === "button").listeners.click();
    assert.match(nodes.find(n => n.attributes.role === "status").textContent,
      /fixture-only.*No action was sent/);
    assert.equal(nodes.filter(n => n.tagName === "h2").length, 1);
  }
});
