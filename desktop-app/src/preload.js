// Minimal preload. The desktop shell is a pure webview over the live SPA; the
// renderer needs no privileged bridge, so this deliberately exposes nothing.
// It exists as the seam where a later OpenAI-loopback bridge (start a local
// 127.0.0.1 listener in the main process, hand the caught code back to the SPA)
// would attach via contextBridge — kept empty until that follow-up ships.
'use strict';
