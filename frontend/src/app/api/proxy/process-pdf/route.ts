import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:5001'
const API_KEY = process.env.API_KEY || ''

export const maxDuration = 600
export const dynamic = 'force-dynamic'

export async function POST(request: NextRequest) {
    try {
        const body = await request.json()

        const response = await fetch(`${BACKEND_URL}/process-pdf`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${API_KEY}`,
            },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(595_000),
        })

        // Backend artik JSON doner: { filename, download_url, size_mb, processing_time_sec, pages, job_id }
        const data = await response.json().catch(() => ({ error: 'Invalid backend response' }))
        return NextResponse.json(data, { status: response.status })
    } catch (error) {
        console.error('Proxy error:', error)
        const message = error instanceof Error ? error.message : 'Backend connection failed'
        return NextResponse.json({ error: message }, { status: 500 })
    }
}

export async function OPTIONS() {
    return NextResponse.json({}, { status: 200 })
}
