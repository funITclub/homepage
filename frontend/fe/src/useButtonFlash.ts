// ボタンの色の決まり（以前の _buttons.html を React に移したもの）。
//
// ・オン・オフを持つボタン（aria-pressed を付けたもの。聞き流しの「くり返し」「一時停止」など）：
//   オンの間は青（.active）、オフで元の色。押すたびに入れ替わる。入れ替えは各画面が行う
// ・押すたびに1回動くボタン（前へ・次へ・10秒・解答など）：押した瞬間だけ青くなり、すぐ戻る。
//   iPhone の Safari は触っている間の :active を出さないことがあるので、押したときに
//   .fe-flash を一瞬付けて出す
// スマホで押したボタンが「マウスが乗っている」塗りのまま残る件は、app.css の
// @media (hover: none) で消している。

import { useEffect } from 'react'

const FLASH_MS = 180

export function useButtonFlash() {
  useEffect(() => {
    const timers = new WeakMap<Element, number>()
    const onClick = (event: MouseEvent) => {
      const button = (event.target as Element | null)?.closest?.('.btn')
      // オン・オフを持つボタンは、オンの青（.active）で状態を見せるので光らせない
      if (!button || button.hasAttribute('aria-pressed')) return
      button.classList.add('fe-flash')
      window.clearTimeout(timers.get(button))
      timers.set(button, window.setTimeout(() => button.classList.remove('fe-flash'), FLASH_MS))
    }
    document.addEventListener('click', onClick)
    return () => document.removeEventListener('click', onClick)
  }, [])
}
