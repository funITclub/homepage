// 画面の枠。見出し（アプリ名・メニュー・いまの ID）と、アドレスごとの画面。
//
// ダッシュボードは ID の有無にかかわらず /（ID は URL に出さない）。ID で入る・作るのは /id/。
// 見出しの ID の表示とダッシュボードの中身が ID の有無で変わるので、いま入っている記録（me）を
// 最初に読み、読めてから画面を出す。
// ID で入ったら EnterPage が setMe で入れかえる。
// トーストはどこからでも出せるよう、いちばん外で包む。

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { Link, Navigate, NavLink, Route, Routes, useSearchParams } from 'react-router'

import { api, type Me } from './api'
import { clearCorner } from './corner'
import { Dashboard } from './Dashboard'
import { EnterPage } from './EnterPage'
import { GuidePage } from './GuidePage'
import { HistoryPage } from './HistoryPage'
import { LearnQuizPage } from './LearnQuizPage'
import { LearnReadPage } from './LearnReadPage'
import { LearnResultPage } from './LearnResultPage'
import { LearnStartPage } from './LearnStartPage'
import { QuizPage } from './QuizPage'
import { StatsPage } from './StatsPage'
import { PlanPage } from './PlanPage'
import { LoadError, Loading } from './Status'
import { ToastProvider } from './toast'
import { useButtonFlash } from './useButtonFlash'
import { usePageView } from './usePageView'

type MeState = { me: Me; setMe: (me: Me) => void }

const MeContext = createContext<MeState>({
  me: { entered: false, code: null, is_temporary: true },
  setMe: () => {},
})

export const useMe = () => useContext(MeContext)


export function App() {
  useButtonFlash()
  const [me, setMe] = useState<Me | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setError(null)
    api.me().then(setMe).catch((e: Error) => setError(e.message))
  }, [])

  useEffect(load, [load])

  return (
    <ToastProvider>
      <div className="fe-app">
        <Header me={me} />
        <main className="fe-main fe-body">
          {error && <LoadError message={error} onRetry={load} />}
          {!error && !me && <Loading rows={3} />}
          {me && (
            <MeContext.Provider value={{ me, setMe }}>
              <Routes>
                <Route path="/" element={<IndexRoute />} />
                <Route path="/id/" element={<IdRoute />} />
                <Route path="/about/" element={<GuidePage />} />
                <Route path="/guide/" element={<Navigate to="/about/" replace />} />
                <Route path="/quiz/" element={<QuizPage />} />
                <Route path="/learn/" element={<LearnStartPage />} />
                <Route path="/learn/:id/read/" element={<LearnReadPage />} />
                <Route path="/learn/:id/quiz/" element={<LearnQuizPage />} />
                <Route path="/learn/:id/result/" element={<LearnResultPage />} />
                <Route path="/stats/" element={<StatsPage />} />
                <Route path="/history/" element={<HistoryPage />} />
                <Route path="/planandcheck/" element={<PlanPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </MeContext.Provider>
          )}
        </main>
      </div>
    </ToastProvider>
  )
}

const MENU = [
  { to: '/quiz/', label: '1問1答' },
  { to: '/learn/', label: '学習モード' },
  { to: '/stats/', label: '分野別正答率' },
  { to: '/history/', label: '履歴' },
  { to: '/about/', label: 'このアプリについて' },
]

function Header({ me }: { me: Me | null }) {
  return (
    <header className="fe-header">
      <div className="fe-main fe-header-inner">
        <h1 className="fe-title">
          <Link to="/">基本情報技術者試験 対策</Link>
        </h1>
        {/* いまの ID は題名の行の右に置く（メニューに混ぜると、幅によって行の頭に落ちるため）。
            ID なしのときは「ID で入る」だけ（ダッシュボードのポップアップを「次回から表示しない」にしたあとの入り口） */}
        {me?.code && (
          <span className="fe-id">
            ID: <strong>{me.code}</strong>
            <Link to="/id/?switch" className="btn btn-outline-light btn-sm ms-2">ID を切り替える</Link>
          </span>
        )}
        {me && !me.code && (
          <span className="fe-id">
            <Link to="/id/" className="btn btn-outline-light btn-sm">ID で入る</Link>
          </span>
        )}
        <nav className="fe-nav">
          {/* メニューから移ったら、学習コーナー（corner.tsx）の中分類を忘れて、ふつうの画面にする */}
          <NavLink to="/" end onClick={clearCorner}>ダッシュボード</NavLink>
          {/* menu: true は、メニューから移ったしるし（学習モードの入口は、そのとき中分類をすべて畳んで出す） */}
          {MENU.map((item) => (
            <NavLink key={item.to} to={item.to} state={{ menu: true }} onClick={clearCorner}>{item.label}</NavLink>
          ))}
        </nav>
      </div>
    </header>
  )
}

/** /：ダッシュボード。ページビューは ID の有無で分けて数える（ID ありは以前の「マイページ」の欄） */
function IndexRoute() {
  const { me } = useMe()
  return <DashboardWithView page={me.code ? 'mypage' : 'index'} />
}

/** /id/：ID で入る・作る。ID で入っていれば（?switch でなければ）ダッシュボードへ */
function IdRoute() {
  const { me } = useMe()
  const [params] = useSearchParams()
  if (me.code && !params.has('switch')) return <Navigate to="/" replace />
  return <EnterPage />
}

function DashboardWithView({ page }: { page: string }) {
  usePageView(page)
  return <Dashboard />
}
