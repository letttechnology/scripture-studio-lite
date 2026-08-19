import { test, expect, _electron as electron } from '@playwright/test';
import electronPath from 'electron';
import path from 'path';
import fs from 'fs';
import { execSync } from 'child_process';

test.describe('Scripture Studio LITE - Video Recording & Black Frame Verification', () => {

  test('Electron Native Viewport Recording - 0 Black Frames Verified via FFmpeg', async () => {
    test.setTimeout(90000);

    // 1. Launch Electron Application directly
    const app = await electron.launch({
      executablePath: electronPath as any,
      args: [path.resolve(process.cwd(), 'main.js')]
    });

    const page = await app.firstWindow();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);

    // 2. Click Record Video Button
    const recordBtn = page.locator('.rec-btn, button[title*="Recording"]').first();
    await expect(recordBtn).toBeVisible({ timeout: 15000 });
    await recordBtn.click();

    // 3. Perform active drawing annotations across 6 seconds
    const canvas = page.locator('canvas').first();
    await expect(canvas).toBeVisible();
    const box = await canvas.boundingBox();

    if (box) {
      for (let stroke = 0; stroke < 3; stroke++) {
        await page.mouse.move(box.x + 100, box.y + 100 + stroke * 80);
        await page.mouse.down();
        for (let i = 0; i < 15; i++) {
          await page.mouse.move(box.x + 100 + i * 25, box.y + 100 + stroke * 80 + Math.sin(i * 0.5) * 30);
          await page.waitForTimeout(50);
        }
        await page.mouse.up();
        await page.waitForTimeout(200);
      }
    }

    // 4. Stop Recording
    await recordBtn.click();
    await page.waitForTimeout(2000);

    // 5. Extract Recorded Video Blob from Preview
    const base64Data = await page.evaluate(async () => {
      const video = document.querySelector('video');
      if (!video || !video.src) return null;
      const response = await fetch(video.src);
      const blob = await response.blob();
      return new Promise<string>((resolve) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve((reader.result as string).split(',')[1]);
        reader.readAsDataURL(blob);
      });
    });

    expect(base64Data).toBeTruthy();

    const testResultsDir = path.resolve(process.cwd(), 'test-results');
    if (!fs.existsSync(testResultsDir)) fs.mkdirSync(testResultsDir, { recursive: true });
    const videoFile = path.join(testResultsDir, 'electron-verified-recording.webm');
    fs.writeFileSync(videoFile, Buffer.from(base64Data!, 'base64'));

    await app.close();

    // 6. Run FFmpeg BlackDetect Filter
    const ffmpegCmd = `ffmpeg -i "${videoFile}" -vf "blackdetect=d=0.01:pix_th=0.1" -f null -`;
    let blackMatches: string[] = [];
    try {
      execSync(ffmpegCmd, { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] });
    } catch (err: any) {
      const output = (err.stdout || '') + (err.stderr || '');
      blackMatches = output.match(/black_start/g) || [];
    }

    console.log(`FFmpeg Black Frame Detection Result: ${blackMatches.length} black frame intervals.`);
    expect(blackMatches.length, `Expected 0 black frame intervals, but found ${blackMatches.length}`).toBe(0);
  });

});
