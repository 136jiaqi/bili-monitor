import json
import time
import os
import requests
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# ================= 从 GitHub Secrets 安全读取 =================
BILI_UID = os.environ.get("BILI_UID")
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK")
LIKE_THRESHOLD = 50  # 预警阈值
# ============================================================

def get_video_list_with_browser():
    """使用 Playwright 模拟浏览器抓取，绕过 WBI 签名和 412 风控"""
    if not BILI_UID:
        print("错误：未检测到 BILI_UID")
        return []

    videos = []
    print(f"正在启动模拟浏览器，目标 UID: {BILI_UID}")

    with sync_playwright() as p:
        # 启动无头浏览器
        browser = p.chromium.launch(headless=True)
        # 模拟真实设备指纹
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()

        try:
            # 1. 先访问用户空间主页，获取必要的 Cookie 环境
            print(f"正在访问用户空间: https://space.bilibili.com/{BILI_UID}/video")
            page.goto(f"https://space.bilibili.com/{BILI_UID}/video", wait_until="networkidle", timeout=60000)
            time.sleep(5) # 等待页面渲染和脚本执行

            # 2. 拦截并监听 B 站的搜索接口请求
            # B 站页面滚动或加载时会调用 arc/search 接口
            # 我们直接从页面 DOM 中提取初步数据，或者通过 API 拦截
            
            # 尝试直接通过 API 抓取（在有 Cookie 语境下）
            api_url = f"https://api.bilibili.com/x/space/arc/search?mid={BILI_UID}&ps=30&tid=0&pn=1&order=pubdate"
            
            # 使用 page.evaluate 借用浏览器的 session 发起请求
            response_data = page.evaluate(f"""
                fetch("{api_url}").then(res => res.json())
            """)

            if response_data.get('code') == 0:
                vlist = response_data['data']['list']['vlist']
                for v in vlist:
                    videos.append({
                        "title": v['title'],
                        "bvid": v['bvid'],
                        "created": v['created'],
                        "play": v['play'],
                        "comment": v['video_review'],
                        "like": 0 # 稍后同步详情
                    })
                print(f"成功抓取到 {len(videos)} 个视频")
            else:
                print(f"浏览器内请求接口失败: {response_data.get('message')}")
                # 备用方案：尝试从 DOM 节点解析（MediaCrawler 逻辑）
                video_elements = page.query_selector_all(".list-item")
                if video_elements:
                    print(f"尝试从页面元素解析，发现 {len(video_elements)} 个列表项")
                    # 这里可以添加更复杂的解析逻辑
        
        except Exception as e:
            print(f"浏览器运行异常: {e}")
        finally:
            browser.close()

    # 3. 同步点赞详情（使用 requests 配合随机延时）
    if videos:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
        print("正在获取详细统计数据...")
        for video in videos[:20]: # 优先处理最新的 20 条
            try:
                stat_url = f"https://api.bilibili.com/x/web-interface/archive/stat?bvid={video['bvid']}"
                res = requests.get(stat_url, headers=headers, timeout=10).json()
                if res.get('code') == 0:
                    video['like'] = res['data']['like']
                    video['play'] = res['data']['view']
                time.sleep(1.5)
            except:
                continue

    return videos

def send_dingtalk_msg(content):
    if not DINGTALK_WEBHOOK: return
    data = {
        "msgtype": "text",
        "text": {"content": f"【XMODhub 监控预警】\n{content}\n点赞增长表现优异，请及时复盘！"}
    }
    try:
        requests.post(DINGTALK_WEBHOOK, json=data, timeout=10)
    except:
        pass

def generate_html(videos, error_info=""):
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
        <title>XMODhub 监控看板</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-50 p-4 md:p-8">
        <div class="max-w-6xl mx-auto">
            <div class="bg-white rounded-2xl shadow-sm p-6 mb-6 border border-slate-200">
                <h1 class="text-2xl font-bold text-slate-800 tracking-tight">XMODhub 视频监控</h1>
                <p class="text-slate-500 mt-2 text-sm">账户 UID: {BILI_UID} | 最后同步: {now.strftime('%Y-%m-%d %H:%M:%S')}</p>
                {f'<div class="mt-4 p-3 bg-red-50 text-red-600 rounded-lg text-xs">状态提示: {error_info}</div>' if error_info else '<div class="mt-4 p-3 bg-green-50 text-green-700 rounded-lg text-xs font-medium">● 数据实时同步中</div>'}
            </div>
            
            <div class="flex gap-2 mb-6 overflow-x-auto pb-2">
                <button onclick="render('all')" id="btn-all" class="px-4 py-2 rounded-xl bg-blue-600 text-white whitespace-nowrap shadow-md transition-all hover:bg-blue-700">全部</button>
                <button onclick="render('7')" id="btn-7" class="px-4 py-2 rounded-xl bg-white border border-slate-200 text-slate-600 whitespace-nowrap hover:bg-slate-50">7天内</button>
                <button onclick="render('30')" id="btn-30" class="px-4 py-2 rounded-xl bg-white border border-slate-200 text-slate-600 whitespace-nowrap hover:bg-slate-50">30天内</button>
            </div>

            <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead class="bg-slate-50/50 border-b border-slate-100 text-slate-500 text-xs uppercase tracking-wider">
                            <tr>
                                <th class="p-4 font-semibold">发布时间</th>
                                <th class="p-4 font-semibold">内容详情</th>
                                <th class="p-4 font-semibold text-right">播放量</th>
                                <th class="p-4 font-semibold text-right">点赞</th>
                            </tr>
                        </thead>
                        <tbody id="vBody" class="divide-y divide-slate-50 text-slate-700"></tbody>
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
                
                document.querySelectorAll('button').forEach(b => {{
                    b.className = "px-4 py-2 rounded-xl bg-white border border-slate-200 text-slate-600 whitespace-nowrap hover:bg-slate-50 transition-all";
                }});
                document.getElementById('btn-' + filter).className = "px-4 py-2 rounded-xl bg-blue-600 text-white whitespace-nowrap shadow-md font-medium";

                const filtered = rawData.filter(v => {{
                    if(filter === '7') return v.created >= t7;
                    if(filter === '30') return v.created >= t30;
                    return true;
                }});

                if(filtered.length === 0) {{
                    body.innerHTML = '<tr><td colspan="4" class="p-12 text-center text-slate-400">暂无数据，请稍后刷新</td></tr>';
                    return;
                }}

                filtered.forEach(v => {{
                    const date = new Date(v.created * 1000).toLocaleDateString();
                    body.innerHTML += `
                        <tr class="hover:bg-slate-50/80 transition-colors">
                            <td class="p-4 text-xs text-slate-400 font-mono">${{date}}</td>
                            <td class="p-4"><a href="https://www.bilibili.com/video/${{v.bvid}}" target="_blank" class="text-blue-600 hover:text-blue-800 font-medium line-clamp-1">${{v.title}}</a></td>
                            <td class="p-4 text-right font-mono text-sm">${{v.play.toLocaleString()}}</td>
                            <td class="p-4 text-right font-mono text-orange-600 font-bold">${{v.like.toLocaleString()}}</td>
                        </tr>
                    `;
                }});
            }}
            render('all');
        </script>
    </body>
    </html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_template)

def monitor_logic(current_videos):
    history_file = "history.json"
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                old_list = json.load(f)
                old_map = {v['bvid']: v['like'] for v in old_list}
            
            for v in current_videos:
                if v['bvid'] in old_map:
                    diff = v['like'] - old_map[v['bvid']]
                    if diff >= LIKE_THRESHOLD:
                        send_dingtalk_msg(f"视频标题：{v['title']}\\n当前点赞：{v['like']}\\n本周期新增：{diff}")
        except Exception as e:
            print(f"历史对比失败: {e}")
            
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(current_videos, f, ensure_ascii=False)

if __name__ == "__main__":
    # 使用浏览器模拟模式抓取
    videos = get_video_list_with_browser()
    
    if not videos:
        generate_html([], error_info="[风控警报] B站响应了 412 拦截或空数据。建议尝试在 Actions 脚本中更换 IP 区域。")
    else:
        monitor_logic(videos)
        generate_html(videos)
        print("脚本成功结束。")
