// どのアドレスでも EventsPage が描く。一覧・新規登録・編集の切りかえは EventsPage の中で
// アドレスを見て行う（パネルを開け閉めしても一覧を描き直さないため）。
// トーストはどこからでも出せるよう、いちばん外で包む。

import { useEffect, useRef } from 'react'
import { Route, Routes } from 'react-router'

import { EventsPage } from './EventsPage'
import { ToastProvider, useToast } from './toast'

export function App({ notices }: { notices: string[] }) {
  return (
    <ToastProvider>
      <Notices notices={notices} />
      <Routes>
        <Route path="*" element={<EventsPage />} />
      </Routes>
    </ToastProvider>
  )
}

/** Django から渡された知らせを、開いたときに一度だけトーストで出す */
function Notices({ notices }: { notices: string[] }) {
  const toast = useToast()
  const shown = useRef(false)
  useEffect(() => {
    if (shown.current) return
    shown.current = true
    for (const text of notices) toast.show(text, { duration: 8000 })
  }, [notices, toast])
  return null
}
