#!/usr/bin/env python3
"""Generate the public README visuals under docs/assets/readme/.

The visuals are messenger-style conversations showing the product doing
real work. Each panel is written as a small self-contained HTML page (the
committed source of truth, one per locale) and screenshotted with headless
Chrome into a 2x PNG for the README. The Korean panels use the product's
own prompt strings; the other locales translate them.

    python3 scripts/build_readme_visuals.py            # HTML only
    python3 scripts/build_readme_visuals.py --render   # HTML + PNG (needs Chrome)
"""

from __future__ import annotations

import html
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets" / "readme"
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome", "chromium", "chromium-browser",
)

CSS = """
:root{--wall:#efeae2;--sent:#d9fdd3;--recv:#fff;--ink:#111b21;--meta:#667781;--green:#1f8a5b;--amber:#b8791a;--blue:#53bdeb}
*{box-sizing:border-box}
body{margin:0;background:#f6f4ef;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Apple SD Gothic Neo","Noto Sans KR","Hiragino Sans","Noto Sans JP","PingFang SC","Noto Sans SC",sans-serif;color:var(--ink);-webkit-font-smoothing:antialiased}
.msg{max-width:84%;padding:8px 11px 7px;border-radius:14px;font-size:14px;line-height:1.38;position:relative;box-shadow:0 1px 1px rgba(0,0,0,.08);white-space:pre-wrap}
.me{align-self:flex-end;background:var(--sent);border-bottom-right-radius:4px}
.ai{align-self:flex-start;background:var(--recv);border-bottom-left-radius:4px}
.t{display:block;text-align:right;font-size:10.5px;color:var(--meta);margin-top:3px}
.me .t:after{content:" ✓✓";color:var(--blue);letter-spacing:-2px}
.card{display:flex;align-items:center;gap:10px;background:#f7f5f0;border:1px solid #e3ded4;border-radius:10px;padding:8px 10px;margin:-2px 0 8px;font-weight:600;font-size:13.5px}
.card i{width:30px;height:30px;border-radius:7px;display:grid;place-items:center;font-style:normal;font-size:17px}
.card i.doc{background:#e7effa}.card i.cal{background:#fbe9e3}
.pill{align-self:center;background:#e1dbd0;color:#5c5650;font-size:11.5px;font-weight:600;padding:4px 11px;border-radius:12px}
.chip{align-self:flex-start;background:#fff;border:1.5px solid var(--green);color:var(--green);font-size:11.5px;font-weight:700;padding:3px 10px;border-radius:12px;margin-top:-3px}
.chip.amber{border-color:var(--amber);color:var(--amber)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:26px;padding:34px}
.tile{background:var(--wall);border-radius:24px;padding:16px 14px;display:flex;flex-direction:column;gap:9px;min-height:180px;
 }.tile.col{padding:20px 18px;gap:10px;
 background-image:radial-gradient(rgba(0,0,0,.035) 1px,transparent 1.2px);background-size:22px 22px}
"""


GREEN = "green"
AMBER = "amber"


def esc(s: str) -> str:
    return html.escape(s, quote=False)


UI = {
    "en": {"name": "Personal AgentOS", "sub": "on your computer", "restart": "after a restart",
           "note": "Launch notes.md", "event": "dentist appointment · tomorrow 16:00"},
    "ko": {"name": "Personal AgentOS", "sub": "내 컴퓨터에서", "restart": "재시작 후",
           "note": "출시 메모.md", "event": "치과 약속 · 내일 16:00"},
    "ja": {"name": "Personal AgentOS", "sub": "自分のコンピュータで", "restart": "再起動後",
           "note": "Launch notes.md", "event": "歯医者の予約 · 明日 16:00"},
    "zh-CN": {"name": "Personal AgentOS", "sub": "在你的电脑上", "restart": "重启之后",
              "note": "Launch notes.md", "event": "牙医预约 · 明天 16:00"},
}

# Hero, left phone: one calendar turn. Korean uses the product's own strings
# (calendar_conversation.py); the other locales translate them.
HERO_CAL = {
    "en": [
        ("me", "Schedule a dentist appointment tomorrow at 3.", "9:41"),
        ("ai", "This is a draft. Nothing is on your calendar yet.\nTitle: dentist appointment\nWhen: tomorrow 15:00 – 16:00\nReply “approve” to create exactly this, “make it 4pm” to change it, “cancel” to stop.", "9:41"),
        ("me", "make it 4pm", "9:42"),
        ("ai", "This is a draft. Nothing is on your calendar yet.\nTitle: dentist appointment\nWhen: tomorrow 16:00 – 17:00\nReply “approve” to create exactly this.", "9:42"),
        ("me", "approve", "9:42"),
        ("ai", "Created the event on your calendar.", "9:42", ("cal", "EVENT"), ("asked before acting", AMBER)),
    ],
    "ko": [
        ("me", "내일 3시에 치과 약속 잡아줘.", "9:41"),
        ("ai", "일정 초안입니다. 아직 캘린더에 만들지 않았습니다.\n제목: 치과 약속\n일시: 내일 15:00 – 16:00\n\"승인\"이라고 답하면 이 내용 그대로 만듭니다. 바꾸려면 예: \"4시로\". 그만두려면 \"취소\".", "9:41"),
        ("me", "4시로", "9:42"),
        ("ai", "일정 초안입니다. 아직 캘린더에 만들지 않았습니다.\n제목: 치과 약속\n일시: 내일 16:00 – 17:00\n\"승인\"이라고 답하면 이 내용 그대로 만듭니다.", "9:42"),
        ("me", "승인", "9:42"),
        ("ai", "캘린더에 일정을 만들었습니다.", "9:42", ("cal", "EVENT"), ("행동 전에 먼저 물어봄", AMBER)),
    ],
    "ja": [
        ("me", "Schedule a dentist appointment tomorrow at 3.", "9:41"),
        ("ai", "予定の下書きです。まだカレンダーには作成していません。\n件名: 歯医者の予約\n日時: 明日 15:00 – 16:00\n「approve」で作成、「make it 4pm」で変更、「cancel」で中止。", "9:41"),
        ("me", "make it 4pm", "9:42"),
        ("ai", "予定の下書きです。まだカレンダーには作成していません。\n件名: 歯医者の予約\n日時: 明日 16:00 – 17:00\n「approve」と答えればこの内容のまま作成します。", "9:42"),
        ("me", "approve", "9:42"),
        ("ai", "カレンダーに予定を作成しました。", "9:42", ("cal", "EVENT"), ("実行前に確認", AMBER)),
    ],
    "zh-CN": [
        ("me", "Schedule a dentist appointment tomorrow at 3.", "9:41"),
        ("ai", "这是草稿。日历上还没有任何内容。\n标题：牙医预约\n时间：明天 15:00 – 16:00\n回复“approve”创建，“make it 4pm”修改，“cancel”停止。", "9:41"),
        ("me", "make it 4pm", "9:42"),
        ("ai", "这是草稿。日历上还没有任何内容。\n标题：牙医预约\n时间：明天 16:00 – 17:00\n回复“approve”即按此原样创建。", "9:42"),
        ("me", "approve", "9:42"),
        ("ai", "已在你的日历上创建了该事件。", "9:42", ("cal", "EVENT"), ("先问过你才做", AMBER)),
    ],
}

# Hero, right phone: save a note from an allowed folder, restart, find it again.
HERO_FILE = {
    "en": [
        ("me", "Summarize “Launch review” and save it as “Launch notes”.", "10:03"),
        ("ai", "Saved “Launch notes” to your workspace folder. The original file is untouched.", "10:03", ("doc", "NOTE"), ("only the folders you allowed", GREEN)),
        ("divider", "RESTART"),
        ("me", "Find “Launch notes” in my saved results.", "14:20"),
        ("ai", "Saved result: Launch notes.md", "14:20", ("doc", "NOTE"), ("still yours after a restart", GREEN)),
    ],
    "ko": [
        ("me", "“출시 검토” 자료를 요약해서 “출시 메모”로 저장해줘.", "10:03"),
        ("ai", "“출시 메모”를 작업공간 폴더에 저장했습니다. 원본 파일은 그대로입니다.", "10:03", ("doc", "NOTE"), ("허용한 폴더만 사용", GREEN)),
        ("divider", "RESTART"),
        ("me", "저장한 결과에서 “출시 메모” 찾아줘.", "14:20"),
        ("ai", "저장 결과: 출시 메모.md", "14:20", ("doc", "NOTE"), ("재시작해도 내 것", GREEN)),
    ],
    "ja": [
        ("me", "Summarize “Launch review” and save it as “Launch notes”.", "10:03"),
        ("ai", "“Launch notes” を作業スペースのフォルダに保存しました。元のファイルはそのままです。", "10:03", ("doc", "NOTE"), ("許可したフォルダだけ", GREEN)),
        ("divider", "RESTART"),
        ("me", "Find “Launch notes” in my saved results.", "14:20"),
        ("ai", "保存結果: Launch notes.md", "14:20", ("doc", "NOTE"), ("再起動しても自分のもの", GREEN)),
    ],
    "zh-CN": [
        ("me", "Summarize “Launch review” and save it as “Launch notes”.", "10:03"),
        ("ai", "已把“Launch notes”保存到你的工作区文件夹。原文件未改动。", "10:03", ("doc", "NOTE"), ("只用你允许的文件夹", GREEN)),
        ("divider", "RESTART"),
        ("me", "Find “Launch notes” in my saved results.", "14:20"),
        ("ai", "保存结果：Launch notes.md", "14:20", ("doc", "NOTE"), ("重启后仍然是你的", GREEN)),
    ],
}

EN_ASKS = (
    "Summarize “Launch review” and save it as “Launch notes”.",
    "Find anything about the budget in my mail.",
    "Schedule a dentist appointment tomorrow at 3.",
    "Remember that I have a peanut allergy.",
    "Look up these two products and compare them.",
    "Find “Launch notes” in my saved results.",
)
KO_ASKS = (
    "“출시 검토” 자료를 요약해서 “출시 메모”로 저장해줘.",
    "메일에서 예산 관련 내용 찾아줘.",
    "내일 3시에 치과 약속 잡아줘.",
    "땅콩 알레르기가 있다는 걸 기억해 줘.",
    "이 두 제품을 조사해서 비교해줘.",
    "저장한 결과에서 “출시 메모” 찾아줘.",
)
# The product understands Korean and English requests today, so the ja and
# zh-CN panels show the English request with a localized reply.
_SCENE_REPLIES = {
    "en": (
        ("Read the folder you allowed and saved a new note in your workspace folder. The original is untouched.", "saved"),
        ("Searched only the mailbox you connected.", "read-only"),
        ("Draft, not on your calendar yet: ‘Dentist’, tomorrow 15:00. Reply approve to create exactly this.", "asks first"),
        ("Kept. See or correct it here; delete it on the web page.", "editable"),
        ("Read three public pages from a search. What they say, what stayed unknown, and the links.", "sourced"),
        ("Saved result: Launch notes.md", "continues"),
    ),
    "ko": (
        ("허용한 폴더를 읽고 작업공간 폴더에 새 메모를 저장했습니다. 원본은 그대로입니다.", "저장됨"),
        ("연결한 메일함만 검색했습니다.", "읽기만"),
        ("일정 초안입니다. 아직 캘린더에 만들지 않았습니다. 제목: 치과 약속 · 내일 15:00 · ‘승인’이라고 답하면 만듭니다.", "먼저 물어봄"),
        ("기억했습니다. 여기서 보고 고칠 수 있고, 삭제는 웹에서 합니다.", "수정 가능"),
        ("검색해서 공개 페이지 세 개를 읽었습니다. 페이지가 말하는 것, 확인 안 된 것, 출처 링크를 나눠서 드립니다.", "출처 있음"),
        ("저장 결과: 출시 메모.md", "이어서"),
    ),
    "ja": (
        ("許可したフォルダを読み、作業スペースに新しいメモを保存しました。元のファイルはそのままです。", "保存済み"),
        ("接続したメールボックスだけを検索しました。", "読み取りのみ"),
        ("下書きです。まだカレンダーには入っていません。『歯医者』明日 15:00。approve と答えれば作成します。", "先に確認"),
        ("覚えました。ここで確認・修正できます。削除は Web 画面で行います。", "修正できる"),
        ("検索して公開ページを3つ読みました。書かれていること、未確認のこと、出典リンクを分けて示します。", "出典あり"),
        ("保存結果: Launch notes.md", "続きから"),
    ),
    "zh-CN": (
        ("读取了你允许的文件夹，在工作区文件夹里保存了一条新笔记。原文件未改动。", "已保存"),
        ("只搜索了你连接的邮箱。", "只读"),
        ("草稿，尚未写入日历：“牙医”，明天 15:00。回复 approve 即按此创建。", "先问你"),
        ("已记住。可在这里查看和修改；删除在网页端进行。", "可修改"),
        ("搜索后读了三个公开页面。分开列出页面所说的、尚未确认的，以及来源链接。", "有出处"),
        ("保存结果：Launch notes.md", "接着来"),
    ),
}
SCENES = {
    loc: [(ask, reply, chip) for ask, (reply, chip) in zip(KO_ASKS if loc == "ko" else EN_ASKS, replies)]
    for loc, replies in _SCENE_REPLIES.items()
}
SCENE_TITLES = {
    "en": "Five everyday requests that run today, and one after a restart",
    "ko": "오늘 실제로 되는 다섯 가지 요청과 재시작 후 이어가기",
    "ja": "今日実際に動く5つの依頼と、再起動後の続き",
    "zh-CN": "今天就能完成的五个日常请求，以及重启后的继续",
}
HERO_TITLES = {
    "en": "Two real conversations: a calendar draft that waits for approval, and a saved note found again after a restart",
    "ko": "실제 대화 두 개: 승인을 기다리는 일정 초안, 재시작 후 다시 찾은 저장 메모",
    "ja": "実際の会話2つ: 承認を待つ予定の下書きと、再起動後に見つけ直した保存メモ",
    "zh-CN": "两段真实对话：等待批准的日程草稿，以及重启后再次找到的已保存笔记",
}




def _resolve(messages, ui):
    out = []
    for m in messages:
        if m[0] == "divider":
            out.append(("divider", ui["restart"]))
            continue
        m = list(m)
        if len(m) > 3 and m[3]:
            icon, key = m[3]
            m[3] = (icon, ui["note"] if key == "NOTE" else ui["event"])
        out.append(tuple(m))
    return out


def msg_html(m) -> str:
    kind = m[0]
    if kind == "divider":
        return f'<div class="pill">{esc(m[1])}</div>'
    text, time = m[1], m[2] if len(m) > 2 else ""
    attach = m[3] if len(m) > 3 else None
    chip = m[4] if len(m) > 4 else None
    parts = [f'<div class="msg {kind}">']
    if attach:
        icon, label = attach
        glyph = "📄" if icon == "doc" else "📅"
        parts.append(f'<div class="card"><i class="{icon}">{glyph}</i>{esc(label)}</div>')
    parts.append(esc(text))
    if time:
        parts.append(f'<span class="t">{esc(time)}</span>')
    parts.append("</div>")
    if chip:
        label, col = chip
        parts.append(f'<div class="chip{" amber" if col == AMBER else ""}">{esc(label)}</div>')
    return "".join(parts)


def column_html(messages) -> str:
    return '<div class="tile col">' + "".join(msg_html(m) for m in messages) + "</div>"


def page(title: str, body: str, width: int) -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{esc(title)}</title>'
            f'<style>{CSS}body{{width:{width}px}}</style></head><body>{body}</body></html>\n')


def build_hero(locale: str) -> str:
    ui = UI[locale]
    body = ('<div class="grid">' + column_html(_resolve(HERO_CAL[locale], ui))
            + column_html(_resolve(HERO_FILE[locale], ui)) + "</div>")
    return page(HERO_TITLES[locale], body, 1000)


def build_scenes(locale: str) -> str:
    ui = UI[locale]
    tiles = []
    for i, (ask, reply, chip) in enumerate(SCENES[locale]):
        inner = ""
        if i == len(SCENES[locale]) - 1:
            inner += f'<div class="pill">{esc(ui["restart"])}</div>'
        inner += f'<div class="msg me">{esc(ask)}</div>'
        inner += f'<div class="msg ai">{esc(reply)}</div>'
        inner += f'<div class="chip{" amber" if i == 2 else ""}">{esc(chip)}</div>'
        tiles.append(f'<div class="tile">{inner}</div>')
    return page(SCENE_TITLES[locale], '<div class="grid">' + "".join(tiles) + "</div>", 1000)


SIZES = {"hero": (1000, 665), "scenes": (1000, 690)}


def chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        if Path(c).is_file() or shutil.which(c):
            return c
    return None


def render(name: str, kind: str) -> None:
    exe = chrome()
    if not exe:
        raise SystemExit("no Chrome/Chromium found for --render")
    w, h = SIZES[kind]
    subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=2", f"--window-size={w},{h}",
                    f"--screenshot={OUT / (name + '.png')}", (OUT / (name + ".html")).as_uri()],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(argv: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for locale in SCENES:
        for kind, build in (("hero", build_hero), ("scenes", build_scenes)):
            name = f"{kind}.{locale}"
            (OUT / f"{name}.html").write_text(build(locale), encoding="utf-8")
            if "--render" in argv:
                render(name, kind)


if __name__ == "__main__":
    main(sys.argv[1:])
