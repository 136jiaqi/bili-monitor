import requests
import json
import time
import os
from datetime import datetime, timedelta

# ================= 从 GitHub Secrets 安全读取 =================
# 确保你已经在 GitHub Settings -> Secrets -> Actions 中配置了这两个变量
BILI_UID = os.environ.get("BILI_UID")
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK")
LIKE_THRESHOLD = 50  # 预警阈值：点赞一小时增长超过此数值则报警
# ============================================================

def get_video_list():
    """获取账号下所有视频数据"""
    if not BILI_UID:
        print("错误：未检测到 BILI_UID，请检查 GitHub Secrets 配置")
        return []
        
    videos = []
    page = 1
    # 模拟浏览器请求头，降低被 B 站拦截的风险
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Referer": f"https://space.bilibili.com/{BILI_UID}",
        "Origin": "https://space.bilibili.com"
    }

    try:
        while True:
            # 尝试抓取视频列表接口
            url = f"https://api.bilibili.com/x/space/wbi/arc/search?mid={BILI_UID}&ps=30&tid=0&pn={page}&keyword=&order=pubdate"
            print(f"正在抓取第 {page} 页视频列表...")
            response = requests.get(url, headers=headers, timeout=10).json()
            
            if response.get('code') == 0:
                vlist = response['data']['list']['vlist']
                if not vlist:
                    break
                for v in vlist:
                    videos.append({
                        "title": v['title'],
                        "bvid": v['bvid'],
                        "created": v['created'],
                        "play": v['play'],
                        "comment": v['video_review'],
                        "like": 0  # 初始设为0，稍后获取详情
                    })
                page += 1
                if page > 10: break # 最多抓取 10 页，约 300 个视频
                time.sleep(1) # 强制休眠 1 秒，防止请求过快
            else:
                print(f"B站接口返回异常: {response.get('message')}")
                break
    except Exception as e:
        print(f"列表抓取过程中发生网络异常: {e}")
    
    # 二次请求：获取每个视频的实时点赞量
    print(f"列表获取完成，共有 {len(videos)} 个视频，开始获取点赞详情...")
    for video in videos:
        try:
            detail_url = f"https://api.bilibili.com/x/web-interface/archive/stat?bvid={video['bvid']}"
            res = requests.get(detail_url, headers=headers, timeout=10).json()
            if res.get('code') == 0:
                video['like'] = res['data']['like']
            time.sleep(0.5) # 详情接口请求间隔
        except:
            continue
        
    return videos

def send_dingtalk_msg(content):
    """发送钉钉机器人通知"""
    if not DINGTALK_WEBHOOK:
        print("警告：未配置钉钉 Webhook，跳过通知")
        return
        
    data = {
        "msgtype": "text",
        "text": {"content": f"【XMODhub 监控预警】\n{content}\n该视频点赞增长较快，请关注并考虑追加相关内容！"}
    }
    try:
        requests.post(DINGTALK_WEBHOOK, json=data, timeout=10)
    except Exception as e:
        print(f"钉钉发送失败: {e}")

def generate_html(videos, error_msg=""):
    """生成静态看板 HTML 文件"""
    now = datetime.now()
    seven_days_ago = (now - timedelta(days=7)).timestamp()
    thirty_days_ago = (now - timedelta(days=30)).timestamp()
    video_json = json.dumps(videos, ensure_ascii=False)

    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>XMODhub 视频监控看板</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-50 p-4 md:p-8">
        <div class="max-w-6xl mx-auto">
            <div class="bg-white rounded-2xl shadow-sm p-6 mb-6 border border-slate-200">
                <h1 class="text-2xl font-bold text-slate-800">XMODhub 视频推广监控看板</h1>
                <p class="text-slate-500 mt-2">监控账户 UID: {BILI_UID} | 自动更新时间: {now.strftime('%Y-%m-%d %H:%M:%S')}</p>
                {f'<p class="text-red-500 mt-2 font-bold bg-red-50 p-2 rounded">⚠️ 运行提示: {error_msg}</p>' if error_msg else ''}
            </div>
            
            <div class="flex flex-wrap gap-2 mb-6">
                <button onclick="render('all')" id="btn-all" class="px-5 py-2 rounded-lg bg-blue-600 text-white font-medium shadow-sm transition-all hover:bg-blue-700">所有视频</button>
                <button onclick="render('7')" id="btn-7" class="px-5 py-2 rounded-lg bg-white text-slate-600 border border-slate-200 font-medium hover:bg-slate-50">仅监控近 7 天</button>
                <button onclick="render('30')" id="btn-30" class="px-5 py-2 rounded-lg bg-white text-slate-600 border border-slate-200 font-medium hover:bg-slate-50">仅监控近 30 天</button>
            </div>

            <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-50 text-slate-600 text-sm">
                                <th class="p-4 font-semibold">发布日期</th>
                                <th class="p-4 font-semibold">视频标题</th>
                                <th class="p-4 font-semibold text-right">播放量</th>
                                <th class="p-4 font-semibold text-right">点赞</th>
                                <th class="p-4 font-semibold text-right">评论</th>
                            </tr>
                        </thead>
                        <tbody id="vBody" class="text-slate-700 divide-y divide-slate-100">
                            <!-- 数据由 JS 渲染 -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <script>
            const rawData = {video_json};
            const t7 = {seven_days_ago};
            const t30 = {thirty_days_ago};

            function render(filter) {{
                const body = document.getElementById('vBody');
                body.innerHTML = '';
                
                // 重置按钮样式
                document.querySelectorAll('button').forEach(b => {{
                    b.className = "px-5 py-2 rounded-lg bg-white text-slate-600 border border-slate-200 font-medium hover:bg-slate-50";
                }});
                document.getElementById('btn-' + filter).className = "px-5 py-2 rounded-lg bg
