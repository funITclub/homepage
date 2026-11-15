// countdown の画面の入口。
//
// Django の入れ物のページ（works/countdown/templates/countdown/app.html）にある
// <div id="countdown-root"> に React の画面を描く。URL の頭と置き場（ID）のことは data-* で受け取る。

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'

import { configure } from './api'
import { App } from './App'
import './app.css'

const root = document.getElementById('countdown-root')

/** Django の知らせ（ID を作りました など）。入れ物のページが json_script で渡す */
function readNotices(): string[] {
  try {
    const data: unknown = JSON.parse(document.getElementById('countdown-notices')?.textContent ?? '[]')
    return Array.isArray(data) ? data.map(String) : []
  } catch {
    return []
  }
}

if (root) {
  const { basePath = '/countdown/events/', apiUrl = '', enterUrl = '', board = '', mailUrl = '', notifyTo = '' } = root.dataset
  configure({ apiUrl, enterUrl, board: board || null, mailUrl, notifyTo })

  createRoot(root).render(
    <StrictMode>
      {/* basename の下のアドレス（/, /create/, /12/update/ など）で画面を切りかえる */}
      <BrowserRouter basename={basePath}>
        <App notices={readNotices()} />
      </BrowserRouter>
    </StrictMode>,
  )
}
