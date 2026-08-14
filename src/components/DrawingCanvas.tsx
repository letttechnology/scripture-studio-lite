import React, { useRef, useEffect, useState } from 'react';
import { DrawStroke, Point, ToolType } from '../types';

interface DrawingCanvasProps {
  currentTool: ToolType;
  currentColor: string;
  currentWidth: number;
  strokes: DrawStroke[];
  onStrokesChange: (strokes: DrawStroke[]) => void;
  canvasRef: React.RefObject<HTMLCanvasElement>;
}

export const DrawingCanvas: React.FC<DrawingCanvasProps> = ({
  currentTool,
  currentColor,
  currentWidth,
  strokes,
  onStrokesChange,
  canvasRef
}) => {
  const [isDrawing, setIsDrawing] = useState(false);
  const [currentPoints, setCurrentPoints] = useState<Point[]>([]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const resizeCanvas = () => {
      const parent = canvas.parentElement;
      if (parent) {
        canvas.width = parent.clientWidth;
        canvas.height = parent.clientHeight;
        redrawCanvas();
      }
    };

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    return () => window.removeEventListener('resize', resizeCanvas);
  }, [strokes]);

  const redrawCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    strokes.forEach((stroke) => {
      renderStroke(ctx, stroke);
    });

    if (currentPoints.length > 0) {
      renderStroke(ctx, {
        id: 'active',
        tool: currentTool,
        color: currentColor,
        width: currentWidth,
        opacity: currentTool === 'highlight' ? 0.35 : 1,
        points: currentPoints
      });
    }
  };

  const renderStroke = (ctx: CanvasRenderingContext2D, stroke: DrawStroke) => {
    if (stroke.points.length === 0) return;

    ctx.save();
    ctx.strokeStyle = stroke.color;
    ctx.fillStyle = stroke.color;
    ctx.lineWidth = stroke.width;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.globalAlpha = stroke.opacity;

    if (stroke.tool === 'pen' || stroke.tool === 'highlight') {
      ctx.beginPath();
      ctx.moveTo(stroke.points[0].x, stroke.points[0].y);
      for (let i = 1; i < stroke.points.length; i++) {
        const p = stroke.points[i];
        ctx.lineTo(p.x, p.y);
      }
      ctx.stroke();
    } else if (stroke.tool === 'underline') {
      const p1 = stroke.points[0];
      const p2 = stroke.points[stroke.points.length - 1];
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p1.y);
      ctx.stroke();
    } else if (stroke.tool === 'circle') {
      const p1 = stroke.points[0];
      const p2 = stroke.points[stroke.points.length - 1];
      const rx = Math.abs(p2.x - p1.x) / 2;
      const ry = Math.abs(p2.y - p1.y) / 2;
      const cx = Math.min(p1.x, p2.x) + rx;
      const cy = Math.min(p1.y, p2.y) + ry;

      ctx.beginPath();
      ctx.ellipse(cx, cy, Math.max(rx, 10), Math.max(ry, 10), 0, 0, 2 * Math.PI);
      ctx.stroke();
    } else if (stroke.tool === 'box') {
      const p1 = stroke.points[0];
      const p2 = stroke.points[stroke.points.length - 1];
      const width = p2.x - p1.x;
      const height = p2.y - p1.y;

      ctx.beginPath();
      ctx.rect(p1.x, p1.y, width, height);
      ctx.stroke();
    } else if (stroke.tool === 'arrow') {
      const p1 = stroke.points[0];
      const p2 = stroke.points[stroke.points.length - 1];
      const headLength = 16;
      const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x);

      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(p2.x, p2.y);
      ctx.lineTo(
        p2.x - headLength * Math.cos(angle - Math.PI / 6),
        p2.y - headLength * Math.sin(angle - Math.PI / 6)
      );
      ctx.lineTo(
        p2.x - headLength * Math.cos(angle + Math.PI / 6),
        p2.y - headLength * Math.sin(angle + Math.PI / 6)
      );
      ctx.closePath();
      ctx.fill();
    }

    ctx.restore();
  };

  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const pressure = e.pressure || 0.5;

    if (currentTool === 'eraser') {
      // Remove strokes near touch/click
      const filtered = strokes.filter((stroke) => {
        return !stroke.points.some(
          (p) => Math.hypot(p.x - x, p.y - y) < currentWidth * 2
        );
      });
      onStrokesChange(filtered);
      return;
    }

    setIsDrawing(true);
    setCurrentPoints([{ x, y, pressure }]);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!isDrawing && currentTool !== 'eraser') return;

    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const pressure = e.pressure || 0.5;

    if (currentTool === 'eraser' && e.buttons > 0) {
      const filtered = strokes.filter((stroke) => {
        return !stroke.points.some(
          (p) => Math.hypot(p.x - x, p.y - y) < currentWidth * 2
        );
      });
      onStrokesChange(filtered);
      return;
    }

    if (isDrawing) {
      setCurrentPoints((prev) => [...prev, { x, y, pressure }]);
      redrawCanvas();
    }
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!isDrawing) return;
    setIsDrawing(false);

    if (currentPoints.length > 0) {
      const newStroke: DrawStroke = {
        id: Date.now().toString(),
        tool: currentTool,
        color: currentColor,
        width: currentWidth,
        opacity: currentTool === 'highlight' ? 0.35 : 1,
        points: currentPoints
      };
      onStrokesChange([...strokes, newStroke]);
    }
    setCurrentPoints([]);
  };

  useEffect(() => {
    redrawCanvas();
  }, [currentPoints, strokes]);

  return (
    <canvas
      ref={canvasRef}
      className={`drawing-canvas ${currentTool === 'eraser' ? 'eraser-mode' : ''}`}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    />
  );
};
