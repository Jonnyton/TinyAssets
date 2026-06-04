<!-- WorkflowMark -- cropped from the selected A2 rotated chat image. -->
<script lang="ts">
  let {
    size = 28
  } = $props();
</script>

<img
  class="workflow-mark"
  src="/workflow-mark.png"
  alt=""
  aria-hidden="true"
  width={size}
  height={size}
  decoding="async"
  style={`--mark-size:${size}px`}
/>

<style>
  .workflow-mark {
    display: block;
    flex-shrink: 0;
    width: var(--mark-size);
    height: var(--mark-size);
    object-fit: cover;
    border-radius: 5px;
  }
</style>
