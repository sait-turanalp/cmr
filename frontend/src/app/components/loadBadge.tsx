'use client'

import { useEffect, useState } from 'react'

/**
 * Anlik yuk rozeti — sag ust kosede, yalnizca 2+ es zamanli uretim varken.
 *
 * Sayilan sey acik sekme degil, CALISAN uretim: backend'deki aktif is sayaci.
 * 20 sekme acik ama uretim yoksa gorunmez; iki sekmede ayni anda uretim varsa 2.
 */
export function LoadBadge() {
  const [active, setActive] = useState(0)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      try {
        const r = await fetch('/api/proxy/active', { cache: 'no-store' })
        if (!r.ok) return
        const d = await r.json()
        if (!cancelled) setActive(d.active_jobs ?? 0)
      } catch {
        /* backend erisilemiyorsa rozet sessizce gizli kalir */
      }
    }
    tick()
    const id = setInterval(tick, 4000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  // Gorunurlugu ayri tut: cikarken de animasyon olsun (aniden yok olmasin)
  useEffect(() => { setVisible(active >= 2) }, [active])

  if (active < 2 && !visible) return null

  return (
    <div
      className="fixed top-4 right-4 z-50 pointer-events-none"
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(-6px)',
        transition: 'opacity 400ms cubic-bezier(0.16,1,0.3,1), transform 400ms cubic-bezier(0.16,1,0.3,1)',
      }}
    >
      <div className="flex items-center gap-2 rounded-full bg-white/90 backdrop-blur px-3 py-1.5 shadow-sm border border-gray-200/80">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-70 animate-ping" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
        </span>
        <span className="text-xs text-gray-600">
          <span className="font-semibold text-gray-900">{active}</span> üretim sürüyor
          <span className="text-gray-400"> · hız paylaşılıyor</span>
        </span>
      </div>
    </div>
  )
}
