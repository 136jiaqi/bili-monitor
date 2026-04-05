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
    """获取账号下视频数据"""
    if not BILI_UID:
        print("错误：未检测到 BILI_UID")
        return []
        
    videos = []
    page = 1
    # 模拟更真实的浏览器指纹
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Referer": f"https://space.bilibili.com/{BILI_UID}",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
    }

    print(f"正在启动抓取，目标 UID: {BILI_UID}")
    
    try:
        while page <= 5: # 监控最近的 150 条视频通常足够了
            url = f"https://api.bilibili.com/x/space/wbi/arc/search?mid={BILI_UID}&ps=30&tid=0&pn={page}&keyword=&order=pubdate"
            print(f"读取第 {page} 页列表...")
            
            # 增加重试机制
            for attempt in range(3):
                try:
                    response = requests.get(url, headers=headers, timeout=15)
                    res_json = response.json()
                    if res_json.get('code') == 0:
                        vlist = res_json['data']['list']['vlist']
                        if not vlist: break
                        for v in vlist:
                            videos.append({
                                "title": v['title'],
                                "bvid": v['bvid'],
                                "created": v['created'],
                                "play": v['play'],
                                "comment": v['video_review'],
                                "like": 0
                            })
                        print(f"第 {page} 页抓取成功，当前累计 {len(videos)} 个视频")
                        break
                    elif res_json.get('code') == -412:
                        print("被 B 站风控拦截 (412)，正在重试...")
                        time.sleep(5)
                    else:
                        print(f"接口返回错误: {res_json.get('message')}")
                        break
                except Exception as e:
                    print(f"请求失败，重试中... ({e})")
                    time.sleep(2)
            
            page += 1
            time.sleep(2) # 适当延时
            
    except Exception as e:
        print(f"主程序异常: {e}")
    
    # 获取详细点赞
    print("开始同步点赞数据详情...")
    for index, video in enumerate(videos):
        if index % 10 == 0: print(f"进度: {index}/{len(videos)}")
        try:
            detail_url = f"https://api.bilibili.com/x/web-interface/archive/stat?bvid={video['bvid']}"
            res = requests.get(detail_url, headers=headers, timeout=10).json()
            if res.get('code') == 0:
                video['like'] = res['data']['like']
            time.sleep(0.6) 
        except:
            continue
        
    return videos

def send_dingtalk_msg(content):
    """发送钉钉通知"""
    if not DINGTALK_WEBHOOK: return
    data = {
        "msgtype": "text",
        "text": {"content": f"【XMODhub 监控预警】\n{content}\n该视频表现活跃，建议追加相关内容！"}
    }
    try:
        requests.post(DINGTALK_WEBHOOK, json=data, timeout=10)
    except:
        pass

def generate_html(videos, error_info=""):
    """生成看板 HTML 文件"""
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
                <h1 class="text-2xl font-bold text-slate-800">XMODhub 视频推广看板</h1>
                <p class="text-slate-500 mt-2">账户 UID: {BILI_UID} | 更新时间: {now.strftime('%Y-%m-%d %H:%M:%S')}</p>
                {f'<div class="mt-4 p-3 bg-red-50 text-red-600 rounded-lg text-sm">提示: {error_info}</div>' if error_info else ''}
            </div>
            
            <div class="flex gap-2 mb-6 overflow-x-auto pb-2">
                <button onclick="render('all')" id="btn-all" class="px-4 py-2 rounded-lg bg-blue-600 text-white whitespace-nowrap">所有视频</button>
                <button onclick="render('7')" id="btn-7" class="px-4 py-2 rounded-lg bg-white border whitespace-nowrap">近7天</button>
                <button onclick="render('30')" id="btn-30" class="px-4 py-2 rounded-lg bg-white border whitespace-nowrap">近30天</button>
            </div>

            <div class="bg-white rounded-2xl shadow-sm border overflow-hidden">
                <div class="overflow-x-auto">
                    <table class="w-full text-left">
                        <thead class="bg-slate-50 border-b text-slate-600 text-sm">
                            <tr>
                                <th class="p-4 font-semibold">发布日期</th>
                                <th class="p-4 font-semibold">标题</th>
                                <th class="p-4 font-semibold text-right">播放</th>
                                <th class="p-4 font-semibold text-right">点赞</th>
                                <th class="p-4 font-semibold text-right">评论</th>
                            </tr>
                        </thead>
                        <tbody id="vBody" class="divide-y text-slate-700"></tbody>
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
                
                document.querySelectorAll('button').forEach(b => b.className = "px-4 py-2 rounded-lg bg-white border whitespace-nowrap text-slate-600");
                document.getElementById('btn-' + filter).className = "px-4 py-2 rounded-lg bg-blue-600 text-white whitespace-nowrap";

                const filtered = rawData.filter(v => {{
                    if(filter === '7') return v.created >= t7;
                    if(filter === '30') return v.created >= t30;
                    return true;
                }});

                if(filtered.length === 0) {{
                    body.innerHTML = '<tr><td colspan="5" class="p-12 text-center text-slate-400">没有抓取到符合条件的视频数据</td></tr>';
                    return;
                }}

                filtered.forEach(v => {{
                    const date = new Date(v.created * 1000).toLocaleDateString();
                    body.innerHTML += `
                        <tr class="hover:bg-slate-50">
                            <td class="p-4 text-sm text-slate-400">${{date}}</td>
                            <td class="p-4"><a href="https://www.bilibili.com/video/${{v.bvid}}" target="_blank" class="text-blue-600 hover:underline line-clamp-1">${{v.title}}</a></td>
                            <td class="p-4 text-right font-mono">${{v.play.toLocaleString()}}</td>
                            <td class="p-4 text-right font-mono text-orange-600 font-bold">${{v.like.toLocaleString()}}</td>
                            <td class="p-4 text-right font-mono">${{v.comment.toLocaleString()}}</td>
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
                        send_dingtalk_msg(f"视频：{v['title']}\n当前点赞：{v['like']}\n新增点赞：{diff}")
        except:
            pass
            
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(current_videos, f, ensure_ascii=False)

if __name__ == "__main__":
    videos = get_video_list()
    if not videos:
        generate_html([], error_info="抓取失败，请检查 UID 或稍后重试。")
    else:
        monitor_logic(videos)
        generate_html(videos)
        print("执行完成。")
