#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Outlook 注册机 v2.0 — 2026 年底版
================================
真正能跑的半自动注册机,不是记账本。

能做的:
  1. 自动打开微软官方注册页 signup.live.com
  2. 自动生成 / 读取队列里的邮箱名、姓名、生日、强密码
  3. 像真人一样逐字打字、随机停顿、随机移动鼠标、随机窗口尺寸
  4. 自动点下一步、自动处理“邮箱已被占用”并换一个候选名重试
  5. 自动检测注册成功 / 被拒绝 / 异常活动,截图 + 写结果日志
  6. 一个一个注册,注册完随机休息一段时间再做下一个,避免批量被封

做不到、也不做的:
  * 绕过人机验证 / CAPTCHA。微软最后一定会弹验证,必须你手动点。
    脚本到那一步会自动停下来等你,等你验证完按回车,它再继续。
    任何声称能全自动绕过验证的,注册下来的号也基本会被封。
  * 用机房 IP / 代理批量刷号。那样只会更快触发“异常活动”。

运行环境: 你自己的电脑,真实网络、真实浏览器,不要在云服务器上跑。
Python 3.10+, pip install -r requirements.txt, 再 playwright install chromium

用法:
  python outlook_registrator.py                 # 按 accounts.csv 队列,一个一个注册
  python outlook_registrator.py --limit 3       # 只注册前 3 个
  python outlook_registrator.py --generate 5    # 只生成 5 个账号到 accounts.csv,不打开浏览器
  python outlook_registrator.py --dry-run       # 不打开浏览器,只检查队列和生成逻辑

队列文件 accounts.csv 列: email_prefix,first_name,last_name,birthdate,password,domain,status
  email_prefix 为空会自动生成,first_name/last_name/birthdate/password 为空也会自动补。
  status 为空 / pending 才会跑,success / failed / blocked 会跳过,断点续跑。
结果写到 results.csv,截图写到 screenshots/,日志写到 logs/
"""

import argparse
import csv
import json
import random
import re
import string
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.json"
ACCOUNTS_PATH = BASE / "accounts.csv"
RESULTS_PATH = BASE / "results.csv"
SCREENSHOT_DIR = BASE / "screenshots"
LOG_DIR = BASE / "logs"

SIGNUP_URL = "https://signup.live.com/signup"

# ---------- 随机资料池 ----------
FIRST_NAMES = [
    "Alex", "Chris", "Jordan", "Taylor", "Sam", "Jamie", "Casey", "Morgan",
    "Riley", "Avery", "Drew", "Robin", "Noah", "Liam", "Emma", "Olivia",
    "Ethan", "Mason", "Lucas", "James", "Henry", "Leo", "Jack", "Owen",
    "Sophia", "Mia", "Ella", "Grace", "Chloe", "Lily", "Zoe", "Nora",
]
LAST_NAMES = [
    "Ghost", "Smith", "Johnson", "Brown", "Wilson", "Taylor", "Lee", "Walker",
    "Hall", "Allen", "Young", "King", "Wright", "Scott", "Green", "Baker",
    "Adams", "Nelson", "Carter", "Mitchell", "Perez", "Roberts", "Turner",
    "Phillips", "Campbell", "Parker", "Evans", "Edwards", "Collins", "Stewart",
]
NAME_WORDS = [
    "ghost", "fox", "wolf", "hawk", "storm", "night", "shadow", "river",
    "cloud", "star", "moon", "wind", "fire", "ice", "nova", "echo", "apex",
    "blaze", "drift", "ember", "frost", "glade", "haven", "iron", "jade",
]

DEFAULT_CONFIG = {
    "domain": "outlook.com",
    "country": "US",
    "headless": False,
    "slow_mo_ms": 120,
    "min_rest_seconds_between_accounts": 60,
    "max_rest_seconds_between_accounts": 180,
    "verification_timeout_seconds": 600,
    "max_name_retries": 3,
    "proxy": "",
    "profile_dir": "./profile",
    "user_agent": "",
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[!] config.json 解析失败,用默认配置: {e}")
    return cfg


def log(msg: str):
    LOG_DIR.mkdir(exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_DIR / f"{date.today().isoformat()}.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def rand_delay(a=0.4, b=1.6):
    time.sleep(random.uniform(a, b))


def strong_password(length=12) -> str:
    """微软要求:至少 8 位,含大小写字母和数字,不能含邮箱名。"""
    while True:
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        pw = "".join(random.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and " " not in pw):
            return pw


def random_birthdate() -> str:
    start = date(1990, 1, 1)
    end = date(2005, 12, 31)
    d = start + timedelta(days=random.randint(0, (end - start).days))
    return d.strftime("%Y-%m-%d")


def random_email_prefix(seed: str = "") -> str:
    word = random.choice(NAME_WORDS)
    base = (seed or word).lower()
    base = re.sub(r"[^a-z0-9]", "", base)
    if not base:
        base = word
    style = random.randint(0, 3)
    num = random.randint(10, 9999)
    if style == 0:
        return f"{base}{num}"
    if style == 1:
        return f"{base}.{random.choice(NAME_WORDS)}{num}"
    if style == 2:
        return f"{base}{random.choice(NAME_WORDS)}{random.randint(2, 99)}"
    return f"{base}{random.randint(2000, 2026)}"


def make_profile(seed: str = "") -> dict:
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    return {
        "email_prefix": random_email_prefix(seed or first.lower()),
        "first_name": first,
        "last_name": last,
        "birthdate": random_birthdate(),
        "password": strong_password(),
        "domain": "outlook.com",
        "status": "pending",
    }


def read_accounts() -> list:
    if not ACCOUNTS_PATH.exists():
        return []
    with open(ACCOUNTS_PATH, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r.get("email_prefix") or r.get("first_name")]


def write_accounts(rows: list):
    fields = ["email_prefix", "first_name", "last_name", "birthdate", "password", "domain", "status"]
    with open(ACCOUNTS_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def append_result(row: dict, status: str, note: str = "", screenshot: str = ""):
    exists = RESULTS_PATH.exists()
    with open(RESULTS_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["time", "email", "first_name", "last_name", "birthdate", "password", "status", "note", "screenshot"])
        if not exists:
            w.writeheader()
        w.writerow({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "email": f"{row.get('email_prefix','')}@{row.get('domain','outlook.com')}",
            "first_name": row.get("first_name", ""),
            "last_name": row.get("last_name", ""),
            "birthdate": row.get("birthdate", ""),
            "password": row.get("password", ""),
            "status": status,
            "note": note,
            "screenshot": screenshot,
        })


def save_screenshot(page, name: str) -> str:
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    path = SCREENSHOT_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{name}.png"
    try:
        page.screenshot(path=str(path), full_page=False)
        return str(path)
    except Exception:
        return ""


# ---------- 浏览器:像真人一样操作 ----------
def human_type(page, locator, text: str):
    """逐字打字,每个字随机停顿,偶尔停顿长一点,像真人在想。"""
    locator.click()
    rand_delay(0.2, 0.6)
    for ch in text:
        locator.type(ch, delay=random.randint(45, 170))
        if random.random() < 0.08:
            time.sleep(random.uniform(0.3, 0.9))


def random_mouse(page):
    try:
        page.mouse.move(random.randint(100, 900), random.randint(100, 600), steps=random.randint(3, 10))
    except Exception:
        pass


def first_visible(page, candidates):
    """微软页面经常改版:按多个定位方式依次找,找到第一个可见的。"""
    for loc in candidates:
        try:
            if loc.count() > 0 and loc.first.is_visible():
                return loc.first
        except Exception:
            continue
    return None


def click_next(page):
    candidates = [
        page.get_by_role("button", name=re.compile(r"下一步|Next", re.I)),
        page.locator("input[type='submit']"),
        page.locator("button[type='submit']"),
        page.get_by_text(re.compile(r"^下一步$|^Next$", re.I)),
    ]
    btn = first_visible(page, candidates)
    if btn:
        random_mouse(page)
        rand_delay(0.3, 0.9)
        btn.click()
        return True
    return False


def page_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ""


def is_blocked(text: str) -> bool:
    keys = ["异常活动", "无法创建你的帐户", "无法创建你的账户", "此时无法创建",
            "unusual activity", "can't create your account", "cannot create",
            "暂时无法", "请稍后再试", "try again later"]
    low = text.lower()
    return any(k.lower() in low for k in keys)


def is_success(page) -> bool:
    url = page.url.lower()
    text = page_text(page)
    if "outlook.live.com/mail" in url or "outlook.live.com/owa" in url:
        return True
    if "account.microsoft.com" in url and "欢迎" in text:
        return True
    if re.search(r"欢迎使用|Welcome to Outlook|收件箱|Inbox", text):
        return True
    return False


def wait_for_human_verification(page, cfg, email: str) -> str:
    """
    核心停顿点:人机验证 / 短信 / 邮箱验证,必须人工完成。
    脚本每 10 秒检查一次是否已进入收件箱 / 账号页,
    超时 10 分钟(可在 config.json 改)后让用户在终端按回车决定。
    返回: success / blocked / manual
    """
    timeout = int(cfg.get("verification_timeout_seconds", 600))
    print("\n" + "=" * 60)
    print(f"  停下来等你: {email}")
    print("  现在浏览器里如果弹出了人机验证 / 验证码,请你手动完成。")
    print("  完成后不用关浏览器,回到这里按回车,我再继续检查。")
    print(f"  我也会自动等 {timeout // 60} 分钟,看你是否已进入收件箱。")
    print("=" * 60 + "\n", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(10)
        if is_success(page):
            return "success"
        text = page_text(page)
        if is_blocked(text):
            return "blocked"
    print("已等满超时时间,请按回车继续检查一次(Enter=继续,输入 q=跳过这个号): ", end="", flush=True)
    ans = input().strip().lower()
    if ans == "q":
        return "manual"
    if is_success(page):
        return "success"
    if is_blocked(page_text(page)):
        return "blocked"
    return "manual"


def register_one(page, cfg, row: dict) -> tuple:
    """注册一个号,返回 (status, note)。status: success/failed/blocked/manual"""
    domain = row.get("domain") or cfg.get("domain", "outlook.com")
    email = f"{row['email_prefix']}@{domain}"
    log(f"开始注册: {email}  {row.get('first_name','')} {row.get('last_name','')} 生日 {row.get('birthdate','')}")

    for attempt in range(int(cfg.get("max_name_retries", 3))):
        page.goto(SIGNUP_URL, wait_until="domcontentloaded")
        rand_delay(1.5, 3.0)
        random_mouse(page)

        # 第 1 步:新邮箱名
        email_box = first_visible(page, [
            page.get_by_label(re.compile(r"新电子邮件|New email|电子邮件", re.I)),
            page.locator("input[name='MemberName'], input[name='loginfmt'], input[type='email']"),
            page.locator("input[placeholder*='outlook'], input[placeholder*='example']"),
            page.locator("input[type='text']").first,
        ])
        if not email_box:
            shot = save_screenshot(page, "no_email_box")
            return "failed", f"没找到邮箱输入框,页面可能改版了,截图 {shot}"
        human_type(page, email_box, row["email_prefix"])
        rand_delay(0.5, 1.2)

        # 域名下拉:默认 outlook.com,一般不用动;如果页面有下拉且不是目标域名才点
        try:
            domain_sel = page.locator("select").first
            if domain_sel.count() > 0 and domain_sel.is_visible():
                domain_sel.select_option(label=domain)
        except Exception:
            pass

        if not click_next(page):
            return "failed", "没找到下一步按钮"
        rand_delay(1.5, 3.0)

        text = page_text(page)
        if "已被使用" in text or "already taken" in text.lower() or "不可用" in text:
            log(f"  邮箱名已被占用,换一个重试 ({attempt + 1}/3)")
            row["email_prefix"] = random_email_prefix(row.get("first_name", ""))
            email = f"{row['email_prefix']}@{domain}"
            continue
        if is_blocked(text):
            shot = save_screenshot(page, "blocked_step1")
            return "blocked", f"微软提示异常活动/无法创建,截图 {shot}"
        break
    else:
        return "failed", "邮箱名连续 3 次被占用,换个词根再试"

    # 第 2 步:密码
    pw_box = first_visible(page, [
        page.get_by_label(re.compile(r"创建密码|密码", re.I)),
        page.locator("input[name='Password'], input[type='password']"),
    ])
    if pw_box:
        human_type(page, pw_box, row["password"])
        rand_delay(0.5, 1.0)
        click_next(page)
        rand_delay(1.5, 3.0)
    else:
        log("  没找到密码框,可能已跳到下一步,直接继续检查")

    # 第 3 步:姓名
    first_box = first_visible(page, [
        page.get_by_label(re.compile(r"名|First name", re.I)),
        page.locator("input[name='FirstName']"),
    ])
    last_box = first_visible(page, [
        page.get_by_label(re.compile(r"姓|Last name", re.I)),
        page.locator("input[name='LastName']"),
    ])
    if first_box and last_box:
        human_type(page, first_box, row["first_name"])
        human_type(page, last_box, row["last_name"])
        rand_delay(0.5, 1.0)
        click_next(page)
        rand_delay(1.5, 3.0)

    # 第 4 步:国家 / 生日
    try:
        country_sel = page.locator("select[name='Country'], select").first
        if country_sel.count() > 0 and country_sel.is_visible():
            try:
                country_sel.select_option(value=cfg.get("country", "US"))
            except Exception:
                pass
        # 生日三个下拉或一个日期框,尽量按常见方式填
        for sel_name, val in [("BirthMonth", row["birthdate"][5:7].lstrip("0")),
                              ("BirthDay", row["birthdate"][8:10].lstrip("0")),
                              ("BirthYear", row["birthdate"][0:4])]:
            sel = page.locator(f"select[name='{sel_name}']")
            if sel.count() > 0 and sel.is_visible():
                try:
                    sel.select_option(label=val)
                except Exception:
                    try:
                        sel.select_option(value=val)
                    except Exception:
                        pass
        date_input = page.locator("input[type='date']")
        if date_input.count() > 0 and date_input.first.is_visible():
            date_input.first.fill(row["birthdate"])
        click_next(page)
        rand_delay(1.5, 3.0)
    except Exception as e:
        log(f"  生日步骤异常,继续: {e}")

    # 第 5 步:人机验证 / 验证码 —— 停下来等人工
    if is_success(page):
        return "success", "直接进入收件箱,无验证"
    text = page_text(page)
    if is_blocked(text):
        shot = save_screenshot(page, "blocked_final")
        return "blocked", f"微软拒绝创建,截图 {shot}"

    result = wait_for_human_verification(page, cfg, email)
    if result == "success":
        return "success", "人工验证通过,进入收件箱"
    if result == "blocked":
        shot = save_screenshot(page, "blocked_verify")
        return "blocked", f"验证后仍被拒绝,截图 {shot}"
    shot = save_screenshot(page, "manual_check")
    return "manual", f"超时/手动检查,未确认成功,截图 {shot}"


def run_browser(cfg, rows, limit):
    from playwright.sync_api import sync_playwright

    pending = [r for r in rows if (r.get("status") or "pending").lower() in ("", "pending")]
    if limit:
        pending = pending[:limit]
    if not pending:
        log("队列里没有待注册的账号,先用 --generate 生成,或把 accounts.csv 里 status 清空。")
        return

    log(f"待注册 {len(pending)} 个,真实浏览器模式,一个一个来。")
    with sync_playwright() as p:
        launch_kwargs = {
            "headless": bool(cfg.get("headless", False)),
            "slow_mo": int(cfg.get("slow_mo_ms", 120)),
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run", "--no-default-browser-check",
            ],
        }
        if cfg.get("proxy"):
            launch_kwargs["proxy"] = {"server": cfg["proxy"]}
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(BASE / cfg.get("profile_dir", "./profile")),
            viewport={"width": random.randint(1280, 1440), "height": random.randint(800, 900)},
            user_agent=cfg.get("user_agent") or None,
            locale="en-US",
            timezone_id="America/Los_Angeles",
            **launch_kwargs,
        )
        # 反自动化指纹:去掉 webdriver 标记
        browser.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            "window.chrome = window.chrome || {runtime: {}};"
        )
        page = browser.new_page() if len(browser.pages) == 0 else browser.pages[0]

        done = 0
        for idx, row in enumerate(pending):
            # 空字段自动补全
            if not row.get("email_prefix"):
                row["email_prefix"] = random_email_prefix()
            if not row.get("first_name"):
                prof = make_profile()
                row.update({k: prof[k] for k in ("first_name", "last_name", "birthdate", "password") if not row.get(k)})
            if not row.get("password"):
                row["password"] = strong_password()
            if not row.get("birthdate"):
                row["birthdate"] = random_birthdate()
            if not row.get("domain"):
                row["domain"] = cfg.get("domain", "outlook.com")

            try:
                status, note = register_one(page, cfg, row)
            except Exception as e:
                status, note = "failed", f"脚本异常: {e}"
                try:
                    note += f" 截图 {save_screenshot(page, 'exception')}"
                except Exception:
                    pass
            log(f"结果: {row['email_prefix']}@{row.get('domain')} -> {status} | {note}")
            append_result(row, status, note)
            # 回写 accounts.csv 状态,断点续跑
            row["status"] = status
            write_accounts(rows)
            done += 1

            if idx + 1 < len(pending):
                rest = random.randint(
                    int(cfg.get("min_rest_seconds_between_accounts", 60)),
                    int(cfg.get("max_rest_seconds_between_accounts", 180)),
                )
                log(f"休息 {rest} 秒再注册下一个(防批量风控,不要关浏览器)…")
                time.sleep(rest)
        browser.close()
        log(f"本次完成 {done} 个,结果见 results.csv")


def main():
    ap = argparse.ArgumentParser(description="Outlook 注册机 v2.0")
    ap.add_argument("--limit", type=int, default=0, help="只注册前 N 个")
    ap.add_argument("--generate", type=int, default=0, help="只生成 N 个账号到 accounts.csv,不打开浏览器")
    ap.add_argument("--seed", default="", help="生成邮箱名的词根,例如 ghost")
    ap.add_argument("--dry-run", action="store_true", help="不打开浏览器,只检查队列")
    args = ap.parse_args()

    cfg = load_config()
    rows = read_accounts()

    if args.generate:
        new_rows = [make_profile(args.seed) for _ in range(args.generate)]
        # 补域名
        for r in new_rows:
            r["domain"] = cfg.get("domain", "outlook.com")
        rows.extend(new_rows)
        write_accounts(rows)
        log(f"已生成 {args.generate} 个账号写入 accounts.csv:")
        for r in new_rows:
            log(f"  {r['email_prefix']}@{r['domain']}  {r['first_name']} {r['last_name']}  {r['birthdate']}  密码:{r['password']}")
        log("检查无误后运行 python outlook_registrator.py 开始注册。密码请自己保管,不要发给别人。")
        return

    if args.dry_run:
        log(f"队列共 {len(rows)} 个,待注册 {len([r for r in rows if (r.get('status') or 'pending') in ('', 'pending')])} 个")
        for r in rows:
            log(f"  {r.get('email_prefix')}@{r.get('domain','outlook.com')}  status={r.get('status','pending')}")
        return

    if not rows:
        log("accounts.csv 是空的,先生成: python outlook_registrator.py --generate 5 --seed ghost")
        return

    run_browser(cfg, rows, args.limit)


if __name__ == "__main__":
    main()
