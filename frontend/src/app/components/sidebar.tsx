'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { signOut } from 'next-auth/react'
import { FileSpreadsheet, LogOut, Lock, Menu, X } from 'lucide-react'

export function Sidebar() {
  const pathname = usePathname()
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      {/* Hamburger butonu */}
      <button
        onClick={() => setIsOpen(true)}
        className="fixed top-4 left-4 z-30 p-2 rounded-md bg-white shadow-sm border border-gray-100 hover:bg-gray-50 transition-colors"
        aria-label="Menüyü aç"
      >
        <Menu size={20} className="text-gray-700" />
      </button>

      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/20 backdrop-blur-[1px]"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Drawer */}
      <div className={`fixed top-0 left-0 z-40 h-full w-64 bg-white shadow-xl flex flex-col transform transition-transform duration-250 ease-in-out ${isOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <h1 className="text-xl font-bold text-gray-900">UCS Group</h1>
          <button
            onClick={() => setIsOpen(false)}
            className="p-1 rounded-md hover:bg-gray-100 transition-colors"
            aria-label="Menüyü kapat"
          >
            <X size={18} className="text-gray-500" />
          </button>
        </div>

        <nav className="flex-1 py-4">
          <Link
            href="/dashboard"
            onClick={() => setIsOpen(false)}
            className={`flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors ${pathname === '/dashboard' ? 'bg-gray-100 font-medium' : ''}`}
          >
            <FileSpreadsheet size={18} />
            PDF Oluştur
          </Link>
          <Link
            href="/dashboard/security"
            onClick={() => setIsOpen(false)}
            className={`flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors ${pathname === '/dashboard/security' ? 'bg-gray-100 font-medium' : ''}`}
          >
            <Lock size={18} />
            Güvenlik
          </Link>
        </nav>

        <button
          className="flex items-center gap-3 px-4 py-3 text-sm text-gray-600 hover:bg-gray-50 transition-colors border-t border-gray-100 w-full"
          onClick={() => signOut({ callbackUrl: '/' })}
        >
          <LogOut size={18} />
          Çıkış Yap
        </button>
      </div>
    </>
  )
}
