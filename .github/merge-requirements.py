"""WG の requirements.txt を、本番の分に足す（.github/workflows/deploy.yml）。

同じパッケージを両方が指定していたら、本番（homepage）の版を使う。WG ごとに
違う版を入れることはできない（1つのアプリとして動かすため）。食い違いは警告に出し、
デプロイは止めない。止めると、homepage の更新に WG が追従するまで公開できなくなる。
"""

import re
import sys


def name(line):
    """'Django==5.2.3' → 'django'。版の指定や環境マーカーは落とす。"""
    return re.split(r'[=<>!~\[; ]', line.strip(), maxsplit=1)[0].strip().lower()


def main(base_path, extra_path):
    base = open(base_path, encoding='utf8').read().splitlines()
    have = {name(line): line.strip() for line in base if line.strip() and not line.startswith('#')}

    added = []
    for line in open(extra_path, encoding='utf8').read().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key = name(line)
        if key in have:
            if have[key] != line:
                print(f'::warning::{extra_path}: {line} は本番の {have[key]} を使います')
            continue
        have[key] = line
        added.append(line)

    if added:
        with open(base_path, 'a', encoding='utf8') as f:
            f.write('\n# WG のアプリが必要とするもの（取り込み時に追加）\n')
            f.write('\n'.join(added) + '\n')
        print('足したもの:', ', '.join(added))
    else:
        print('足すものはありません')


if __name__ == '__main__':
    main(*sys.argv[1:3])
