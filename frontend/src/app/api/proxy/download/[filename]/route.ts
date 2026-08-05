import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:5001'

export const maxDuration = 600
export const dynamic = 'force-dynamic'

// Browser -> /api/proxy/download/<file> -> backend /api/download/<file>
// Public (auth yok). Backend kendisi filename formatini ve path traversal'i kontrol eder.
// Response'u stream olarak forward ederiz (bellekte buffer yok, buyuk PDF'lerde OOM yok).
// Guvenli ASCII subset: kullanici dosya adi Content-Disposition header'ina
// girmeden once sanitize edilir. Unicode karakterler icin filename* RFC5987
// encoding'i kullaniriz.
function sanitizeAscii(name: string): string {
    return name.replace(/[\r\n"\\\/]/g, '_').replace(/[^\x20-\x7E]/g, '_').slice(0, 200)
}

export async function GET(
    request: NextRequest,
    context: { params: Promise<{ filename: string }> }
) {
    try {
        const { filename } = await context.params
        if (!/^out_[\w\-.]+_[a-f0-9]{8}\.pdf$/.test(filename)) {
            return NextResponse.json({ error: 'invalid filename' }, { status: 400 })
        }

        const upstream = await fetch(`${BACKEND_URL}/api/download/${encodeURIComponent(filename)}`, {
            method: 'GET',
            signal: AbortSignal.timeout(595_000),
        })

        if (!upstream.ok) {
            const err = await upstream.json().catch(() => ({ error: 'upstream error' }))
            return NextResponse.json(err, { status: upstream.status })
        }

        // Browser'in kullanici-dostu dosya adini ayarla. Query string ?name=...
        // ile frontend xlsx dosya adini gonderir; Content-Disposition header'i
        // hem ASCII (filename=) hem UTF-8 (filename*=) varyantlari icerir.
        const rawName = request.nextUrl.searchParams.get('name') || filename
        const asciiName = sanitizeAscii(rawName) || 'document.pdf'
        const utf8Name = encodeURIComponent(rawName)
        const disposition = `attachment; filename="${asciiName}"; filename*=UTF-8''${utf8Name}`

        return new NextResponse(upstream.body, {
            status: 200,
            headers: {
                'Content-Type': 'application/pdf',
                'Content-Disposition': disposition,
                'Cache-Control': 'public, max-age=3600',
            },
        })
    } catch (error) {
        console.error('Download proxy error:', error)
        return NextResponse.json({ error: 'download failed' }, { status: 500 })
    }
}
