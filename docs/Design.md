# Scripture Studio LITE Technical Design Document

## 1. Overview & Vision
Scripture Studio LITE is a scripture drawing, annotation, and video recording application for deep biblical exegesis.

## 2. Core Architecture
- Viewport Stack: iframe for web scripture + transparent canvas overlay
- Dual-Mode Input Engine: Interact Mode (pointer-events: none) vs. Draw Mode (pointer-events: auto)
- Persistent Session Partition: persist:scripturestudio
- Combined Screen + Microphone Recording Pipeline: DisplayMedia + Mic WebM engine
