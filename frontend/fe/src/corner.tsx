// 学習コーナー。plan&check（/planandcheck/）と、その計画の中分類から開いた 1問1答・学習モード。
//
// 計画の行の「解説」（学習モード）「1問1答」を押すと、その中分類をここに覚える（ブラウザのセッション）。
// 覚えているあいだは、
//   ・1問1答は出題設定を出さない（出題設定はボタンを押したときにその中分類にしてある）
//   ・学習モードは入口（学習対象・読む時間を選ぶ画面）を通さず、その中分類のおまかせで始める
//   ・学習モードの読む段階は時間を数えない（残り時間を出さず、自動で進まない）。進むボタンは「問題へ進む」
//   ・ここで解いた分だけを学習計画（plan&check）の結果に数える（ヘッダーから開いた分・問題メールは数えない）
//   ・各画面のいちばん上に plan&check へ戻るボタンを出す（plan&check 自体には戻るボタンを置かない）
// 学習モードは 読む → 解く → 結果 → もう1ラウンド と画面が移るので、URL ではなくここに持つ。
// ヘッダーのメニュー・ダッシュボード・学習モードの入口へ移ったら忘れる（clearCorner）。
//
// セッションの記憶が使えないとき（プライベートブラウズの制限など）は、覚えずにふつうの画面になる。

import { Link } from 'react-router'

import { Icon } from './Icon'

export type Corner = { subject: string; code: number; label: string }

const KEY = 'fe_corner'

export function getCorner(): Corner | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as Corner) : null
  } catch {
    return null
  }
}

export function setCorner(corner: Corner) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(corner))
  } catch {
    // 覚えられなくても、ふつうの画面で続けられる
  }
}

export function clearCorner() {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // 同上
  }
}

/** 学習コーナーの画面のいちばん上の「戻る」。中分類も添える */
export function CornerBack({ to, corner }: { to: string; corner?: Corner | null }) {
  return (
    <div className="fe-corner-back">
      <Link to={to} className="btn btn-outline-secondary btn-sm">
        <Icon name="arrow-left" className="me-1" />戻る
      </Link>
      {corner && <strong className="ms-2">{corner.label}</strong>}
    </div>
  )
}

/** 学習コーナーにいるときだけ、plan&check へ戻るボタンを出す（学習モードの各画面のいちばん上） */
export function CornerBackIfAny() {
  const corner = getCorner()
  return corner ? <CornerBack to="/planandcheck/" corner={corner} /> : null
}
