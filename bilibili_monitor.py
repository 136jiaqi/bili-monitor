import json
import time
import os
import requests
import random
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# ================= 从 GitHub Secrets 安全读取 =================
BILI_UID = os.environ.get("BILI_UID")
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK")
LIKE_THRESHOLD = 50  # 预警阈值
# ============================================================

def get_video_list_with_browser():
    """使用 Playwright 增强模拟抓取，加入 Cookie 注入和防爬增强"""
    if not BILI_UID:
        print("错误：未检测到 BILI_UID")
        return []

    videos = []
    print(f"正在启动增强型模拟浏览器，目标 UID: {BILI_UID}")

    with sync_playwright() as p:
        # 使用真实的浏览器配置
        browser = p.chromium.launch(headless=True)
        # 伪造更像真实用户的 Context
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai"
        )
        page = context.new_page()

        try:
            # 1. 第一步：访问 B 站首页，建立基础 Session 和 Cookie
            print("正在建立访问环境...")
            page.goto("https://www.bilibili.com", wait_until="networkidle", timeout=60000)
            time.sleep(random.uniform(2, 4))

            # 2. 第二步：跳转到目标空间，模拟真实轨迹
            space_url = f"https://space.bilibili.com/{BILI_UID}/video"
            print(f"正在访问空间: {space_url}")
            page.goto(space_url, wait_until="networkidle", timeout=60000)
            
            # 模拟随机滚动，触发数据加载
            page.mouse.wheel(0, 500)
            time.sleep(random.uniform(3, 6))

            # 3. 第三步：在浏览器上下文执行 API 请求（此时带有完整的 Web 指纹和 Cookie）
            api_url = f"https://api.bilibili.com/x/space/arc/search?mid={BILI_UID}&ps=30&tid=0&pn=1&order=pubdate"
            print("正在提取接口数据...")
            
            # 尝试多次抓取
            for attempt in range(3):
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
                            "like": 0
                        })
                    print(f"抓取成功：获取到 {len(videos)} 个视频")
                    break
                elif response_data.get('code') == -412:
                    print(f"尝试 {attempt + 1}: 仍被风控 (412)，正在变换策略...")
                    time.sleep(5)
                    page.reload()
                    time.sleep(5)
                else:
                    print(f"接口返回非预期结果: {response_data.get('message')}")
                    break
        
        except Exception as e:
            print(f"浏览器执行过程中发生异常: {e}")
        finally:
            browser.close()

    # 4. 获取详细统计数据 (增加更真实的 Headers)
    if videos:
        print("正在同步点赞等详细数据...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Referer": f"https://space.bilibili.com/{BILI_UID}/video"
        }
        for video in videos[:15]: # 限制前15个，减少请求频率
            try:
                stat_url = f"https://api.bilibili.com/x/web-interface/archive/stat?bvid={video['bvid']}"
                res = requests.get(stat_url, headers=headers, timeout=10).json()
                if res.get('code') == 0:
                    video['like'] = res['data']['like']
                    video['play'] = res['data']['view']
                time.sleep(random.uniform(1.0, 2.5)) # 随机间隔
            except:
                continue

    return videos

def send_dingtalk_msg(content):
    if not DINGTALK_WEBHOOK: return
    data = {
        "msgtype": "text",
        "text": {"content": f"【XMODhub 监控预警】\n{content}\n点赞增长表现活跃，建议复盘内容策略！"}
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
                <div class="flex justify-between items-start">
                    <div>
                        <h1 class="text-2xl font-bold text-slate-800 tracking-tight">XMODhub 视频监控</h1>
                        <p class="text-slate-500 mt-1 text-sm font-medium">账户 UID: {BILI_UID} | 更新周期: 每小时</p>
                    </div>
                    <div class="text-right text-xs text-slate-400">
                        最后同步: {now.strftime('%H:%M:%S')}
                    </div>
                </div>
                {f'<div class="mt-4 p-4 bg-amber-50 border border-amber-100 text-amber-700 rounded-xl text-xs flex items-center">⚠️ {error_info}</div>' if error_info else '<div class="mt-4 p-4 bg-emerald-50 border border-emerald-100 text-emerald-700 rounded-xl text-xs font-semibold flex items-center"><span class="w-2 h-2 bg-emerald-500 rounded-full mr-2 animate-pulse"></span> 系统运行正常，数据已实时同步</div>'}
            </div>
            
            <div class="flex gap-3 mb-6 overflow-x-auto pb-2 no-scrollbar">
                <button onclick="render('all')" id="btn-all" class="px-5 py-2.5 rounded-xl bg-slate-900 text-white whitespace-nowrap shadow-lg text-sm transition-all">全部视频</button>
                <button onclick="render('7')" id="btn-7" class="px-5 py-2.5 rounded-xl bg-white border border-slate-200 text-slate-600 whitespace-nowrap hover:bg-slate-50 text-sm transition-all">最近 7 天</button>
                <button onclick="render('30')" id="btn-30" class="px-5 py-2.5 rounded-xl bg-white border border-slate-200 text-slate-600 whitespace-nowrap hover:bg-slate-50 text-sm transition-all">最近 30 天</button>
            </div>

            <div class="bg-white rounded-3xl shadow-xl border border-slate-100 overflow-hidden">
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-50/80 text-slate-500 text-[11px] uppercase tracking-widest border-b border-slate-100">
                                <th class="p-5 font-bold">发布日期</th>
                                <th class="p-5 font-bold">视频标题</th>
                                <th class="p-5 font-bold text-right">总播放量</th>
                                <th class="p-5 font-bold text-right">当前点赞</th>
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
                    b.className = "px-5 py-2.5 rounded-xl bg-white border border-slate-200 text-slate-600 whitespace-nowrap hover:bg-slate-50 text-sm transition-all";
                }});
                const activeBtn = document.getElementById('btn-' + filter);
                activeBtn.className = "px-5 py-2.5 rounded-xl bg-slate-900 text-white whitespace-nowrap shadow-lg text-sm transition-all";

                const filtered = rawData.filter(v => {{
                    if(filter === '7') return v.created >= t7;
                    if(filter === '30') return v.created >= t30;
                    return true;
                }});

                if(filtered.length === 0) {{
                    body.innerHTML = '<tr><td colspan="4" class="p-20 text-center text-slate-300 font-medium italic">暂未抓取到有效视频数据...</td></tr>';
                    return;
                }}

                filtered.forEach(v => {{
                    const date = new Date(v.created * 1000).toLocaleDateString();
                    body.innerHTML += `
                        <tr class="hover:bg-slate-50/50 transition-colors group">
                            <td class="p-5 text-xs text-slate-400 font-mono italic">${{date}}</td>
                            <td class="p-5">
                                <a href="https://www.bilibili.com/video/${{v.bvid}}" target="_blank" class="text-slate-800 group-hover:text-blue-600 font-semibold line-clamp-1 transition-colors">${{v.title}}</a>
                            </td>
                            <td class="p-5 text-right font-mono text-sm text-slate-500">${{v.play.toLocaleString()}}</td>
                            <td class="p-5 text-right font-mono text-base text-orange-500 font-black tracking-tighter">${{v.like.toLocaleString()}}</td>
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
                        send_dingtalk_msg(f"视频：{v['title']}\\n当前点赞：{v['like']}\\n周期新增：{diff}")
        except Exception as e:
            print(f"历史数据对比异常: {e}")
            
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(current_videos, f, ensure_ascii=False)

if __name__ == "__main__":
    videos = get_video_list_with_browser()
    
    if not videos:
        # 如果依然失败，显示更具体的建议
        generate_html([], error_info="[风控拦截] B 站当前拒绝了来自数据中心的自动抓取请求。这通常与 IP 区域有关。系统将继续在下个整点尝试。")
    else:
        monitor_logic(videos)
        generate_html(videos)
        print("所有流程已执行成功。")
