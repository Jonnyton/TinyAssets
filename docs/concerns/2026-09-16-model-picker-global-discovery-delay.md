# Model switching waits on unrelated source discovery

Filed September16,2026. Original-owner live app picker disables choice while
refreshing the entire catalogue. Fable5.1 confirms global client freshness and
synchronous per-member discovery in providers/served_model_plan.py. A slow or
expired source can delay selecting a different accepted source and its execution.

Small connection-clarity patch reuses an unexpired scoped snapshot on reopen,
but does not solve first-open/server planning delay. Follow up with per-source
freshness and discovery isolation, keeping execution-time authority checks,
cost limits, exact explicit choices and truthful unknown availability. Do not
claim this solved by promoting the button or enabling stale choices globally.
