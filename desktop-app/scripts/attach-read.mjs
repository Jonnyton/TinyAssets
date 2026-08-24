// Read the TinyAssets desktop app's visible conversation over its opt-in CDP
// endpoint (launch the app with `--attach`, then run this). Loopback only.
//
//   node scripts/attach-read.mjs [port]
//
// Prints the rendered text of the app's <main> — i.e. the current conversation —
// so a tester/agent can SEE what the desktop app is showing without a browser.
const port = process.argv[2] || '9222';

async function main() {
  const listRes = await fetch(`http://127.0.0.1:${port}/json/list`);
  const targets = await listRes.json();
  const page = targets.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
  if (!page) {
    console.error('No page target on CDP port ' + port + ' — is the app running with --attach?');
    process.exit(1);
  }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  const send = (id, method, params) =>
    ws.send(JSON.stringify({ id, method, params: params || {} }));
  await new Promise((resolve, reject) => {
    ws.addEventListener('error', reject);
    ws.addEventListener('open', () => {
      send(1, 'Runtime.enable');
      send(2, 'Runtime.evaluate', {
        expression:
          "(document.querySelector('main')||document.body).innerText",
        returnByValue: true,
      });
    });
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id === 2) {
        const text = msg.result?.result?.value ?? '(no value)';
        console.log('URL page:', page.url);
        console.log('---- desktop <main> text ----');
        console.log(text);
        ws.close();
        resolve();
      }
    });
  });
}

main().catch((e) => {
  console.error('attach-read failed:', e.message);
  process.exit(1);
});
