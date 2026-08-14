export type ToolType = 'pen' | 'underline' | 'circle' | 'box' | 'arrow' | 'highlight' | 'eraser';

export interface Point {
  x: number;
  y: number;
  pressure?: number;
}

export interface DrawStroke {
  id: string;
  tool: ToolType;
  color: string;
  width: number;
  opacity: number;
  points: Point[];
}

export interface ScripturePassage {
  title: string;
  reference: string;
  verses: {
    number: number;
    text: string;
  }[];
}

export interface StudioConfig {
  fontSize: number;
  lineHeight: number;
  fontFamily: string;
  textColor: string;
  backgroundColor: string;
  showVerseNumbers: boolean;
}
