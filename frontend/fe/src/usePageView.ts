// 画面を出したことを数える（apps/fe/pageviews.py）。画面の切りかえは React の中で行い、
// Django を通らないので、各画面が出たときにここから知らせる。数え損ねても画面には関係ないので、
// 失敗は黙って捨てる。

import { useEffect } from 'react'

import { api } from './api'

export function usePageView(page: string) {
  useEffect(() => {
    api.pageview(page).catch(() => {})
  }, [page])
}
