'use client'

import { useState, useCallback, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { Button } from '@/components/ui/button'
import { useToast } from '@/hooks/use-toast'
import { Loader2, Upload, FileSpreadsheet, X } from 'lucide-react'
import { ResultPage } from './resultPage'
import ExcelJS from 'exceljs'
import { Progress } from '@/components/ui/progress'

const API_URL = process.env.NEXT_PUBLIC_API_URL

export function ConvertForm() {
  const [file, setFile] = useState<File | null>(null)
  const [isConverting, setIsConverting] = useState(false)
  const [result, setResult] = useState<{
    downloadUrl: string
    fileName: string
    sizeMb?: number
    processingTime?: number
    pages?: number
  } | null>(null)
  const [progress, setProgress] = useState(0)
  const [displayedProgress, setDisplayedProgress] = useState(0)  // Yumuşak animasyon için
  const [elapsedSec, setElapsedSec] = useState(0)
  const [currency, setCurrency] = useState<string>('$')
  // SSR'da her zaman false; localStorage mount sonrası okunur (hydration mismatch olmaz).
  const [turboMode, setTurboMode] = useState(false)
  useEffect(() => {
    setTurboMode(localStorage.getItem('cmr-turbo-mode') === 'true')
  }, [])
  const { toast } = useToast()

  const toggleTurbo = () => {
    setTurboMode(prev => {
      const next = !prev
      localStorage.setItem('cmr-turbo-mode', String(next))
      return next
    })
  }

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const selectedFile = acceptedFiles[0]
    if (selectedFile && selectedFile.name.endsWith('.xlsx')) {
      setFile(selectedFile)
    } else {
      toast({
        title: 'Geçersiz Dosya Formatı',
        description: 'Lütfen XLSX uzantılı bir dosya yükleyiniz.',
        variant: 'destructive',
      })
    }
  }, [toast])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx']
    },
    multiple: false
  })

  const fetchProgress = async () => {
    try {
      const response = await fetch('/api/proxy/progress', {
        method: 'GET',
      })
      if (!response.ok) return null
      const data = await response.json()
      if (!data.total || data.total === 0) return null
      return Math.min(99, Math.round((data.current / data.total) * 100))
    } catch {
      return null
    }
  }

  const handleConvert = async () => {
    if (!file) return

    setIsConverting(true)
    setProgress(0)
    setDisplayedProgress(0)
    setElapsedSec(0)

    try {
      // Eski "isfree" gate kaldirildi. Backend multi-worker + async download
      // mimarisinde paralel isler kabul ediliyor; on kontrol gereksiz ve
      // bazi durumlarda 429 donup "Failed to fetch" hatasi yaratiyordu.
      const workbook = new ExcelJS.Workbook()
      const fileData = await file.arrayBuffer()
      await workbook.xlsx.load(fileData)

      const worksheet = workbook.getWorksheet(1)

      if (!worksheet) {
        throw new Error('Excel dosyasında geçerli bir tablo bulunamadı.')
      }

      const jsonData: Record<string, any>[] = []
      const headerRow = worksheet.getRow(1)

      if (!headerRow) {
        throw new Error('Tabloda başlık eksik veya yok.')
      }

      worksheet.eachRow((row, rowIndex) => {
        if (rowIndex === 1) return
        const rowData: Record<string, any> = {}
        row.eachCell((cell, colIndex) => {
          const headerCell = headerRow.getCell(colIndex)
          const header = headerCell.value?.toString() || `Column${colIndex}`

          // Akıllı formatlama: Sadece sayıları yuvarla, stringleri olduğu gibi bırak
          let value = cell.value
          if (typeof value === 'number') {
            // Ondalıklı sayıları 2 haneye yuvarla
            value = Number(value.toFixed(2))
          }
          rowData[header] = value
        })
        jsonData.push(rowData)
      })

      const response = await fetch('/api/proxy/process-pdf', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ data: jsonData, currency: currency, mode: turboMode ? 'turbo' : 'normal' }),
      })

      if (!response.ok) {
        // Backend size limit (413) icin net mesaj goster; digerleri generic.
        let msg = 'PDF oluşturulurken bir hata oluştu.'
        try {
          const errBody = await response.json()
          if (response.status === 413 && errBody?.max_rows) {
            msg = `Çok fazla satır (${errBody.received}). Tek seferde en fazla ${errBody.max_rows} satır işlenebilir. Dosyayı bölerek deneyin.`
          } else if (errBody?.error) {
            msg = errBody.error
          }
        } catch { /* response body JSON değilse generic */ }
        throw new Error(msg)
      }

      // Backend artik bytes degil JSON doner:
      //   { filename, download_url, size_mb, processing_time_sec, pages, job_id }
      // download_url'i proxy endpoint'i uzerinden kullaniriz; kullanici "indir"e
      // bastiginda browser kendi download manager'i ile 24MB'i ceker — biz
      // aradaki Blob/arrayBuffer adimina girmiyoruz.
      const meta = await response.json()
      if (!meta.filename) throw new Error('PDF olusturuldu ama dosya adi eksik.')

      setProgress(100)
      // Kullanici dostu dosya adi: xlsx adindan turet, proxy'ye ?name= ile
      // ilet — browser bu adla indirir (backend filename token'li kalir).
      const friendlyName = file.name.replace(/\.xlsx$/i, '.pdf')
      setResult({
        downloadUrl: `/api/proxy/download/${encodeURIComponent(meta.filename)}?name=${encodeURIComponent(friendlyName)}`,
        fileName: file.name,
        sizeMb: meta.size_mb,
        processingTime: meta.processing_time_sec,
        pages: meta.pages,
      })
      toast({
        title: 'İşlem Tamamlandı',
        description: 'PDF başarıyla oluşturuldu.',
      })

    } catch (error) {
      console.error('Conversion failed:', error)
      toast({
        title: 'Hata',
        description: error instanceof Error ? error.message : 'PDF oluşturulurken bir hata oluştu. Tekrar deneyin.',
        variant: 'destructive',
      })
    } finally {
      setIsConverting(false)
    }
  }

  const handleReset = () => {
    setFile(null)
    setResult(null)
    setProgress(0)
    setDisplayedProgress(0)
    setElapsedSec(0)
  }

  // Backend'den progress — hizli polling (500ms), ilk poll anında.
  // Geri dusmez; backend henuz is baslatmadiysa null doner, 0'da kalir.
  useEffect(() => {
    if (!isConverting) return
    let cancelled = false
    let maxSeen = 0
    let timeoutId: ReturnType<typeof setTimeout> | null = null

    const tick = async () => {
      if (cancelled) return
      const p = await fetchProgress()
      if (!cancelled && p !== null && p > maxSeen) {
        maxSeen = p
        setProgress(p)
      }
      if (!cancelled) timeoutId = setTimeout(tick, 500)
    }
    tick()

    return () => {
      cancelled = true
      if (timeoutId) clearTimeout(timeoutId)
    }
  }, [isConverting])

  // Elapsed timer: her saniye guncel tutar (kullanici "hala calisiyor" anlasın).
  useEffect(() => {
    if (!isConverting) return
    const start = Date.now()
    const id = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - start) / 1000))
    }, 1000)
    return () => clearInterval(id)
  }, [isConverting])

  // Smooth interpolation: displayedProgress ~60fps ile progress'e yaklasır.
  // Tick'ler arası donuk his biter; bar "nefes alir" gibi akar.
  // Ayrıca backend ilk veriyi gonderene kadar 0 -> 3'e yavas yavas kendi kendine
  // ilerler (kullanici "takıldı mı" diye düşünmesin).
  useEffect(() => {
    if (!isConverting) return
    let rafId: number
    let lastTime = performance.now()
    const animate = (now: number) => {
      const dt = (now - lastTime) / 1000
      lastTime = now
      setDisplayedProgress((prev) => {
        const target = progress > 0 ? progress : Math.min(3, prev + dt * 1.5)
        const diff = target - prev
        if (Math.abs(diff) < 0.05) return target
        // Ease: saniyede mesafenin %250'si kadar ilerle (yumusak ama hizli).
        return prev + diff * Math.min(1, dt * 2.5)
      })
      rafId = requestAnimationFrame(animate)
    }
    rafId = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(rafId)
  }, [isConverting, progress])

  if (result) {
    return (
      <div className="min-h-[75vh] flex items-center justify-center">
        <ResultPage
          fileName={result.fileName}
          downloadUrl={result.downloadUrl}
          sizeMb={result.sizeMb}
          processingTime={result.processingTime}
          pages={result.pages}
          turboMode={turboMode}
          onReset={handleReset}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold mb-2">PDF Oluştur</h1>
        <p className="text-gray-600">Başlamak için bir .xlsx dosyası sürükleyin veya seçin.</p>
      </div>
      <div className="bg-white p-6 rounded-lg shadow-md space-y-4">
      {/* Turbo toggle — sağ üst */}
      <div className="flex justify-end -mt-1">
        <div className="relative group flex items-center gap-2">
          <span className={`flex items-center gap-1 text-xs font-semibold px-1.5 py-0.5 rounded border select-none transition-colors duration-200 ${turboMode ? 'border-orange-300 bg-orange-50' : 'border-gray-200 bg-gray-50'}`}>
            <span style={turboMode ? {
              background: 'linear-gradient(90deg, #FF2D00 0%, #FF6B00 60%, #FF9500 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              color: 'transparent',
              WebkitTextStrokeWidth: 0,
              textShadow: 'none',
            } : { color: '#9CA3AF' }}>Turbo</span>
            {/* flame — right side of badge */}
            <span className="relative w-4 h-4 flex-shrink-0">
              <svg className={`absolute inset-0 transition-opacity duration-300 ${turboMode ? 'opacity-0' : 'opacity-100'}`} width="16" height="16" viewBox="5 1 14 21" fill="none">
                <path d="M12 2C12 2 6 8 6 14a6 6 0 0 0 12 0c0-3-1.5-5.5-3-7.5 0 0 0 3-2 4 0-3-1-5.5-1-6.5Z" fill="#D1D5DB" />
              </svg>
              <svg className={`absolute inset-0 transition-opacity duration-300 ${turboMode ? 'opacity-100' : 'opacity-0'}`} width="16" height="16" viewBox="5 1 14 21" fill="none">
                <defs>
                  <linearGradient id="fireGradBadge" x1="12" y1="22" x2="12" y2="2" gradientUnits="userSpaceOnUse">
                    <stop offset="0%" stopColor="#FF2D00" />
                    <stop offset="45%" stopColor="#FF8C00" />
                    <stop offset="100%" stopColor="#FFE234" />
                  </linearGradient>
                </defs>
                <path d="M12 2C12 2 6 8 6 14a6 6 0 0 0 12 0c0-3-1.5-5.5-3-7.5 0 0 0 3-2 4 0-3-1-5.5-1-6.5Z" fill="url(#fireGradBadge)" />
                <path d="M12 14c0 1.5-.8 2.5-2 3 .3-1 .3-2-.5-3 .8.2 1.8-1 2-3 .5 1 .5 2 .5 3Z" fill="#FFE234" opacity="0.9"/>
              </svg>
            </span>
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={turboMode}
            onClick={toggleTurbo}
            className="relative inline-flex h-5 w-9 cursor-pointer rounded-full focus:outline-none bg-gray-200"
          >
            {/* fire gradient overlay — crossfade */}
            <span
              className="absolute inset-0 rounded-full transition-opacity duration-300"
              style={{ background: 'linear-gradient(90deg, #FF2D00 0%, #FF8C00 55%, #FFE234 100%)', opacity: turboMode ? 1 : 0 }}
            />
            <span className={`relative z-10 inline-block h-4 w-4 rounded-full bg-white shadow-sm transform transition-transform duration-200 mt-0.5 ${turboMode ? 'translate-x-[18px]' : 'translate-x-0.5'}`} />
          </button>
          <div className="absolute bottom-full right-0 mb-2 w-56 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 leading-relaxed">
            Beta (deneysel) özellik. Hızı 5 katına kadar artırabilir. Sonuçlar dosya boyutuna göre değişir.
            <div className="absolute top-full right-4 border-4 border-transparent border-t-gray-900" />
          </div>
        </div>
      </div>
      <div
        {...getRootProps()}
        className={`p-8 border-2 border-dashed rounded-lg text-center cursor-pointer transition-colors ${isDragActive ? 'border-primary bg-primary/10' : 'border-gray-300 hover:border-primary'
          }`}
      >
        <input {...getInputProps()} />
        {file ? (
          <div className="flex items-center justify-center gap-2">
            <FileSpreadsheet className="h-8 w-8 text-primary" />
            <span className="text-sm text-gray-600">{file.name}</span>
            <Button
              variant="ghost"
              size="icon"
              className="ml-2"
              onClick={(e) => {
                e.stopPropagation()
                setFile(null)
              }}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        ) : (
          <div>
            <Upload className="h-12 w-12 mx-auto text-gray-400 mb-2" />
            <p className="text-sm text-gray-600">
              Bir XLSX dosyası sürükleyin veya seçin
            </p>
          </div>
        )}
      </div>
      {isConverting && (
        <div className="space-y-2">
          <Progress
            value={displayedProgress}
            className="w-full h-4"
          />
          <div className="flex items-center justify-between text-sm text-gray-700 tabular-nums">
            <span className="font-semibold">
              {progress === 0 ? 'Hazırlanıyor…' : `${Math.round(displayedProgress)}% Tamamlandı`}
            </span>
            <span className="text-gray-500">
              {Math.floor(elapsedSec / 60)}:{String(elapsedSec % 60).padStart(2, '0')}
            </span>
          </div>
        </div>
      )}

      {/* Currency Selection */}
      <div className="space-y-2">
        <div className="flex items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => setCurrency('$')}
            className={`px-6 py-2.5 rounded-lg font-medium text-sm transition-all duration-200 ${currency === '$'
              ? 'bg-primary text-white shadow-md'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
          >
            $ USD
          </button>
          <button
            type="button"
            onClick={() => setCurrency('€')}
            className={`px-6 py-2.5 rounded-lg font-medium text-sm transition-all duration-200 ${currency === '€'
              ? 'bg-primary text-white shadow-md'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
          >
            € EUR
          </button>
          <button
            type="button"
            onClick={() => setCurrency('₺')}
            className={`px-6 py-2.5 rounded-lg font-medium text-sm transition-all duration-200 ${currency === '₺'
              ? 'bg-primary text-white shadow-md'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
          >
            ₺ TRY
          </button>
        </div>
      </div>

      <Button
        onClick={handleConvert}
        disabled={!file || isConverting}
        className="w-full"
      >
        {isConverting ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Oluşturuluyor...
          </>
        ) : (
          'PDF Oluştur'
        )}
      </Button>
      </div>

      <div className="mt-8">
        <h2 className="text-xl font-semibold mb-2">Yönergeler:</h2>
        <ol className="list-decimal list-inside space-y-2 text-gray-600">
          <li>Dosyanın XLSX formatında olduğundan emin olun.</li>
          <li>Dosyanın gerekli bütün sütunları içerdiğiden emin olun.</li>
          <li>Dosyayı sürükleyin veya seçin.</li>
          <li>Oluşturulan dosyayı indirin.</li>
        </ol>
      </div>
    </div>
  )
}