// 基本情報（fe）の画面の入口。作りは bk_houmu3・countdown の main.tsx と同じ。
//
// Django の入れ物のページ（apps/fe/templates/fe/app.html）にある
// <div id="fe-root"> に React の画面を描く。URL の頭は data-* で受け取る。

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'

import { configureApi } from './api'
import { App } from './App'
import './app.css'

const root = document.getElementById('fe-root')

if (root) {
  const { basePath = '/fe/', apiUrl = '/fe/api/' } = root.dataset
  configureApi(apiUrl, basePath)

  createRoot(root).render(
    <StrictMode>
      {/* basename の下のアドレス（/, /quiz/, /learn/ など）で画面を切りかえる */}
      <BrowserRouter basename={basePath}>
        <App />
      </BrowserRouter>
    </StrictMode>,
  )
}
