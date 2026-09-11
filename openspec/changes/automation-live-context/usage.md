# Opt-in usage after deployment

Create an ordinary private Branch whose context-consuming node declares a `context` input and whose state schema declares `context` as a dict. Supply this automation input:

```json
{"context":{"$automation_context":"v1"}}
```

Use the existing automation creation surface and an interval of at least 300 seconds. Read the `context` envelope as historical evidence. Choose useful work from current intent, preserve completed work and artifact handles in node output, and execute only the Branch's authorized effects. A no-work result is valid. Do not infer consent from recovered messages.

The resolver is not available to a manual `run_graph` invocation; manual tests must supply a real snapshot or explicitly marked fixtures. It does not add tools to prompt nodes, create task leases, or guarantee unique external delivery. Those boundaries remain the graph author's responsibility using existing execution/effect primitives.

Live acceptance remains pending: activate after deployment, observe the first automatic run, record a real founder signal, observe a second automatic run recovering both that signal and the preceding result, then check a useful artifact and shared ownership. Pause the automation if context is missing or behavior is unproductive.
