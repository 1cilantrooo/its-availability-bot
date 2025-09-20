# check_its.py ーー 完全貼り替え版（施設選択＋9/10月チェック＋LINE通知）
from playwright.sync_api import sync_playwright
from utils import notify_line_api
import os, json, re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # Python 3.11+

# 共通のカレンダー入口URL（あなたが貼ってくれたもの）
CALENDAR_URL = "https://as.its-kenpo.or.jp/apply/empty_calendar?s=PWdqTjMwRFpwWlNaMUpIZDlrSGR3MVda"

# 監視対象の施設（サイトの表記に合わせる）
FACILITIES = [
    "ホテルハーヴェスト旧軽井沢",
    "トスラブ箱根和奏林",
    "トスラブ箱根ビオーレ",
    "蓼科東急ホテル",
]
# 監視する月（ページ内に「9月」「10月」が見える状態まで送る）
TARGET_MONTHS = {9, 10}

# “空きあり”の判定に使う文字
POSITIVE_MARKS = ["◎", "○", "△", "空き", "予約可"]

# ===== 通知まわり・運用オプション =====
DIFF_NOTIFY = True                   # True=変化があった施設だけ通知
STATE_FILE = "last_state.json"       # 前回結果の保存先
CAPTURE_HIT_SCREENSHOT = True        # ヒット時にスクショ保存
SHOT_DIR = "hits"                    # スクショ保存ディレクトリ
TZ_JP = ZoneInfo("Asia/Tokyo")       # 実行タイムゾーン

# 月の自動追従：実行時点の今月＋来月を常に追う
def compute_target_months(dt=None):
    dt = dt or datetime.now(TZ_JP)
    this_m = dt.month
    next_m = 1 if this_m == 12 else this_m + 1
    return {this_m, next_m}

TARGET_MONTHS = compute_target_months()   # ← これで固定{9,10}を置き換え

def load_last_state(path=STATE_FILE):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state, path=STATE_FILE):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 状態保存に失敗: {e}", flush=True)

def is_login_page(url: str) -> bool:
    return any(k in url.lower() for k in ("login", "signin", "auth"))


def visible_tab(page):
    # display:none じゃないタブ（=今表示されてる施設パネル）
    return page.locator('.tabContent .tabConBody:not([style*="display:none"])').first

def has_availability_in_container(root) -> bool:
    """
    表示中の施設パネル(root)のカレンダーだけを対象に空き判定。
    説明文や凡例の○/△は無視する。
    """
    # まずはクラス判定（サイト実装に合わせてクラス名を追加OK）
    if root.locator(".tb-calendar td.empty, .tb-calendar td.a_little").count() > 0:
        return True

    # セル単位の文字判定（カレンダー表に限定）
    cells = root.locator(".tb-calendar td")   # ← ここがポイント
    cnt = cells.count()
    for i in range(cnt):
        try:
            txt = cells.nth(i).inner_text(timeout=200)
            if "◎" in txt or "○" in txt or "△" in txt:
                return True
        except Exception:
            pass

    return False

def try_click_update(page) -> None:
    """施設を選んだ後に押しがちなボタンを順に試す。"""
    labels = ["検索", "再表示", "表示", "絞り込み", "検索する", "表示する", "OK", "決定", "反映"]
    for label in labels:
        try:
            page.get_by_role("button", name=label).first.click()
            page.wait_for_load_state("networkidle")
            return
        except Exception:
            pass
    # 汎用submit
    try:
        page.locator('input[type=submit], button[type=submit]').first.click()
        page.wait_for_load_state("networkidle")
    except Exception:
        pass


def _norm(s: str) -> str:
    import re, unicodedata
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"\s+", "", s)                     # 空白除去
    s = re.sub(r"[()（）・/／\-‐–—_]", "", s)      # 記号いろいろ除去
    return s

def choose_facility(page, name: str) -> str | None:
    """
    施設タブ(#top_tabs)から name に該当する <li> をクリック。
    クリック後、#page-title が「◯◯申込」に変わるのを待ち、
    その施設専用コンテナ（#tcas_XXXX）を返す。
    失敗時は None。
    """
    import re, unicodedata

    def _norm(s: str) -> str:
        if not s: return ""
        s = unicodedata.normalize("NFKC", s).lower()
        s = re.sub(r"\s+", "", s)
        s = re.sub(r"[()（）・/／\\\-‐–—_]", "", s)
        return s

    target = name.strip()
    target_norm = _norm(target)

    def extract_tcas_id(li_el) -> str | None:
        # <a onclick="showTab(this, 'as_819')"> から as_819 → tcas_819 を得る
        try:
            a = li_el.locator("a")
            onclick = a.get_attribute("onclick") or ""
            m = re.search(r"showTab\(this,\s*'as_(\d+)'\)", onclick)
            if m:
                return f"#tcas_{m.group(1)}"
        except Exception:
            pass
        return None

    # 1) 完全一致
    try:
        lis = page.locator("#top_tabs li")
        # span 完全一致の li を探す
        idx = -1
        spans = lis.locator("span")
        count = spans.count()
        for i in range(count):
            txt = (spans.nth(i).inner_text(timeout=200) or "").strip()
            if txt == target:
                idx = i
                break
        if idx >= 0:
            li = lis.nth(idx)
            tcas = extract_tcas_id(li)
            spans.nth(idx).click()
            # タイトルが切り替わるまで待つ
            page.wait_for_function(
                """(expected) => {
                    const el = document.querySelector('#page-title');
                    return el && el.textContent && el.textContent.includes(expected);
                }""",
                arg=f"{target}申込"
            )
            if tcas:
                # その施設専用パネル内だけでカレンダー可視を待つ
                page.wait_for_selector(f'{tcas} .tb-calendar', timeout=8000)
                return tcas
    except Exception as e:
        print(f"[DEBUG] タブクリック(完全一致)失敗: {e}")

    # 2) 表記ゆれ（部分一致）
    try:
        lis = page.locator("#top_tabs li")
        spans = lis.locator("span")
        count = spans.count()
        candidates = []
        for i in range(count):
            lab = (spans.nth(i).inner_text(timeout=200) or "").strip()
            if not lab:
                continue
            candidates.append(lab)
            if _norm(lab) in target_norm or target_norm in _norm(lab):
                li = lis.nth(i)
                tcas = extract_tcas_id(li)
                spans.nth(i).click()
                page.wait_for_function(
                    """(expected) => {
                        const el = document.querySelector('#page-title');
                        return el && el.textContent && el.textContent.includes(expected);
                    }""",
                    arg=f"{target}申込"
                )
                if tcas:
                    page.wait_for_selector(f'{tcas} .tb-calendar', timeout=8000)
                    return tcas
        print(f"[DEBUG] #top_tabs の候補: {candidates}")
    except Exception as e:
        print(f"[DEBUG] タブ候補取得失敗: {e}")

    return None
def month_labels_present(html: str) -> bool:
    return all(f"{m}月" in html for m in sorted(TARGET_MONTHS))


def ensure_target_months(page, tcas: str) -> None:
    """
    指定施設パネル(tcas)内で TARGET_MONTHS(例: {9,10}) の両方が見えるまで、
    前月/翌月だけで調整（“今月”ボタンは使わない）
    """
    root = page.locator(tcas)
    page.wait_for_timeout(200)

    min_t = min(TARGET_MONTHS)
    max_t = max(TARGET_MONTHS)

    for _ in range(12):  # 暴走防止
        vis = _visible_months_in(root)
        # デバッグしたければ：
        # print(f"[DEBUG] visible months: {sorted(vis)} ; target: {sorted(TARGET_MONTHS)}", flush=True)

        if min_t in vis and max_t in vis:
            return  # 目的達成

        if not vis:
            # 何も読めないときは一歩だけ進めて再評価
            if not _click_next(root, page):
                break
            continue

        cur_min = min(vis)
        cur_max = max(vis)

        if cur_min > max_t:
            # 行き過ぎ（例：11/12が見えていて {9,10} を狙う）→ 前へ戻る
            if not _click_prev(root, page):
                break
        elif cur_max < min_t:
            # まだ前（例：7/8が見えていて {9,10} を狙う）→ 次へ進む
            if not _click_next(root, page):
                break
        else:
            # 部分一致（例：10/11が見えていて {9,10} を狙う）
            moved = False
            if min_t not in vis:
                moved = _click_prev(root, page)
            if not moved and max_t not in vis:
                moved = _click_next(root, page)
            if not moved:
                break

def _visible_months_in(root) -> set[int]:
    """その施設パネル内で現在DOMに見えている '◯月' の数値集合を返す"""
    try:
        html = root.inner_html(timeout=2000)
    except Exception:
        html = ""
    months = set()
    for m in re.findall(r'(\d{1,2})月', html):
        try:
            months.add(int(m))
        except Exception:
            pass
    return months

def _click_next(root, page) -> bool:
    # 翌月へ
    try:
        nxt = root.locator("#nextMonth")
        if nxt.count():
            nxt.first.click()
            page.wait_for_load_state("networkidle")
            return True
    except Exception:
        pass
    for label in ("翌月＞", "翌月", "次月", "次へ", ">", "→", "Next"):
        try:
            btn = root.get_by_role("button", name=label)
            if btn.count():
                btn.first.click()
                page.wait_for_load_state("networkidle")
                return True
        except Exception:
            pass
        try:
            cand = root.locator(f'input[type="button"][value="{label}"]')
            if cand.count():
                cand.first.click()
                page.wait_for_load_state("networkidle")
                return True
        except Exception:
            pass
    return False

def _click_prev(root, page) -> bool:
    # 前月へ
    try:
        prv = root.locator("#prevMonth")
        if prv.count():
            prv.first.click()
            page.wait_for_load_state("networkidle")
            return True
    except Exception:
        pass
    for label in ("＜前月", "前月", "前へ", "前", "<", "←", "Prev"):
        try:
            btn = root.get_by_role("button", name=label)
            if btn.count():
                btn.first.click()
                page.wait_for_load_state("networkidle")
                return True
        except Exception:
            pass
        try:
            cand = root.locator(f'input[type="button"][value="{label}"]')
            if cand.count():
                cand.first.click()
                page.wait_for_load_state("networkidle")
                return True
        except Exception:
            pass
    return False

def check_facility(page, name: str):
    """施設をチェックし、結果dictを返す"""
    print(f"[DEBUG] facility: {name} -> goto", flush=True)
    page.goto(CALENDAR_URL, wait_until="domcontentloaded", timeout=20000)
    print(f"[DEBUG] landed: {page.url}", flush=True)

    if is_login_page(page.url):
        return {"name": name, "available": None, "reason": "session_expired", "shot": None}

    tcas = choose_facility(page, name)
    if not tcas:
        return {"name": name, "available": None, "reason": "select_failed", "shot": None}

    try:
        page.wait_for_selector(f"{tcas} .tb-calendar td", timeout=8000)
        print(f"[DEBUG] {name}: カレンダー表示を確認", flush=True)
    except Exception as e:
        print(f"[ERROR] {name}: カレンダー表示待ち失敗 {e}", flush=True)
        return {"name": name, "available": None, "reason": "calendar_not_ready", "shot": None}

    ensure_target_months(page, tcas)
    root = page.locator(tcas)

    available = has_availability_in_container(root)
    shot_path = None
    if available and CAPTURE_HIT_SCREENSHOT:
        os.makedirs(SHOT_DIR, exist_ok=True)
        ts = datetime.now(TZ_JP).strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r'[\\/:*?"<>| ]+', "_", name)
        shot_path = os.path.join(SHOT_DIR, f"hit_{safe}_{ts}.png")
        try:
            page.screenshot(path=shot_path, full_page=True)
            print(f"[DEBUG] screenshot saved: {shot_path}", flush=True)
        except Exception as e:
            print(f"[WARN] screenshot failed: {e}", flush=True)

    print(f"[DEBUG] facility done: {name}", flush=True)
    return {"name": name, "available": available, "reason": None, "shot": shot_path}


def main():
    print("[DEBUG] main start", flush=True)
    with sync_playwright() as p:
        print("[DEBUG] playwright started", flush=True)
        # デバッグ中は headless=False のままでOK。常時運用は True 推奨。
        browser = p.chromium.launch(headless=True, slow_mo=0)
        print("[DEBUG] browser launched", flush=True)
        context = browser.new_context(storage_state="auth_state.json")
        print("[DEBUG] context created", flush=True)
        page = context.new_page()
        print("[DEBUG] new page created", flush=True)

        current = {}   # {facility_name: True/False}
        issues  = []   # セッション切れ/選択失敗など

        for name in FACILITIES:
            print(f"[DEBUG] check start: {name}", flush=True)
            try:
                result = check_facility(page, name)
                if result["available"] is None:
                    issues.append((name, result["reason"]))
                else:
                    current[name] = bool(result["available"])
            except Exception as e:
                print(f"[ERROR] {name} check failed: {e}", flush=True)
            print(f"[DEBUG] check end: {name}", flush=True)

        context.close()
        browser.close()
    print("[DEBUG] main end", flush=True)

    # ---- 差分通知 or 逐次通知 ----
    if not DIFF_NOTIFY:
        # 従来動作：空きがあった施設を毎回通知
        lines = [f"{k}: {'○' if v else '×'}" for k,v in current.items() if v]
        if lines:
            notify_line_api("[ITS] 空きあり\n" + "\n".join(lines) + f"\n{CALENDAR_URL}")
        else:
            print("[ITS] 今回は空き検知なし（逐次通知OFF）")
        return

    # 差分比較
    last = load_last_state()
    changes = []  # (name, before, after)
    for k, v_now in current.items():
        v_before = last.get(k)
        if v_before is None:
            # 初回は「状態登録のみ」で通知しない（うるさくしない）
            continue
        if bool(v_now) != bool(v_before):
            changes.append((k, bool(v_before), bool(v_now)))

    # 状態保存（次回比較用）
    save_state(current)

    # 変化があったものだけ通知
    if changes:
        lines = []
        for name, before, after in changes:
            trans = f"{'○' if before else '×'} → {'○' if after else '×'}"
            lines.append(f"{name}: {trans}")
        msg = "[ITS] 状態変化がありました\n" + "\n".join(lines) + f"\n{CALENDAR_URL}"
        notify_line_api(msg)
    else:
        print("[ITS] 状態変化なし（通知なし）")
    if issues:
        msg = "[ITS] チェック異常\n" + "\n".join([f"{n}: {r}" for n, r in issues])
        notify_line_api(msg)

if __name__ == "__main__":
    main()