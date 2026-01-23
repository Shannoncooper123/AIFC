import { NextResponse } from 'next/server';
import fs from 'fs/promises';
import path from 'path';

const BASE_DIR = '/home/sunfayao/monitor';
const TRADE_STATE_PATH = path.join(BASE_DIR, 'agent', 'trade_state.json');
const ASSET_TIMELINE_PATH = path.join(BASE_DIR, 'logs', 'asset_timeline.json');

// 服务器端保护：至少每10分钟记录一次，避免过于频繁写入
const MIN_INTERVAL_MINUTES = 10;
const MAX_DAYS = 7;

async function ensureTimelineFile() {
  try {
    await fs.mkdir(path.dirname(ASSET_TIMELINE_PATH), { recursive: true });
    try {
      await fs.access(ASSET_TIMELINE_PATH);
    } catch {
      const initial = { timeline: [] };
      await fs.writeFile(ASSET_TIMELINE_PATH, JSON.stringify(initial, null, 2), 'utf-8');
    }
  } catch (e) {
    // ignore; will be handled by caller
  }
}

function toISO8601NowUTC() {
  return new Date().toISOString();
}

function parseISOToDate(s: string): Date {
  try {
    return new Date(s);
  } catch {
    return new Date(0);
  }
}

async function readJsonSafe(filePath: string): Promise<any> {
  try {
    const content = await fs.readFile(filePath, 'utf-8');
    return JSON.parse(content);
  } catch {
    return null;
  }
}

async function writeJsonSafe(filePath: string, data: any) {
  await fs.writeFile(filePath, JSON.stringify(data, null, 2), 'utf-8');
}

function pruneOldEntries(timeline: any[], maxDays: number): any[] {
  const cutoff = new Date(Date.now() - maxDays * 24 * 60 * 60 * 1000);
  return timeline.filter((s) => {
    const t = parseISOToDate(s.timestamp);
    return t > cutoff;
  });
}

export async function POST() {
  try {
    await ensureTimelineFile();

    // 读取 trade_state
    const tradeState = await readJsonSafe(TRADE_STATE_PATH);
    if (!tradeState || !tradeState.account) {
      return NextResponse.json({ ok: false, error: 'trade_state.account not found' }, { status: 400 });
    }

    // 读取现有 timeline
    const timelineData = (await readJsonSafe(ASSET_TIMELINE_PATH)) || { timeline: [] };
    const timeline: any[] = Array.isArray(timelineData.timeline) ? timelineData.timeline : [];

    // 最短间隔保护：如果最近一次记录小于 MIN_INTERVAL_MINUTES，则跳过写入
    const last = timeline[timeline.length - 1];
    if (last) {
      const lastTime = parseISOToDate(last.timestamp);
      const diffMinutes = (Date.now() - lastTime.getTime()) / 60000;
      if (diffMinutes < MIN_INTERVAL_MINUTES) {
        return NextResponse.json({ ok: true, skipped: true, reason: 'interval_too_short', lastRecordedAt: last.timestamp });
      }
    }

    const account = tradeState.account || {};
    const snapshot = {
      timestamp: toISO8601NowUTC(),
      equity: Number((account.equity ?? 0.0).toFixed(2)),
      balance: Number((account.balance ?? 0.0).toFixed(2)),
      unrealized_pnl: Number((account.unrealized_pnl ?? 0.0).toFixed(2)),
      realized_pnl: Number((account.realized_pnl ?? 0.0).toFixed(2)),
      reserved_margin: Number((account.reserved_margin_sum ?? 0.0).toFixed(2)),
      positions_count: account.positions_count ?? 0,
    };

    timeline.push(snapshot);
    const pruned = pruneOldEntries(timeline, MAX_DAYS);
    const newData = { timeline: pruned };

    await writeJsonSafe(ASSET_TIMELINE_PATH, newData);

    return NextResponse.json({ ok: true, latest: snapshot, timeline_length: pruned.length });
  } catch (error) {
    console.error('Error recording asset snapshot:', error);
    return NextResponse.json({ ok: false, error: 'Failed to record asset snapshot' }, { status: 500 });
  }
}

// 可选：GET 用于调试当前时间线长度
export async function GET() {
  try {
    const data = (await readJsonSafe(ASSET_TIMELINE_PATH)) || { timeline: [] };
    return NextResponse.json({ ok: true, timeline_length: (data.timeline || []).length, latest: (data.timeline || [])[data.timeline.length - 1] || null });
  } catch (error) {
    return NextResponse.json({ ok: false }, { status: 500 });
  }
}