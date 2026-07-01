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

  // Keyboard nudge: arrow keys resize via the same onDelta callback the drag uses,
  // so the divider is operable without a pointer.
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    const STEP = 10;
    const key = e.key;
    const delta =
      direction === "horizontal"
        ? key === "ArrowLeft" ? -STEP : key === "ArrowRight" ? STEP : 0
        : key === "ArrowUp" ? -STEP : key === "ArrowDown" ? STEP : 0;
    if (delta === 0) return;
    e.preventDefault();
    onDelta(delta);
    onDeltaEnd?.();
  }, [direction, onDelta, onDeltaEnd]);

  const isH = direction === "horizontal";
  // Widen the interactive target to ≥24px (WCAG) while keeping the visual line thin:
  // negative margins on the cross axis reclaim the extra hit width so the layout
  // footprint stays ~the original 7px.
  const HIT = 24;
  const OFFSET = (HIT - 7) / 2;

  return (
    <div
      className="draggable-divider"
      role="separator"
      aria-orientation={isH ? "vertical" : "horizontal"}
      tabIndex={0}
      onMouseDown={handleMouseDown}
      onKeyDown={handleKeyDown}
      style={{
        flex: `0 0 ${HIT}px`,
        margin: isH ? `0 -${OFFSET}px` : `-${OFFSET}px 0`,
        cursor: isH ? "col-resize" : "row-resize",
        position: "relative",
        zIndex: 10,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        className="draggable-divider-line"
        style={{
          position: "absolute",
          ...(isH
            ? { top: 0, bottom: 0, width: "3px" }
            : { left: 0, right: 0, height: "3px" }
          ),
        }}
      />
    </div>
  );
}
