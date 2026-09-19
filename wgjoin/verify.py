# wgjoin/verify.py
#
# 確認のメールのリンクと、送りすぎの歯止め。どちらもアドレスを保存しない。
#
# リンク … 「どの WG の手続きか」と使い捨ての番号だけを署名して入れる（アドレスは入れない）。
#          リンクが届いた＝そのアドレスの持ち主、なので、開いた人をメンバーとして扱う。
#          期限は WG_JOIN_LINK_MAX_AGE。使い終わった番号はキャッシュに覚えて二度使わせない。
# 歯止め … 同じ IP・同じアドレスからの送信を数える。アドレスはそのまま持たず、
#          SECRET_KEY で鍵を掛けたハッシュにして数える。

import hashlib
import hmac
import secrets
import time

from django.conf import settings
from django.core import signing
from django.core.cache import cache

SALT = 'wgjoin.verify'


class LinkInvalid(Exception):
    """リンクが壊れている・期限切れ・使用済み。"""


def make_link_token(wg_pk):
    return signing.dumps({'wg': wg_pk, 'n': secrets.token_urlsafe(12)}, salt=SALT)


def read_link_token(token):
    """(wg の pk, 使い捨ての番号)。使えないリンクなら LinkInvalid。"""
    try:
        data = signing.loads(token, salt=SALT, max_age=settings.WG_JOIN_LINK_MAX_AGE)
    except signing.BadSignature as e:  # SignatureExpired も含む
        raise LinkInvalid from e
    if is_used(data['n']):
        raise LinkInvalid
    return data['wg'], data['n']


def _used_key(nonce):
    return f'wgjoin-used:{nonce}'


def is_used(nonce):
    return bool(cache.get(_used_key(nonce)))


def mark_used(nonce):
    # リンクの期限が切れるまで覚えておけば足りる
    cache.set(_used_key(nonce), 1, settings.WG_JOIN_LINK_MAX_AGE)


def _count(key, limit, seconds):
    """窓の中の件数を1つ増やし、上限を超えたら False。キャッシュが使えなければ通す。"""
    now = time.time()
    try:
        entry = cache.get(key)
        if entry and now - entry[1] < seconds:
            count, started = entry[0] + 1, entry[1]
        else:
            count, started = 1, now
        cache.set(key, (count, started), seconds)
    except Exception:
        return True
    return count <= limit


def address_key(email):
    return hmac.new(settings.SECRET_KEY.encode(), email.lower().encode(), hashlib.sha256).hexdigest()


def allow_send(ip, email):
    """このリクエストで確認のメールを送ってよいか（settings.WG_JOIN_SEND_LIMITS）。"""
    ip_limit, address_limit = settings.WG_JOIN_SEND_LIMITS
    ok = True
    if ip:
        ok = _count(f'wgjoin-send-ip:{ip}', *ip_limit) and ok
    ok = _count(f'wgjoin-send-addr:{address_key(email)}', *address_limit) and ok
    return ok
