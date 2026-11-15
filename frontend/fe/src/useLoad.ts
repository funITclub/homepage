// 画面を開いたときに API から1回読む。読み込み中・失敗・やり直しをまとめて扱う。

import { useCallback, useEffect, useState } from 'react'

export function useLoad<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)

  // deps が変わったら読み直す（履歴の絞り込みなど）
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const reload = useCallback(() => {
    setError(null)
    return load()
      .then((value) => setData(value))
      .catch((e: Error) => setError(e.message))
  }, deps)

  useEffect(() => {
    void reload()
  }, [reload])

  return { data, setData, error, reload }
}
