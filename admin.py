#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏福苑獨立委員會聽證會 — 編輯後台
執行方式：python3 admin.py
"""

import os
import json
import subprocess
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import pdfplumber

app = Flask(__name__)
app.secret_key = 'wangfukcourtcommittee2026'

# Jinja2 過濾器
app.jinja_env.filters['enumerate'] = enumerate

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
TRANSCRIPT_DIR = BASE_DIR  # PDF 謄本放在同一目錄

# ──────────────────────────────────────────────
# 數據讀寫工具
# ──────────────────────────────────────────────

def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_all_days():
    return load_json('days.json')['days']

def get_all_topics():
    return load_json('topics.json')['topics']

def get_all_people():
    return load_json('people.json')['people']

def get_settings():
    return load_json('settings.json')

def find_by_id(items, item_id):
    return next((x for x in items if x['id'] == item_id), None)

def now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M')

# ──────────────────────────────────────────────
# 謄本搜尋（全文索引，啟動時載入）
# ──────────────────────────────────────────────

transcript_index = {}  # { 'day1': [(line_no, text), ...], ... }

def build_transcript_index():
    global transcript_index
    for i in range(1, 20):
        pdf_path = os.path.join(TRANSCRIPT_DIR, f'day{i}.pdf')
        if not os.path.exists(pdf_path):
            break
        lines = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ''
                    for line in text.split('\n'):
                        line = line.strip()
                        if line:
                            # 嘗試提取行號
                            parts = line.split(' ', 1)
                            if parts[0].isdigit() and len(parts) > 1:
                                lines.append((int(parts[0]), parts[1]))
                            else:
                                lines.append((0, line))
        except Exception as e:
            print(f'警告：無法讀取 day{i}.pdf: {e}')
        transcript_index[f'day{i}'] = lines
    print(f'謄本索引建立完成，共 {len(transcript_index)} 份。')

def search_transcripts(query, max_results=50):
    results = []
    query_lower = query.lower()
    for day_id, lines in transcript_index.items():
        day_num = day_id.replace('day', '')
        for line_no, text in lines:
            if query in text or query_lower in text.lower():
                results.append({
                    'day_id': day_id,
                    'day_label': f'第{day_num}天',
                    'line_no': line_no,
                    'text': text
                })
                if len(results) >= max_results:
                    return results
    return results

# ──────────────────────────────────────────────
# 路由：主頁 / 儀表板
# ──────────────────────────────────────────────

@app.route('/')
def dashboard():
    days = get_all_days()
    topics = get_all_topics()
    people = get_all_people()
    settings = get_settings()
    published_days = sum(1 for d in days if d['published'])
    published_topics = sum(1 for t in topics if t['published'])
    published_people = sum(1 for p in people if p['published'])
    return render_template('admin/dashboard.html',
        days=days, topics=topics, people=people, settings=settings,
        published_days=published_days, published_topics=published_topics,
        published_people=published_people)

# ──────────────────────────────────────────────
# 路由：聽證日 (Days)
# ──────────────────────────────────────────────

@app.route('/days')
def days_list():
    days = get_all_days()
    return render_template('admin/days_list.html', days=days)

@app.route('/days/<day_id>/edit', methods=['GET', 'POST'])
def day_edit(day_id):
    data = load_json('days.json')
    day = find_by_id(data['days'], day_id)
    if not day:
        flash('找不到該聽證日', 'error')
        return redirect(url_for('days_list'))

    topics = get_all_topics()
    people = get_all_people()

    if request.method == 'POST':
        day['summary'] = request.form.get('summary', '').strip()
        # 重點：一行一項
        kp_raw = request.form.get('key_points', '')
        day['key_points'] = [x.strip() for x in kp_raw.split('\n') if x.strip()]
        # 議題關聯
        day['topic_ids'] = request.form.getlist('topic_ids')
        # 人物關聯
        day['people_ids'] = request.form.getlist('people_ids')
        day['published'] = 'published' in request.form
        day['updated_at'] = now_str()
        save_json('days.json', data)
        flash(f'第{day["day_number"]}天已儲存', 'success')
        return redirect(url_for('day_edit', day_id=day_id))

    return render_template('admin/day_edit.html', day=day, topics=topics, people=people)

@app.route('/days/<day_id>/news/add', methods=['POST'])
def day_news_add(day_id):
    data = load_json('days.json')
    day = find_by_id(data['days'], day_id)
    if day:
        news_item = {
            'title': request.form.get('title', '').strip(),
            'url': request.form.get('url', '').strip(),
            'source': request.form.get('source', '').strip(),
            'date': request.form.get('date', '').strip()
        }
        if news_item['url']:
            day['news'].append(news_item)
            day['updated_at'] = now_str()
            save_json('days.json', data)
            flash('新聞連結已加入', 'success')
    return redirect(url_for('day_edit', day_id=day_id))

@app.route('/days/<day_id>/news/delete/<int:news_idx>', methods=['POST'])
def day_news_delete(day_id, news_idx):
    data = load_json('days.json')
    day = find_by_id(data['days'], day_id)
    if day and 0 <= news_idx < len(day['news']):
        day['news'].pop(news_idx)
        day['updated_at'] = now_str()
        save_json('days.json', data)
        flash('已刪除新聞連結', 'success')
    return redirect(url_for('day_edit', day_id=day_id))

@app.route('/days/new', methods=['GET', 'POST'])
def day_new():
    data = load_json('days.json')
    if request.method == 'POST':
        day_num = int(request.form.get('day_number', 0))
        new_day = {
            'id': f'day{day_num}',
            'day_number': day_num,
            'date': request.form.get('date', ''),
            'title': f'第{day_num}天',
            'summary': '',
            'key_points': [],
            'news': [],
            'topic_ids': [],
            'people_ids': [],
            'published': False,
            'updated_at': now_str()
        }
        # 避免重複
        if not find_by_id(data['days'], new_day['id']):
            data['days'].append(new_day)
            data['days'].sort(key=lambda x: x['day_number'])
            save_json('days.json', data)
            flash(f'第{day_num}天已建立', 'success')
            return redirect(url_for('day_edit', day_id=new_day['id']))
        else:
            flash('該聽證日已存在', 'error')
    return render_template('admin/day_new.html')

# ──────────────────────────────────────────────
# 路由：議題 (Topics)
# ──────────────────────────────────────────────

@app.route('/topics')
def topics_list():
    topics = get_all_topics()
    return render_template('admin/topics_list.html', topics=topics)

@app.route('/topics/new', methods=['GET', 'POST'])
def topic_new():
    data = load_json('topics.json')
    if request.method == 'POST':
        existing_ids = [t['id'] for t in data['topics']]
        # 生成新 ID
        num = len(data['topics']) + 1
        new_id = f'topic-{num}'
        while new_id in existing_ids:
            num += 1
            new_id = f'topic-{num}'
        new_topic = {
            'id': new_id,
            'name': request.form.get('name', '').strip(),
            'description': '',
            'entries': [],
            'published': False,
            'updated_at': now_str()
        }
        data['topics'].append(new_topic)
        save_json('topics.json', data)
        flash(f'議題「{new_topic["name"]}」已建立', 'success')
        return redirect(url_for('topic_edit', topic_id=new_id))
    return render_template('admin/topic_new.html')

@app.route('/topics/<topic_id>/edit', methods=['GET', 'POST'])
def topic_edit(topic_id):
    data = load_json('topics.json')
    topic = find_by_id(data['topics'], topic_id)
    if not topic:
        flash('找不到該議題', 'error')
        return redirect(url_for('topics_list'))

    days = get_all_days()

    if request.method == 'POST':
        topic['name'] = request.form.get('name', '').strip()
        topic['description'] = request.form.get('description', '').strip()
        topic['published'] = 'published' in request.form
        topic['updated_at'] = now_str()
        save_json('topics.json', data)
        flash(f'議題「{topic["name"]}」已儲存', 'success')
        return redirect(url_for('topic_edit', topic_id=topic_id))

    return render_template('admin/topic_edit.html', topic=topic, days=days)

@app.route('/topics/<topic_id>/entries/add', methods=['POST'])
def topic_entry_add(topic_id):
    data = load_json('topics.json')
    topic = find_by_id(data['topics'], topic_id)
    if topic:
        entry = {
            'day_id': request.form.get('day_id', ''),
            'content': request.form.get('content', '').strip(),
            'news': []
        }
        if entry['day_id'] and entry['content']:
            # 若已有該天記錄則更新，否則新增
            existing = next((e for e in topic['entries'] if e['day_id'] == entry['day_id']), None)
            if existing:
                existing['content'] = entry['content']
            else:
                topic['entries'].append(entry)
            topic['updated_at'] = now_str()
            save_json('topics.json', data)
            flash('已儲存該天記錄', 'success')
    return redirect(url_for('topic_edit', topic_id=topic_id))

@app.route('/topics/<topic_id>/entries/delete/<day_id>', methods=['POST'])
def topic_entry_delete(topic_id, day_id):
    data = load_json('topics.json')
    topic = find_by_id(data['topics'], topic_id)
    if topic:
        topic['entries'] = [e for e in topic['entries'] if e['day_id'] != day_id]
        topic['updated_at'] = now_str()
        save_json('topics.json', data)
        flash('已刪除該天記錄', 'success')
    return redirect(url_for('topic_edit', topic_id=topic_id))

@app.route('/topics/<topic_id>/delete', methods=['POST'])
def topic_delete(topic_id):
    data = load_json('topics.json')
    topic = find_by_id(data['topics'], topic_id)
    if topic:
        data['topics'] = [t for t in data['topics'] if t['id'] != topic_id]
        save_json('topics.json', data)
        flash(f'議題已刪除', 'success')
    return redirect(url_for('topics_list'))

# ──────────────────────────────────────────────
# 路由：人物／機構 (People)
# ──────────────────────────────────────────────

@app.route('/people')
def people_list():
    people = get_all_people()
    return render_template('admin/people_list.html', people=people)

@app.route('/people/new', methods=['GET', 'POST'])
def person_new():
    data = load_json('people.json')
    if request.method == 'POST':
        num = len(data['people']) + 1
        existing_ids = [p['id'] for p in data['people']]
        new_id = f'person-{num}'
        while new_id in existing_ids:
            num += 1
            new_id = f'person-{num}'
        new_person = {
            'id': new_id,
            'name': request.form.get('name', '').strip(),
            'type': request.form.get('type', 'individual'),
            'role': request.form.get('role', '').strip(),
            'description': '',
            'represented_by': request.form.get('represented_by', '').strip(),
            'day_ids': [],
            'topic_ids': [],
            'published': False,
            'updated_at': now_str()
        }
        data['people'].append(new_person)
        save_json('people.json', data)
        flash(f'「{new_person["name"]}」已建立', 'success')
        return redirect(url_for('person_edit', person_id=new_id))
    return render_template('admin/person_new.html')

@app.route('/people/<person_id>/edit', methods=['GET', 'POST'])
def person_edit(person_id):
    data = load_json('people.json')
    person = find_by_id(data['people'], person_id)
    if not person:
        flash('找不到該人物／機構', 'error')
        return redirect(url_for('people_list'))

    days = get_all_days()
    topics = get_all_topics()

    if request.method == 'POST':
        person['name'] = request.form.get('name', '').strip()
        person['type'] = request.form.get('type', 'individual')
        person['role'] = request.form.get('role', '').strip()
        person['description'] = request.form.get('description', '').strip()
        person['represented_by'] = request.form.get('represented_by', '').strip()
        person['day_ids'] = request.form.getlist('day_ids')
        person['topic_ids'] = request.form.getlist('topic_ids')
        person['published'] = 'published' in request.form
        person['updated_at'] = now_str()
        save_json('people.json', data)
        flash(f'「{person["name"]}」已儲存', 'success')
        return redirect(url_for('person_edit', person_id=person_id))

    return render_template('admin/person_edit.html', person=person, days=days, topics=topics)

@app.route('/people/<person_id>/delete', methods=['POST'])
def person_delete(person_id):
    data = load_json('people.json')
    person = find_by_id(data['people'], person_id)
    if person:
        data['people'] = [p for p in data['people'] if p['id'] != person_id]
        save_json('people.json', data)
        flash('已刪除', 'success')
    return redirect(url_for('people_list'))

# ──────────────────────────────────────────────
# 路由：謄本搜尋
# ──────────────────────────────────────────────

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    results = []
    if query:
        results = search_transcripts(query)
    return render_template('admin/search.html', query=query, results=results)

# ──────────────────────────────────────────────
# 路由：發布
# ──────────────────────────────────────────────

@app.route('/publish', methods=['POST'])
def publish():
    try:
        settings = get_settings()
        coming_soon = settings.get('coming_soon', True)

        # 執行 build.py 生成靜態網站（本地）
        result = subprocess.run(
            ['python3', os.path.join(BASE_DIR, 'build.py')],
            capture_output=True, text=True, cwd=BASE_DIR
        )
        if result.returncode != 0:
            flash(f'網站生成失敗：{result.stderr}', 'error')
            return redirect(url_for('dashboard'))

        # 若處於「整理中」模式，推送時以佔位頁面取代首頁
        real_index = os.path.join(BASE_DIR, 'docs', 'index.html')
        backup_index = os.path.join(BASE_DIR, 'docs', '_real_index.html')
        coming_soon_html = os.path.join(BASE_DIR, 'docs', '_coming_soon.html')

        if coming_soon and os.path.exists(coming_soon_html):
            import shutil
            shutil.copy(real_index, backup_index)      # 備份真實首頁
            shutil.copy(coming_soon_html, real_index)  # 用佔位頁面替換

        # Git 操作
        git_cmds = [
            ['git', 'add', 'docs/', 'data/'],
            ['git', 'commit', '-m', f'更新：{now_str()}'],
            ['git', 'push']
        ]
        push_failed = False
        for cmd in git_cmds:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE_DIR)
            if r.returncode != 0 and 'nothing to commit' not in r.stdout and 'nothing to commit' not in r.stderr:
                if cmd[1] == 'push':
                    push_failed = True
                    flash(f'已生成，但推送失敗（請確認 GitHub 設定）：{r.stderr}', 'warning')

        # 推送完成後還原真實首頁（本地保留完整預覽）
        if coming_soon and os.path.exists(backup_index):
            import shutil
            shutil.copy(backup_index, real_index)
            os.remove(backup_index)

        if not push_failed:
            settings['last_published'] = now_str()
            save_json('settings.json', settings)
            if coming_soon:
                flash('已推送至 GitHub（外界目前看到「整理中」頁面，本地預覽正常）', 'success')
            else:
                flash('網站已成功正式發布！', 'success')

    except Exception as e:
        flash(f'發布時出錯：{str(e)}', 'error')

    return redirect(url_for('dashboard'))

@app.route('/preview', methods=['POST'])
def preview_build():
    """只生成靜態文件，不推送到 GitHub"""
    try:
        result = subprocess.run(
            ['python3', os.path.join(BASE_DIR, 'build.py')],
            capture_output=True, text=True, cwd=BASE_DIR
        )
        if result.returncode != 0:
            flash(f'生成失敗：{result.stderr}', 'error')
        else:
            flash('網站已生成（本地預覽），尚未發布到 GitHub', 'success')
    except Exception as e:
        flash(f'生成時出錯：{str(e)}', 'error')
    return redirect(url_for('dashboard'))

# ──────────────────────────────────────────────
# 設定
# ──────────────────────────────────────────────

@app.route('/settings', methods=['GET', 'POST'])
def settings_page():
    settings = get_settings()
    if request.method == 'POST':
        settings['site_title'] = request.form.get('site_title', '').strip()
        settings['site_subtitle'] = request.form.get('site_subtitle', '').strip()
        settings['site_description'] = request.form.get('site_description', '').strip()
        settings['github_repo'] = request.form.get('github_repo', '').strip()
        settings['coming_soon'] = request.form.get('coming_soon', 'true') == 'true'
        save_json('settings.json', settings)
        flash('設定已儲存', 'success')
        return redirect(url_for('settings_page'))
    return render_template('admin/settings.html', settings=settings)

# ──────────────────────────────────────────────
# 啟動
# ──────────────────────────────────────────────

if __name__ == '__main__':
    print('正在建立謄本索引，請稍候...')
    build_transcript_index()
    print('後台已啟動，請在瀏覽器開啟：http://localhost:5001')
    import webbrowser
    webbrowser.open('http://localhost:5001')
    app.run(debug=False, port=5001)
