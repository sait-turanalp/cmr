import type { Metadata } from 'next'
import { Sidebar } from '../components/sidebar'
import { LoadBadge } from '../components/loadBadge'

export const metadata: Metadata = {
  title: 'UCS Group CMR System',
  description: 'UCS Group CMR System',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="min-h-screen">
      <Sidebar />
      <LoadBadge />
      <main className="p-8 pt-16 overflow-y-auto">
        {children}
      </main>
    </div>
  )
}
