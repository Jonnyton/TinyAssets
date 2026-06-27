import * as React from "react";

export function TinyAssetsMark({ size = 28 }: { size?: number }) {
  return (
    <img
      className="tinyassets-mark"
      src="/tinyassets-mark.png"
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

export default TinyAssetsMark;
