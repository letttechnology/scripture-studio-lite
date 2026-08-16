import React, { useState, useRef, useEffect } from 'react';
import { DrawingCanvas } from './components/DrawingCanvas';
import { ScriptureViewer } from './components/ScriptureViewer';
import { Toolbar } from './components/Toolbar';
import { DrawStroke, ScripturePassage, StudioConfig, ToolType } from './types';
import { BookOpen, Type, Sliders, Download, Layers } from 'lucide-react';

const SAMPLE_PASSAGES: ScripturePassage[] = [
  {
    title: "What Is God's Grace?",
    reference: "1 Corinthians 1:4–9",
    verses: [
      { number: 4, text: "I give thanks to my God always for you because of the grace of God that was given you in Christ Jesus," },
      { number: 5, text: "that in every way you were enriched in him in all speech and all knowledge—" },
      { number: 6, text: "even as the testimony of Christ was confirmed among you—" },
      { number: 7, text: "so that you are not lacking in any gift, as you wait eagerly for the revealing of our Lord Jesus Christ," },
      { number: 8, text: "who will confirm you to the end, guiltless in the day of our Lord Jesus Christ." },
      { number: 9, text: "God is faithful, by whom you were called into the fellowship of his Son, Jesus Christ our Lord." }
    ]
  },
  {
    title: "In the Beginning Was the Word",
    reference: "John 1:1–5",
    verses: [
      { number: 1, text: "In the beginning was the Word, and the Word was with God, and the Word was God." },
      { number: 2, text: "He was in the beginning with God." },
      { number: 3, text: "All things were made through him, and without him was not any thing made that was made." },
      { number: 4, text: "In him was life, and the life was the light of men." },
      { number: 5, text: "The light shines in the darkness, and the darkness has not overcome it." }
    ]
  }
];

export const App: React.FC = () => {
  const [selectedPassage, setSelectedPassage] = useState<ScripturePassage>(SAMPLE_PASSAGES[0]);
  const [customText, setCustomText] = useState<string>('');
  const [isCustomMode, setIsCustomMode] = useState<boolean>(false);

  const [currentTool, setCurrentTool] = useState<ToolType>('pen');
  const [currentColor, setCurrentColor] = useState<string>('#ff6b35');
  const [currentWidth, setCurrentWidth] = useState<number>(3);
  const [strokes, setStrokes] = useState<DrawStroke[]>([]);

  const [config, setConfig] = useState<StudioConfig>({
    fontSize: 28,
    lineHeight: 2.2,
    fontFamily: 'Inter',
    textColor: '#e0e0e0',
    backgroundColor: '#121212',
    showVerseNumbers: true
  });

  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [recordedVideoUrl, setRecordedVideoUrl] = useState<string | null>(null);
  const [autoSave, setAutoSave] = useState(false);
  const [hasDownloaded, setHasDownloaded] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const previewVideoRef = useRef<HTMLVideoElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunksRef = useRef<Blob[]>([]);
  const timerIntervalRef = useRef<any>(null);

  // Recording Timer
  useEffect(() => {
    if (isRecording) {
      timerIntervalRef.current = setInterval(() => {
        setRecordingTime((prev) => prev + 1);
      }, 1000);
    } else {
      clearInterval(timerIntervalRef.current);
    }
    return () => clearInterval(timerIntervalRef.current);
  }, [isRecording]);

  const handleUndo = () => {
    setStrokes((prev) => prev.slice(0, -1));
  };

  const handleClear = () => {
    setStrokes([]);
  };

  const startRecording = async () => {
    try {
      // Access Microphone Audio
      const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // Capture Canvas Stream (30fps for smooth flicker-free capture)
      const canvas = canvasRef.current;
      if (!canvas) return;
      const canvasStream = canvas.captureStream(30);

      // Combine Canvas Video Track + Audio Track
      const combinedStream = new MediaStream([
        ...canvasStream.getVideoTracks(),
        ...audioStream.getAudioTracks()
      ]);

      const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
        ? 'video/webm;codecs=vp9,opus'
        : 'video/webm';

      const recorder = new MediaRecorder(combinedStream, { mimeType });
      recordedChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          recordedChunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        const blob = new Blob(recordedChunksRef.current, { type: 'video/webm' });
        const url = URL.createObjectURL(blob);
        setRecordedVideoUrl(url);
        setHasDownloaded(false);

        const now = new Date();
        const YYYY = now.getFullYear();
        const MM = String(now.getMonth() + 1).padStart(2, '0');
        const DD = String(now.getDate()).padStart(2, '0');
        const hh = String(now.getHours()).padStart(2, '0');
        const mm = String(now.getMinutes()).padStart(2, '0');
        const ss = String(now.getSeconds()).padStart(2, '0');
        const timestampFilename = `scripture-studio-recording-${YYYY}${MM}${DD}-${hh}${mm}${ss}.webm`;

        // Auto-Save recording if setting is enabled
        if (autoSave) {
          const a = document.createElement('a');
          a.href = url;
          a.download = timestampFilename;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          setHasDownloaded(true);
        }

        // Stop audio tracks
        audioStream.getTracks().forEach((track) => track.stop());
      };

      recorder.start(100);
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
      setRecordingTime(0);
    } catch (err) {
      alert('Microphone/Screen permission access is required to record audio and video.');
      console.error(err);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const handleCloseModal = () => {
    if (!hasDownloaded && !autoSave) {
      const confirmDiscard = window.confirm(
        'You have an unsaved video recording. Are you sure you want to close and discard it?'
      );
      if (!confirmDiscard) return;
    }

    if (previewVideoRef.current) {
      previewVideoRef.current.pause();
      previewVideoRef.current.currentTime = 0;
    }
    if (recordedVideoUrl) {
      URL.revokeObjectURL(recordedVideoUrl);
    }
    setRecordedVideoUrl(null);
    setHasDownloaded(false);
  };

  const currentPassageData = isCustomMode
    ? {
        title: 'Custom Passage',
        reference: 'User Text Input',
        verses: customText
          ? customText.split('\n').filter(Boolean).map((line, idx) => ({ number: idx + 1, text: line }))
          : [{ number: 1, text: 'Type or paste custom text to begin drawing.' }]
      }
    : selectedPassage;

  return (
    <div className="app-container">
      {/* Top Header Bar */}
      <div className="top-bar">
        <div className="studio-title">
          <BookOpen size={22} />
          <span>SCRIPTURE STUDIO</span>
          <span className="studio-badge">LOOK AT THE BOOK</span>
        </div>

        {/* Passage & Layout Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <select
            value={isCustomMode ? 'custom' : selectedPassage.reference}
            onChange={(e) => {
              if (e.target.value === 'custom') {
                setIsCustomMode(true);
              } else {
                setIsCustomMode(false);
                const passage = SAMPLE_PASSAGES.find((p) => p.reference === e.target.value);
                if (passage) setSelectedPassage(passage);
              }
            }}
            style={{
              background: '#2a2a2a',
              color: '#ffffff',
              border: '1px solid #444',
              padding: '6px 12px',
              borderRadius: '6px',
              cursor: 'pointer'
            }}
          >
            {SAMPLE_PASSAGES.map((p) => (
              <option key={p.reference} value={p.reference}>
                {p.title} ({p.reference})
              </option>
            ))}
            <option value="custom">Custom Passage...</option>
          </select>

          {/* Line Height Control */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#888', fontSize: '0.85rem' }}>
            <Type size={16} />
            <span>Spacing:</span>
            <input
              type="range"
              min="1.5"
              max="3.5"
              step="0.1"
              value={config.lineHeight}
              onChange={(e) => setConfig({ ...config, lineHeight: parseFloat(e.target.value) })}
              style={{ width: '80px', accentColor: '#ff6b35' }}
            />
          </div>

          {/* Auto-Save Toggle */}
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#aaa', fontSize: '0.85rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={autoSave}
              onChange={(e) => setAutoSave(e.target.checked)}
              style={{ accentColor: '#ff6b35' }}
            />
            <span>Auto-Save</span>
          </label>
        </div>
      </div>

      {/* Main Scripture & Drawing Canvas Viewport */}
      <div className="viewport-area">
        <ScriptureViewer passage={currentPassageData} config={config} />
        <DrawingCanvas
          currentTool={currentTool}
          currentColor={currentColor}
          currentWidth={currentWidth}
          strokes={strokes}
          onStrokesChange={setStrokes}
          canvasRef={canvasRef}
        />
      </div>

      {/* Bottom Floating Toolbar */}
      <Toolbar
        currentTool={currentTool}
        onSelectTool={setCurrentTool}
        currentColor={currentColor}
        onSelectColor={setCurrentColor}
        onUndo={handleUndo}
        onClear={handleClear}
        isRecording={isRecording}
        recordingTime={recordingTime}
        onToggleRecording={toggleRecording}
      />

      {/* Video Preview Modal */}
      {recordedVideoUrl && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.85)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000
          }}
        >
          <div
            style={{
              background: '#1e1e1e',
              borderRadius: '16px',
              padding: '24px',
              maxWidth: '720px',
              width: '90%',
              border: '1px solid #333',
              boxShadow: '0 20px 50px rgba(0,0,0,0.8)'
            }}
          >
            <h2 style={{ color: '#ff6b35', marginBottom: '16px', fontFamily: "'Outfit', sans-serif" }}>
              Recording Complete!
            </h2>
            <video ref={previewVideoRef} src={recordedVideoUrl} controls autoPlay style={{ width: '100%', borderRadius: '8px', marginBottom: '20px' }} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button
                onClick={handleCloseModal}
                style={{
                  background: 'transparent',
                  color: '#aaa',
                  border: '1px solid #444',
                  padding: '8px 16px',
                  borderRadius: '6px',
                  cursor: 'pointer'
                }}
              >
                Close
              </button>
              <a
                href={recordedVideoUrl}
                download={(() => {
                  const now = new Date();
                  const YYYY = now.getFullYear();
                  const MM = String(now.getMonth() + 1).padStart(2, '0');
                  const DD = String(now.getDate()).padStart(2, '0');
                  const hh = String(now.getHours()).padStart(2, '0');
                  const mm = String(now.getMinutes()).padStart(2, '0');
                  const ss = String(now.getSeconds()).padStart(2, '0');
                  return `scripture-studio-recording-${YYYY}${MM}${DD}-${hh}${mm}${ss}.webm`;
                })()}
                onClick={() => setHasDownloaded(true)}
                style={{
                  background: '#ff6b35',
                  color: '#fff',
                  padding: '8px 20px',
                  borderRadius: '6px',
                  textDecoration: 'none',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}
              >
                <Download size={16} /> Download Video
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
