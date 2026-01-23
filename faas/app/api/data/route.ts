import { NextResponse } from 'next/server';
import fs from 'fs/promises';
import path from 'path';

const BASE_DIR = '/home/sunfayao/monitor';

const FILE_PATHS = {
    'trade_state': path.join(BASE_DIR, 'agent', 'trade_state.json'),
    'asset_timeline': path.join(BASE_DIR, 'logs', 'asset_timeline.json'),
    'position_history': path.join(BASE_DIR, 'logs', 'position_history.json'),
    'agent_reports': path.join(BASE_DIR, 'logs', 'agent_reports.json'),
    'pending_orders': path.join(BASE_DIR, 'agent', 'pending_orders.json'),
};

async function readJsonFile(filePath: string, sliceEnd?: number) {
    try {
        const content = await fs.readFile(filePath, 'utf-8');
        const data = JSON.parse(content);

        if (sliceEnd) {
            if (data.timeline) data.timeline = data.timeline.slice(-sliceEnd);
            if (data.positions) data.positions = data.positions.slice(-sliceEnd);
            if (data.reports) data.reports = data.reports.slice(-sliceEnd);
        }

        return data;
    } catch (error) {
        console.error(`Error reading or parsing file ${filePath}:`, error);
        return null;
    }
}

export async function GET() {
    try {
        const [trade_state, asset_timeline, position_history, agent_reports, pending_orders] = await Promise.all([
            readJsonFile(FILE_PATHS.trade_state),
            readJsonFile(FILE_PATHS.asset_timeline, 500),
            readJsonFile(FILE_PATHS.position_history, 30),
            readJsonFile(FILE_PATHS.agent_reports,10),
            readJsonFile(FILE_PATHS.pending_orders),
        ]);

        return NextResponse.json({ 
            trade_state, 
            asset_timeline, 
            position_history, 
            agent_reports, 
            pending_orders 
        });
    } catch (error) {
        console.error('Error fetching dashboard data:', error);
        return NextResponse.json({ error: 'Failed to fetch dashboard data' }, { status: 500 });
    }
}

