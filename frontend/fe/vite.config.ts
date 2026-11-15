// 基本情報（fe）の画面（React）のビルド設定。作りは bk_houmu3・countdown と同じ。
//
// ビルドしたものは Django の static に出し、WhiteNoise がそのまま配る。
//   works/fe/static/fe/app/app.js
//   works/fe/static/fe/app/app.css
// 入れ物のテンプレート（fe/app.html）が、この2つを決まった名前で読む。
//
// ファイル名は決まった名前にし、ここではハッシュを付けない。テンプレートが {% static %} で
// 名前を指して読むため。ハッシュは本番の collectstatic（config/settings.py の STORAGES）が付ける。
// ファイルを1つにまとめるのも同じ理由（分けると、JS の中から読むファイル名は
// collectstatic に書きかえてもらえない）。

import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const outDir = fileURLToPath(new URL('../../works/fe/static/fe/app', import.meta.url))

export default defineConfig({
  plugins: [react()],
  build: {
    outDir,
    emptyOutDir: true,
    // 古いブラウザ向けの書きかえはしない（いまのブラウザが読める形のまま出す）
    target: 'es2022',
    rollupOptions: {
      input: fileURLToPath(new URL('./src/main.tsx', import.meta.url)),
      output: {
        entryFileNames: 'app.js',
        assetFileNames: 'app[extname]',
        codeSplitting: false,
      },
    },
  },
})
