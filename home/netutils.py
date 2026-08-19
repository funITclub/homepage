# home/netutils.py
#
# アクセス元の IP を求める。views と middleware の両方から使う。

def client_ip(request):
    """アクセス元の IP。Azure は X-Forwarded-For に「IP:ポート」で入れてくる。

    **右端（最後）の値を使う。** X-Forwarded-For は誰でも付けられるヘッダで、
    左端はクライアントが自由に詐称できる。信用できるのは自分たちの手前にある
    Azure の front end が付けた値＝右端だけ。左端を信じると、攻撃者が他人の IP を
    名乗って**無関係な人を遮断させる**ことができてしまう。

    App Service に直接（front end を通さずに）到達できる経路があれば、この前提は
    崩れる。遮断は補助的な仕組みとして扱うこと。
    """
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        last = forwarded.split(',')[-1].strip()
        # 「IP:ポート」形式のときだけポートを落とす（IPv6 は : を多く含む）
        return last.rsplit(':', 1)[0] if last.count(':') == 1 else last
    return request.META.get('REMOTE_ADDR', '')


