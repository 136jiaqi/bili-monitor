import requests
import json
import time
import os
from datetime import datetime, timedelta

# ================= 从 GitHub Secrets 安全读取 =================
BILI_UID = os.environ.get("BILI_UID")
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK")
LIKE_THRESHOLD = 50  # 预警阈值
# ============================================================

def get_video_list():
    """获取账号下视频数据 - 采用兼容性更好的 web-interface 接口"""
    if not BILI_UID:
        print("错误：未检测到 BILI_UID")
        return []
        
    videos = []
    # 模拟高度真实的浏览器环境
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
        "Accept": "application/json, text/plain, */*",
    }

    print(f"开始尝试抓取，UID: {BILI_UID}")
    
    # 尝试使用 web-interface 获取投稿视频（这个接口对 Actions 更友好）
    # 如果 wbi 接口失败，这通常是最好的替代方案
    url = f"https://api.bilibili.com/x/polymer/web-dynamic/v1/portal?host_mid={BILI_UID}"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        res_json = response.json()
        
        if res_json.get('code') == 0:
            items = res_json.get('data', {}).get('items', [])
            for item in items:
                # 过滤出视频类型的动态
                if item.get('type') == 'DYNAMIC_TYPE_AV':
                    modules = item.get('modules', {})
                    module_author = modules.get('module_author', {})
                    module_dynamic = modules.get('module_dynamic', {})
                    major = module_dynamic.get('major', {}).get('archive', {})
                    
                    if major:
                        videos.append({
                            "title": major.get('title'),
                            "bvid": major.get('bvid'),
                            "created": module_author.get('pub_ts', int(time.time())),
                            "play": int(major.get('stat', {}).get('view', 0).replace('万','0000').replace('+', '').split('.')[0]) if isinstance(major.get('stat', {}).get('view'), str) else major.get('stat', {}).get('view', 0),
                            "comment": 0, # 该接口不直接返回评论数
                            "like": 0
                        })
            print(f"动态接口抓取成功，发现 {len(videos)} 个视频")
        else:
            print(f"动态接口失败: {res_json.get('message')}")
    except Exception as e:
        print(f"动态接口请求异常: {e}")

    # 如果上述接口也没抓到，尝试备用接口 (Space Arc)
    if not videos:
        print("尝试备用空间搜索接口...")
        alt_url = f"https://api.bilibili.com/x/space/arc/search?mid={BILI_UID}&ps=30&tid=0&pn=1&order=pubdate"
        try:
            res = requests.get(alt_url, headers=headers, timeout=15).json()
            if res.get('code') == 0:
                vlist = res['data']['list']['vlist']
                for v in vlist:
                    videos.append({
                        "title": v['title'],
                        "bvid": v['bvid'],
                        "created": v['created'],
                        "play": v['play'],
                        "comment": v['video_review'],
                        "like": 0
                    })
        except:
            pass

    # 统一获取详细点赞（这个接口目前最稳）
    print("正在同步实时数据详情...")
    for video in videos:
        try:
            detail_url = f"https://api.bilibili.com/x/web-interface/archive/stat?bvid={video['bvid']}"
            res = requests.get(detail_url, headers=headers, timeout=10).json()
            if res.get('code') == 0:
                data = res['data']
                video['like'] = data.get('like', 0)
                video['play'] = data.get('view', video['play'])
                video['comment'] = data.get('reply', 0)
            time.sleep(1) # 加大间隔，防止被封
        except:
            continue
        
    return videos

def send_dingtalk_msg(content):
    if not DINGTALK_WEBHOOK: return
    data = {
        "msgtype": "text",
        "text": {"content": f"【XMODhub 监控预警】\n{content}\n点赞增长较快，建议关注！"}
    }
    try: requests.post(DINGTALK_WEBHOOK, json=data, timeout=10)
    except: pass

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
                <h1 class="text-2xl font-bold text-slate-800">XMODhub 视频推广看板</h1>
                <p class="text-slate-500 mt-2">UID: {BILI_UID} | 更新: {now.strftime('%Y-%m-%d %H:%M:%S')}</p>
                {f'<div class="mt-4 p-3 bg-amber-50 text-amber-700 rounded-lg text-sm">提示: {error_info}</div>' if error_info else ''}
            </div>
            <div class="flex gap-2 mb-6 overflow-x-auto pb-2">
                <button onclick="render('all')" id="btn-all" class="px-4 py-2 rounded-lg bg-blue-600 text-white whitespace-nowrap">所有视频</button>
                <button onclick="render('7')" id="btn-7" class="px-4 py-2 rounded-lg bg-white border border-slate-200 whitespace-nowrap">近7天</button>
                <button onclick="render('30')" id="btn-30" class="px-4 py-2 rounded-lg bg-white border border-slate-200 whitespace-nowrap">近30天</button>
            </div>
            <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                <table class="w-full text-left">
                    <thead class="bg-slate-50 border-b text-slate-600 text-sm">
                        <tr>
                            <th class="p-4">发布日期</th>
                            <th class="p-4">视频标题</th>
                            <th class="p-4 text-right">播放量</th>
                            <th class="p-4 text-right">点赞</th>
                        </tr>
                    </thead>
                    <tbody id="vBody" class="divide-y divide-slate-50 text-slate-700"></tbody>
                </table>
            </div>
        </div>
        <script>
            const rawData = {video_json};
            const t7 = {seven_days_ago};
            const t30 = {thirty_days_ago};
            function render(filter) {{
                const body = document.getElementById('vBody');
                body.innerHTML = '';
                document.querySelectorAll('button').forEach(b => b.className = "px-4 py-2 rounded-lg bg-white border border-slate-200 text-slate-600 whitespace-nowrap");
                document.getElementById('btn-' + filter).className = "px-4 py-2 rounded-lg bg-blue-600 text-white whitespace-nowrap font-medium";
                const filtered = rawData.filter(v => {{
                    if(filter === '7') return v.created >= t7;
                    if(filter === '30') return v.created >= t30;
                    return true;
                }});
                if(filtered.length === 0) {{
                    body.innerHTML = '<tr><td colspan="4" class="p-12 text-center text-slate-400">暂无数据</td></tr>';
                    return;
                }}
                filtered.forEach(v => {{
                    const date = new Date(v.created * 1000).toLocaleDateString();
                    body.innerHTML += `
                        <tr class="hover:bg-slate-50">
                            <td class="p-4 text-sm text-slate-400">${{date}}</td>
                            <td class="p-4"><a href="https://www.bilibili.com/video/${{v.bvid}}" target="_blank" class="text-blue-600 hover:underline line-clamp-1">${{v.title}}</a></td>
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
                        send_dingtalk_msg(f"视频：{v['title']}\\n当前总点赞：{v['like']}\\n周期内新增：{diff}")
        except: pass
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(current_videos, f, ensure_ascii=False)

if __name__ == "__main__":
    videos = get_video_list()
    if not videos:
        generate_html([], error_info="接口访问受限。这通常是 B 站对 GitHub 的临时封锁，系统将在一小时后重试。")
    else:
        monitor_logic(videos)
        generate_html(videos)
        print("任务执行完成。")
