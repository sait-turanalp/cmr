'use client'

import { Button } from "@/components/ui/button"
import { CheckCircle } from 'lucide-react'

interface ResultPageProps {
  fileName: string
  downloadUrl: string
  sizeMb?: number
  processingTime?: number
  pages?: number
  onReset: () => void
}

export function ResultPage({ fileName, downloadUrl, sizeMb, processingTime, pages, onReset }: ResultPageProps) {
  const suggestedName = fileName.replace(/\.xlsx$/i, '.pdf')

  return (
    <div className="text-center space-y-4">
      <div className="bg-green-50 rounded-full w-16 h-16 mx-auto flex items-center justify-center">
        <CheckCircle className="w-8 h-8 text-green-500" />
      </div>
      <div>
        <h2 className="text-2xl font-bold text-gray-900">PDF Hazır!</h2>
        <p className="text-gray-500 mt-1 text-sm">
          {pages ? `${pages} sayfa` : 'PDF'}
          {processingTime ? `, ${processingTime < 60 ? `${Math.round(processingTime)} saniyede` : `${Math.round(processingTime / 60)} dakikada`} oluşturuldu` : ' oluşturuldu'}
        </p>
      </div>
      <div className="flex flex-col sm:flex-row justify-center gap-3 pt-4">
        {/* Native browser download: tiklanir tiklanmaz browser'in kendi download
            manager'i devreye girer (hiz, resume, pause hep orda). Biz stream etmeyiz. */}
        <a
          href={downloadUrl}
          download={suggestedName}
          className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-white shadow hover:bg-primary/90 transition-colors sm:w-auto"
        >
          PDF indir
        </a>
        <Button variant="outline" onClick={onReset} className="sm:w-auto">
          Yeni PDF oluştur
        </Button>
      </div>
    </div>
  )
}
