<!--
  StatusPill — daemon-status capsule. Live / idle / paid / self / error.
  Ported from design-source/ui_kits/workflow-web/Primitives.jsx
-->
<script lang="ts">
  type Kind = 'live' | 'idle' | 'paid' | 'self' | 'error';

  let {
    children,
    kind = 'live' as Kind,
    pulse = false
  } = $props();
</script>

<span class="pill pill--{kind}">
  <span class="dot" class:pulse></span>
  {@render children?.()}
</span>

<style>
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 4px 11px 4px 9px;
    border-radius: 999px;
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    border: 1px solid;
  }
  .pill--live   { background: rgba(109,211,166,0.1);  color: #8de6bf; border-color: rgba(109,211,166,0.3); }
  .pill--idle   { background: rgba(217,168,74,0.1);   color: #e6bc6c; border-color: rgba(217,168,74,0.3); }
  .pill--paid   { background: rgba(138,99,206,0.12);  color: #c1aae3; border-color: rgba(138,99,206,0.3); }
  .pill--self   { background: rgba(255,255,255,0.04); color: var(--fg-2); border-color: var(--border-1); }
  .pill--error  { background: rgba(233,69,96,0.12);   color: #f48ba1; border-color: rgba(233,69,96,0.35); }

  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
  }
  .pill--live  .dot { background: #6dd3a6; }
  .pill--idle  .dot { background: #d9a84a; }
  .pill--paid  .dot { background: #8a63ce; }
  .pill--self  .dot { background: var(--fg-3); }
  .pill--error .dot { background: #e94560; }

  .dot.pulse {
    animation: pulse 1.8s infinite ease-in-out;
  }
  .pill--live .dot.pulse { box-shadow: 0 0 8px #6dd3a6; }
  .pill--paid .dot.pulse { box-shadow: 0 0 8px #8a63ce; }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.45; }
  }
</style>
