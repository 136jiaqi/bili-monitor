import requests
import json
import time
import os
from datetime import datetime, timedelta

# ================= 配置区域 =================
BILI_UID = "你的UID"  # 替换为你的B站UID
DINGTALK_WEBHOOK = "你的钉钉Webhook地址"  # 替换为你的钉钉机器人地址
LIKE_THRESHOLD = 50  # 预警阈值：每小时点赞增加超过50则报警
# ===========================================

def get_video_list():
    """获取账号下所有视频数据"""
    videos = []
    page = 1
    while True:
        url = f"https://api.bilibili.com/x/space/wbi/arc/search?mid={BILI_UID}&ps=30&tid=0&pn={page}&keyword=&order=pubdate"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": f"https://space.bilibili.com/{BILI_UID}"
        }
        try:
            response = requests.get(url, headers=headers).json()
            if response['code'] == 0:
                vlist = response['data']['list']['vlist']
                if not vlist:
                    break
                for v in vlist:
                    videos.append({
                        "title": v['title'],
                        "bvid": v['bvid'],
                        "created": v['created'],  # 时间戳
                        "play": v['play'],
                        "comment": v['video_review'],
                        "like": 0, # 初始点赞设为0，需二次请求获取详情
                        "pic": v['pic']
                    })
                page += 1
            else:
                break
        except Exception as e:
            print(f"抓取失败: {e}")
            break
    
    # 获取详细点赞数（B站列表接口不带点赞，需循环获取）
    for video in videos:
        detail_url = f"https://api.bilibili.com/x/web-interface/archive/stat?bvid={video['bvid']}"
        res = requests.get(detail_url, headers=headers).json()
        if res['code'] == 0:
            video['like'] = res['data']['like']
        time.sleep(0.2) # 防止请求过快
        
    return videos

def send_dingtalk_msg(content):
    """发送钉钉通知"""
    data = {
        "msgtype": "text",
        "text": {"content": f"【数据预警】\n{content}\n该追加相关内容了！"}
    }
    requests.post(DINGTALK_WEBHOOK, json=data)

def generate_html(videos):
    """生成静态HTML看板"""
    now = datetime.now()
    seven_days_ago = (now - timedelta(days=7)).timestamp()
    thirty_days_ago = (now - timedelta(days=30)).timestamp()

    # 将数据转为JS脚本嵌入HTML，实现前端筛选
    video_json = json.dumps(videos, ensure_ascii=False)

    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>XMODhub 视频推广监控看板</title>
        <style>
            body {{ font-family: 'PingFang SC', sans-serif; background: #f4f7f6; margin: 0; padding: 20px; }}
            .header {{ background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 20px; }}
            .controls {{ margin: 20px 0; }}
            button {{ padding: 10px 20px; margin-right: 10px; cursor: pointer; border: none; border-radius: 4px; background: #00a1d6; color: white; }}
            button:hover {{ background: #00b5e5; }}
            table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; }}
            th, td {{ padding: 15px; text-align: left; border-bottom: 1px solid #eee; }}
            th {{ background: #00a1d6; color: white; }}
            .hot {{ color: #ff4d4f; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>XMODhub 视频推广监控看板</h2>
            <p>说明：本看板每小时自动更新一次，实时监控点赞、播放与评论。当前更新时间：{now.strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        <div class="controls">
            <button onclick="renderTable('all')">所有视频</button>
            <button onclick="renderTable('7')">近 7 天</button>
            <button onclick="renderTable('30')">近 30 天</button>
        </div>

        <table id="videoTable">
            <thead>
                <tr>
                    <th>发布时间</th>
                    <th>视频标题</th>
                    <th>播放量</th>
                    <th>点赞数</th>
                    <th>评论数</th>
                </tr>
            </thead>
            <tbody id="tableBody"></tbody>
        </table>

        <script>
            const data = {video_json};
            const sevenDaysAgo = {seven_days_ago};
            const thirtyDaysAgo = {thirty_days_ago};

            function renderTable(filter) {{
                const tbody = document.getElementById('tableBody');
                tbody.innerHTML = '';
                
                const filteredData = data.filter(v => {{
                    if(filter === '7') return v.created >= sevenDaysAgo;
                    if(filter === '30') return v.created >= thirtyDaysAgo;
                    return true;
                }});

                filteredData.forEach(v => {{
                    const date = new Date(v.created * 1000).toLocaleString();
                    const row = `<tr>
                        <td>${{date}}</td>
                        <td><a href="https://www.bilibili.com/video/${{v.bvid}}" target="_blank">${{v.title}}</a></td>
                        <td>${{v.play}}</td>
                        <td>${{v.like}}</td>
                        <td>${{v.comment}}</td>
                    </tr>`;
                    tbody.innerHTML += row;
                }});
            }}
            renderTable('all');
        </script>
    </body>
    </html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_template)

def monitor_logic(current_videos):
    """监控逻辑：对比旧数据，判断是否预警"""
    history_file = "history.json"
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            old_data = {{v['bvid']: v['like'] for v in json.load(f)}}
        
        for v in current_videos:
            if v['bvid'] in old_data:
                increase = v['like'] - old_data[v['bvid']]
                if increase >= LIKE_THRESHOLD:
                    send_dingtalk_msg(f"视频《{v['title']}》点赞异常激增！\n一小时内新增点赞：{increase}")
    
    # 保存当前数据为下一次对比的“旧数据”
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(current_videos, f, ensure_ascii=False)

if __name__ == "__main__":
    print("开始执行任务...")
    all_videos = get_video_list()
    monitor_logic(all_videos)
    generate_html(all_videos)
    print("任务执行完成，index.html 已更新。")
