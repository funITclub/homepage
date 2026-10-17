# config/subapps.py
#
# サブアプリ（WG のアプリ・公表した成果物）を、フォルダーを見て自動で組み込む。
#
#   wg/<名前>/     作っている途中。WG一覧へ送り返す
#   works/<名前>/  公表したもの。成果物一覧へ送り返す
#
# WG のアプリはこのリポジトリには入れない（ソースは WG の非公開リポジトリのまま）。
# デプロイのワークフローが、そのときだけ wg/ に取り込んで App Service に載せる。
# このリポジトリを手元で動かすと wg/ は空なので、何も足されないだけで済む。
#
# フォルダー名がそのまま URL になり（wg/protein → /protein/）、URL の名前空間にも
# 使う。アプリの urls.py の app_name も同じ名前にしておくこと。
#
# 1 つの WG が複数のアプリを持つときは、URL を入れ子にできる。取り込みのときに
# アプリの中へ .url という 1 行のファイルを置くと、その中身を URL として使う
# （wg/welfare_tracker/.url に welfare/tracker → /welfare/tracker/）。
# フォルダー名は Django のアプリ名になるので、ほかの WG と重ならない名前にする。

from pathlib import Path

# 置き場所と、通行証が無かったときに送り返す先（config/gate.py）
FOLDERS = {
    'wg': 'home:wg_list',
    'works': 'home:work_list',
}

URL_FILE = '.url'


def _url_of(path):
    """URL に使う道。.url があればその中身、無ければフォルダー名。"""
    marker = path / URL_FILE
    if marker.exists():
        url = marker.read_text(encoding='utf8').strip().strip('/')
        if url:
            return url
    return path.name


def discover(base_dir):
    """[(フォルダー, アプリ名, URL), …] を、置かれている順（名前順）で返す。

    __init__.py と urls.py の両方があるものだけを取る。取り込みが途中で
    壊れたときに、半端なものを読み込まないため。
    """
    found = []
    for folder in FOLDERS:
        root = Path(base_dir) / folder
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir()):
            if not path.is_dir() or path.name.startswith(('_', '.')):
                continue
            if (path / '__init__.py').exists() and (path / 'urls.py').exists():
                found.append((folder, path.name, _url_of(path)))
    return found


def installed(base_dir):
    """INSTALLED_APPS に足すもの。"""
    return [f'{folder}.{name}' for folder, name, _url in discover(base_dir)]


def gate_back(base_dir):
    """config/gate.py の対応表（URL → 送り返す先）。

    入れ子のときは、上の段（/welfare/）で一度通れば下（/welfare/tracker/）も
    開ける。同じ WG のアプリのあいだを行き来できるようにするため。
    """
    return {f'/{url}/': FOLDERS[folder] for folder, _name, url in discover(base_dir)}
