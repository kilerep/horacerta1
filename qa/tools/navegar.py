"""Navegador minimo para os agentes-persona usarem o HoraCerta local (so biblioteca padrao).

Mantem o cookie de sessao, pega o CSRF sozinho e mostra o que interessa da pagina:
status, para onde redirecionou, mensagens de aviso, titulos e erros de formulario.

    python qa/tools/navegar.py SESSIONID get /me/painel/
    python qa/tools/navegar.py SESSIONID post /me/servicos/rapido/ client_name="Dona Maria" title="Trocar chuveiro"
    python qa/tools/navegar.py SESSIONID texto /me/servicos/      (texto visivel da pagina)

Servidor padrao: http://127.0.0.1:8765 (mude com HC_BASE).
"""

import http.cookiejar
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html import unescape

BASE = os.environ.get("HC_BASE", "http://127.0.0.1:8765")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def opener(sessionid, follow=True):
    jar = http.cookiejar.CookieJar()
    host = urllib.parse.urlparse(BASE).hostname
    jar.set_cookie(http.cookiejar.Cookie(0, "sessionid", sessionid, None, False, host, False, False, "/", True,
                                         False, None, False, None, None, {}))
    handlers = [urllib.request.HTTPCookieProcessor(jar)]
    if not follow:
        handlers.append(NoRedirect())
    return urllib.request.build_opener(*handlers), jar


def fetch(op, method, path, data=None):
    req = urllib.request.Request(BASE + path, data=data, method=method)
    try:
        resp = op.open(req, timeout=60)
        return resp.status, resp.geturl(), resp.read().decode("utf-8", "replace"), dict(resp.headers)
    except urllib.error.HTTPError as err:
        return err.code, err.headers.get("Location", BASE + path), err.read().decode("utf-8", "replace"), dict(err.headers)


def visible_text(html):
    html = re.sub(r"(?is)<(script|style|svg)\b.*?</\1>", " ", html)
    html = re.sub(r"(?is)<(aside|nav)\b[^>]*class=\"[^\"]*(sidebar|bottom-nav)[^\"]*\".*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def summary(status, url, html, headers):
    out = [f"STATUS {status}  URL {url.replace(BASE, '')}"]
    ctype = headers.get("Content-Type", "")
    if "html" not in ctype:
        out.append(f"ARQUIVO {ctype} {headers.get('Content-Disposition', '')}")
        return "\n".join(out)
    title = re.search(r"(?is)<title>(.*?)</title>", html)
    out.append("TITULO " + (unescape(title.group(1)).strip() if title else "-"))
    for msg in re.findall(r'(?is)class="hc-global-feedback[^"]*"[^>]*>(.*?)</div>', html):
        out.append("AVISO " + visible_text(msg))
    for err in re.findall(r'(?is)<ul class="errorlist[^"]*">(.*?)</ul>', html):
        out.append("ERRO_FORM " + visible_text(err))
    for h in re.findall(r"(?is)<h[12][^>]*>(.*?)</h[12]>", html)[:12]:
        out.append("H " + visible_text(h))
    return "\n".join(out)


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    sessionid, action, path = sys.argv[1], sys.argv[2], sys.argv[3]
    op, _ = opener(sessionid)
    if action in ("get", "texto"):
        status, url, html, headers = fetch(op, "GET", path)
        print(summary(status, url, html, headers) if action == "get" else visible_text(html)[:6000])
        return
    if action == "post":
        _, _, page, _ = fetch(op, "GET", path)
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page)
        fields = dict(arg.split("=", 1) for arg in sys.argv[4:])
        if token:
            fields.setdefault("csrfmiddlewaretoken", token.group(1))
        data = urllib.parse.urlencode(fields).encode()
        op_no, _ = opener(sessionid, follow=False)
        # reaproveita o cookie csrftoken obtido no GET
        for handler in op.handlers:
            if isinstance(handler, urllib.request.HTTPCookieProcessor):
                op_no = urllib.request.build_opener(handler, NoRedirect())
        status, url, html, headers = fetch(op_no, "POST", path, data)
        if status in (301, 302):
            print(f"STATUS {status}  REDIRECIONA {headers.get('Location', url)}")
            status, url, html, headers = fetch(op, "GET", headers.get("Location", path).replace(BASE, ""))
        print(summary(status, url, html, headers))
        return
    print(__doc__)


if __name__ == "__main__":
    main()
