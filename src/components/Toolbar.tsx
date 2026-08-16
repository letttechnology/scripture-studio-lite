import React from 'react';
import { ToolType } from '../types';
import {
  Pencil,
  Underline as UnderlineIcon,
  Circle as CircleIcon,
  Square,
  MoveUpRight,
  Highlighter,
  Eraser,
  Undo,
  RotateCcw,
  Video,
  Square as StopSquare
} from 'lucide-react';

interface ToolbarProps {
  currentTool: ToolType;
  onSelectTool: (tool: ToolType) => void;
  currentColor: string;
  onSelectColor: (color: string) => void;
  onUndo: () => void;
  onClear: () => void;
  isRecording: boolean;
  recordingTime: number;
  onToggleRecording: () => void;
}

const COLOR_PALETTE = [
  '#ff6b35', // Piper Orange
  '#ffd166', // Accent Yellow
  '#4cc9f0', // Electric Blue
  '#06d6a0', // Lime Green
  '#ffffff'  // Pure White
];

export const Toolbar: React.FC<ToolbarProps> = ({
  currentTool,
  onSelectTool,
  currentColor,
  onSelectColor,
  onUndo,
  onClear,
  isRecording,
  recordingTime,
  onToggleRecording
}) => {
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="bottom-toolbar">
      {/* Drawing Tools Group */}
      <div className="tool-group">
        <button
          className={`icon-btn ${currentTool === 'pen' ? 'active' : ''}`}
          onClick={() => onSelectTool('pen')}
          title="Freehand Pen"
        >
          <Pencil size={18} />
        </button>
        <button
          className={`icon-btn ${currentTool === 'underline' ? 'active' : ''}`}
          onClick={() => onSelectTool('underline')}
          title="Underline"
        >
          <UnderlineIcon size={18} />
        </button>
        <button
          className={`icon-btn ${currentTool === 'circle' ? 'active' : ''}`}
          onClick={() => onSelectTool('circle')}
          title="Circle Word / Phrase"
        >
          <CircleIcon size={18} />
        </button>
        <button
          className={`icon-btn ${currentTool === 'box' ? 'active' : ''}`}
          onClick={() => onSelectTool('box')}
          title="Box / Rectangle"
        >
          <Square size={18} />
        </button>
        <button
          className={`icon-btn ${currentTool === 'arrow' ? 'active' : ''}`}
          onClick={() => onSelectTool('arrow')}
          title="Connection Arrow"
        >
          <MoveUpRight size={18} />
        </button>
        <button
          className={`icon-btn ${currentTool === 'highlight' ? 'active' : ''}`}
          onClick={() => onSelectTool('highlight')}
          title="Text Highlighter"
        >
          <Highlighter size={18} />
        </button>
        <button
          className={`icon-btn ${currentTool === 'eraser' ? 'active' : ''}`}
          onClick={() => onSelectTool('eraser')}
          title="Stroke Eraser"
        >
          <Eraser size={18} />
        </button>
      </div>

      <div className="divider" />

      {/* Color Palette */}
      <div className="tool-group">
        {COLOR_PALETTE.map((color) => (
          <div
            key={color}
            className={`color-dot ${currentColor === color ? 'active' : ''}`}
            style={{ backgroundColor: color, color: color }}
            onClick={() => onSelectColor(color)}
          />
        ))}
      </div>

      <div className="divider" />

      {/* History Controls */}
      <div className="tool-group">
        <button className="icon-btn" onClick={onUndo} title="Undo Stroke (Ctrl+Z)">
          <Undo size={18} />
        </button>
        <button className="icon-btn" onClick={onClear} title="Clear All Annotations">
          <RotateCcw size={18} />
        </button>
      </div>

      <div className="divider" />

      {/* Recording Control */}
      <div className="tool-group">
        {isRecording ? (
          <div className="rec-badge" onClick={onToggleRecording} style={{ cursor: 'pointer' }}>
            <div className="rec-dot" />
            <span>{formatTime(recordingTime)}</span>
            <StopSquare size={16} fill="#ff4d4d" style={{ marginLeft: '4px' }} />
          </div>
        ) : (
          <button
            className="icon-btn"
            onClick={onToggleRecording}
            title="Start Audio & Screen Video Recording"
            style={{ color: '#ff4d4d', background: 'rgba(255, 77, 77, 0.15)' }}
          >
            <Video size={20} />
          </button>
        )}
      </div>
    </div>
  );
};
