import { NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:5001'
const API_KEY = process.env.API_KEY || ''

// Anlik yuk: kac is calisiyor, her isin dustugu worker payi ne.
// Rozet bunu okur; cache'lenmemeli, her cagride taze.
export async function GET() {
    try {
        const response = await fetch(`${BACKEND_URL}/api/active`, {
            method: 'GET',
            headers: { 'Authorization': `Bearer ${API_KEY}` },
            cache: 'no-store',
        })
        const data = await response.json()
        return NextResponse.json(data, { status: response.status })
    } catch (error) {
        console.error('Proxy error:', error)
        // Rozet, backend'e ulasilamadiginda sessizce gizlenir.
        return NextResponse.json({ active_jobs: 0, unavailable: true }, { status: 200 })
    }
}

export async function OPTIONS() {
    return NextResponse.json({}, { status: 200 })
}
