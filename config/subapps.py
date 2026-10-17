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

from pathlib import Path

# 置き場所と、通行証が無かったときに送り返す先（config/gate.py）
FOLDERS = {
    'wg': 'home:wg_list',
    'works': 'home:work_list',
}


def discover(base_dir):
    """[(フォルダー, アプリ名), …] を、置かれている順（名前順）で返す。

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
                found.append((folder, path.name))
    return found


def installed(base_dir):
    """INSTALLED_APPS に足すもの。"""
    return [f'{folder}.{name}' for folder, name in discover(base_dir)]


def gate_back(base_dir):
    """config/gate.py の対応表（URL → 送り返す先）。"""
    return {f'/{name}/': FOLDERS[folder] for folder, name in discover(base_dir)}
