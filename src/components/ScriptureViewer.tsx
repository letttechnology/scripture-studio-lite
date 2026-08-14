import React from 'react';
import { ScripturePassage, StudioConfig } from '../types';

interface ScriptureViewerProps {
  passage: ScripturePassage;
  config: StudioConfig;
}

export const ScriptureViewer: React.FC<ScriptureViewerProps> = ({ passage, config }) => {
  return (
    <div
      className="scripture-container"
      style={{
        fontFamily: config.fontFamily,
        fontSize: `${config.fontSize}px`,
        lineHeight: config.lineHeight,
        color: config.textColor,
      }}
    >
      <div style={{ marginBottom: '32px', textAlign: 'center' }}>
        <h1
          style={{
            fontFamily: "'Outfit', sans-serif",
            fontSize: '1.8em',
            fontWeight: 700,
            color: '#ff6b35',
            letterSpacing: '0.02em',
            marginBottom: '6px'
          }}
        >
          {passage.title}
        </h1>
        <div style={{ color: '#888888', fontSize: '0.9em', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          {passage.reference}
        </div>
      </div>

      <div style={{ maxWidth: '850px', margin: '0 auto', textAlign: 'justify' }}>
        {passage.verses.map((verse) => (
          <span key={verse.number} style={{ display: 'inline', marginRight: '6px' }}>
            {config.showVerseNumbers && (
              <sup className="verse-num">{verse.number}</sup>
            )}
            <span>{verse.text} </span>
          </span>
        ))}
      </div>
    </div>
  );
};
