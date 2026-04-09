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
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
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

def get_all_residents():
    return load_json('residents.json')['residents']

def get_all_testimonies():
    return load_json('testimonies.json')['testimonies']

def get_settings():
    return load_json('settings.json')

def find_by_id(items, item_id):
    return next((x for x in items if x['id'] == item_id), None)

def now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M')

# ──────────────────────────────────────────────
# 謄本搜尋（索引緩存至檔案，只在 PDF 有更新時重建）
# ──────────────────────────────────────────────

transcript_index = {}
INDEX_CACHE_PATH = os.path.join(DATA_DIR, 'transcript_index.json')

def get_pdf_fingerprint():
    """取得所有謄本 PDF 的最後修改時間，用作緩存有效性判斷"""
    fingerprint = {}
    for i in range(1, 20):
        pdf_path = os.path.join(TRANSCRIPT_DIR, f'day{i}.pdf')
        if not os.path.exists(pdf_path):
            break
        fingerprint[f'day{i}'] = os.path.getmtime(pdf_path)
    return fingerprint

def build_transcript_index():
    global transcript_index

    current_fingerprint = get_pdf_fingerprint()

    # 嘗試載入緩存
    if os.path.exists(INDEX_CACHE_PATH):
        try:
            with open(INDEX_CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            if cache.get('fingerprint') == current_fingerprint:
                transcript_index = {k: [tuple(x) for x in v]
                                    for k, v in cache['index'].items()}
                print(f'謄本索引從緩存載入，共 {len(transcript_index)} 份（即時完成）')
                return
            else:
                print('偵測到新謄本 PDF，重新建立索引...')
        except Exception:
            print('緩存讀取失敗，重新建立索引...')
    else:
        print('首次建立謄本索引，請稍候...')

    # 重新掃描 PDF（從 days.json 讀取 pdf_file 欄位）
    new_index = {}
    try:
        days_data = load_json('days.json')['days']
    except Exception:
        days_data = []

    for day in sorted(days_data, key=lambda d: d.get('day_number', 0)):
        day_id = day.get('id', '')
        pdf_filename = day.get('pdf_file', '').strip()
        if not pdf_filename:
            # 沒有填 pdf_file 則跳過
            continue
        pdf_path = os.path.join(TRANSCRIPT_DIR, pdf_filename)
        if not os.path.exists(pdf_path):
            print(f'警告：找不到 {pdf_filename}，跳過')
            continue
        lines = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ''
                    for line in text.split('\n'):
                        line = line.strip()
                        if line:
                            parts = line.split(' ', 1)
                            if parts[0].isdigit() and len(parts) > 1:
                                lines.append((int(parts[0]), parts[1]))
                            else:
                                lines.append((0, line))
        except Exception as e:
            print(f'警告：無法讀取 {pdf_filename}: {e}')
        new_index[day_id] = lines
        print(f'  ✓ {pdf_filename}')

    transcript_index = new_index

    # 儲存緩存
    with open(INDEX_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump({'fingerprint': current_fingerprint, 'index': new_index},
                  f, ensure_ascii=False)
    print(f'謄本索引建立完成並已緩存，共 {len(transcript_index)} 份。')

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
        day['pdf_file'] = request.form.get('pdf_file', '').strip()
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
            'description': request.form.get('description', '').strip(),
            'represented_by': request.form.get('represented_by', '').strip(),
            'day_ids': request.form.getlist('day_ids'),
            'topic_ids': request.form.getlist('topic_ids'),
            'published': 'published' in request.form,
            'updated_at': now_str()
        }
        data['people'].append(new_person)
        save_json('people.json', data)
        flash(f'「{new_person["name"]}」已建立', 'success')
        return redirect(url_for('person_edit', person_id=new_id))
    days = get_all_days()
    topics = get_all_topics()
    return render_template('admin/person_edit.html', person=None, days=days, topics=topics)

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

    # 載入此人的口供記錄
    testimony_data = load_json('testimonies.json')
    all_days = get_all_days()
    days_map = {d['id']: d for d in all_days}
    person_testimonies = [
        {**t, 'day': days_map.get(t.get('day_id', ''), {})}
        for t in testimony_data['testimonies']
        if t.get('witness_id') == person_id
    ]
    person_testimonies.sort(key=lambda t: t['day'].get('day_number', 999))

    TESTIMONY_TYPE_LABELS = {
        'committee_statement_1': '委員會證人陳述書／口供一',
        'committee_statement_2': '委員會證人陳述書／口供二',
        'police_statement': '警方口供',
        'oral': '親身作供',
    }
    for t in person_testimonies:
        t['testimony_type_label'] = TESTIMONY_TYPE_LABELS.get(t.get('testimony_type', ''), '')

    return render_template('admin/person_edit.html', person=person, days=days, topics=topics,
                           person_testimonies=person_testimonies)

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
# 路由：居民心聲 (Residents)
# ──────────────────────────────────────────────

@app.route('/residents')
def residents_list():
    residents = get_all_residents()
    days = get_all_days()
    days_map = {d['id']: d for d in days}
    return render_template('admin/residents_list.html', residents=residents, days_map=days_map)

@app.route('/residents/new', methods=['GET', 'POST'])
def resident_new():
    data = load_json('residents.json')
    days = get_all_days()
    if request.method == 'POST':
        num = len(data['residents']) + 1
        existing_ids = [r['id'] for r in data['residents']]
        new_id = f'resident-{num}'
        while new_id in existing_ids:
            num += 1
            new_id = f'resident-{num}'
        new_resident = {
            'id': new_id,
            'name': request.form.get('name', '').strip(),
            'type': request.form.get('type', 'testimony'),
            'role': request.form.get('role', '').strip(),
            'content': request.form.get('content', '').strip(),
            'day_id': request.form.get('day_id', '').strip(),
            'published': 'published' in request.form,
            'updated_at': now_str()
        }
        data['residents'].append(new_resident)
        save_json('residents.json', data)
        flash(f'「{new_resident["name"]}」已建立', 'success')
        return redirect(url_for('resident_edit', resident_id=new_id))
    return render_template('admin/resident_edit.html', resident=None, days=days)

@app.route('/residents/<resident_id>/edit', methods=['GET', 'POST'])
def resident_edit(resident_id):
    data = load_json('residents.json')
    resident = find_by_id(data['residents'], resident_id)
    if not resident:
        flash('找不到該記錄', 'error')
        return redirect(url_for('residents_list'))

    days = get_all_days()

    if request.method == 'POST':
        resident['name'] = request.form.get('name', '').strip()
        resident['type'] = request.form.get('type', 'testimony')
        resident['role'] = request.form.get('role', '').strip()
        resident['content'] = request.form.get('content', '').strip()
        resident['day_id'] = request.form.get('day_id', '').strip()
        resident['published'] = 'published' in request.form
        resident['updated_at'] = now_str()
        save_json('residents.json', data)
        flash(f'「{resident["name"]}」已儲存', 'success')
        return redirect(url_for('resident_edit', resident_id=resident_id))

    return render_template('admin/resident_edit.html', resident=resident, days=days)

@app.route('/residents/<resident_id>/delete', methods=['POST'])
def resident_delete(resident_id):
    data = load_json('residents.json')
    resident = find_by_id(data['residents'], resident_id)
    if resident:
        name = resident['name']
        data['residents'] = [r for r in data['residents'] if r['id'] != resident_id]
        save_json('residents.json', data)
        flash(f'「{name}」已刪除', 'success')
    return redirect(url_for('residents_list'))

# ──────────────────────────────────────────────
# 路由：口供記錄 (Testimonies)
# ──────────────────────────────────────────────

@app.route('/testimonies')
def testimonies_list():
    testimonies = get_all_testimonies()
    people = get_all_people()
    days = get_all_days()
    topics = get_all_topics()
    people_map = {p['id']: p for p in people}
    days_map = {d['id']: d for d in days}
    topics_map = {t['id']: t for t in topics}
    def sort_key(t):
        day = days_map.get(t.get('day_id', ''), {})
        return (day.get('day_number', 999), people_map.get(t.get('witness_id', ''), {}).get('name', ''))
    testimonies = sorted(testimonies, key=sort_key)
    return render_template('admin/testimonies_list.html',
        testimonies=testimonies, people_map=people_map,
        days_map=days_map, topics_map=topics_map)

@app.route('/testimonies/new', methods=['GET', 'POST'])
def testimony_new():
    data = load_json('testimonies.json')
    people = get_all_people()
    days = get_all_days()
    topics = get_all_topics()
    # 從人物頁新增時帶入的 person_id
    from_person = request.args.get('from_person') or request.form.get('from_person', '')
    if request.method == 'POST':
        num = len(data['testimonies']) + 1
        existing_ids = [t['id'] for t in data['testimonies']]
        new_id = f'testimony-{num}'
        while new_id in existing_ids:
            num += 1
            new_id = f'testimony-{num}'
        new_testimony = {
            'id': new_id,
            'witness_id': request.form.get('witness_id', ''),
            'day_id': request.form.get('day_id', ''),
            'testimony_type': request.form.get('testimony_type', ''),
            'topic_ids': request.form.getlist('topic_ids'),
            'content': request.form.get('content', '').strip(),
            'evidence': [],
            'published': 'published' in request.form,
            'updated_at': now_str()
        }
        data['testimonies'].append(new_testimony)
        save_json('testimonies.json', data)
        flash('口供記錄已建立', 'success')
        back_pid = request.form.get('from_person', '')
        if back_pid:
            return redirect(url_for('person_edit', person_id=back_pid))
        return redirect(url_for('testimony_edit', testimony_id=new_id))
    return render_template('admin/testimony_edit.html',
        testimony=None, people=people, days=days, topics=topics,
        from_person=from_person)

@app.route('/testimonies/<testimony_id>/edit', methods=['GET', 'POST'])
def testimony_edit(testimony_id):
    data = load_json('testimonies.json')
    testimony = find_by_id(data['testimonies'], testimony_id)
    if not testimony:
        flash('找不到該記錄', 'error')
        return redirect(url_for('testimonies_list'))
    people = get_all_people()
    days = get_all_days()
    topics = get_all_topics()
    from_person = request.args.get('from_person') or request.form.get('from_person', '')
    if request.method == 'POST':
        testimony['witness_id'] = request.form.get('witness_id', '')
        testimony['day_id'] = request.form.get('day_id', '')
        testimony['testimony_type'] = request.form.get('testimony_type', '')
        testimony['topic_ids'] = request.form.getlist('topic_ids')
        testimony['content'] = request.form.get('content', '').strip()
        testimony['published'] = 'published' in request.form
        testimony['updated_at'] = now_str()
        save_json('testimonies.json', data)
        flash('已儲存', 'success')
        back_pid = request.form.get('from_person', '')
        if back_pid:
            return redirect(url_for('person_edit', person_id=back_pid))
        return redirect(url_for('testimony_edit', testimony_id=testimony_id))
    return render_template('admin/testimony_edit.html',
        testimony=testimony, people=people, days=days, topics=topics,
        from_person=from_person)

@app.route('/testimonies/<testimony_id>/delete', methods=['POST'])
def testimony_delete(testimony_id):
    data = load_json('testimonies.json')
    back_pid = request.form.get('from_person', '')
    data['testimonies'] = [t for t in data['testimonies'] if t['id'] != testimony_id]
    save_json('testimonies.json', data)
    flash('已刪除', 'success')
    if back_pid:
        return redirect(url_for('person_edit', person_id=back_pid))
    return redirect(url_for('testimonies_list'))

@app.route('/testimonies/<testimony_id>/evidence/add', methods=['POST'])
def testimony_evidence_add(testimony_id):
    data = load_json('testimonies.json')
    testimony = find_by_id(data['testimonies'], testimony_id)
    if testimony:
        item = {
            'title': request.form.get('title', '').strip(),
            'description': request.form.get('description', '').strip()
        }
        if item['title']:
            testimony.setdefault('evidence', []).append(item)
            testimony['updated_at'] = now_str()
            save_json('testimonies.json', data)
            flash('證據已加入', 'success')
    return redirect(url_for('testimony_edit', testimony_id=testimony_id))

@app.route('/testimonies/<testimony_id>/evidence/delete/<int:idx>', methods=['POST'])
def testimony_evidence_delete(testimony_id, idx):
    data = load_json('testimonies.json')
    testimony = find_by_id(data['testimonies'], testimony_id)
    if testimony and 0 <= idx < len(testimony.get('evidence', [])):
        testimony['evidence'].pop(idx)
        testimony['updated_at'] = now_str()
        save_json('testimonies.json', data)
        flash('已刪除', 'success')
    return redirect(url_for('testimony_edit', testimony_id=testimony_id))

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

@app.route('/preview-site/')
@app.route('/preview-site/<path:filename>')
def preview_site(filename='index.html'):
    """在後台內直接預覽生成的網站"""
    return send_from_directory(os.path.join(BASE_DIR, 'docs'), filename)

@app.route('/preview-testimony-site/')
@app.route('/preview-testimony-site/<path:filename>')
def preview_testimony_site(filename='index.html'):
    return send_from_directory(os.path.join(BASE_DIR, 'docs-testimony'), filename)

@app.route('/preview-testimony', methods=['POST'])
def preview_testimony_build():
    try:
        result = subprocess.run(
            ['python3', os.path.join(BASE_DIR, 'build_testimony.py'), '--preview'],
            capture_output=True, text=True, cwd=BASE_DIR
        )
        if result.returncode != 0:
            return f'<p>生成失敗：{result.stderr}</p>', 500
        from flask import redirect
        return redirect('/preview-testimony-site/')
    except Exception as e:
        return f'<p>生成時出錯：{str(e)}</p>', 500

@app.route('/preview', methods=['POST'])
def preview_build():
    """預覽模式：生成含草稿的完整網站，完成後跳轉至預覽頁（在新分頁開啟）"""
    try:
        result = subprocess.run(
            ['python3', os.path.join(BASE_DIR, 'build.py'), '--preview'],
            capture_output=True, text=True, cwd=BASE_DIR
        )
        if result.returncode != 0:
            return f'<p>生成失敗：{result.stderr}</p>', 500
        from flask import redirect
        return redirect('/preview-site/')
    except Exception as e:
        return f'<p>生成時出錯：{str(e)}</p>', 500

# ──────────────────────────────────────────────
# 路由：支持記者
# ──────────────────────────────────────────────

@app.route('/support', methods=['GET', 'POST'])
def support_page():
    support = load_json('support.json')
    if request.method == 'POST':
        support['block_1'] = {
            'title':     request.form.get('block_1_title', '').strip(),
            'content':   request.form.get('block_1_content', '').strip(),
            'url':       request.form.get('block_1_url', '').strip(),
            'url_label': request.form.get('block_1_url_label', '').strip(),
        }
        support['block_2'] = {
            'title':     request.form.get('block_2_title', '').strip(),
            'content':   request.form.get('block_2_content', '').strip(),
            'url':       request.form.get('block_2_url', '').strip(),
            'url_label': request.form.get('block_2_url_label', '').strip(),
        }
        save_json('support.json', support)
        flash('支持記者頁面已儲存', 'success')
        return redirect(url_for('support_page'))
    return render_template('admin/support_edit.html', support=support)

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
# 路由：文件資料庫
# ──────────────────────────────────────────────

def get_documents():
    return load_json('documents.json')

def save_documents(data):
    save_json('documents.json', data)

@app.route('/documents')
def documents_list():
    data = get_documents()
    return render_template('admin/documents_list.html', data=data)

@app.route('/documents/topics/new', methods=['POST'])
def document_topic_new():
    data = get_documents()
    name = request.form.get('name', '').strip()
    if name:
        import uuid
        topic_id = 'topic-' + uuid.uuid4().hex[:8]
        data['topics'].append({'id': topic_id, 'name': name, 'documents': []})
        save_documents(data)
        flash(f'議題「{name}」已建立', 'success')
    return redirect(url_for('documents_list'))

@app.route('/documents/topics/<topic_id>/rename', methods=['POST'])
def document_topic_rename(topic_id):
    data = get_documents()
    topic = next((t for t in data['topics'] if t['id'] == topic_id), None)
    if topic:
        new_name = request.form.get('name', '').strip()
        if new_name:
            topic['name'] = new_name
            save_documents(data)
            flash('議題已更新', 'success')
    return redirect(url_for('documents_list'))

@app.route('/documents/topics/<topic_id>/delete', methods=['POST'])
def document_topic_delete(topic_id):
    data = get_documents()
    data['topics'] = [t for t in data['topics'] if t['id'] != topic_id]
    save_documents(data)
    flash('議題已刪除', 'success')
    return redirect(url_for('documents_list'))

@app.route('/documents/topics/<topic_id>/documents/new', methods=['GET', 'POST'])
def document_new(topic_id):
    data = get_documents()
    topic = next((t for t in data['topics'] if t['id'] == topic_id), None)
    if not topic:
        flash('找不到該議題', 'error')
        return redirect(url_for('documents_list'))
    if request.method == 'POST':
        doc = {
            'title': request.form.get('title', '').strip(),
            'url': request.form.get('url', '').strip(),
            'description': request.form.get('description', '').strip(),
            'date': request.form.get('date', '').strip(),
        }
        topic['documents'].append(doc)
        save_documents(data)
        flash(f'「{doc["title"]}」已加入', 'success')
        return redirect(url_for('documents_list'))
    return render_template('admin/document_edit.html', topic=topic, doc=None, doc_idx=None)

@app.route('/documents/topics/<topic_id>/documents/<int:doc_idx>/edit', methods=['GET', 'POST'])
def document_edit(topic_id, doc_idx):
    data = get_documents()
    topic = next((t for t in data['topics'] if t['id'] == topic_id), None)
    if not topic or doc_idx >= len(topic['documents']):
        flash('找不到該文件', 'error')
        return redirect(url_for('documents_list'))
    doc = topic['documents'][doc_idx]
    if request.method == 'POST':
        doc['title'] = request.form.get('title', '').strip()
        doc['url'] = request.form.get('url', '').strip()
        doc['description'] = request.form.get('description', '').strip()
        doc['date'] = request.form.get('date', '').strip()
        save_documents(data)
        flash('文件已儲存', 'success')
        return redirect(url_for('documents_list'))
    return render_template('admin/document_edit.html', topic=topic, doc=doc, doc_idx=doc_idx)

@app.route('/documents/topics/<topic_id>/documents/<int:doc_idx>/delete', methods=['POST'])
def document_delete(topic_id, doc_idx):
    data = get_documents()
    topic = next((t for t in data['topics'] if t['id'] == topic_id), None)
    if topic and doc_idx < len(topic['documents']):
        removed = topic['documents'].pop(doc_idx)
        save_documents(data)
        flash(f'「{removed["title"]}」已刪除', 'success')
    return redirect(url_for('documents_list'))

# ──────────────────────────────────────────────
# 啟動
# ──────────────────────────────────────────────

if __name__ == '__main__':
    build_transcript_index()
    print('後台已啟動，請在瀏覽器開啟：http://localhost:5001')
    import webbrowser
    webbrowser.open('http://localhost:5001')
    # use_reloader=False 避免 debug 模式下索引被建立兩次
    app.run(debug=True, port=5001, use_reloader=True, reloader_type='stat')
