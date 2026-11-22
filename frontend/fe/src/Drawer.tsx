// 右から出るサイドバー。1問1答の出題設定で使う。
//
// ・開くと右から滑り込み、中の最初の入力欄（input・select・textarea）に合わせる
// ・背景を押す・Esc・「閉じる」（×）で閉じる
// ・閉じている間も DOM に置いたまま（滑り出る動きを見せるため）。閉じている間は読み上げ・Tab の対象から外す（inert）
// ・見た目は app.css の .fe-drawer まわり

import { useEffect, useId, useRef, type ReactNode } from 'react'

import { Icon } from './Icon'

export function Drawer({ open, onClose, title, children }: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}) {
  const panel = useRef<HTMLElement>(null)
  const titleId = useId()

  useEffect(() => {
    if (!open) return
    // 滑り込みが始まってから合わせる（すぐだと、まだ画面の外にあってスクロールが飛ぶことがある）
    const timer = window.setTimeout(() => {
      panel.current?.querySelector<HTMLElement>('input, select, textarea')?.focus({ preventScroll: true })
    }, 200)
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      window.clearTimeout(timer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  return (
    <div className={`fe-drawer${open ? ' fe-drawer-open' : ''}`} inert={!open}>
      <div className="fe-drawer-backdrop" onClick={onClose} />
      <aside ref={panel} className="fe-drawer-panel" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="fe-drawer-head">
          <h2 id={titleId} className="fe-drawer-title">{title}</h2>
          <button type="button" className="btn btn-link btn-sm fe-drawer-close" aria-label="閉じる" onClick={onClose}>
            <Icon name="times" />
          </button>
        </div>
        {children}
      </aside>
    </div>
  )
}
