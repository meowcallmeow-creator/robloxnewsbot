"""X(트위터) 계정 -> 디스코드 웹훅 봇. 표준 라이브러리만 사용."""
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
STATE_FILE = ROOT / "state.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def fetch_tweets(user):
    data = json.loads(http(f"https://api.fxtwitter.com/2/profile/{user}/statuses"))
    return data.get("results", [])


def clean_text(t):
    return html.unescape(t.get("text") or "").strip()


def translate(text, target):
    q = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": target, "dt": "t", "q": text})
    data = json.loads(http("https://translate.googleapis.com/translate_a/single?" + q))
    return "".join(seg[0] for seg in data[0] if seg[0])


def post(webhook, content):
    body = json.dumps({"content": content[:1990]}).encode()
    http(webhook, body, {"Content-Type": "application/json"})


def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf8"))
    webhook = os.environ.get("DISCORD_WEBHOOK_URL") or cfg.get("webhook_url")
    dry = "--dry" in sys.argv
    if not webhook and not dry:
        sys.exit("웹훅 URL이 필요합니다. config.json의 webhook_url 또는 DISCORD_WEBHOOK_URL 환경변수에 넣어 주세요.")
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

    for user in cfg["accounts"]:
        try:
            tweets = fetch_tweets(user)
        except Exception as e:
            print(f"[{user}] 가져오기 실패: {e}")
            continue
        if cfg.get("skip_retweets"):
            tweets = [t for t in tweets if not t.get("reposted_by")
                      and t["author"]["screen_name"].lower() == user.lower()]
        if cfg.get("skip_replies"):
            tweets = [t for t in tweets if not t.get("replying_to")]
        tweets = [t for t in tweets if t.get("id")]
        tweets.sort(key=lambda t: int(t["id"]))
        last = int(state.get(user, 0))
        if not last:  # 첫 실행: 기존 글은 올리지 않고 기준점만 저장
            if tweets:
                state[user] = tweets[-1]["id"]
            print(f"[{user}] 첫 실행: 기준점만 저장")
            continue
        for t in [t for t in tweets if int(t["id"]) > last]:
            link = f"https://{cfg['link_domain']}/{t['author']['screen_name']}/status/{t['id']}"
            msg = link
            text = clean_text(t)
            if cfg.get("translate") and text and t.get("lang") != cfg["target_lang"]:
                try:
                    msg += "\n\n" + translate(text, cfg["target_lang"])
                except Exception as e:
                    print(f"[{user}] 번역 실패(링크만 전송): {e}")
            print(f"[{user}] 전송:\n{msg}\n")
            if not dry:
                post(webhook, msg)
            state[user] = t["id"]

    if not dry:
        STATE_FILE.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
