#!/usr/bin/env python3
"""資料（pptx）の文字を差し替える。書式・配置はそのまま残る。

資料を作った生成スクリプト（pptxgenjs）は手元に残っていないので、直すときは
出来上がった pptx の文字だけを入れ替える。図形の位置や色は触らない。

使い方:

    python3 docs/deck/edit_text.py docs/deck/changes/<名前>.json

JSON の形（ファイルごと・スライド番号ごとに、[図形の番号, いまの文字, 新しい文字]）:

    {
      "static/guide/00_概要.pptx": {
        "3": [
          [6, "いまの文字", "新しい文字"],
          [7, "箇条書きの\\n行は", ["1行目", "2行目"]]
        ]
      }
    }

「いまの文字」が一致しないときは、何も書かずに止まる（別のところを壊さないため）。
図形の番号と現在の文字は dump_text.py で調べる。

直したあとは、必ず見た目を確かめること（文字が長いと隣とぶつかる）:

    bash docs/deck/topdf.sh static/guide/00_概要.pptx /tmp/00.pdf

必要なもの: pip install python-pptx
"""

import json
import sys

from pptx import Presentation


def set_text(shape, new):
    """図形の文字を差し替える。書式は最初のランのものを引き継ぐ。"""
    lines = new if isinstance(new, list) else [new]
    paragraphs = shape.text_frame.paragraphs
    if len(paragraphs) < len(lines):
        raise SystemExit(f'行が多すぎます（{len(paragraphs)} 行の図形に {len(lines)} 行）')
    for paragraph, line in zip(paragraphs, lines):
        if not paragraph.runs:
            raise SystemExit(f'差し替えられない行があります: {paragraph.text!r}')
        paragraph.runs[0].text = line
        for extra in paragraph.runs[1:]:
            extra.text = ''
    for paragraph in paragraphs[len(lines):]:      # 余った行は空にする
        for run in paragraph.runs:
            run.text = ''


def apply(changes):
    # 先にすべて検査してから書く。途中で止まって半端な資料にしないため。
    loaded = {}
    for path, slides in changes.items():
        pres = Presentation(path)
        for slide_no, items in slides.items():
            shapes = list(pres.slides[int(slide_no) - 1].shapes)
            for index, old, _new in items:
                found = shapes[index].text_frame.text
                if found != old:
                    raise SystemExit(f'{path} スライド{slide_no} [{index}] が違います\n'
                                     f'  いまの文字: {found!r}\n  指定した文字: {old!r}')
        loaded[path] = pres

    for path, slides in changes.items():
        pres = loaded[path]
        for slide_no, items in slides.items():
            shapes = list(pres.slides[int(slide_no) - 1].shapes)
            for index, _old, new in items:
                set_text(shapes[index], new)
        pres.save(path)
        print(f'{path}: {sum(len(v) for v in slides.values())} か所')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    with open(sys.argv[1], encoding='utf8') as f:
        apply(json.load(f))
