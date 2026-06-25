import * as React from "react";

export function WorkflowMark({ size = 28 }: { size?: number }) {
  return (
    <img
      className="workflow-mark"
      src="/workflow-mark.png"
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      decoding="async"
      style={{
        display: "block",
        flexShrink: 0,
        width: size,
        height: size,
        objectFit: "cover",
        borderRadius: 5,
      }}
    />
  );
}

export default WorkflowMark;
