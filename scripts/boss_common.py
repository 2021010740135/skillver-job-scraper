#!/usr/bin/env python3
"""Shared BOSS CDP runtime: Chrome, login, city, list/detail helpers.

CLIs: chrome_cdp.py, scrape_list.py, scrape_details.py.
Cleaning: clean_classify_input.py, clean_details.py.
Export: export_skillver_csv.py.
"""

__version__ = "1.0.0"

import json
import time
import random
import sys
import os
import re
import hashlib
import glob
import platform
import subprocess
import shutil
import signal
import logging
import ntpath
import importlib.util
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl
from urllib.request import Request, urlopen

websocket = None
requests = None

try:
    from scripts import job_schema
except ImportError:
    import job_schema  # noqa: F401


def configure_stdio_utf8():
    """Avoid UnicodeEncodeError when printing emoji on Windows GBK consoles."""
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError, AttributeError):
            try:
                reconfigure(errors="replace")
            except (OSError, ValueError, AttributeError):
                pass


configure_stdio_utf8()

# ============================================================
# 全局常量
# ============================================================

# CDP 默认端口（可通过 --cdp-port 覆盖）
DEFAULT_CDP_PORT = 9222

# API 基础路径（便于统一修改）
API_JOB_LIST_PATH = "/wapi/zpgeek/search/joblist.json"
HOT_CITY_URL = "https://www.zhipin.com/wapi/zpgeek/search/job/hot/city.json"
CITY_GROUP_URL = "https://www.zhipin.com/wapi/zpCommon/data/cityGroup.json"

# 请求频率保护
MAX_PAGES = 10          # 单次最大页数
MAX_API_REQUESTS = 500  # 单次最大 API 请求数
MAX_BATCH_KEYWORDS = 8  # 单批最多岗位关键词（批间休息由人工控制）
# 批内岗间等待（秒）：默认 8–15 分钟随机
DEFAULT_POSITION_GAP_SEC = (480, 900)
_ENCRYPT_JOB_ID_IN_LINK_RE = re.compile(r"/job_detail/([^./]+)\.html", re.IGNORECASE)

# Skillver：最低详情数 / 页批 / 搜索预算（归类由 Agent 决策文件完成）
DEFAULT_SKILLVER_MIN_DETAILS = 5
DEFAULT_SKILLVER_MAX_MIN_DETAILS = 50
DEFAULT_SKILLVER_MAX_DETAILS = 5  # deprecated alias of min-details
DEFAULT_SKILLVER_PAGE_BATCH_SIZE = 1
DEFAULT_SKILLVER_MAX_PAGES = 8  # unused as a flip cap; kept for older callers
MULTI_SELECT_FILTER_KEYS = ("experience", "scale")
_ANON_COMPANY_RE = re.compile(r"^(某.+|匿名.*|保密.*)$")
_ILLEGAL_DIRNAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

def get_default_chrome_path():
    system = platform.system()
    if system == "Darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if system == "Windows":
        candidates = []
        local_app_data = os.environ.get("LOCALAPPDATA")
        program_roots = []
        for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
            base = os.environ.get(env_name)
            if base:
                program_roots.append(base)
        if local_app_data:
            candidates.append(ntpath.join(local_app_data, "Microsoft", "Edge", "Application", "msedge.exe"))
        for base in program_roots:
            candidates.append(ntpath.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
        if local_app_data:
            candidates.append(ntpath.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe"))
        for base in program_roots:
            candidates.append(ntpath.join(base, "Google", "Chrome", "Application", "chrome.exe"))
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        return candidates[0] if candidates else "msedge.exe"

    candidates = [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/snap/bin/chromium",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[0]


def get_default_profile_dir():
    system = platform.system()
    if system == "Darwin":
        return os.path.expanduser("~/Library/Application Support/Google/Chrome")
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = ntpath.join(os.path.expanduser("~"), "AppData", "Local")
        edge = ntpath.join(base, "Microsoft", "Edge", "User Data")
        chrome = ntpath.join(base, "Google", "Chrome", "User Data")
        if os.path.exists(edge):
            return edge
        if os.path.exists(chrome):
            return chrome
        return edge
    return os.path.expanduser("~/.config/google-chrome")


DEFAULT_CHROME_PATH = get_default_chrome_path()
DEFAULT_PROFILE_DIR = get_default_profile_dir()

DEFAULT_CDP_DATA_DIR = os.path.expanduser("~/.boss-zhipin-scraper/chrome-profile")
DEFAULT_DATA_DIR = "data"
DEFAULT_CITY_INPUT = "上海"

# Skillver 标准岗主路径（P4）；legacy raw/batches / keywords-file 已退出主路径
DEFAULT_SKILLVER_CATALOG = os.path.join("data", "position_catalog.json")
DEFAULT_SKILLVER_SEEN = os.path.join("data", "seen_jobs.json")
DEFAULT_SKILLVER_UNEXPORTED = os.path.join("data", "unexported_details.json")
LOGIN_PROBE_QUERY = "Java"
LOGIN_PROBE_CITY = "101020100"
LOGIN_PROBE_TARGETS = (
    ("Java", "101020100"),
    ("AI Agent", "101010100"),
    ("产品经理", "101280600"),
)
LOGIN_PROBE_PAGE_SIZE = 10
LOGIN_PROBE_MAX_INTERVAL = 15
LOGIN_PROBE_MAX_TRANSIENT_ERRORS = 2
LOGIN_RESTRICTED_CODES = {31, 37}
# BOSS 风控码会随平台策略变化，码表追不上时按 message 关键字兜底识别风控/限流，
# 避免把「已登录但被风控」误判为 RESPONSE_ERROR 进而当成登录失败。
LOGIN_RESTRICTED_MESSAGE_KEYWORDS = (
    "环境存在异常",
    "访问频繁",
    "操作太频繁",
    "安全校验",
    "滑块",
    "验证",
)
DEFAULT_LOGIN_TIMEOUT = 300

# 全局请求计数器
_request_counter = 0
_live_city_maps_cache = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("boss_cdp")


def search_term_dirname(term):
    cleaned = _ILLEGAL_DIRNAME_RE.sub("_", str(term or "").strip())
    cleaned = cleaned.strip(" .")
    return cleaned or "search"


def search_term_dir(term):
    return os.path.join(DEFAULT_DATA_DIR, search_term_dirname(term))


def default_output_path(kind, keyword=None):
    """Default scrape JSON: data/<搜索词>/jobs.json or details.json."""
    name = "jobs.json" if kind == "jobs" else "details.json" if kind == "details" else f"{kind}.json"
    return os.path.join(search_term_dir(keyword), name)


def require_runtime_dependencies(*names):
    global requests, websocket

    missing = []
    if "requests" in names and requests is None:
        try:
            import requests as requests_module
            requests = requests_module
        except ImportError:
            missing.append("requests")
    if "websocket" in names and websocket is None:
        try:
            import websocket as websocket_module
            websocket = websocket_module
        except ImportError:
            missing.append("websocket-client")
    if missing:
        print(f"缺少依赖: {' '.join(missing)}")
        print("请运行: python scripts/chrome_cdp.py --check")
        print("（会安装 uv 并 uv sync 到本 skill 的 .venv，勿 pip 进系统 Python）")
        return False
    return True


def _load_ensure_uv_env():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ensure_uv_env.py")
    spec = importlib.util.spec_from_file_location("ensure_uv_env", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ensure_skill_env(*, reexec_if_needed: bool = True) -> bool:
    """Delegate to stdlib-only bootstrap so --check works before deps exist."""
    mod = _load_ensure_uv_env()
    if mod is None:
        print("❌ 找不到 scripts/ensure_uv_env.py")
        return False
    return bool(mod.ensure_skill_env(reexec_if_needed=reexec_if_needed))


# ============================================================
# 筛选参数映射
# Source snapshots:
# - 城市: https://www.zhipin.com/wapi/zpgeek/search/job/hot/city.json + cityGroup.json
# - 筛选项: https://www.zhipin.com/wapi/zpgeek/search/job/condition.json
# ============================================================
# 城市码表已外置到 data/city_codes.json（全量城市，覆盖一二三四五线），
# 见 issue #24。resolve_city 查询链：本地静态 → 运行时拉 BOSS 接口 → 9 位裸码兜底。
# 仓库内路径（开发态）与打包后路径（pip install）都在 _city_data_path() 里处理。
CITY_DATA_FILENAME = "city_codes.json"

_local_city_map_cache = None


def _city_data_path():
    """返回 data/city_codes.json 的路径，兼容仓库开发态与 pip 打包态。"""
    # 1. 仓库开发态：脚本在 scripts/，数据在 ../data/
    repo_data = os.path.join(os.path.dirname(__file__), "..", "data", CITY_DATA_FILENAME)
    if os.path.isfile(repo_data):
        return os.path.normpath(repo_data)
    # 2. 打包态：wheel force-include 到包根 data/，用 importlib.resources 兜底
    try:
        from importlib.resources import files  # py3.9+
        pkg_data = files(__package__ or "__main__").joinpath("..", "data", CITY_DATA_FILENAME) \
            if __package__ else None
    except Exception:
        pkg_data = None
    if pkg_data is not None and os.path.isfile(str(pkg_data)):
        return str(pkg_data)
    # 3. 找不到则返回开发态路径（让调用方决定降级）
    return os.path.normpath(repo_data)


def load_local_city_map():
    """读取本地 data/city_codes.json 静态全量城市码表。

    返回 (name_to_code, code_to_name) 两个字典；读取失败返回 ({}, {})。
    结果缓存，重复调用零开销。
    """
    global _local_city_map_cache
    if _local_city_map_cache is not None:
        return _local_city_map_cache
    name_to_code = {}
    try:
        path = _city_data_path()
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for name, code in raw.items():
                if name and code is not None:
                    name_to_code[str(name)] = str(code)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        log.debug(f"读取本地城市码表失败: {e}")
    code_to_name = {code: name for name, code in name_to_code.items()}
    _local_city_map_cache = name_to_code, code_to_name
    return _local_city_map_cache

SCALE_MAP = {
    "0-20人": "301", "20-99人": "302", "100-499人": "303",
    "500-999人": "304", "1000-9999人": "305", "10000人以上": "306",
}

STAGE_MAP = {
    "未融资": "801", "天使轮": "802", "A轮": "803", "B轮": "804",
    "C轮": "805", "D轮及以上": "806", "已上市": "807", "不需要融资": "808",
}

SALARY_MAP = {
    "不限": "0", "3K以下": "402", "3-5K": "403", "5-10K": "404",
    "10-20K": "405", "20-50K": "406", "50K以上": "407",
}

EXPERIENCE_MAP = {
    "不限": "0", "在校生": "108", "应届生": "102", "经验不限": "101",
    "1年以内": "103", "1-3年": "104",
    "3-5年": "105", "5-10年": "106", "10年以上": "107",
}

DEGREE_MAP = {
    "不限": "0", "初中及以下": "209", "中专/中技": "208", "高中": "206",
    "大专": "202", "本科": "203", "硕士": "204", "博士": "205",
}

INDUSTRY_MAP = {
    "互联网": "1001", "电子商务": "1002", "金融": "1003", "游戏": "1004",
    "企业服务": "1005", "教育培训": "1006", "社交网络": "1007",
    "医疗健康": "1008", "生活服务": "1009", "广告营销": "1010",
}

JOB_TYPE_MAP = {
    "不限": "0",
    "全职": "1901",
    "实习": "1902",
    "兼职": "1903",
}


# ============================================================
# 全局请求计数器辅助
# ============================================================
def incr_request():
    """递增全局请求计数，达到上限时抛出异常"""
    global _request_counter
    _request_counter += 1
    if _request_counter > MAX_API_REQUESTS:
        raise RuntimeError(f"已达到单次最大请求数 {MAX_API_REQUESTS}，停止抓取")
    if _request_counter >= MAX_API_REQUESTS * 0.8:
        log.warning(f"⚠️ 请求次数接近上限: {_request_counter}/{MAX_API_REQUESTS}")


# ============================================================
# CDP 连接
# ============================================================
class CDPSession:
    def __init__(self, cdp_port=DEFAULT_CDP_PORT):
        if not require_runtime_dependencies("requests", "websocket"):
            raise RuntimeError("缺少 CDP 运行依赖")
        self.cdp_port = cdp_port
        resp = requests.get(f"http://127.0.0.1:{cdp_port}/json/version", timeout=10)
        ws_url = resp.json()["webSocketDebuggerUrl"]
        self.ws = websocket.create_connection(ws_url, timeout=60)
        self.mid = 0

    def send(self, method, params=None, sid=None, timeout=30):
        """发送 CDP 命令并等待匹配的响应。

        Args:
            method: CDP 方法名
            params: 参数字典
            sid: Target session ID
            timeout: 等待响应的超时秒数，默认 30s

        Returns:
            CDP 响应字典

        Raises:
            TimeoutError: 超过 max_retries 仍未收到匹配响应
        """
        self.mid += 1
        msg = {"id": self.mid, "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        self.ws.send(json.dumps(msg))

        start_time = time.time()
        max_retries = 1000

        for attempt in range(max_retries):
            # 检查超时
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise TimeoutError(
                    f"CDP send({method}) 超时 ({timeout}s), "
                    f"已跳过 {attempt} 条不匹配消息"
                )

            try:
                raw = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                raise TimeoutError(f"CDP WebSocket recv 超时, method={method}")

            try:
                r = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                log.debug(f"跳过非 JSON 消息: {raw[:100]}")
                continue

            if r.get("id") == self.mid:
                return r

            # 不匹配的消息：可能是事件通知，记录并跳过
            event_name = r.get("method", "unknown")
            log.debug(f"跳过不匹配消息 (id={r.get('id')}, event={event_name})")

        raise TimeoutError(
            f"CDP send({method}) 在 {max_retries} 条消息内未找到匹配响应"
        )

    def eval_js(self, js, sid):
        r = self.send("Runtime.evaluate", {"expression": js, "returnByValue": True}, sid)
        return r.get("result", {}).get("result", {}).get("value", None)

    def close(self):
        self.ws.close()


BACKGROUND_VISIBILITY_SCRIPT = (
    "Object.defineProperty(document, 'hidden', {get: () => false});"
    "Object.defineProperty(document, 'visibilityState', {get: () => 'visible'});"
    "Object.defineProperty(document, 'webkitHidden', {get: () => false});"
    "Object.defineProperty(document, 'webkitVisibilityState', {get: () => 'visible'});"
)


def human_scroll(cdp, sid):
    """模拟人类滚动: 随机次数、随机距离、随机停顿，偶尔回滚一点"""
    total_scrolls = random.randint(3, 6)
    for i in range(total_scrolls):
        # 大部分往下滚，偶尔往上回滚一点（模拟阅读回看）
        if random.random() < 0.15:
            delta = -random.randint(50, 150)
        else:
            delta = random.randint(150, 500)
        cdp.eval_js(f"window.scrollBy(0,{delta})", sid)
        # 滚动间隔随机：有时快速连续滚，有时停下来"看"
        if random.random() < 0.3:
            time.sleep(random.uniform(2.0, 4.0))
        else:
            time.sleep(random.uniform(0.5, 1.5))


def human_mouse_jitter(cdp, sid):
    """偶尔移动鼠标位置，模拟人在页面上活动"""
    if random.random() < 0.4:
        x = random.randint(100, 800)
        y = random.randint(100, 600)
        cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": x, "y": y
        }, sid)


def create_page_session(cdp, background=True):
    """Create and attach an about:blank target without stealing focus by default.

    Background pages report themselves as hidden, which prevents BOSS detail
    pages from rendering reliably. Register the existing visibility override
    before callers navigate. Interactive callers such as the login flow must
    opt into a foreground target explicitly.
    """
    target = cdp.send(
        "Target.createTarget",
        {"url": "about:blank", "background": background},
    )
    target_id = target["result"]["targetId"]
    attached = cdp.send(
        "Target.attachToTarget",
        {"targetId": target_id, "flatten": True},
    )
    session_id = attached["result"]["sessionId"]
    if background:
        cdp.send(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": BACKGROUND_VISIBILITY_SCRIPT},
            session_id,
        )
    return target_id, session_id


# ============================================================
# 通过页面内 XHR 调 API 获取列表数据（明文薪资）
# ============================================================
FETCH_API_JS_TEMPLATE = """
(function(){
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '__API_URL__', false);
    xhr.send();
    if (xhr.status !== 200) return JSON.stringify({error: xhr.status, jobs: []});
    var data = JSON.parse(xhr.responseText);
    var jobs = (data.zpData || {}).jobList || [];
    var results = jobs.map(function(j) {
        return {
            title: j.jobName || '',
            salary: j.salaryDesc || '',
            location: (j.cityName || '') + '\\u00b7' + (j.areaDistrict || '') + '\\u00b7' + (j.businessDistrict || ''),
            tags: [j.jobExperience || '', j.jobDegree || ''].filter(function(t){return t && t !== '\\u4e0d\\u9650';}).join(' | '),
            boss_name: j.brandName || '',
            boss_title: j.bossTitle || '',
            security_id: j.securityId || '',
            lid: j.lid || '',
            encrypt_job_id: j.encryptJobId || '',
            job_link: j.encryptJobId ? 'https://www.zhipin.com/job_detail/' + j.encryptJobId + '.html' : ''
        };
    });
    return JSON.stringify({
        code: data.code,
        message: data.message || '',
        jobs: results
    });
})()
"""

# ============================================================
# DEPRECATED: DOM 提取作为 fallback（薪资可能是加密字体）
# 此方法已弃用，仅作为 API 方式失败时的最后降级手段。
# 新代码应优先使用 FETCH_API_JS_TEMPLATE 通过 API 获取数据。
# ============================================================
EXTRACT_LIST_JS = """
(function(){
    var results = [];
    var cards = document.querySelectorAll('li.job-card-box');
    for (var i = 0; i < cards.length; i++) {
        var card = cards[i];
        var nameEl = card.querySelector('.job-name');
        var salaryEl = card.querySelector('.job-salary');
        var locEl = card.querySelector('.company-location');
        var tagEls = card.querySelectorAll('.tag-list li');
        var bossEl = card.querySelector('.boss-name');
        var bossLink = card.querySelector('.boss-info');
        var tags = [];
        for (var j = 0; j < tagEls.length; j++) tags.push(tagEls[j].innerText.trim());
        var jobLink = nameEl ? (nameEl.getAttribute('href') || '') : '';
        if (jobLink && jobLink.charAt(0) === '/') jobLink = 'https://www.zhipin.com' + jobLink;
        var cLink = bossLink ? (bossLink.getAttribute('href') || '') : '';
        if (cLink && cLink.charAt(0) === '/') cLink = 'https://www.zhipin.com' + cLink;
        var t = nameEl ? nameEl.innerText.trim() : '';
        if (t) results.push({
            title: t,
            salary: salaryEl ? salaryEl.innerText.trim() : '',
            salary_source: 'dom_untrusted',
            location: locEl ? locEl.innerText.trim() : '',
            tags: tags.join(' | '),
            boss_name: bossEl ? bossEl.innerText.trim() : '',
            job_link: jobLink,
            company_link: cLink
        });
    }
    return JSON.stringify(results);
})()
"""

# ============================================================
# 详情页提取与校验
# ============================================================
DETAIL_LOGIN_MARKER = "登录查看完整内容"
DETAIL_DESCRIPTION_MARKER = "职位描述"
DETAIL_COMPETITIVENESS_MARKER = "竞争力分析"
DETAIL_SAFETY_MARKER = "BOSS 安全提示"
MIN_DETAIL_TEXT_LENGTH = 120


class DetailExtractionError(ValueError):
    """The rendered page does not contain a usable job description."""


class DetailLoginRequiredError(DetailExtractionError):
    """The detail page is truncated because the BOSS session is not logged in."""


EXTRACT_DETAIL_JS = """
(function(){
    var pageText = document.body ? document.body.innerText : '';
    var tags = [];
    var benefitWords = ['五险','补充医疗','定期体检','带薪年假','年终奖','零食','餐补',
        '节日福利','加班补助','股票期权','员工旅游','交通补助','通讯补贴','团建',
        '生日福利','免费班车','全勤奖','包吃','弹性工作','下午茶','租房补贴',
        '体检','健身','文化','充电假','司龄假','红包','能量补贴','社团','三薪',
        '绩效','底薪','保底','活动基金','学习基金','节日礼品','无障碍'];
    var noiseWords = ['BOSS直聘','boss','BOSS','来自BOSS直聘','金','金币'];
    function isBenefit(t) {
        if (t === '...' || t.length > 15 || t.length < 2) return true;
        for (var i = 0; i < benefitWords.length; i++) {
            if (t.includes(benefitWords[i])) return true;
        }
        for (var i = 0; i < noiseWords.length; i++) {
            if (t === noiseWords[i] || t.includes(noiseWords[i])) return true;
        }
        return false;
    }
    document.querySelectorAll('.job-tags .tag-all span, .job-keyword-list span').forEach(function(s){
        var t = s.innerText.trim();
        if(t && !isBenefit(t)) tags.push(t);
    });
    var jd = '';
    var sections = document.querySelectorAll('.job-detail-section, .job-sec');
    for (var i = 0; i < sections.length; i++) {
        var text = (sections[i].innerText || '').trim();
        if (text.indexOf('职位描述') !== -1 && text.length > jd.length) {
            jd = text;
        }
    }
    var locationText = '';
    var locSelectors = [
        '.job-location .location-address',
        '.job-location',
        '.location-address',
        '.job-address',
        '.job-area'
    ];
    for (var li = 0; li < locSelectors.length; li++) {
        var locEl = document.querySelector(locSelectors[li]);
        if (!locEl) continue;
        var locRaw = (locEl.innerText || '').replace(/\\s+/g, ' ').trim();
        if (!locRaw) continue;
        locationText = locRaw;
        if (locRaw.indexOf('\\u00b7') !== -1 || locRaw.indexOf('·') !== -1) break;
    }
    return JSON.stringify({
        jd: jd,
        page_text: pageText.substring(0, 12000),
        tags: tags,
        location: locationText,
        url: location.href
    });
})()
"""


def _normalize_detail_whitespace(text):
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").splitlines()]
    normalized = "\n".join(lines).strip()
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return re.sub(r"[ \t]{2,}", " ", normalized)


def _looks_like_navigation_page(text):
    return (
        DETAIL_DESCRIPTION_MARKER not in text
        and "无障碍专区" in text
        and "首页" in text
        and "职位" in text
        and "公司" in text
    )


def _is_boss_activity_line(text):
    """True for recruiter activity labels like「在线」「今日活跃」."""
    return text == "在线" or text.endswith("活跃")


def map_list_boss_active_status(job):
    """Map list-API job fields to ``boss_active_status``.

    BOSS ``/wapi/zpgeek/search/joblist.json`` typically exposes ``bossOnline``
    but not ``activeTimeDesc``. Prefer ``activeTimeDesc`` when present;
    otherwise map ``bossOnline=True`` to 「在线」. Detailed labels such as
    「刚刚活跃」still come from the detail path.
    """
    if not isinstance(job, dict):
        return ""
    desc = str(job.get("activeTimeDesc") or "").strip()
    if desc:
        return desc
    if job.get("bossOnline"):
        return "在线"
    return ""


def resolve_boss_active_status(list_status="", detail_status=""):
    """Prefer detail activity text; fall back to list mapping result."""
    detail = str(detail_status or "").strip()
    if detail:
        return detail
    return str(list_status or "").strip()


def _recruiter_footer_info(lines):
    """Locate recruiter card footer and optional activity status.

    Returns ``(footer_start, boss_active_status)``. ``footer_start`` is the
    line index where the recruiter card begins (to truncate JD), or ``None``.
    ``boss_active_status`` is e.g. ``今日活跃`` / ``在线``, or ``""``.
    """
    stripped_lines = [line.strip() for line in lines]
    end = len(stripped_lines)
    while end and not stripped_lines[end - 1]:
        end -= 1

    def card_info(card_end):
        while card_end and not stripped_lines[card_end - 1]:
            card_end -= 1
        if card_end < 4 or stripped_lines[card_end - 2] != "·":
            return None, ""
        activity_or_name = stripped_lines[card_end - 4]
        has_activity_line = _is_boss_activity_line(activity_or_name)
        if has_activity_line:
            start = card_end - 5
            status = activity_or_name
        else:
            start = card_end - 4
            status = ""
        if start < 0:
            return None, ""
        return start, status

    for marker in (DETAIL_COMPETITIVENESS_MARKER, DETAIL_SAFETY_MARKER):
        try:
            marker_index = stripped_lines.index(marker)
        except ValueError:
            continue
        start, status = card_info(marker_index)
        if start is not None:
            return start, status
    return card_info(end)


def _recruiter_footer_start(lines):
    start, _status = _recruiter_footer_info(lines)
    return start


def normalize_location(location):
    """Collapse BOSS ``城市·区·商圈`` segments; drop empty ``·`` pieces."""
    text = str(location or "").strip()
    if not text:
        return ""
    parts = [p.strip() for p in text.replace("/", "·").split("·") if p.strip()]
    return "·".join(parts)


def resolve_detail_location(list_location="", detail_location="", city_fallback=""):
    """Prefer detail-page location, then list card, then CLI city name."""
    for candidate in (detail_location, list_location, city_fallback):
        normalized = normalize_location(candidate)
        if normalized:
            return normalized
    return ""


_LOCATION_LINE_RE = re.compile(
    r"^([\u4e00-\u9fffA-Za-z]{2,12}"
    r"(?:·[\u4e00-\u9fffA-Za-z0-9]{1,20}){1,3})$"
)


def _location_from_page_text(page_text):
    """Best-effort parse of ``城市·区`` lines near the top of detail page text."""
    for line in str(page_text or "").splitlines()[:40]:
        text = normalize_location(line.replace(" ", ""))
        if not text or "职位描述" in text or "登录" in text:
            continue
        if "·" not in text:
            continue
        if re.search(r"\d", text) or "K" in text.upper() or "薪" in text:
            continue
        if _LOCATION_LINE_RE.match(text):
            return text
    return ""


def extract_detail_fields(extracted, min_length=MIN_DETAIL_TEXT_LENGTH):
    """Return validated JD, boss activity status, and location as separate fields.

    ``jd`` never includes the recruiter card or activity label.
    ``boss_active_status`` is extracted from that card when present.
    ``location`` prefers DOM extractor output, then a conservative page_text parse.

    ``page_text`` is diagnostic input only. It is never persisted unless it has
    an explicit job-description section that passes all checks.
    """
    if not isinstance(extracted, dict):
        raise DetailExtractionError("detail extractor returned non-dict")

    raw_jd = str(extracted.get("jd") or "")
    page_text = str(extracted.get("page_text") or "")
    diagnostic_text = "\n".join((raw_jd, page_text))

    if DETAIL_LOGIN_MARKER in diagnostic_text:
        raise DetailLoginRequiredError(
            "detail page is truncated at the login wall; refresh the BOSS login session"
        )
    if _looks_like_navigation_page(diagnostic_text):
        raise DetailExtractionError("detail page rendered navigation chrome without a JD")

    text = raw_jd
    if not text and DETAIL_DESCRIPTION_MARKER in page_text:
        text = page_text
    if DETAIL_DESCRIPTION_MARKER in text:
        text = text.split(DETAIL_DESCRIPTION_MARKER, 1)[1]

    lines = text.replace("\r\n", "\n").splitlines()
    footer_start, boss_active_status = _recruiter_footer_info(lines)
    if footer_start is not None:
        lines = lines[:footer_start]
    else:
        for index, line in enumerate(lines):
            if line.strip() == DETAIL_SAFETY_MARKER:
                lines = lines[:index]
                break

    jd = _normalize_detail_whitespace("\n".join(lines))
    if len(jd) < min_length:
        raise DetailExtractionError(
            f"job description too short after validation: {len(jd)} < {min_length}"
        )
    location = normalize_location(extracted.get("location") or "")
    if not location:
        location = _location_from_page_text(page_text)
    return {
        "jd": jd,
        "boss_active_status": boss_active_status,
        "location": location,
    }


def extract_job_description(extracted, min_length=MIN_DETAIL_TEXT_LENGTH):
    """Return validated JD text without BOSS page chrome."""
    return extract_detail_fields(extracted, min_length=min_length)["jd"]


# ============================================================
# 解析城市参数（支持中文和代码）
# ============================================================
class CityAPIResponseError(ValueError):
    """BOSS 城市接口返回业务错误或无效响应。"""


class CityResolutionError(ValueError):
    """无法把用户输入解析为有效城市码。"""


def fetch_boss_json(url, timeout=10):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    if not isinstance(data, dict):
        raise CityAPIResponseError(f"BOSS 城市接口返回非对象响应: {url}")

    code = data.get("code")
    if code != 0:
        message = data.get("message") or "未知错误"
        raise CityAPIResponseError(
            f"BOSS 城市接口返回业务错误 code={code}, message={message}: {url}"
        )
    if not isinstance(data.get("zpData"), dict):
        raise CityAPIResponseError(f"BOSS 城市接口响应缺少有效 zpData: {url}")
    return data


def load_live_city_maps(timeout=10):
    global _live_city_maps_cache
    if _live_city_maps_cache is not None:
        return _live_city_maps_cache

    name_to_code = {}

    try:
        hot_city_data = fetch_boss_json(HOT_CITY_URL, timeout=timeout)
        for item in hot_city_data.get("zpData", {}).get("hotCityList", []):
            name = item.get("name")
            code = item.get("code")
            if name and code is not None:
                name_to_code[name] = str(code)

        city_group_data = fetch_boss_json(CITY_GROUP_URL, timeout=timeout)
        for group in city_group_data.get("zpData", {}).get("cityGroup", []):
            for item in group.get("cityList", []):
                name = item.get("name")
                code = item.get("code")
                if name and code is not None:
                    name_to_code.setdefault(name, str(code))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError,
            CityAPIResponseError) as e:
        log.warning(f"加载 BOSS 在线城市映射失败: {e}")

    code_to_name = {code: name for name, code in name_to_code.items()}
    _live_city_maps_cache = name_to_code, code_to_name
    return _live_city_maps_cache


def resolve_city(city_input):
    """把「中文城市名 / 城市码」解析为 (name, code)。

    查询链（逐级降级）:
      1. 本地静态码表 data/city_codes.json（全量、离线可用）
      2. 运行时拉 BOSS 接口 hot/city.json + cityGroup.json（自愈）
      3. 都查不到时接受 9 位裸 city code，其他输入报错
    """
    if not city_input:
        return city_input, city_input

    # 1. 本地静态码表
    local_map, local_reverse = load_local_city_map()
    if city_input in local_map:
        return city_input, local_map[city_input]
    if city_input in local_reverse:
        return local_reverse[city_input], city_input

    # 2. 运行时拉 BOSS 接口
    live_map, live_reverse = load_live_city_maps()
    if city_input in live_map:
        return city_input, live_map[city_input]
    if city_input in live_reverse:
        return live_reverse[city_input], city_input

    # 3. 仍未命中的 9 位纯数字视为用户直接传入的裸 city code
    if re.fullmatch(r"\d{9}", city_input):
        return city_input, city_input

    raise CityResolutionError(
        f"无法解析城市 '{city_input}'：本地城市码表和 BOSS 在线城市接口均未命中。"
        "请传入受支持的中文城市名或 9 位 city code；已停止抓取，"
        "避免将无效城市参数误判为 0 个岗位。"
    )


def list_cities(keyword=None, use_live=True):
    """打印支持的城市列表。keyword 非空时只打印城市名含该关键词的城市。

    优先用运行时拉取的最新码表（use_live=True），拉取失败回退本地静态码表。
    """
    name_to_code = {}
    if use_live:
        live_map, _ = load_live_city_maps()
        name_to_code.update(live_map)
    if not name_to_code:
        local_map, _ = load_local_city_map()
        name_to_code.update(local_map)
    if not name_to_code:
        print("⚠️ 无法加载城市码表（本地静态文件缺失且网络拉取失败）")
        return

    items = sorted(name_to_code.items(), key=lambda kv: kv[0])
    if keyword:
        keyword = keyword.strip()
        items = [(n, c) for n, c in items if keyword in n]
        if not items:
            print(f"没有匹配「{keyword}」的城市")
            return
    print(f"共 {len(items)} 个城市（支持中文城市名或城市码）：")
    for name, code in items:
        print(f"  {name}\t{code}")


class LoginProbeStatus(Enum):
    """Outcome of one login probe request."""

    AVAILABLE = "available"
    UNAUTHENTICATED = "unauthenticated"
    RESTRICTED = "restricted"
    EMPTY = "empty"
    RESPONSE_ERROR = "response_error"


@dataclass(frozen=True)
class LoginProbeResult:
    """Structured login probe result with the original failure context."""

    status: LoginProbeStatus
    code: int | None = None
    message: str = ""
    retryable: bool = False


def classify_login_probe_response(data, http_status=200):
    """Classify a BOSS search response without collapsing failures to bool."""
    if http_status == 401:
        return LoginProbeResult(
            LoginProbeStatus.UNAUTHENTICATED,
            message="HTTP 401",
        )
    if http_status in (403, 429):
        return LoginProbeResult(
            LoginProbeStatus.RESTRICTED,
            message=f"HTTP {http_status}",
        )
    if http_status != 200:
        return LoginProbeResult(
            LoginProbeStatus.RESPONSE_ERROR,
            message=f"HTTP {http_status}",
            retryable=http_status == 0 or http_status >= 500,
        )
    if not isinstance(data, dict):
        return LoginProbeResult(
            LoginProbeStatus.RESPONSE_ERROR,
            message="响应不是 JSON 对象",
            retryable=True,
        )

    raw_code = data.get("code")
    try:
        code = int(raw_code) if raw_code is not None else None
    except (TypeError, ValueError):
        code = None
    message = str(data.get("message") or data.get("msg") or "")

    if code in LOGIN_RESTRICTED_CODES:
        return LoginProbeResult(LoginProbeStatus.RESTRICTED, code=code, message=message)
    if code != 0:
        # code 不在已知风控码集合里时，再按 message 关键字兜底判定是否风控，
        # 避免新风控码被当成不可恢复的 RESPONSE_ERROR 误拦已登录用户。
        if any(kw in message for kw in LOGIN_RESTRICTED_MESSAGE_KEYWORDS):
            return LoginProbeResult(LoginProbeStatus.RESTRICTED, code=code, message=message)
        return LoginProbeResult(LoginProbeStatus.RESPONSE_ERROR, code=code, message=message)

    zp_data = data.get("zpData")
    if not isinstance(zp_data, dict):
        return LoginProbeResult(
            LoginProbeStatus.RESPONSE_ERROR,
            code=code,
            message="响应缺少 zpData",
            retryable=True,
        )
    job_list = zp_data.get("jobList")
    if not isinstance(job_list, list):
        return LoginProbeResult(
            LoginProbeStatus.RESPONSE_ERROR,
            code=code,
            message="响应缺少 jobList",
            retryable=True,
        )
    if not job_list:
        return LoginProbeResult(LoginProbeStatus.EMPTY, code=code)
    if any(
        (job.get("salaryDesc") or "").strip()
        for job in job_list
        if isinstance(job, dict)
    ):
        return LoginProbeResult(LoginProbeStatus.AVAILABLE, code=code)
    return LoginProbeResult(LoginProbeStatus.UNAUTHENTICATED, code=code)


def is_logged_in_search_response(data):
    """Return True only when BOSS returns jobs with plaintext salary."""
    result = classify_login_probe_response(data)
    return result.status is LoginProbeStatus.AVAILABLE


def build_login_probe_url(query, city_code):
    params = {
        "scene": 1,
        "query": query,
        "city": city_code,
        "page": 1,
        "pageSize": LOGIN_PROBE_PAGE_SIZE,
    }
    return f"{API_JOB_LIST_PATH}?{urlencode(params)}"


def probe_login_state(cdp, sid, query=LOGIN_PROBE_QUERY, city_code=LOGIN_PROBE_CITY):
    """Run exactly one budgeted search probe and return its structured state."""
    probe_url = build_login_probe_url(query, city_code)
    js = f"""
    (function(){{
        var xhr = new XMLHttpRequest();
        xhr.open('GET', '{probe_url}', false);
        xhr.send();
        return JSON.stringify({{
            httpStatus: xhr.status,
            body: xhr.responseText
        }});
    }})()
    """
    incr_request()
    val = cdp.eval_js(js, sid)
    if not val:
        return LoginProbeResult(
            LoginProbeStatus.RESPONSE_ERROR,
            message="探测响应为空",
            retryable=True,
        )
    try:
        envelope = json.loads(val) if isinstance(val, str) else val
    except (json.JSONDecodeError, ValueError):
        return LoginProbeResult(
            LoginProbeStatus.RESPONSE_ERROR,
            message="探测响应不是有效 JSON",
            retryable=True,
        )
    if not isinstance(envelope, dict):
        return LoginProbeResult(
            LoginProbeStatus.RESPONSE_ERROR,
            message="探测响应格式异常",
            retryable=True,
        )

    raw_http_status = envelope.get("httpStatus", 200)
    try:
        http_status = int(raw_http_status)
    except (TypeError, ValueError):
        http_status = 0
    body = envelope.get("body", envelope)
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return LoginProbeResult(
                LoginProbeStatus.RESPONSE_ERROR,
                message="搜索接口响应不是有效 JSON",
                retryable=True,
            )
    return classify_login_probe_response(body, http_status=http_status)


def describe_login_probe_result(result):
    """Return a concise user-facing explanation for a non-available state."""
    context = []
    if result.code is not None:
        context.append(f"code: {result.code}")
    if result.message:
        context.append(result.message)
    suffix = f"（{'; '.join(context)}）" if context else ""

    if result.status is LoginProbeStatus.UNAUTHENTICATED:
        return f"未检测到可用登录态{suffix}"
    if result.status is LoginProbeStatus.RESTRICTED:
        return f"BOSS 接口返回限制状态{suffix}"
    if result.status is LoginProbeStatus.EMPTY:
        return "探测样本没有职位，暂时无法确认登录态"
    return f"登录探测响应异常{suffix}"


# ============================================================
# 登录状态检测
# ============================================================
def check_login_state(cdp_port=DEFAULT_CDP_PORT):
    """通过 CDP 检测 BOSS直聘登录状态。

    Returns:
        LoginProbeResult: 登录探测的结构化状态
    """
    cdp = None
    tid = None
    try:
        cdp = CDPSession(cdp_port)
        tid, sid = create_page_session(cdp)

        # 先导航到 BOSS直聘，确保 cookie 域名正确
        cdp.send("Page.navigate", {"url": "https://www.zhipin.com/"}, sid)
        time.sleep(4)

        return probe_login_state(cdp, sid)
    except (requests.ConnectionError, requests.Timeout, KeyError,
            json.JSONDecodeError, websocket.WebSocketException,
            TimeoutError, RuntimeError) as e:
        log.error(f"登录状态检测失败: {e}")
        return LoginProbeResult(
            LoginProbeStatus.RESPONSE_ERROR,
            message=str(e),
        )
    finally:
        if cdp is not None:
            if tid is not None:
                try:
                    cdp.send("Target.closeTarget", {"targetId": tid})
                except (KeyError, websocket.WebSocketException, TimeoutError):
                    log.debug("关闭登录探测 target 失败", exc_info=True)
            try:
                cdp.close()
            except websocket.WebSocketException:
                log.debug("关闭登录探测 CDP 连接失败", exc_info=True)


def wait_for_login(cdp_port=DEFAULT_CDP_PORT, timeout=DEFAULT_LOGIN_TIMEOUT, interval=3):
    """Open BOSS login page and wait until plaintext salary is available."""
    cdp = CDPSession(cdp_port)
    tid, sid = create_page_session(cdp, background=False)
    cdp.send(
        "Page.navigate",
        {"url": "https://www.zhipin.com/web/user/"},
        sid,
    )

    deadline = time.time() + timeout
    logged_in = False
    attempt = 0
    transient_errors = 0
    print(f"等待 BOSS 登录完成（最长 {timeout}s）", end="", flush=True)
    try:
        while time.time() <= deadline:
            query, city_code = LOGIN_PROBE_TARGETS[attempt % len(LOGIN_PROBE_TARGETS)]
            try:
                result = probe_login_state(cdp, sid, query=query, city_code=city_code)
            except RuntimeError as e:
                print(f"\n❌ {e}")
                return False

            if result.status is LoginProbeStatus.AVAILABLE:
                logged_in = True
                print("\n✅ 已检测到 BOSS 登录态，且接口返回明文薪资")
                return True
            if result.status is LoginProbeStatus.RESTRICTED:
                print(f"\n❌ {describe_login_probe_result(result)}，已停止登录探测")
                print("   当前问题不是尚未登录；请先在浏览器中完成验证或稍后再试")
                return False
            if result.status is LoginProbeStatus.RESPONSE_ERROR:
                if not result.retryable:
                    print(f"\n❌ {describe_login_probe_result(result)}，已停止登录探测")
                    return False
                transient_errors += 1
                if transient_errors > LOGIN_PROBE_MAX_TRANSIENT_ERRORS:
                    print(f"\n❌ {describe_login_probe_result(result)}，连续异常次数过多")
                    return False
            else:
                transient_errors = 0

            print(".", end="", flush=True)
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            delay = min(interval * (2 ** attempt), LOGIN_PROBE_MAX_INTERVAL, remaining)
            time.sleep(delay)
            attempt += 1
        print("\n❌ 等待登录超时")
        print("   浏览器会继续保持打开；登录后可重新运行 --check 或抓取命令")
        return False
    finally:
        if logged_in:
            cdp.send("Target.closeTarget", {"targetId": tid})
        cdp.close()


# ============================================================
# 增量写入 JSON
# ============================================================
def append_json(path, new_jobs):
    """追加 jobs 到 JSON 文件，按 encrypt_job_id / job_link 去重。"""
    existing = []
    seen_ids = set()
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            existing = data.get("jobs", [])
            seen_ids = {job_schema.job_dedupe_key(j) for j in existing}
        except (json.JSONDecodeError, OSError, ValueError):
            data = {}
    added = 0
    for j in new_jobs:
        key = job_schema.job_dedupe_key(j)
        if not key or key in seen_ids:
            continue
        existing.append(j)
        seen_ids.add(key)
        added += 1
    data["jobs"] = existing
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return added


def flush_jobs(path, meta, jobs):
    """每次有新数据就全量刷写（jobs 去重后），保证异常退出也能保留"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    existing_jobs = []
    seen_ids = set()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                old = json.load(f)
            existing_jobs = old.get("jobs", [])
            seen_ids = {job_schema.job_dedupe_key(j) for j in existing_jobs}
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    for j in jobs:
        key = job_schema.job_dedupe_key(j)
        if not key or key in seen_ids:
            continue
        existing_jobs.append(j)
        seen_ids.add(key)
    meta["total"] = len(existing_jobs)
    meta["jobs"] = existing_jobs
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


# ============================================================
# 合并外部 JSON 文件
# ============================================================
def merge_jobs(external_path, new_jobs):
    """从外部 JSON 加载 jobs，与 new_jobs 按 job_id 合并去重。

    Args:
        external_path: 已有 JSON 文件路径
        new_jobs: 新抓取的 jobs 列表

    Returns:
        合并后的 jobs 列表
    """
    try:
        with open(external_path, "r", encoding="utf-8") as f:
            old_data = json.load(f)
    except (json.JSONDecodeError, OSError, ValueError) as e:
        log.warning(f"无法加载合并文件 {external_path}: {e}")
        return new_jobs

    old_jobs = old_data.get("jobs", [])
    merged = list(old_jobs)
    seen_ids = {job_schema.job_dedupe_key(j) for j in merged}

    added = 0
    for j in new_jobs:
        key = job_schema.job_dedupe_key(j)
        if not key or key in seen_ids:
            continue
        merged.append(j)
        seen_ids.add(key)
        added += 1

    print(f"合并: 旧文件 {len(old_jobs)} 条 + 新抓取 {len(new_jobs)} 条 = {len(merged)} 条 (新增 {added})")
    return merged


def merge_details(external_path, new_details):
    """从外部 JSON 加载详情，与 new_details 按 job_id 合并去重。

    详情文件本身可能是列表结构（scrape_details 输出）或带 jobs/details 键的字典，
    这里都做兼容。优先保留 new_details 中的同名记录（更新覆盖旧值）。

    Args:
        external_path: 已有详情 JSON 文件路径
        new_details: 新抓取的详情列表（可为空）

    Returns:
        合并后的详情列表
    """
    if not external_path:
        return new_details
    try:
        with open(external_path, "r", encoding="utf-8") as f:
            old_data = json.load(f)
    except (json.JSONDecodeError, OSError, ValueError) as e:
        log.warning(f"无法加载合并详情文件 {external_path}: {e}")
        return new_details

    if isinstance(old_data, list):
        old_details = old_data
    elif isinstance(old_data, dict):
        old_details = old_data.get("details") or old_data.get("jobs") or []
    else:
        old_details = []

    merged = merge_details_from_lists(old_details, new_details)
    print(f"合并详情: 旧文件 {len(old_details)} 条 + 新抓取 {len(new_details)} 条 = {len(merged)} 条")
    return merged


def merge_details_from_lists(old_details, new_details):
    """把两份详情列表按 job_id 合并去重，new_details 优先（同 id 用新覆盖旧）。"""
    by_id = {}
    for d in old_details:
        jid = d.get("job_id", "") if isinstance(d, dict) else ""
        if jid:
            by_id[jid] = d
    for d in new_details:
        jid = d.get("job_id", "") if isinstance(d, dict) else ""
        if jid:
            by_id[jid] = d
    return list(by_id.values())


# ============================================================
# 构建搜索 URL
# ============================================================
def normalize_filter_codes(raw):
    """Normalize CLI filter values to an ordered unique list of codes.

    Accepts a single code, comma-separated string, list/tuple of codes, or
    repeated CLI values already collected as a list.
    """
    if raw is None:
        return []
    chunks = []
    if isinstance(raw, (list, tuple)):
        for item in raw:
            chunks.extend(normalize_filter_codes(item))
        # re-dedupe while preserving order after flattening
        ordered = []
        seen = set()
        for code in chunks:
            if code in seen:
                continue
            seen.add(code)
            ordered.append(code)
        return ordered
    text = str(raw).strip()
    if not text:
        return []
    ordered = []
    seen = set()
    for part in re.split(r"[,，\s]+", text):
        code = part.strip()
        if not code or code in seen:
            continue
        seen.add(code)
        ordered.append(code)
    return ordered


def resolve_job_type(value):
    """Map 求职类型 label/code to joblist.json jobType. 不限 → None (omit)."""
    text = str(value or "").strip()
    if not text or text.lower() in ("0", "不限", "unlimited", "any"):
        return None
    if text in JOB_TYPE_MAP:
        code = JOB_TYPE_MAP[text]
        return None if code == "0" else code
    if text.isdigit():
        return None if text == "0" else text
    allowed = "/".join(JOB_TYPE_MAP.keys())
    raise ValueError(f"未知求职类型: {text}。可用: {allowed} 或代码 1901/1902/1903")


def encode_filter_param(value):
    """Encode filter value for BOSS query/API (comma-joined multi-select)."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        codes = [str(v).strip() for v in value if str(v).strip()]
        return ",".join(codes) if codes else None
    text = str(value).strip()
    return text or None


def normalize_filters_dict(filters):
    """Normalize known multi-select filters; leave others as scalar strings."""
    out = {}
    for key, value in (filters or {}).items():
        if value in (None, "", [], ()):
            continue
        if key in MULTI_SELECT_FILTER_KEYS:
            codes = normalize_filter_codes(value)
            if codes:
                out[key] = codes
            continue
        text = str(value).strip()
        if text:
            out[key] = text
    return out


def build_search_url(keyword, city_code, page, filters):
    params = {"query": keyword, "city": city_code, "page": page}
    for key, code in (filters or {}).items():
        encoded = encode_filter_param(code)
        if encoded:
            params[key] = encoded
    return f"https://www.zhipin.com/web/geek/job?{urlencode(params)}"


def should_use_dom_fallback(jobs, allow_dom_fallback=False):
    return allow_dom_fallback and not jobs


def parse_api_list_response(value):
    """Parse in-page joblist.json eval result (envelope or legacy job array)."""
    empty = {"code": None, "message": "", "error": None, "jobs": []}
    if not value:
        return dict(empty)
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (json.JSONDecodeError, ValueError, TypeError):
        return dict(empty)
    if isinstance(parsed, list):
        http_err = None
        jobs = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            if item.get("error") and not (item.get("title") or item.get("job_link")):
                http_err = item.get("error")
                continue
            if item.get("title") or item.get("job_link"):
                jobs.append(item)
        return {
            "code": None if jobs or http_err is None else None,
            "message": "",
            "error": http_err,
            "jobs": jobs,
        }
    if not isinstance(parsed, dict):
        return dict(empty)
    jobs = []
    raw_jobs = parsed.get("jobs")
    if isinstance(raw_jobs, list):
        for item in raw_jobs:
            if not isinstance(item, dict) or item.get("error"):
                continue
            if item.get("title") or item.get("job_link"):
                jobs.append(item)
    return {
        "code": parsed.get("code"),
        "message": str(parsed.get("message") or ""),
        "error": parsed.get("error"),
        "jobs": jobs,
    }


def raise_if_search_api_blocked(payload):
    """Stop immediately on HTTP failure or BOSS wind-control codes."""
    data = payload or {}
    if data.get("error"):
        raise SystemExit(
            f"搜索 API HTTP {data.get('error')}，已停止。请稍后再试，不要硬闯。"
        )
    code = data.get("code")
    if code in (None, "", 0, "0"):
        return
    message = str(data.get("message") or "").strip()
    raise SystemExit(
        f"搜索 API 异常 code={code} {message}，已停止。请稍后再试，不要硬闯。"
    )


def parse_api_jobs_eval_value(value):
    return parse_api_list_response(value).get("jobs") or []


def build_detail_url(job):
    """Build the URL used for detail navigation without mutating job_link."""
    link = job.get("job_link", "")
    if not link:
        return ""

    parsed = urlparse(link)
    params = parse_qsl(parsed.query, keep_blank_values=True)
    existing_keys = {key for key, _ in params}
    for query_key, job_key in (("lid", "lid"), ("securityId", "security_id")):
        value = job.get(job_key) or job.get(query_key) or ""
        if value and query_key not in existing_keys:
            params.append((query_key, value))
            existing_keys.add(query_key)

    return urlunparse(parsed._replace(query=urlencode(params)))


def find_latest_detail_file(result_dir=DEFAULT_DATA_DIR):
    pattern = os.path.join(result_dir, "boss_details_*.json")
    files = [path for path in glob.glob(pattern) if os.path.isfile(path)]
    if not files:
        return None
    return max(files, key=lambda path: (os.path.getmtime(path), path))


def detail_candidate_paths(input_path=None, detail_output=None, result_dir=DEFAULT_DATA_DIR):
    candidates = []
    if detail_output:
        candidates.append(detail_output)
    if input_path:
        directory = os.path.dirname(input_path) or "."
        basename = os.path.basename(input_path)
        if basename.startswith("boss_jobs_"):
            candidates.append(os.path.join(directory, basename.replace("boss_jobs_", "boss_details_", 1)))
    latest = find_latest_detail_file(result_dir)
    if latest:
        candidates.append(latest)

    deduped = []
    seen = set()
    for path in candidates:
        normalized = os.path.abspath(os.path.expanduser(path))
        if normalized not in seen:
            deduped.append(path)
            seen.add(normalized)
    return deduped


def load_existing_details(input_path=None, detail_output=None, result_dir=DEFAULT_DATA_DIR):
    for path in detail_candidate_paths(input_path, detail_output, result_dir):
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                details = json.load(f)
            if isinstance(details, list):
                print(f"加载详情文件: {path}")
                return details
        except (json.JSONDecodeError, OSError, ValueError) as e:
            log.warning(f"无法加载详情文件 {path}: {e}")
    return None


# ============================================================
# 抓取列表
# ============================================================
def scrape_list(keyword, city_input, max_pages, filters, output_path,
                cdp_port=DEFAULT_CDP_PORT, fmt="json", allow_dom_fallback=False,
                on_page=None, start_page=1):
    city_name, city_code = resolve_city(city_input)
    cdp = CDPSession(cdp_port)
    all_jobs = []
    seen = set()
    if not output_path:
        output_path = default_output_path("jobs", keyword)

    filters = normalize_filters_dict(filters)

    def _codes_label(code_or_list, mapping):
        encoded = encode_filter_param(code_or_list)
        if not encoded:
            return ""
        labels = []
        for code in str(encoded).split(","):
            label = next((k for k, v in mapping.items() if v == code), code)
            labels.append(label)
        return ",".join(labels)

    # 显示筛选条件
    filter_desc = []
    if filters.get("scale"):
        filter_desc.append(f"规模={_codes_label(filters['scale'], SCALE_MAP)}")
    if filters.get("stage"):
        for k, v in STAGE_MAP.items():
            if v == filters["stage"]:
                filter_desc.append(f"融资={k}")
    if filters.get("salary"):
        for k, v in SALARY_MAP.items():
            if v == filters["salary"]:
                filter_desc.append(f"薪资={k}")
    if filters.get("experience"):
        filter_desc.append(f"经验={_codes_label(filters['experience'], EXPERIENCE_MAP)}")
    if filters.get("degree"):
        for k, v in DEGREE_MAP.items():
            if v == filters["degree"]:
                filter_desc.append(f"学历={k}")
    if filters.get("industry"):
        for k, v in INDUSTRY_MAP.items():
            if v == filters["industry"]:
                filter_desc.append(f"行业={k}")
    if filters.get("jobType"):
        filter_desc.append(
            f"求职类型={_codes_label(filters['jobType'], JOB_TYPE_MAP)}"
        )

    print(f"=== BOSS直聘抓取 ===")
    print(f"关键词: {keyword} | 城市: {city_name} | 页数: {max_pages}")
    if filter_desc:
        print(f"筛选: {' | '.join(filter_desc)}")
    print()

    tid, sid = create_page_session(cdp)

    start_page = max(1, int(start_page or 1))
    max_pages = max(start_page, int(max_pages or start_page))

    try:
        for pg in range(start_page, max_pages + 1):
            print(f"--- [{pg}/{max_pages} 页, {len(all_jobs)} 条已抓] ---")
            incr_request()

            # 本批第一页：导航到搜索页建立 cookie/session
            if pg == start_page:
                url = build_search_url(keyword, city_code, pg, filters)
                cdp.send("Page.navigate", {"url": url}, sid)
                time.sleep(random.uniform(6, 10))
                human_scroll(cdp, sid)
                human_mouse_jitter(cdp, sid)

            # 优先用 API 获取明文数据
            api_params = {
                "scene": "1",
                "query": keyword,
                "city": city_code,
                "page": pg,
                "pageSize": 30,
            }
            for k, v in filters.items():
                encoded = encode_filter_param(v)
                if encoded:
                    api_params[k] = encoded
            api_url = f"{API_JOB_LIST_PATH}?{urlencode(api_params)}"
            api_js = FETCH_API_JS_TEMPLATE.replace("__API_URL__", api_url)
            val = cdp.eval_js(api_js, sid)
            payload = parse_api_list_response(val)
            raise_if_search_api_blocked(payload)
            jobs = parse_api_jobs_eval_value(val)

            # DOM 提取的薪资可能是加密字体，默认禁用；只有显式允许时才降级。
            if should_use_dom_fallback(jobs, allow_dom_fallback):
                log.warning("⚠️ API 获取失败，回退到 DOM 提取（此方式已弃用，数据可能不完整）")
                if pg > 1:
                    url = build_search_url(keyword, city_code, pg, filters)
                    cdp.send("Page.navigate", {"url": url}, sid)
                    time.sleep(random.uniform(4, 8))
                    human_scroll(cdp, sid)
                val = cdp.eval_js(EXTRACT_LIST_JS, sid)
                if val:
                    try:
                        jobs = json.loads(val) if isinstance(val, str) else val
                    except (json.JSONDecodeError, ValueError):
                        print(f"  ⚠️ JSON 解析失败")
                        jobs = []
            elif not jobs:
                log.warning("⚠️ API 未返回职位数据，已跳过 DOM fallback；如需强制降级可加 --allow-dom-fallback")

            if not jobs:
                print("  ⚠️ 无数据")
                continue

            new = 0
            page_new_jobs = []
            for j in jobs:
                item = job_schema.project_list_job(j)
                if city_name and not item["location"]:
                    item["location"] = city_name
                key = job_schema.job_dedupe_key(item)
                if not key or key in seen:
                    continue
                seen.add(key)
                all_jobs.append(item)
                page_new_jobs.append(item)
                new += 1
                print(
                    f"  ✓ {item['title']} | {item.get('salary','?')} | "
                    f"{item.get('location','')} | {item.get('boss_name','')}"
                )

            print(f"  本页 {len(jobs)} 条, 新增 {new}, 累计 {len(all_jobs)}")

            # 每页抓完就写入文件，异常退出也能保留
            if output_path:
                flush_jobs(output_path, {
                    "keyword": keyword,
                    "city": city_name,
                    "filters": filters,
                    "filter_desc": filter_desc,
                    "scraped_at": datetime.now().isoformat(),
                }, all_jobs)

            # P5：标准岗可在每页后做匹配/详情；返回 False 则停止翻页
            if on_page is not None:
                try:
                    should_continue = on_page(pg, page_new_jobs, all_jobs)
                except TypeError:
                    should_continue = on_page(pg, page_new_jobs)
                if should_continue is False:
                    print(f"  ⏹ 已达详情配额或停止条件，不再翻页（当前第 {pg} 页）")
                    break

            if pg < max_pages:
                d = random.uniform(12, 22)
                print(f"  翻页等待 {d:.0f}s...\n")
                time.sleep(d)

    except KeyboardInterrupt:
        print("\n中断")
    except RuntimeError as e:
        print(f"\n⚠️ {e}")
    finally:
        cdp.send("Target.closeTarget", {"targetId": tid})
        cdp.close()

    print(f"\n{'='*60}")
    print(f"完成: {len(all_jobs)} 条")

    if all_jobs:
        # 最终写入（含时间戳更新）
        flush_jobs(output_path, {
            "keyword": keyword,
            "city": city_name,
            "filters": filters,
            "filter_desc": filter_desc,
            "scraped_at": datetime.now().isoformat(),
        }, all_jobs)
        print(f"已保存: {output_path}")
    else:
        print("无数据")

    return {"keyword": keyword, "city": city_name, "total": len(all_jobs), "jobs": all_jobs}


# ============================================================
# 抓取详情
# ============================================================
def resolve_encrypt_job_id(job):
    """Return BOSS encryptJobId from a list/detail record, or parse it from job_link."""
    if not isinstance(job, dict):
        return ""
    eid = str(job.get("encrypt_job_id") or "").strip()
    if eid:
        return eid
    link = str(job.get("job_link") or job.get("link") or "")
    match = _ENCRYPT_JOB_ID_IN_LINK_RE.search(link)
    return match.group(1) if match else ""


def build_detail_record(job, extracted, position=None, city_fallback=""):
    record = {
        "encrypt_job_id": resolve_encrypt_job_id(job),
        "title": job.get("title", ""),
        "company": job.get("boss_name") or job.get("company") or "",
        "salary": job.get("salary", ""),
        "location": resolve_detail_location(
            list_location=job.get("location", ""),
            detail_location=extracted.get("location", ""),
            city_fallback=city_fallback,
        ),
        "jd": extracted.get("jd", ""),
    }
    if position:
        record["position_name"] = position.get("position_name", "")
        record["job_intent_id"] = position.get("job_intent_id", "")
        record["job_intent_label"] = position.get("job_intent_label", "")
    return record


def _load_skillver_export_module():
    """Load export_skillver_csv for shared catalog/seen conventions."""
    try:
        from scripts import export_skillver_csv as mod
        return mod
    except ImportError:
        pass
    import importlib.util

    export_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "export_skillver_csv.py",
    )
    spec = importlib.util.spec_from_file_location(
        "export_skillver_csv", export_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load Skillver export helpers: {export_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_position_catalog(path=None):
    """Load Skillver position_catalog.json (same asset as export script)."""
    mod = _load_skillver_export_module()
    return mod.load_catalog(path or DEFAULT_SKILLVER_CATALOG)


def resolve_standard_position(position_name, catalog=None, catalog_path=None):
    """Resolve a catalog position name; SystemExit if unknown."""
    mod = _load_skillver_export_module()
    rows = catalog if catalog is not None else mod.load_catalog(
        catalog_path or DEFAULT_SKILLVER_CATALOG
    )
    return mod.resolve_position(rows, position_name)


def resolve_search_query(query=None, position_name=None):
    """Search box text. --query wins; --position-name is an alias."""
    q = str(query or "").strip() or str(position_name or "").strip()
    if not q:
        raise ValueError("请指定 --query（搜索词；也可用 --position-name 作为别名）")
    return q


def catalog_bindings_by_name(catalog):
    out = {}
    for item in catalog or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("position_name") or "").strip()
        job_intent_id = str(item.get("job_intent_id") or "").strip()
        job_intent_label = str(item.get("job_intent_label") or "").strip()
        if name and job_intent_id and job_intent_label:
            out[name] = {
                "position_name": name,
                "job_intent_id": job_intent_id,
                "job_intent_label": job_intent_label,
            }
    return out


def load_skillver_seen(path=None, catalog=None, catalog_names=None):
    mod = _load_skillver_export_module()
    names = catalog_names
    if names is None and catalog is not None:
        names = set(catalog_position_names(catalog))
    if not path:
        return mod.empty_seen()
    return mod.load_seen(
        path,
        catalog_names=names,
    )


def save_skillver_seen(path, seen):
    if not path:
        raise ValueError("seen_jobs.json path is required")
    mod = _load_skillver_export_module()
    mod.save_seen(path, seen)


def skillver_seen_detail_ids(seen):
    mod = _load_skillver_export_module()
    return mod.detail_ids_in_seen(seen)


def mark_skillver_seen_scraped(
    seen, *, key, job_id, position_name, catalog_names=None
):
    mod = _load_skillver_export_module()
    mod.mark_scraped(
        seen,
        key=key,
        job_id=job_id,
        position_name=position_name,
        catalog_names=catalog_names,
    )


def add_skillver_unexported(
    *,
    key,
    query="",
    details_path="",
    position_name="",
    path=None,
):
    """Add a scraped detail to the unexported index (CSV not written yet)."""
    if not key:
        return
    mod = _load_skillver_export_module()
    store_path = path or DEFAULT_SKILLVER_UNEXPORTED
    try:
        store = mod.load_unexported(store_path)
        mod.add_unexported(
            store,
            key=key,
            query=query,
            details_path=details_path,
            position_name=position_name,
        )
        mod.save_unexported(store_path, store)
    except (OSError, TypeError, ValueError) as exc:
        log.warning(f"写入 unexported 失败: {exc}")


def _as_path_list(value):
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)]


def infer_classify_input_path(decisions_path):
    name = os.path.basename(str(decisions_path or ""))
    if "classify_decisions_" in name:
        return os.path.join(
            os.path.dirname(str(decisions_path)),
            name.replace("classify_decisions_", "classify_input_", 1),
        )
    return None


def count_catalog_mapped(results, catalog_names):
    """Count decision rows whose position_name is a catalog name."""
    names = set(catalog_names or [])
    total = 0
    for item in results or []:
        if not isinstance(item, dict):
            continue
        pos = item.get("position_name")
        if pos is None:
            continue
        pos = str(pos).strip()
        if pos and (not names or pos in names):
            total += 1
    return total


def resolve_decision_batches(classify_input_path, decisions_path):
    """Return [(classify_input_or_None, decisions_path), ...]."""
    decision_paths = _as_path_list(decisions_path)
    if not decision_paths:
        raise ValueError("缺少 --details-from-decisions")
    classify_paths = _as_path_list(classify_input_path)
    if not classify_paths:
        for dec in decision_paths:
            inferred = infer_classify_input_path(dec)
            if inferred and os.path.isfile(inferred):
                classify_paths.append(inferred)
    if classify_paths and len(classify_paths) != len(decision_paths):
        raise ValueError(
            f"classify-input ({len(classify_paths)}) 与 "
            f"decisions ({len(decision_paths)}) 数量须一致"
        )
    if not classify_paths:
        return [(None, dec) for dec in decision_paths]
    return list(zip(classify_paths, decision_paths))


def mark_skillver_seen_classified(
    seen, *, key, job, position_name, classified_by, catalog_names=None, query=""
):
    mod = _load_skillver_export_module()
    mod.mark_classified(
        seen,
        key=key,
        job=job,
        position_name=position_name,
        classified_by=classified_by,
        catalog_names=catalog_names,
        query=query,
    )


def mark_skillver_seen_listed(seen, *, key, job, query="", catalog_names=None):
    mod = _load_skillver_export_module()
    mod.mark_listed(
        seen,
        key=key,
        job=job,
        query=query,
        catalog_names=catalog_names,
    )


def skillver_count_details_all(seen):
    mod = _load_skillver_export_module()
    return mod.count_details_all(seen)


def skillver_job_in_seen(seen, key):
    mod = _load_skillver_export_module()
    return mod.job_in_seen(seen, key)


def skillver_is_classified(seen, key):
    mod = _load_skillver_export_module()
    return mod.is_classified(seen, key)


def default_skillver_output_paths(position_name):
    """Default list/detail JSON: data/<搜索词>/jobs.json and details.json."""
    folder = search_term_dir(position_name)
    return os.path.join(folder, "jobs.json"), os.path.join(folder, "details.json")


def iter_detail_json_paths(roots):
    """Yield boss_details_*.json paths under files/directories in roots."""
    for root in roots or []:
        if not root:
            continue
        path = os.path.abspath(os.path.expanduser(root))
        if os.path.isfile(path):
            yield path
            continue
        if os.path.isdir(path):
            patterns = (
                os.path.join(path, "boss_details_*.json"),
                os.path.join(path, "details.json"),
                os.path.join(path, "*", "details.json"),
            )
            for pattern in patterns:
                for matched in sorted(glob.glob(pattern)):
                    if os.path.isfile(matched):
                        yield matched


def load_seen_encrypt_job_ids(roots):
    """Collect encrypt_job_id values from already-scraped detail JSON files only."""
    seen = set()
    for path in iter_detail_json_paths(roots):
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            log.warning(f"无法读取详情去重文件 {path}: {exc}")
            continue
        if not isinstance(payload, list):
            continue
        for item in payload:
            eid = resolve_encrypt_job_id(item)
            if eid:
                seen.add(eid)
    return seen


def filter_jobs_missing_details(jobs, seen_encrypt_ids):
    """Keep jobs whose encrypt_job_id is not in seen_encrypt_ids (detail not scraped yet)."""
    if not jobs:
        return [], 0
    seen_encrypt_ids = seen_encrypt_ids or set()
    kept = []
    skipped = 0
    for job in jobs:
        eid = resolve_encrypt_job_id(job)
        if eid and eid in seen_encrypt_ids:
            skipped += 1
            continue
        kept.append(job)
    return kept, skipped


def keyword_output_slug(keyword, index):
    """Build a short filesystem slug for batch output filenames."""
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", keyword.strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("_")[:32] or "keyword"
    return f"{index:02d}_{cleaned}"


def is_headhunter_job(job):
    """Return True when a list-card job is posted by a headhunter / HR agency.

    Used before detail scraping so --max-details applies to direct-hire posts.
    Does not mutate the saved list JSON.
    """
    if not isinstance(job, dict):
        return False
    boss_title = str(job.get("boss_title") or "")
    if "猎头" in boss_title:
        return True
    if "headhunt" in boss_title.lower():
        return True
    industry = str(job.get("company_industry") or "").strip()
    if industry == "人力资源服务":
        return True
    return False


def filter_out_headhunter_jobs(jobs):
    """Drop headhunter / agency list cards; preserve relative order of the rest.

    Returns:
        (kept_jobs, removed_count)
    """
    if not jobs:
        return [], 0
    kept = []
    removed = 0
    for job in jobs:
        if is_headhunter_job(job):
            removed += 1
            continue
        kept.append(job)
    return kept, removed


# ============================================================
# Skillver：规则过滤（猎头/匿名）+ Agent 决策文件归类
# ============================================================
def clamp_skillver_min_details(value):
    """Return (clamped_value, was_clamped). Default 5; hard max 50."""
    if value is None:
        return DEFAULT_SKILLVER_MIN_DETAILS, False
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SKILLVER_MIN_DETAILS, False
    if n < 1:
        n = 1
    if n > DEFAULT_SKILLVER_MAX_MIN_DETAILS:
        return DEFAULT_SKILLVER_MAX_MIN_DETAILS, True
    return n, False


def catalog_position_names(catalog):
    names = []
    for item in catalog or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("position_name") or "").strip()
        if name:
            names.append(name)
    return names


def is_obvious_non_entity_recruiter(job):
    """Rule-only filter for headhunter / HR agency / anonymous before Agent."""
    if is_headhunter_job(job):
        return True, "rule_non_entity_headhunter"
    name = str((job or {}).get("boss_name") or "").strip()
    if not name:
        return True, "rule_non_entity_empty_company"
    if _ANON_COMPANY_RE.match(name):
        return True, "rule_non_entity_anonymous"
    lowered = name.lower()
    if "匿名" in name or "保密" in name or "headhunt" in lowered:
        return True, "rule_non_entity_anonymous"
    return False, ""


def job_card_for_agent(job, city_fallback=""):
    """Slim card for Agent classify_input. city_fallback kept for call-site compat."""
    del city_fallback
    return job_schema.project_classify_job(job)


def write_json_file(path, payload):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_json_file(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def default_classify_input_path(position_name, batch_index=1):
    return os.path.join(
        search_term_dir(position_name),
        f"classify_input_{int(batch_index)}.json",
    )


def default_list_batch_path(position_name, batch_index=1):
    return os.path.join(
        search_term_dir(position_name),
        f"list_batch_{int(batch_index)}.json",
    )


def default_classify_decisions_path(position_name, batch_index=1):
    return os.path.join(
        search_term_dir(position_name),
        f"classify_decisions_{int(batch_index)}.json",
    )


def load_agent_decisions(path, *, catalog_names, expected_ids, target_position_name=None):
    """Validate Agent decision JSON. Returns (mapping id->name|None, errors)."""
    del target_position_name
    errors = []
    try:
        data = load_json_file(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {}, [f"无法读取决策文件: {exc}"]
    if not isinstance(data, dict):
        return {}, ["决策文件根节点必须是对象"]
    if data.get("schema_version") != 1:
        errors.append("schema_version 必须为 1")
    results = data.get("results")
    if not isinstance(results, list):
        errors.append("results 必须是数组")
        return {}, errors
    catalog_set = set(catalog_names or [])
    expected = set(expected_ids or [])
    mapping = {}
    seen_ids = set()
    for i, item in enumerate(results):
        if not isinstance(item, dict):
            errors.append(f"results[{i}] 必须是对象")
            continue
        eid = str(item.get("id") or "").strip()
        if not eid:
            errors.append(f"results[{i}] 缺少 id")
            continue
        if eid in seen_ids:
            errors.append(f"重复 id: {eid}")
            continue
        seen_ids.add(eid)
        pos = item.get("position_name")
        if pos is None:
            mapping[eid] = None
            continue
        pos = str(pos).strip()
        if not pos:
            mapping[eid] = None
            continue
        if pos not in catalog_set:
            errors.append(f"非法岗名（非 catalog 原名）: {pos!r} id={eid}")
            continue
        mapping[eid] = pos
    if expected:
        missing = sorted(expected - seen_ids)
        extra = sorted(seen_ids - expected)
        if missing:
            errors.append(f"缺少 id: {missing[:8]}{'...' if len(missing) > 8 else ''}")
        if extra:
            errors.append(f"多余 id: {extra[:8]}{'...' if len(extra) > 8 else ''}")
    return mapping, errors


def classify_list_jobs_from_agent(
    jobs,
    target_position_name,
    catalog_names,
    *,
    decisions_by_id,
    seen=None,
    page=None,
    batch_index=None,
):
    """Route jobs using Agent decision map (no in-process LLM)."""
    del target_position_name
    catalog_set = set(catalog_names or [])
    decisions = []
    current = []
    other = []
    none_rows = []
    stats = {"agent_mapped": 0, "skipped_non_entity": 0}

    def _base_decision(job, eid):
        return {
            "encrypt_job_id": eid,
            "title": str(job.get("title") or ""),
            "company": str(job.get("boss_name") or job.get("company") or ""),
            "tags": str(job.get("tags") or job.get("skills") or ""),
            "page": page,
            "batch": batch_index,
            "entity_decision": "",
            "classified_by": "",
            "system_position_name": None,
            "final_route": "",
            "skip_reason": "",
        }

    for job in jobs or []:
        eid = resolve_encrypt_job_id(job)
        dec = _base_decision(job, eid)
        if not eid:
            dec["final_route"] = "none"
            dec["skip_reason"] = "missing_encrypt_job_id"
            decisions.append(dec)
            none_rows.append(dec)
            continue
        if seen is not None and skillver_is_classified(seen, eid):
            dec["final_route"] = "skip"
            dec["skip_reason"] = "already_in_seen"
            decisions.append(dec)
            continue
        non_entity, reason = is_obvious_non_entity_recruiter(job)
        if non_entity:
            stats["skipped_non_entity"] += 1
            dec["entity_decision"] = "reject"
            dec["classified_by"] = "rule"
            dec["final_route"] = "none"
            dec["skip_reason"] = reason
            decisions.append(dec)
            none_rows.append(dec)
            continue
        dec["entity_decision"] = "accept"
        if eid not in (decisions_by_id or {}):
            dec["classified_by"] = "agent"
            dec["final_route"] = "none"
            dec["skip_reason"] = "missing_agent_decision"
            decisions.append(dec)
            none_rows.append(dec)
            continue
        pos = decisions_by_id.get(eid)
        stats["agent_mapped"] += 1
        dec["classified_by"] = "agent"
        dec["system_position_name"] = pos
        if pos and pos in catalog_set:
            job["_classified_position"] = pos
            dec["final_route"] = "current"
            current.append(job)
            decisions.append(dec)
            continue
        dec["final_route"] = "none"
        dec["skip_reason"] = "unclassified"
        decisions.append(dec)
        none_rows.append(dec)

    return {
        "current": current,
        "other": other,
        "none": none_rows,
        "decisions": decisions,
        "agent_stats": stats,
    }


# Backward-compatible alias used by older tests/callers
classify_list_jobs_p6 = classify_list_jobs_from_agent


def filter_jobs_for_agent_classify(jobs, seen=None):
    """Drop seen / non-entity; return (candidates, skip_records)."""
    candidates = []
    skips = []
    for job in jobs or []:
        eid = resolve_encrypt_job_id(job)
        if not eid:
            skips.append({"encrypt_job_id": "", "reason": "missing_encrypt_job_id"})
            continue
        if seen is not None and skillver_job_in_seen(seen, eid):
            skips.append({"encrypt_job_id": eid, "reason": "already_in_seen"})
            continue
        non_entity, reason = is_obvious_non_entity_recruiter(job)
        if non_entity:
            skips.append({"encrypt_job_id": eid, "reason": reason})
            continue
        candidates.append(job)
    return candidates, skips


def persist_classifications(
    seen,
    classify_result,
    target_position_name,
    catalog_names,
):
    """Persist routed jobs into seen and return all catalog-mapped jobs."""
    del target_position_name
    names = set(catalog_names or [])
    lookup = {}
    for dec in classify_result.get("decisions") or []:
        eid = str(dec.get("encrypt_job_id") or "")
        if eid:
            lookup[eid] = dec

    current_jobs = []
    for job in classify_result.get("current") or []:
        eid = resolve_encrypt_job_id(job)
        if not eid:
            continue
        pos = str(
            job.get("_classified_position")
            or (lookup.get(eid) or {}).get("system_position_name")
            or ""
        ).strip()
        mark_skillver_seen_classified(
            seen,
            key=eid,
            job=job,
            position_name=pos,
            classified_by=str(
                (lookup.get(eid) or {}).get("classified_by") or "agent"
            ),
            catalog_names=names,
        )
        if pos:
            current_jobs.append(job)

    for job, pos in classify_result.get("other") or []:
        eid = resolve_encrypt_job_id(job)
        if not eid or not pos:
            continue
        job["_classified_position"] = pos
        mark_skillver_seen_classified(
            seen,
            key=eid,
            job=job,
            position_name=pos,
            classified_by=str(
                (lookup.get(eid) or {}).get("classified_by") or "agent"
            ),
            catalog_names=names,
        )
        current_jobs.append(job)

    for dec in classify_result.get("none") or []:
        if dec.get("skip_reason") != "unclassified":
            continue
        eid = str(dec.get("encrypt_job_id") or "").strip()
        if not eid:
            continue
        mark_skillver_seen_classified(
            seen,
            key=eid,
            job={
                "title": dec.get("title") or "",
                "boss_name": dec.get("company") or "",
            },
            position_name="",
            classified_by=str(dec.get("classified_by") or "agent"),
            catalog_names=names,
        )
    return current_jobs


def write_decision_report(path, payload):
    if not path:
        return
    report_path = os.path.abspath(os.path.expanduser(path))
    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"分类决策报告: {report_path}")


def write_match_skip_report(path, payload):
    if not path:
        return
    report_path = os.path.abspath(os.path.expanduser(path))
    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"匹配跳过报告: {report_path}")


def make_skillver_run_id(position_name):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = keyword_output_slug(position_name, 1)
    if slug.startswith("01_"):
        slug = slug[3:]
    digest = hashlib.md5(f"{stamp}:{position_name}".encode("utf-8")).hexdigest()[:6]
    return f"{stamp}_{slug}_{digest}"


def _load_existing_details_list(detail_output):
    details = []
    if detail_output and os.path.isfile(detail_output):
        try:
            with open(detail_output, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                details = loaded
        except (OSError, json.JSONDecodeError, ValueError):
            details = []
    return details


def run_skillver_list_only_batch(
    *,
    position_binding,
    catalog_names,
    skillver_seen,
    search_keyword,
    city,
    filters,
    max_pages,
    page_batch_size,
    list_start_page,
    list_output,
    list_batch_path=None,
    classify_input_path=None,
    batch_index=1,
    cdp_port=DEFAULT_CDP_PORT,
    fmt="json",
    allow_dom_fallback=False,
    scrape_list_fn=None,
    skillver_seen_path=None,
    query=None,
):
    """Scrape one page-batch, filter non-entity/seen, write list_batch for clean A."""
    scrape_list_fn = scrape_list_fn or scrape_list
    target = str(query or search_keyword or (position_binding or {}).get("position_name") or "").strip()
    start = max(1, int(list_start_page or 1))
    batch = max(1, int(page_batch_size or DEFAULT_SKILLVER_PAGE_BATCH_SIZE))
    if max_pages is not None:
        end_page = min(max(start, int(max_pages)), start + batch - 1)
    else:
        end_page = start + batch - 1
    collected = []
    pages_used = 0

    def on_page(page_num, page_jobs, _all_jobs):
        nonlocal pages_used
        pages_used = page_num
        collected.extend(page_jobs or [])
        return page_num < end_page

    list_data = scrape_list_fn(
        search_keyword,
        city,
        end_page,
        filters,
        list_output,
        cdp_port=cdp_port,
        fmt=fmt,
        allow_dom_fallback=allow_dom_fallback,
        on_page=on_page,
        start_page=start,
    )
    candidates, skips = filter_jobs_for_agent_classify(collected, seen=skillver_seen)
    city_name = str((list_data or {}).get("city") or "").strip()
    if not city_name:
        try:
            city_name, _code = resolve_city(city)
        except (CityResolutionError, CityAPIResponseError, OSError, ValueError):
            city_name = str(city or "").strip()
    payload = {
        "schema_version": 1,
        "query": target,
        "target_position_name": target,
        "catalog_names": list(catalog_names),
        "batch_index": int(batch_index or 1),
        "list_start_page": start,
        "list_end_page": pages_used or end_page,
        "next_list_start_page": (
            (pages_used or start) + 1 if collected else None
        ),
        "city": city_name,
        "jobs": [],
        "skipped": skips,
        "raw_list_jobs": len(collected),
    }
    for item in candidates:
        card = job_schema.project_list_job(item)
        if not card.get("location") and city_name:
            card["location"] = city_name
        payload["jobs"].append(card)
    for item in candidates:
        eid = resolve_encrypt_job_id(item)
        if not eid:
            continue
        mark_skillver_seen_listed(
            skillver_seen,
            key=eid,
            job=item,
            query=target,
            catalog_names=set(catalog_names or []),
        )
    if skillver_seen_path:
        try:
            save_skillver_seen(skillver_seen_path, skillver_seen)
        except OSError as exc:
            log.warning(f"保存 seen 失败: {exc}")
    out_path = (
        list_batch_path
        or classify_input_path
        or default_list_batch_path(target, batch_index or 1)
    )
    write_json_file(out_path, payload)
    print(
        f"list 批次 {batch_index}: 页 {start}-{payload['list_end_page']} "
        f"原始 {len(collected)} → 待清洗/归类 {len(candidates)}；"
        f"已写 {out_path}"
    )
    if payload["next_list_start_page"]:
        print(f"下一批 --list-start-page {payload['next_list_start_page']}")
    else:
        print("已无更多列表页（本页无卡片）")
    return {
        "list_data": list_data,
        "list_batch_path": out_path,
        "classify_input_path": out_path,
        "classify_input": payload,
        "candidates": candidates,
    }


def run_skillver_details_from_decisions(
    *,
    position_binding,
    catalog_names,
    skillver_seen,
    skillver_seen_path,
    classify_input_path,
    decisions_path,
    detail_output,
    cdp_port,
    fmt,
    match_report_path=None,
    decision_report_path=None,
    city_fallback="",
    jobs_path=None,
    scrape_details_fn=None,
    min_details=None,
    catalog=None,
    query=None,
    unexported_path=None,
):
    """Apply Agent decisions then scrape all catalog-mapped details."""
    del min_details
    scrape_details_fn = scrape_details_fn or scrape_details
    target = str(query or (position_binding or {}).get("position_name") or "").strip()
    catalog_set = set(catalog_names)
    catalog_by_name = catalog_bindings_by_name(catalog)
    batches = resolve_decision_batches(classify_input_path, decisions_path)
    classify_input = {}
    jobs_meta = []
    expected_ids = []
    mapping = {}
    errors = []
    for cin, dec in batches:
        if cin:
            try:
                payload = load_json_file(cin)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"无法读取 classify-input: {exc}") from exc
            classify_input = payload
            batch_jobs = payload.get("jobs") or []
            batch_ids = [
                str(item.get("id") or "").strip()
                for item in batch_jobs
                if isinstance(item, dict) and str(item.get("id") or "").strip()
            ]
        else:
            batch_jobs = []
            batch_ids = []
        part, batch_errors = load_agent_decisions(
            dec,
            catalog_names=catalog_names,
            expected_ids=batch_ids,
        )
        errors.extend(batch_errors)
        mapping.update(part)
        jobs_meta.extend(item for item in batch_jobs if isinstance(item, dict))
        if batch_ids:
            expected_ids.extend(batch_ids)
        else:
            expected_ids.extend(part.keys())
    if errors:
        raise ValueError("决策文件不合契约: " + "; ".join(errors))
    city_name = normalize_location(
        city_fallback or classify_input.get("city") or ""
    )
    jobs_by_id = {}
    if jobs_path and os.path.isfile(jobs_path):
        try:
            stored = load_json_file(jobs_path)
        except (OSError, json.JSONDecodeError, ValueError):
            stored = {}
        for item in stored.get("jobs") or []:
            if not isinstance(item, dict):
                continue
            eid = resolve_encrypt_job_id(item)
            if eid:
                jobs_by_id[eid] = job_schema.project_list_job(item)
    for item in jobs_meta:
        if not isinstance(item, dict):
            continue
        eid = str(item.get("id") or "").strip()
        if not eid:
            continue
        base = dict(jobs_by_id.get(eid) or {})
        merged = {
            "title": base.get("title") or item.get("title") or "",
            "boss_name": base.get("boss_name") or item.get("company") or "",
            "boss_title": base.get("boss_title") or item.get("boss_title") or "",
            "salary": base.get("salary") or item.get("salary") or "",
            "location": normalize_location(
                base.get("location") or item.get("location") or ""
            ) or city_name,
            "tags": base.get("tags") or item.get("tags") or "",
            "job_link": base.get("job_link") or item.get("job_link") or "",
            "security_id": base.get("security_id") or item.get("security_id") or "",
            "lid": base.get("lid") or item.get("lid") or "",
            "encrypt_job_id": eid,
        }
        jobs_by_id[eid] = job_schema.project_list_job(merged)

    jobs = [jobs_by_id[eid] for eid in expected_ids if eid in jobs_by_id]
    batch_index = classify_input.get("batch_index")
    result = classify_list_jobs_from_agent(
        jobs,
        target,
        catalog_names,
        decisions_by_id=mapping,
        seen=skillver_seen,
        batch_index=batch_index,
    )
    current_jobs = persist_classifications(
        skillver_seen,
        result,
        target,
        catalog_names,
    )
    try:
        save_skillver_seen(skillver_seen_path, skillver_seen)
    except OSError as exc:
        log.warning(f"保存 seen 失败: {exc}")

    details = _load_existing_details_list(detail_output)
    seen_ids = skillver_seen_detail_ids(skillver_seen)
    baseline = skillver_count_details_all(skillver_seen)
    if current_jobs:
        details = scrape_details_fn(
            {"jobs": current_jobs},
            max_details=None,
            output_path=detail_output,
            cdp_port=cdp_port,
            fmt=fmt,
            seen_encrypt_job_ids=seen_ids,
            title_include=None,
            title_exclude=None,
            position_binding=position_binding,
            skillver_seen=skillver_seen,
            skillver_seen_path=skillver_seen_path,
            existing_details=details,
            skip_headhunter_filter=True,
            catalog_names=catalog_set,
            catalog_by_name=catalog_by_name,
            city_fallback=city_name,
            query=target,
            unexported_path=unexported_path or DEFAULT_SKILLVER_UNEXPORTED,
        )
    new_count = max(0, skillver_count_details_all(skillver_seen) - baseline)
    run_meta = {
        "run_id": make_skillver_run_id(target or "query"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "query": target,
        "target_position_name": target,
        "batch_index": batch_index,
        "classify_input_path": classify_input_path,
        "decisions_path": decisions_path,
        "details_new_this_run": new_count,
        "details_count": skillver_count_details_all(skillver_seen),
        "agent_stats": result.get("agent_stats") or {},
    }
    if decision_report_path:
        write_decision_report(
            decision_report_path,
            {**run_meta, "decisions": result.get("decisions") or []},
        )
    if match_report_path:
        skips = [
            {**dec, "reason": dec.get("skip_reason")}
            for dec in (result.get("none") or [])
        ]
        write_match_skip_report(
            match_report_path,
            {
                "position": position_binding,
                "skipped_count": len(skips),
                "skipped": skips,
            },
        )
    print(
        f"details-from-decisions: 已映射 {len(current_jobs)} / "
        f"none {len(result.get('none') or [])}；"
        f"本批新增详情 {new_count}"
    )
    return {
        "details": details,
        "run_meta": run_meta,
        "decisions": result.get("decisions") or [],
        "match_skips": result.get("none") or [],
        "current_jobs": current_jobs,
    }


def parse_title_patterns(raw):
    """Split comma / Chinese-comma / pipe separated title filter patterns."""
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    parts = re.split(r"[,，|/]+", text)
    return [part.strip() for part in parts if part and part.strip()]


def title_passes_filters(title, include_patterns=None, exclude_patterns=None):
    """Return True when title satisfies include (any) and exclude (none) patterns."""
    text = str(title or "")
    includes = [p for p in (include_patterns or []) if p]
    excludes = [p for p in (exclude_patterns or []) if p]
    if includes and not any(pattern in text for pattern in includes):
        return False
    if excludes and any(pattern in text for pattern in excludes):
        return False
    return True


def filter_jobs_by_title(jobs, include_patterns=None, exclude_patterns=None):
    """Filter list cards by job title before detail scraping.

    Returns:
        (kept_jobs, removed_count)
    """
    includes = list(include_patterns or [])
    excludes = list(exclude_patterns or [])
    if not jobs:
        return [], 0
    if not includes and not excludes:
        return list(jobs), 0
    kept = []
    removed = 0
    for job in jobs:
        title = job.get("title", "") if isinstance(job, dict) else ""
        if title_passes_filters(title, includes, excludes):
            kept.append(job)
        else:
            removed += 1
    return kept, removed


# 面向「AI产品经理」校招盘点的默认标题规则（可通过 CLI 覆盖）
DEFAULT_PM_TITLE_INCLUDE = ("产品经理", "产品运营")
DEFAULT_PM_TITLE_EXCLUDE = (
    "工程师", "开发", "算法", "前端", "后端", "测试", "研发",
    "销售", "老师", "猎头", "架构师", "运维", "数据科学",
)


def scrape_details(list_data, max_details=None, output_path=None,
                   cdp_port=DEFAULT_CDP_PORT, fmt="json",
                   seen_encrypt_job_ids=None,
                   title_include=None, title_exclude=None,
                   position_binding=None,
                   skillver_seen=None,
                   skillver_seen_path=None,
                   existing_details=None,
                   skip_headhunter_filter=False,
                   catalog_names=None,
                   catalog_by_name=None,
                   city_fallback="",
                   query="",
                   unexported_path=None):
    jobs = list(list_data.get("jobs", []) or [])
    city_name = normalize_location(
        city_fallback or (list_data or {}).get("city") or ""
    )
    if skip_headhunter_filter:
        removed_headhunters = 0
    else:
        jobs, removed_headhunters = filter_out_headhunter_jobs(jobs)
    if removed_headhunters:
        print(
            f"已过滤猎头/人力资源中介岗位 {removed_headhunters} 条，"
            f"剩余 {len(jobs)} 条可抓详情"
        )
    jobs, removed_title = filter_jobs_by_title(
        jobs, include_patterns=title_include, exclude_patterns=title_exclude,
    )
    if removed_title:
        print(
            f"已按标题过滤 {removed_title} 条，"
            f"剩余 {len(jobs)} 条可抓详情"
        )
        if title_include:
            print(f"  标题需包含其一: {' / '.join(title_include)}")
        if title_exclude:
            print(f"  标题排除含: {' / '.join(title_exclude)}")
    if seen_encrypt_job_ids is None:
        seen_encrypt_job_ids = set()
    jobs, skipped_seen = filter_jobs_missing_details(jobs, seen_encrypt_job_ids)
    if skipped_seen:
        print(
            f"已跳过已抓详情岗位 {skipped_seen} 条（encrypt_job_id / seen），"
            f"剩余 {len(jobs)} 条"
        )
    # max_details = how many NEW detail pages to open in this call
    if max_details is not None:
        jobs = jobs[: max(0, int(max_details))]
    if not output_path:
        output_path = default_output_path("details")

    results = list(existing_details or [])
    already = len(results)
    print(f"\n=== 抓取岗位详情 ({len(jobs)} 个候选；已有 {already} 条) ===\n")
    seen_links = {
        str(item.get("job_link") or item.get("link") or "")
        for item in results
        if isinstance(item, dict) and (item.get("job_link") or item.get("link"))
    }

    for idx, job in enumerate(jobs):
        link = job.get("job_link", "")
        title = job.get("title", "")
        company = job.get("boss_name", "")
        if not link:
            continue

        # 按 link 去重
        if link in seen_links:
            print(f"[{idx+1}/{len(jobs)}] 跳过重复: {company} - {title}")
            continue
        seen_links.add(link)

        eid = resolve_encrypt_job_id(job)
        if eid and eid in seen_encrypt_job_ids:
            print(f"[{idx+1}/{len(jobs)}] 跳过已抓详情: {company} - {title}")
            continue

        t0 = time.time()
        print(f"[{idx+1}/{len(jobs)}] {company} - {title}")

        incr_request()

        # 每个详情页用新 session 避免检测；自动化 target 默认后台创建。
        ws = CDPSession(cdp_port)
        tid, sid = create_page_session(ws)

        detail_url = build_detail_url(job)
        ws.send("Page.navigate", {"url": detail_url}, sid)
        print(f"  加载页面...")
        time.sleep(random.uniform(5, 10))

        # 模拟人类阅读详情页的滚动行为
        scroll_count = random.randint(3, 7)
        print(f"  模拟滚动 ({scroll_count} 次)...")
        for i in range(scroll_count):
            if random.random() < 0.12:
                # 偶尔往上回滚（回看内容）
                delta = -random.randint(80, 200)
            else:
                delta = random.randint(200, 600)
            ws.eval_js(f"window.scrollBy(0,{delta})", sid)
            # 有时快滚，有时停下来"阅读"
            if random.random() < 0.35:
                time.sleep(random.uniform(2.0, 5.0))
            else:
                time.sleep(random.uniform(0.8, 1.8))

        # 偶尔模拟鼠标移动
        if random.random() < 0.5:
            ws.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": random.randint(200, 800),
                "y": random.randint(200, 600)
            }, sid)
            time.sleep(random.uniform(0.5, 1.5))

        print(f"  提取 JD...")
        val = ws.eval_js(EXTRACT_DETAIL_JS, sid)
        try:
            d = json.loads(val) if isinstance(val, str) else {"jd": "", "tags": []}
        except (json.JSONDecodeError, ValueError, TypeError):
            d = {"jd": "", "tags": []}

        try:
            fields = extract_detail_fields(d)
            d["jd"] = fields["jd"]
            d["boss_active_status"] = resolve_boss_active_status(
                list_status=job.get("boss_active_status", ""),
                detail_status=fields["boss_active_status"],
            )
            d["location"] = fields.get("location") or d.get("location") or ""
        except DetailLoginRequiredError as exc:
            ws.send("Target.closeTarget", {"targetId": tid})
            ws.close()
            raise RuntimeError(
                "BOSS detail login expired; stopped before writing truncated JD data"
            ) from exc
        except DetailExtractionError as exc:
            print(f"  跳过无效详情页: {exc}")
            ws.send("Target.closeTarget", {"targetId": tid})
            ws.close()
            continue

        job_pos = str(job.get("_classified_position") or "").strip()
        binding = None
        if catalog_by_name and job_pos and job_pos in catalog_by_name:
            binding = catalog_by_name[job_pos]
        elif position_binding and position_binding.get("job_intent_id"):
            binding = position_binding
        elif job_pos:
            binding = {
                "position_name": job_pos,
                "job_intent_id": "",
                "job_intent_label": "",
            }
        else:
            binding = position_binding
        detail = build_detail_record(
            job, d, position=binding, city_fallback=city_name
        )
        results.append(detail)
        detail_eid = detail.get("encrypt_job_id") or eid
        if detail_eid:
            seen_encrypt_job_ids.add(detail_eid)

        if d.get("tags"):
            print(f"  技能: {', '.join(d['tags'])}")
        if d.get("boss_active_status"):
            print(f"  活跃: {d['boss_active_status']}")
        print(f"  JD: {len(d.get('jd',''))} 字 ({time.time()-t0:.0f}s)")

        # 每抓完一个详情就写入，异常退出也能保留
        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

        # Skillver seen：详情成功后 has_details=true, exported=false（已导出则保留 true）
        if skillver_seen is not None and skillver_seen_path and detail_eid:
            try:
                mark_skillver_seen_scraped(
                    skillver_seen,
                    key=detail_eid,
                    job_id=str(detail.get("job_id") or ""),
                    position_name=str(
                        (binding or {}).get("position_name")
                        or job_pos
                        or ""
                    ),
                    catalog_names=set(catalog_names) if catalog_names else None,
                )
                save_skillver_seen(skillver_seen_path, skillver_seen)
                if unexported_path:
                    add_skillver_unexported(
                        key=detail_eid,
                        query=query,
                        details_path=output_path,
                        position_name=str(
                            (binding or {}).get("position_name")
                            or job_pos
                            or ""
                        ),
                        path=unexported_path,
                    )
            except (OSError, TypeError, ValueError) as exc:
                log.warning(f"写入 seen 失败（详情已保存）: {exc}")

        ws.send("Target.closeTarget", {"targetId": tid})
        ws.close()
        # 详情页间隔加大，随机 10-25 秒
        gap = random.uniform(10, 25)
        print(f"  等待 {gap:.0f}s 后抓下一个...\n")
        time.sleep(gap)

    # 最终保存（dirname 为空时回退到当前目录，与循环内/其它写文件处保持一致）
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n详情已保存: {output_path}")
    return results


def parse_jobs_eval_value(value):
    return parse_api_jobs_eval_value(value)


def has_usable_smoke_jobs(jobs):
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if (
            job.get("title")
            and job.get("salary")
            and job.get("job_link")
        ):
            return True
    return False


def run_smoke_test(cdp_port=DEFAULT_CDP_PORT):
    """Run a real browser/API smoke test without writing result files."""
    if not require_runtime_dependencies("requests", "websocket"):
        return 1

    try:
        cdp = CDPSession(cdp_port)
        city_name, city_code = resolve_city(DEFAULT_CITY_INPUT)
        search_url = build_search_url(LOGIN_PROBE_QUERY, city_code, 1, {})
        tid, sid = create_page_session(cdp)

        print(f"打开 BOSS 搜索页: {LOGIN_PROBE_QUERY} @ {city_name}")
        cdp.send("Page.navigate", {"url": search_url}, sid)
        time.sleep(4)
        api_url = f"{API_JOB_LIST_PATH}?{urlencode({'scene': '1', 'query': LOGIN_PROBE_QUERY, 'city': city_code, 'page': 1, 'pageSize': 5})}"
        api_js = FETCH_API_JS_TEMPLATE.replace("__API_URL__", api_url)
        jobs = parse_jobs_eval_value(cdp.eval_js(api_js, sid))
        cdp.send("Target.closeTarget", {"targetId": tid})
        cdp.close()

        if has_usable_smoke_jobs(jobs):
            sample = next(job for job in jobs if job.get("salary") and job.get("job_link"))
            print(f"✅ Smoke test 通过: {sample.get('title')} | {sample.get('salary')}")
            return 0
        print("❌ Smoke test 未拿到可用职位；请检查登录态或 BOSS API 返回")
        return 1
    except (requests.ConnectionError, requests.Timeout, KeyError,
            json.JSONDecodeError, websocket.WebSocketException, TimeoutError) as e:
        print(f"❌ Smoke test 失败: {e}")
        return 1


# ============================================================
# --check 环境检查
# ============================================================
def run_check(cdp_port=DEFAULT_CDP_PORT):
    """运行环境诊断：uv → 安装（如需要）→ uv sync → CDP → 登录。"""
    print("=" * 50)
    print("  BOSS直聘 CDP 环境检查")
    print("=" * 50)
    print()

    all_pass = True
    env = _load_ensure_uv_env()
    if env is None:
        print("[1/5] uv...")
        print("  ❌ 找不到 scripts/ensure_uv_env.py")
        print()
        print("❌ 部分检查未通过，请修复后重试")
        print()
        return 1

    print("[1/5] uv...")
    uv = env.which_uv()
    if uv:
        print(f"  ✅ 已安装: {uv}")
    else:
        uv = env.install_uv()
        if uv:
            print(f"  ✅ 已安装: {uv}")
        else:
            print("  ❌ 无法安装 uv")
            all_pass = False

    print("[2/5] uv sync（本 skill 的 .venv）...")
    if not all_pass:
        print("  ❌ 跳过 — 没有 uv")
    elif not env.uv_sync(uv):
        all_pass = False
    elif not env.running_in_skill_venv():
        env.reexec_with_uv(uv)

    print("[3/5] Python 依赖...")
    deps_ok = False
    if all_pass:
        deps_ok = require_runtime_dependencies("websocket", "requests")
        if requests is not None:
            print("  ✅ requests 可导入")
        if websocket is not None:
            print("  ✅ websocket 可导入")
        if deps_ok:
            print("  ✅ 依赖完整")
        else:
            all_pass = False
    else:
        print("  ❌ 跳过 — 项目环境未就绪")

    print("[4/5] CDP 端口连通性...")
    if requests is None:
        print("  ❌ 跳过 — 缺少 requests")
        all_pass = False
    else:
        try:
            resp = requests.get(f"http://127.0.0.1:{cdp_port}/json/version", timeout=5)
            data = resp.json()
            browser = data.get("Browser", "未知")
            print(f"  ✅ 通过 — 浏览器 {browser}")
        except (requests.ConnectionError, requests.Timeout):
            print(f"  ❌ 失败 — 无法连接 127.0.0.1:{cdp_port}")
            print("     请先启动浏览器 CDP: python scripts/chrome_cdp.py --setup-chrome")
            all_pass = False
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  ❌ 失败 — CDP 响应异常: {e}")
            all_pass = False

    print("[5/5] BOSS直聘登录状态...")
    if not deps_ok:
        print("  ❌ 跳过 — 缺少运行依赖")
        all_pass = False
    else:
        try:
            login_result = check_login_state(cdp_port)
            if login_result.status is LoginProbeStatus.AVAILABLE:
                print("  ✅ 已登录")
            elif login_result.status is LoginProbeStatus.EMPTY:
                print(f"  ⚠️  {describe_login_probe_result(login_result)}")
                all_pass = False
            else:
                print(f"  ❌ {describe_login_probe_result(login_result)}")
                all_pass = False
        except Exception as e:
            print(f"  ❌ 检测失败: {e}")
            all_pass = False

    print()
    if all_pass:
        print("✅ 所有检查通过，可以开始抓取")
    else:
        print("❌ 部分检查未通过，请修复后重试")
    print()

    return 0 if all_pass else 1


# ============================================================
# --setup-chrome 自动启动
# ============================================================
def prepare_cdp_profile(copy_login_state=False, reset=False):
    """Prepare an isolated persistent Chrome profile for CDP."""
    cdp_data_dir = DEFAULT_CDP_DATA_DIR
    cdp_default = os.path.join(cdp_data_dir, "Default")

    if reset and os.path.exists(cdp_data_dir):
        shutil.rmtree(cdp_data_dir)

    os.makedirs(cdp_default, exist_ok=True)

    copied = 0
    if copy_login_state:
        default_profile = DEFAULT_PROFILE_DIR
        default_default = os.path.join(default_profile, "Default")
        cookie_files = []
        for rel_dir in ("", "Network"):
            for name in ("Cookies", "Cookies-journal", "Cookies-wal", "Cookies-shm"):
                rel_path = os.path.join(rel_dir, name) if rel_dir else name
                cookie_files.append((os.path.join(default_default, rel_path), os.path.join(cdp_default, rel_path)))

        copy_files = [(os.path.join(default_profile, "Local State"), os.path.join(cdp_data_dir, "Local State"))]
        copy_files.extend(cookie_files)
        for src, dst in copy_files:
            if os.path.exists(src):
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                    copied += 1
                except Exception as e:
                    print(f"  ⚠️  复制 {os.path.basename(src)} 失败: {e}")

    return {
        "path": cdp_data_dir,
        "copied": copied,
        "reset": reset,
        "copy_login_state": copy_login_state,
    }


def is_cdp_ready(cdp_port):
    try:
        resp = requests.get(f"http://127.0.0.1:{cdp_port}/json/version", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def is_chrome_command(command):
    lower = (command or "").lower()
    return any(token in lower for token in (
        "google chrome",
        "google-chrome",
        "chromium",
        "chrome.exe",
        "msedge.exe",
        "microsoft-edge",
        "microsoft edge",
    ))


def normalize_profile_path(path):
    clean = (path or "").strip("\"'")
    if platform.system() == "Windows":
        return ntpath.normcase(ntpath.normpath(clean))
    return os.path.realpath(os.path.expanduser(clean))


def extract_user_data_dir(command):
    match = re.search(r"--user-data-dir=(\"[^\"]+\"|'[^']+'|\S+)", command or "")
    if not match:
        return None
    return match.group(1).strip("\"'")


def iter_chrome_process_commands():
    """Return (pid, command line) tuples for Chrome-like browser processes."""
    if platform.system() == "Windows":
        ps_script = (
            "Get-CimInstance Win32_Process -Filter \"name = 'msedge.exe' OR name = 'chrome.exe'\" | "
            "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
        )
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            return []
        if not r.stdout.strip():
            return []
        try:
            data = json.loads(r.stdout)
        except (json.JSONDecodeError, ValueError):
            return []
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return []
        processes = []
        for item in data:
            command = item.get("CommandLine") or ""
            if not is_chrome_command(command):
                continue
            try:
                processes.append((int(item.get("ProcessId")), command))
            except (TypeError, ValueError):
                continue
        return processes

    try:
        r = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, timeout=5)
    except Exception:
        return []

    processes = []
    for line in r.stdout.splitlines():
        if not is_chrome_command(line):
            continue
        try:
            pid_text, command = line.strip().split(None, 1)
            pid = int(pid_text)
        except ValueError:
            continue
        processes.append((pid, command))
    return processes


def chrome_pids_for_user_data_dir(user_data_dir):
    """Return Chrome PIDs using the given user-data-dir."""
    pids = []
    real_dir = normalize_profile_path(user_data_dir)
    for pid, command in iter_chrome_process_commands():
        if "--user-data-dir=" not in command:
            continue
        path = extract_user_data_dir(command)
        if path and normalize_profile_path(path) == real_dir:
            pids.append(pid)
    return pids


def chrome_user_data_dirs_for_cdp_port(cdp_port):
    """Return user-data-dir paths for Chrome processes using the given CDP port."""
    dirs = []
    port_arg = f"--remote-debugging-port={cdp_port}"
    for _pid, command in iter_chrome_process_commands():
        if port_arg not in command:
            continue
        path = extract_user_data_dir(command)
        if path:
            dirs.append(path)
    return dirs


def cdp_port_uses_profile(cdp_port, cdp_data_dir):
    expected = normalize_profile_path(cdp_data_dir)
    return any(normalize_profile_path(path) == expected for path in chrome_user_data_dirs_for_cdp_port(cdp_port))


def terminate_process(pid, force=False):
    if platform.system() == "Windows":
        cmd = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            cmd.append("/F")
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        return
    os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)


def stop_cdp_chrome(cdp_data_dir):
    """Stop only Chrome processes that use the scraper's isolated profile."""
    pids = chrome_pids_for_user_data_dir(cdp_data_dir)
    if not pids:
        return 0

    for pid in pids:
        try:
            terminate_process(pid, force=False)
        except ProcessLookupError:
            pass
    for _ in range(10):
        time.sleep(0.5)
        if not chrome_pids_for_user_data_dir(cdp_data_dir):
            return len(pids)

    for pid in chrome_pids_for_user_data_dir(cdp_data_dir):
        try:
            terminate_process(pid, force=True)
        except ProcessLookupError:
            pass
    time.sleep(0.5)
    return len(pids)


def wait_for_cdp(cdp_port, timeout=30):
    print("等待 CDP 可用", end="")
    for _ in range(timeout):
        time.sleep(1)
        print(".", end="", flush=True)
        if is_cdp_ready(cdp_port):
            print(f"\n✅ CDP 已就绪 (端口 {cdp_port})")
            return True
    print(f"\n❌ 等待超时 ({timeout}s)，CDP 未就绪")
    print(f"   请手动检查浏览器是否启动，端口 {cdp_port} 是否开放")
    return False


def launch_chrome(cmd):
    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if platform.system() == "Windows":
        creationflags = 0
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        if creationflags:
            kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def run_setup_chrome(cdp_port=DEFAULT_CDP_PORT, copy_login_state=False,
                     reset_profile=False, wait_login=True,
                     login_timeout=DEFAULT_LOGIN_TIMEOUT):
    """自动配置并启动 Chrome CDP 模式"""
    if not require_runtime_dependencies("requests"):
        return 1

    print("=" * 50)
    print("  设置浏览器 CDP 调试模式（Windows 优先 Edge）")
    print("=" * 50)
    print()

    profile = prepare_cdp_profile(copy_login_state=copy_login_state, reset=reset_profile)
    cdp_data_dir = profile["path"]
    print(f"✅ 使用独立浏览器 profile: {cdp_data_dir}")
    if reset_profile:
        print("   已按 --reset-chrome-profile 重建 profile")
    if copy_login_state:
        print(f"   已复制 {profile['copied']} 个登录态文件（Local State + Cookie 相关文件）")
    else:
        print("   默认、首次启动、重复启动都不复制主浏览器 Cookie；首次使用请在此专用浏览器中登录 zhipin.com")

    if is_cdp_ready(cdp_port):
        if cdp_port_uses_profile(cdp_port, cdp_data_dir):
            print(f"\n✅ CDP 已就绪 (端口 {cdp_port})")
            if wait_login:
                return 0 if wait_for_login(cdp_port, timeout=login_timeout) else 1
            return 0
        print(f"\n❌ 端口 {cdp_port} 已被其他浏览器 CDP profile 占用")
        print(f"   请关闭旧 CDP 浏览器，或改用 --cdp-port 指定其他端口")
        return 1

    stopped = stop_cdp_chrome(cdp_data_dir)
    if stopped:
        print(f"\n已关闭 {stopped} 个旧的 BOSS CDP 浏览器进程")

    print(f"\n启动浏览器 (CDP 端口: {cdp_port})...")
    cmd = [
        DEFAULT_CHROME_PATH,
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={cdp_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--remote-allow-origins=*",
    ]
    launch_chrome(cmd)

    if not wait_for_cdp(cdp_port):
        return 1

    print()
    print("浏览器已启动。请在这个专用窗口中登录 zhipin.com。")
    if wait_login:
        print()
        if not wait_for_login(cdp_port, timeout=login_timeout):
            return 1
    print()
    print(f"示例:")
    print(f"  uv run python3 scripts/scrape_list.py --query \"阶跃星辰\" --city 上海")
    print(f"  uv run python3 scripts/chrome_cdp.py --check")
    print(f"  uv run python3 scripts/chrome_cdp.py --stop-chrome")
    print()
    return 0


def run_stop_chrome():
    """关闭 BOSS 专用 CDP 浏览器（按隔离 user-data-dir 精准匹配，不碰主浏览器）。"""
    if not require_runtime_dependencies("requests"):
        return 1

    print("=" * 50)
    print("  关闭 BOSS 专用 CDP 浏览器")
    print("=" * 50)
    print()

    # 只定位 scraper 专用 profile 目录，不复制、不重置
    profile = prepare_cdp_profile(copy_login_state=False, reset=False)
    cdp_data_dir = profile["path"]

    stopped = stop_cdp_chrome(cdp_data_dir)
    if stopped:
        print(f"\n✅ 已关闭 {stopped} 个 BOSS 专用浏览器进程 (profile: {cdp_data_dir})")
    else:
        print(f"\nℹ️  没有找到运行中的 BOSS 专用浏览器进程 (profile: {cdp_data_dir})")
    print()
    print("提示：仅关闭 scraper 隔离 profile 的浏览器，不影响你的主浏览器。")
    print()
    return 0


# ============================================================
# 批内多岗编排（批间休息由人工控制）
# ============================================================
def ensure_scrape_login(cdp_port):
    """Probe login once; exit-style return code semantics via raised SystemExit not used — return result."""
    print("检测登录状态...")
    login_result = check_login_state(cdp_port)
    if login_result.status is LoginProbeStatus.UNAUTHENTICATED:
        print("❌ 未检测到 BOSS直聘登录状态。请先在专用浏览器中登录 zhipin.com。")
        print("   可运行 --check 检查环境，或 --setup-chrome 启动浏览器。")
        return False
    if login_result.status is LoginProbeStatus.RESTRICTED:
        print(f"❌ {describe_login_probe_result(login_result)}，已停止抓取。")
        print("   请先在浏览器中完成验证或稍后再试，不要重复运行登录探测。")
        return False
    if login_result.status is LoginProbeStatus.RESPONSE_ERROR:
        print(f"❌ {describe_login_probe_result(login_result)}，已停止抓取。")
        return False
    if login_result.status is LoginProbeStatus.EMPTY:
        print(f"⚠️  {describe_login_probe_result(login_result)}；继续执行实际职位搜索。\n")
    else:
        print("✅ 已登录\n")
    return True


def filters_from_args(args):
    filters = {}
    for key in ["scale", "stage", "salary", "experience", "degree", "industry"]:
        val = getattr(args, key, None)
        if not val:
            continue
        if key in MULTI_SELECT_FILTER_KEYS:
            codes = normalize_filter_codes(val)
            if codes:
                filters[key] = codes
            continue
        filters[key] = val
    filters = normalize_filters_dict(filters)
    job_type = getattr(args, "job_type", None)
    if job_type:
        job_type_code = resolve_job_type(job_type)
        if job_type_code:
            filters["jobType"] = job_type_code
            filters = normalize_filters_dict(filters)
    return filters


def add_filter_arguments(parser):
    parser.add_argument("--scale", action="append", default=None)
    parser.add_argument("--stage", default=None)
    parser.add_argument("--salary", default=None)
    parser.add_argument("--experience", action="append", default=None)
    parser.add_argument("--degree", default=None)
    parser.add_argument("--industry", default=None)
    parser.add_argument("--job-type", default=None)


def close_chrome_if_requested(flag):
    if not flag:
        return
    profile = prepare_cdp_profile(copy_login_state=False, reset=False)
    stopped = stop_cdp_chrome(profile["path"])
    if stopped:
        print(f"\n🧹 已按 --close-chrome 关闭 BOSS 专用浏览器进程：{stopped} 个")
    else:
        print("\nℹ️  --close-chrome 未发现运行中的 BOSS 专用浏览器进程")
