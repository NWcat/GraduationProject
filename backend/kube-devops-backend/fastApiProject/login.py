import time
import requests
import re
import os
import json
from urllib.parse import unquote

# --- 配置区 ---
# 1. 你的完整 Cookie
RAW_COOKIE = os.environ.get(
    'SANGFOR_COOKIE') or "37rD_2132_saltkey=QNGny0Zr; 37rD_2132_lastvisit=1768352439; bbs_uid=1489223; bbs_log_behavior_product=BBS; bbs_log_behavior_url=http%3A%2F%2Fitgw.sangfor.com%2Fplatform%2Flog%2Fmessage%2FlogBehavior; 37rD_2132_sid=Ux8Ihc; 37rD_2132_lastact=1768356490%09sf.php%09infothread; checkRequestString=d08d4b943cb5fac43b69459b96a6910ce73839aaUlEPVgMCAgUDUlYMAFFRVFQKCQ0DEFJIJEdLHUFUAFoXZXNiFFAOA1RTDlcIBF8JBVEBDQFXCwBQDwEJAgJWBVcIC1wDUA; TY_SESSION_ID=13f87d09-e273-454a-bab7-300f600c53bb; Hm_lvt_bfc48d3eca217cebc173ecb352d01045=1768356042; Hm_lpvt_bfc48d3eca217cebc173ecb352d01045=1768356490; HMACCOUNT=A6BC54082AB125B2; 37rD_2132_wxscan_key=dviooh6o2iokv4qw; 37rD_2132_ulastactivity=f715ERnwwjebfcPTSbQPHgDjvcR%2FSU8eCGI8leRAMKKtrMBI8WBF; 37rD_2132_auth=3f01rL3wPUkElXa7Rl7OthewlRruxpPeQdpdtmRatxg8vA390KTf5wYB2UoFUhbb0NwBQYWn9MfAAfZdujNZQro0dQA5; sfloginstatuser=20260114_1489223; 37rD_2132_connect_is_bind=0; ordinaryLoginReward1489223=20260114"

# 2. 飞书 Webhook 地址
FEISHU_WEBHOOK = os.environ.get(
    'FS_WEBHOOK') or "https://open.feishu.cn/open-apis/bot/v2/hook/42dc4285-e80e-4242-baa9-766477a1cdc3"

# 3. 【保底令牌】你之前抓包成功的固定 Hash
BAODI_HASH = "939ctlO0SeMYgQ4Ja%252FNJrkP%252BdwIIBasZ4%252Fmj%252FYTEevmR1SgA9Q"


def get_realtime_hash(session, headers):
    """
    模拟浏览器点击签到时的探测逻辑
    """
    timestamp = int(time.time() * 1000)
    referer_url = "https://bbs.sangfor.com.cn/plugin.php?id=info:index"

    # 建立 Referer 关联
    try:
        session.get(referer_url, headers=headers, timeout=10)
    except:
        pass

    probe_url = f"https://bbs.sangfor.com.cn/plugin.php?id=sign:index&op=share&noload=1&_={timestamp}"

    ajax_headers = headers.copy()
    ajax_headers.update({
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/plain, */*",
        "Referer": referer_url
    })

    print(f"🔍 正在从状态探测接口抓取实时令牌...")
    try:
        res = session.get(probe_url, headers=ajax_headers, timeout=10)

        # 1. 匹配 HTML 片段中的 hash=
        match = re.search(r'hash=([a-zA-Z0-9%]{40,85})', res.text)
        if match:
            return match.group(1)

        # 2. 备选匹配：匹配 JS 变量定义
        match_js = re.search(r'["\']hash["\']\s*[:=]\s*["\']([a-zA-Z0-9%]{40,85})["\']', res.text)
        if match_js:
            return match_js.group(1)

        # 3. 状态判定
        if "已经签过" in res.text or "今日已签" in res.text:
            return "ALREADY_SIGNED"

    except Exception as e:
        print(f"⚠️ 探测接口请求出错: {e}")

    return None


def start_sign():
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
        "Origin": "https://bbs.sangfor.com.cn"
    }

    # 装载 Cookie
    for item in RAW_COOKIE.split('; '):
        if '=' in item:
            name, value = item.split('=', 1)
            session.cookies.set(name, value.strip(), domain='bbs.sangfor.com.cn')

    # 第一步：尝试获取动态 Hash
    target_hash = get_realtime_hash(session, headers)

    # 结果判定与保底逻辑
    if target_hash == "ALREADY_SIGNED":
        print("✅ 状态确认：今日已完成签到，无需重复获取令牌。")
        return

    if not target_hash:
        print("⚠️ 无法获取动态 Hash，启用【固定令牌兜底】继续尝试...")
        target_hash = BAODI_HASH
    else:
        print(f"✅ 成功捕获最新 Hash: {target_hash[:20]}...")

    # 第二步：提交签到
    print("🚀 正在提交签到 POST 请求...")
    sign_url = "https://bbs.sangfor.com.cn/plugin.php?id=sign:index&op=sign"
    payload = f"hash={target_hash}&ajaxdata=json"

    headers.update({
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://bbs.sangfor.com.cn/plugin.php?id=info:index"
    })

    try:
        response = session.post(sign_url, headers=headers, data=payload, timeout=20)
        res_data = response.json()

        if res_data.get('success'):
            print(f"🎊 签到成功！获得 {res_data.get('sbean', 0)} S豆。")
        else:
            # 如果是保底 Hash 导致的问题，这里会打印服务器返回的具体错误
            print(f"📢 服务器反馈: {res_data.get('msg', '未知错误')}")

    except Exception as e:
        print(f"❌ 签到提交异常: {e}")


if __name__ == "__main__":
    start_sign()