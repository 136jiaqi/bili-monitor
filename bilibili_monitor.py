import requests
import json
import time
import os
from datetime import datetime, timedelta

# ================= 从 GitHub Secrets 安全读取 =================
# os.environ.get 会自动从 GitHub 的运行环境中抓取你刚才设置的 Secret
BILI_UID = os.environ.get("BILI_UID")
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK")
LIKE_THRESHOLD = 50  # 预警阈值：每小时点赞增加超过50则报警
# ============================================================

def get_video_list():
    """获取账号下所有视频数据"""
    if not BILI_UID:
        print("错误：未检测到 BILI_UID，请检查 GitHub Secrets 配置")
        return []
        
    videos = []
    page = 1
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": f"https://space.bilibili.com/{BILI_UID}"
    }

    while True:
        # 使用B站空间搜索接口获取视频列表
        url = f"https://api.bilibili.com/x/space/wbi/arc/search?mid={BILI_UID}&ps=30&tid=0&pn={page}&keyword=&order=pubdate"
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
                        "created": v['created'],
                        "play": v['play'],
                        "comment": v['video_review'],
                        "like": 0
                    })
                page += 1
                if page > 10: break # 安全限制，防止死循环
            else:
                break
        except Exception as e:
            print(f"列表抓取异常: {e}")
            break
    
    # 获取每个视频的详细点赞量
    for video in videos:
        try:
            detail_url = f"https://api.bilibili.com/x/web-interface/archive/stat?bvid={video['bvid']}"
            res = requests.get(detail_url, headers=headers).json()
            if res['code'] == 0:
                video['like'] = res['data']['like']
            time.sleep(0.3) # 稍微加长间隔，防止被封IP
        except:
            continue
        
    return videos

def send_dingtalk_msg(content):
    """发送钉钉通知"""
    if not DINGTALK_WEBHOOK:
        print("警告：未配置钉钉 Webhook，跳过通知")
        return
        
    data = {
        "msgtype": "text",
        "text": {"content": f"【视频监控预警】\n{content}\n该追加相关内容了！"}
    }
    try:
        requests.post(DINGTALK_WEBHOOK, json=data)
    except Exception as e:
        print(f"钉钉发送失败: {e}")

def generate_html(videos):
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
        <title>XMODhub 推广看板</title>
        <style>
            body {{ font-family: sans-serif; background: #f0f2f5; padding: 20px; }}
            .card {{ background: #fff; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
            .btn-group {{ margin: 20px 0; }}
            button {{ padding: 8px 16px; margin-right: 10px; cursor: pointer; border: 1px solid #d9d9d9; background: #fff; border-radius: 4px; }}
            button.active {{ background: #1890ff; color: white; border-color: #1890ff; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #f0f0f0; }}
            th {{ background: #fafafa; }}
            a {{ color: #1890ff; text-decoration: none; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>XMODhub 视频数据看板</h1>
            <p>数据 UID: {BILI_UID} | 更新时间: {now.strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <div class="btn-group">
                <button id="btn-all" onclick="render('all')">所有视频</button>
                <button id="btn-7" onclick="render('7')">近7天</button>
                <button id="btn-30" onclick="render('30')">近30天</button>
            </div>

            <table id="vTable">
                <thead>
                    <tr>
                        <th>发布日期</th>
                        <th>标题</th>
                        <th>播放量</th>
                        <th>点赞</th>
                        <th>评论</th>
                    </tr>
                </thead>
                <tbody id="vBody"></tbody>
            </table>
        </div>

        <script>
            const rawData = {video_json};
            const t7 = {seven_days_ago};
            const t30 = {thirty_days_ago};

            function render(filter) {{
                const body = document.getElementById('vBody');
                body.innerHTML = '';
                
                // 切换按钮样式
                document.querySelectorAll('button').forEach(b => b.classList.remove('active'));
                document.getElementById('btn-' + filter).classList.add('active');

                const filtered = rawData.filter(v => {{
                    if(filter === '7') return v.created >= t7;
                    if(filter === '30') return v.created >= t30;
                    return true;
                }});

                filtered.forEach(v => {{
                    const date = new Date(v.created * 1000).toLocaleDateString();
                    body.innerHTML += `<tr>
                        <td>${{date}}</td>
                        <td><a href="https://www.bilibili.com/video/${{v.bvid}}" target="_blank">${{v.title}}</a></td>
                        <td>${{v.play.toLocaleString()}}</td>
                        <td>${{v.like.toLocaleString()}}</td>
                        <td>${{v.comment.toLocaleString()}}</td>
                    </tr>`;
                }});
            }}
            render('all');
        </script>
    </body>
    </html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_template)

def check_and_alert(current_videos):
    """预警逻辑"""
    history_file = "history.json"
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                old_list = json.load(f)
                old_map = {{v['bvid']: v['like'] for v in old_list}}
            
            for v in current_videos:
                if v['bvid'] in old_map:
                    diff = v['like'] - old_map[v['bvid']]
                    if diff >= LIKE_THRESHOLD:
                        send_dingtalk_msg(f"视频：{v['title']}\n新增点赞：{diff}")
        except:
            pass
            
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(current_videos, f, ensure_ascii=False)

if __name__ == "__main__":
    data = get_video_list()
    if data:
        check_and_alert(data)
        generate_html(data)
        print("Done!")
