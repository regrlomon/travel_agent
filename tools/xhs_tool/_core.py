import os
import sys
import time
import random
from pathlib import Path


def _load_env():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if key and val and key not in os.environ:
            os.environ[key] = val


_load_env()

SPIDER_XHS_DIR = str(Path(__file__).parent / "Spider_XHS")
DEFAULT_COUNT   = int(os.environ.get("XHS_DEFAULT_COUNT", "8"))
DEFAULT_CONTENT = os.environ.get("XHS_DEFAULT_CONTENT", "true").lower() == "true"


def _ensure_ready():
    if not os.path.isdir(SPIDER_XHS_DIR):
        raise RuntimeError(
            f"找不到 Spider_XHS 目录（{SPIDER_XHS_DIR}）\n"
            "请在 .env 中设置 XHS_SPIDER_DIR"
        )
    node_modules = os.path.join(SPIDER_XHS_DIR, "node_modules")
    if not os.path.isdir(node_modules):
        import subprocess
        subprocess.run(["npm", "install", "--prefix", SPIDER_XHS_DIR], check=True)
    os.chdir(SPIDER_XHS_DIR)
    if SPIDER_XHS_DIR not in sys.path:
        sys.path.insert(0, SPIDER_XHS_DIR)


def _parse_note(item: dict) -> dict:
    note       = item.get("note_card") or item
    note_id    = note.get("id") or item.get("id") or ""
    interact   = note.get("interact_info") or {}
    user       = note.get("user") or {}
    xsec_token = item.get("xsec_token") or ""
    url = (
        f"https://www.xiaohongshu.com/explore/{note_id}"
        f"?xsec_token={xsec_token}&xsec_source=pc_search"
        if note_id else ""
    )
    return {
        "title":   note.get("display_title") or note.get("title") or "",
        "author":  user.get("nickname") or "",
        "likes":   interact.get("liked_count") or note.get("like_count") or 0,
        "url":     url,
        "content": "",
    }


def _fetch_content(pc_api, note: dict, cookie: str) -> str:
    if not note["url"]:
        return ""
    try:
        success, _, res_json = pc_api.get_note_info(note["url"], cookie)
        if not success or not res_json:
            return ""
        items = (res_json.get("data") or {}).get("items") or []
        if not items:
            return ""
        return items[0].get("note_card", {}).get("desc") or ""
    except Exception:
        return ""


def search_xhs(
    keyword: str,
    count: int = DEFAULT_COUNT,
    with_content: bool = DEFAULT_CONTENT,
    cookie: str = "",
) -> list[dict]:
    """
    搜索小红书笔记。

    Args:
        keyword:      搜索关键词
        count:        返回条数
        with_content: 是否同时获取正文
        cookie:       留空则读 .env / 环境变量 XHS_COOKIE

    Returns:
        list of {title, author, likes, url, content}
    """
    cookie = cookie or os.environ.get("XHS_COOKIE", "")
    if not cookie:
        raise ValueError("缺少 XHS_COOKIE，请在 .env 中配置")

    _ensure_ready()

    try:
        from apis.xhs_pc_apis import XHS_Apis
    except ImportError as e:
        raise ImportError(f"无法导入 Spider_XHS: {e}") from e

    pc_api = XHS_Apis()
    success, msg, note_list = pc_api.search_some_note(keyword, count, cookie)
    if not success:
        raise RuntimeError(f"搜索失败: {msg}")

    results = [_parse_note(item) for item in note_list]

    if with_content:
        for note in results:
            note["content"] = _fetch_content(pc_api, note, cookie)
            time.sleep(random.uniform(1.0, 2.0))

    return results
