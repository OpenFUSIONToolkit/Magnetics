import { useRef, useCallback } from "react";

interface Props {
  direction: "horizontal" | "vertical";
  onDelta: (delta: number) => void;
  onDeltaEnd?: () => void;
}

export default function DraggableDivider({ direction, onDelta, onDeltaEnd }: Props) {
  const dragging = useRef(false);
  const startPos = useRef(0);
  const rafId = useRef(0);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragging.current = true;
    startPos.current = direction === "horizontal" ? e.clientX : e.clientY;
    document.body.style.cursor = direction === "horizontal" ? "col-resize" : "row-resize";
    document.body.style.userSelect = "none";

    const handleMouseMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      cancelAnimationFrame(rafId.current);
      rafId.current = requestAnimationFrame(() => {
        const pos = direction === "horizontal" ? e.clientX : e.clientY;
        onDelta(pos - startPos.current);
        startPos.current = pos;
      });
    };

    const handleMouseUp = () => {
      dragging.current = false;
      cancelAnimationFrame(rafId.current);
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      onDeltaEnd?.();
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
  }, [direction, onDelta, onDeltaEnd]);

  return (
    <div
      onMouseDown={handleMouseDown}
      style={{
        flex: "0 0 7px",
        cursor: direction === "horizontal" ? "col-resize" : "row-resize",
        position: "relative",
        zIndex: 10,
      }}
    >
      <div
        style={{
          position: "absolute",
          ...(direction === "horizontal"
            ? { top: 0, bottom: 0, left: "2px", right: "2px" }
            : { left: 0, right: 0, top: "2px", bottom: "2px" }
          ),
          background: "var(--border)",
          borderRadius: "2px",
          transition: "background 0.15s",
        }}
      />
    </div>
  );
}
