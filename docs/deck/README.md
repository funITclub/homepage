# 資料（WG 立ち上げガイド）の直し方

資料は `static/guide/*.pptx` にあり、公開サイトの `/guide/` から配っている。

```
00_概要.pptx                    7枚   全員
01_リポジトリの作り方と運用.pptx  13枚   運営
02_パソコンの準備.pptx           14枚   メンバー・初回
03_開発の進め方.pptx             11枚   メンバー
04_アプリケーション構成.pptx      14枚   メンバー
```

## 直し方

**元の生成スクリプト（pptxgenjs）は残っていない。** 一時フォルダーに置いたまま
OS の掃除で消えた。いまある pptx が原本なので、**出来上がった pptx の文字だけを
差し替える**。図形の位置・色・書体は触らない。

1. **どこを直すか調べる**（図形の番号と、いまの文字）

   ```bash
   python3 docs/deck/dump_text.py static/guide/00_概要.pptx 3
   ```

2. **差し替えの指示を書く**（`docs/deck/changes/` に JSON を置く）

   ```json
   {
     "static/guide/00_概要.pptx": {
       "3": [
         [6, "いまの文字", "新しい文字"],
         [7, "箇条書きの\n行は", ["1行目", "2行目"]]
       ]
     }
   }
   ```

   左から「図形の番号」「いまの文字（照合用）」「新しい文字」。箇条書きは行の配列で渡す。

3. **差し替える**

   ```bash
   python3 docs/deck/edit_text.py docs/deck/changes/<名前>.json
   ```

   「いまの文字」が一致しないと、何も書かずに止まる。

4. **見た目を確かめる**（Keynote で PDF に書き出して、全ページ目で見る）

   ```bash
   bash docs/deck/topdf.sh static/guide/00_概要.pptx /tmp/00.pdf
   ```

   **文字を長くすると隣とぶつかる。** 行が増えていないか、はみ出していないかを必ず見る。
   元より長い文言にするときは、短い言い回しを探すほうが早い。

5. 直したらコミットして push する（`/guide/` から配られる。デプロイで新しい版になる）

## 枚数を増やす・アイコンを差し替える

似た作りのスライドを複製して、中身を入れ替える。

```bash
python3 docs/deck/duplicate_slide.py static/guide/01_リポジトリの作り方と運用.pptx 9 11
```

9 枚目を複製して 11 枚目に入れる。そのあと `dump_text.py` で図形の番号を調べ、
`edit_text.py` で文字を入れ替える。

アイコン（画像）は複製元のものが付いてくる。意味が合わないときは、同じ資料の
別のスライドから画像を持ってきて、同じ位置・大きさで置き直す。

```python
from pptx import Presentation
import io

p = Presentation('static/guide/01_リポジトリの作り方と運用.pptx')
blob = list(p.slides[7].shapes)[22].image.blob        # 8枚目の [22] の画像を使う
slide = p.slides[10]
old = list(slide.shapes)[4]                           # 11枚目の [4] を置き換える
geom = (old.left, old.top, old.width, old.height)
old._element.getparent().remove(old._element)
slide.shapes.add_picture(io.BytesIO(blob), *geom)
p.save('static/guide/01_リポジトリの作り方と運用.pptx')
```

色は**円の中で映える向き**で選ぶ（淡い円には濃い色のアイコン、濃い円には淡い色）。

## 必要なもの

```bash
pip install python-pptx
```

PDF の書き出しは Keynote を使う（macOS）。LibreOffice は入れていない。

## 資料の決まりごと

- 配色はネイビー `#001E3C` ＋ アクセント `#5BB8FF`、白いカードの上の文字は `#1A4A70`
- 書体は Consolas（ラベル・数値・コード）＋ Meiryo（日本語）
- 1枚＝1つの話。手順は番号付きのカードで、クリックする場所まで書く（対象はアプリ初心者）
- 表紙の右には 5 本の資料の一覧を出し、その資料を強調する
- 資料と `docs/development.md`・`README.md` が食い違ったら、**文書のほうを正とする**

## 作り直したくなったら

スライドの構成そのものを変えたい（枚数を増やす・図を描き替える）ときは、
pptxgenjs で生成スクリプトから作り直すことになる。そのときは、このフォルダーに
スクリプトを置いて、`static/guide/` へ出力する形にする（一時フォルダーに置かない）。
