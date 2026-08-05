'use client'

import { Button } from "@/components/ui/button"
import { CheckCircle } from 'lucide-react'
import { useState, useEffect } from 'react'

interface ResultPageProps {
  fileName: string
  downloadUrl: string
  sizeMb?: number
  processingTime?: number
  pages?: number
  turboMode?: boolean
  onReset: () => void
}

export function ResultPage({ fileName, downloadUrl, sizeMb, processingTime, pages, turboMode, onReset }: ResultPageProps) {
  const suggestedName = fileName.replace(/\.xlsx$/i, '.pdf')

  // Çarpan: normalTime(1.5 sayfa/sn) / actualTime
  const multiplier = (pages && processingTime && processingTime > 0)
    ? Math.round(pages / 1.5 / processingTime)
    : null
  const showTurboImpact = turboMode && multiplier && multiplier >= 2

  // Sayfa başına süre — 1sn altı ms, üstü saniye
  const perPageMs = (pages && processingTime) ? (processingTime / pages) * 1000 : null
  const msPerPage = perPageMs
    ? perPageMs < 1000
      ? `${Math.round(perPageMs)} milisaniyede`
      : `${(perPageMs / 1000).toFixed(1)} saniyede`
    : null

  const timeLabel = processingTime
    ? processingTime < 60
      ? `${Math.round(processingTime)} saniyede`
      : `${Math.round(processingTime / 60)} dakikada`
    : null

  // Vurgu SADECE ms satirinda ve sadece rakamda — "Her 23 milisaniyede..."
  const perPageNum = perPageMs
    ? perPageMs < 1000 ? String(Math.round(perPageMs)) : (perPageMs / 1000).toFixed(1)
    : null
  const perPageUnit = perPageMs ? (perPageMs < 1000 ? 'milisaniyede' : 'saniyede') : null

  const lines: React.ReactNode[] = [
    <>
      {pages ? `${pages} sayfa` : 'PDF'}
      {timeLabel ? ` ${timeLabel} oluşturuldu` : ' oluşturuldu'}
    </>,
    ...(perPageNum ? [
      <>Her <span className="font-semibold text-gray-900">{perPageNum}</span> {perPageUnit} bir PDF üretildi</>
    ] : []),
  ]

  // Sirali gecis: once eskisi tamamen cikar, SONRA yenisi girer.
  // Crossfade'de ikisi ayni anda yari saydam olup ust uste biniyordu (hayalet etkisi).
  const [lineIdx, setLineIdx] = useState(0)
  const [visible, setVisible] = useState(true)
  useEffect(() => {
    if (lines.length < 2) return
    let swap: ReturnType<typeof setTimeout>
    const id = setInterval(() => {
      setVisible(false)
      swap = setTimeout(() => {
        setLineIdx((i) => (i + 1) % lines.length)
        setVisible(true)
      }, 650)  // fade-out bitince degistir
    }, 4000)
    return () => { clearInterval(id); clearTimeout(swap) }
  }, [lines.length])


  return (
    <div className="text-center">
      <div className="bg-green-50 rounded-full w-14 h-14 mx-auto flex items-center justify-center mb-4">
        <CheckCircle className="w-8 h-8 text-green-600" strokeWidth={2.25} />
      </div>
      <div>
        <h2 className="text-4xl font-bold text-gray-900 tracking-tight">PDF Hazır!</h2>
        {/* Iki metin donusumlu — blur-fade gecis */}
        <div className="mt-2 h-5">
          <p
            className="text-gray-500 text-sm"
            style={{
              opacity: visible ? 1 : 0,
              filter: visible ? 'blur(0px)' : 'blur(3px)',
              transition: 'opacity 650ms cubic-bezier(0.4, 0, 0.2, 1), filter 650ms cubic-bezier(0.4, 0, 0.2, 1)',
            }}
          >
            {lines[lineIdx]}
          </p>
        </div>
      </div>
      {showTurboImpact && (
        <div className="flex justify-center mt-4">
          <div className="relative group inline-flex items-center gap-2 px-4 py-2 rounded-full cursor-default"
            style={{
              background: 'linear-gradient(#fff, #fff) padding-box, linear-gradient(90deg, #FF2D00, #FF8C00, #FFE234) border-box',
              border: '1.5px solid transparent',
              boxShadow: '0 1px 8px rgba(255, 140, 0, 0.10)',
            }}>
            <svg width="20" height="20" viewBox="5 1 14 21" fill="none">
              <defs>
                <linearGradient id="fireGradResult" x1="12" y1="22" x2="12" y2="2" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stopColor="#FF2D00" />
                  <stop offset="45%" stopColor="#FF8C00" />
                  <stop offset="100%" stopColor="#FFE234" />
                </linearGradient>
              </defs>
              <path d="M12 2C12 2 6 8 6 14a6 6 0 0 0 12 0c0-3-1.5-5.5-3-7.5 0 0 0 3-2 4 0-3-1-5.5-1-6.5Z" fill="url(#fireGradResult)" />
              <path d="M12 14c0 1.5-.8 2.5-2 3 .3-1 .3-2-.5-3 .8.2 1.8-1 2-3 .5 1 .5 2 .5 3Z" fill="#FFE234" opacity="0.9"/>
            </svg>
            <span className="text-sm font-bold"
              style={{ background: 'linear-gradient(90deg, #FF2D00 0%, #FF6B00 60%, #FF9500 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
              {multiplier}× daha hızlı üretildi
            </span>
          </div>
        </div>
      )}
      <div className="flex flex-col sm:flex-row justify-center gap-3 mt-6">
        <a
          href={downloadUrl}
          download={suggestedName}
          className="inline-flex items-center justify-center rounded-lg bg-primary px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary/90 transition-colors"
        >
          PDF indir
        </a>
        <Button variant="outline" onClick={onReset} className="rounded-lg px-6 py-2.5 text-sm font-semibold h-auto">
          Yeni PDF oluştur
        </Button>
      </div>
    </div>
  )
}
