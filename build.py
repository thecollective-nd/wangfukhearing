#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
靜態網站生成器
從 data/*.json 生成 docs/ 下的完整靜態網站
"""

import os
import json
import shutil
from jinja2 import Environment, FileSystemLoader
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates', 'public')
OUTPUT_DIR = os.path.join(BASE_DIR, 'docs')

# ──────────────────────────────────────────────
# 工具函數
# ──────────────────────────────────────────────

def load_json(filename):
    with open(os.path.join(DATA_DIR, filename), 'r', encoding='utf-8') as f:
        return json.load(f)

def text_to_html(text):
    """將純文字段落轉為 HTML（空行 → 新段落）"""
    if not text:
        return ''
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    if not paragraphs:
        # 單段
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        return '<p>' + '</p><p>'.join(lines) + '</p>'
    return ''.join(f'<p>{p.replace(chr(10), "<br>")}</p>' for p in paragraphs)

def format_date(date_str):
    """2026-03-19 → 2026年3月19日"""
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return f'{d.year}年{d.month}月{d.day}日'
    except:
        return date_str

def write_html(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'  生成：{os.path.relpath(path, BASE_DIR)}')

# ──────────────────────────────────────────────
# 主體
# ──────────────────────────────────────────────

def build():
    print('=== 開始生成網站 ===')

    # 載入所有數據
    days_data = load_json('days.json')['days']
    topics_data = load_json('topics.json')['topics']
    people_data = load_json('people.json')['people']
    settings = load_json('settings.json')

    # 只顯示已發布的內容
    days = [d for d in days_data if d['published']]
    topics = [t for t in topics_data if t['published']]
    people = [p for p in people_data if p['published']]

    # 建立查找字典
    days_map = {d['id']: d for d in days_data}
    topics_map = {t['id']: t for t in topics_data}
    people_map = {p['id']: p for p in people_data}

    # 設置 Jinja2（從 templates/ 根目錄載入，支援 public/base.html 路徑）
    env = Environment(loader=FileSystemLoader(os.path.join(BASE_DIR, 'templates')))
    env.filters['date_format'] = format_date
    env.filters['text_to_html'] = text_to_html

    # 全域模板變數
    global_ctx = {
        'settings': settings,
        'all_days': days,
        'all_topics': topics,
        'all_people': people,
        'days_map': days_map,
        'topics_map': topics_map,
        'people_map': people_map,
        'build_time': datetime.now().strftime('%Y年%-m月%-d日 %H:%M')
    }

    # 清空並重建 docs/
    if os.path.exists(OUTPUT_DIR):
        # 只清除 HTML，保留 .git 和 assets
        for item in os.listdir(OUTPUT_DIR):
            item_path = os.path.join(OUTPUT_DIR, item)
            if item.startswith('.') or item == 'assets':
                continue
            if os.path.isfile(item_path):
                os.remove(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 複製 CSS
    assets_src = os.path.join(BASE_DIR, 'templates', 'public', 'assets')
    assets_dst = os.path.join(OUTPUT_DIR, 'assets')
    if os.path.exists(assets_src):
        if os.path.exists(assets_dst):
            shutil.rmtree(assets_dst)
        shutil.copytree(assets_src, assets_dst)

    # ── 首頁
    tmpl = env.get_template('public/index.html')
    recent_days = sorted(days, key=lambda x: x['date'], reverse=True)[:5]
    html = tmpl.render(**global_ctx, recent_days=recent_days)
    write_html(os.path.join(OUTPUT_DIR, 'index.html'), html)

    # ── 聽證日列表
    tmpl = env.get_template('public/days_list.html')
    html = tmpl.render(**global_ctx,
        sorted_days=sorted(days, key=lambda x: x['day_number']))
    write_html(os.path.join(OUTPUT_DIR, 'days', 'index.html'), html)

    # ── 個別聽證日
    tmpl = env.get_template('public/day.html')
    for day in days:
        day_topics = [topics_map[tid] for tid in day.get('topic_ids', []) if tid in topics_map]
        day_people = [people_map[pid] for pid in day.get('people_ids', []) if pid in people_map]
        html = tmpl.render(**global_ctx, day=day,
            day_topics=day_topics, day_people=day_people)
        write_html(os.path.join(OUTPUT_DIR, 'days', f'{day["id"]}.html'), html)

    # ── 議題列表
    tmpl = env.get_template('public/topics_list.html')
    html = tmpl.render(**global_ctx)
    write_html(os.path.join(OUTPUT_DIR, 'topics', 'index.html'), html)

    # ── 個別議題
    tmpl = env.get_template('public/topic.html')
    for topic in topics:
        entries_with_days = []
        for entry in topic.get('entries', []):
            d = days_map.get(entry['day_id'])
            if d and d['published']:
                entries_with_days.append({**entry, 'day': d})
        entries_with_days.sort(key=lambda x: x['day']['day_number'])
        html = tmpl.render(**global_ctx, topic=topic, entries=entries_with_days)
        write_html(os.path.join(OUTPUT_DIR, 'topics', f'{topic["id"]}.html'), html)

    # ── 人物／機構列表
    tmpl = env.get_template('public/people_list.html')
    html = tmpl.render(**global_ctx)
    write_html(os.path.join(OUTPUT_DIR, 'people', 'index.html'), html)

    # ── 個別人物／機構
    tmpl = env.get_template('public/person.html')
    for person in people:
        person_days = [days_map[did] for did in person.get('day_ids', []) if did in days_map and days_map[did]['published']]
        person_topics = [topics_map[tid] for tid in person.get('topic_ids', []) if tid in topics_map and topics_map[tid]['published']]
        person_days.sort(key=lambda x: x['day_number'])
        html = tmpl.render(**global_ctx, person=person,
            person_days=person_days, person_topics=person_topics)
        write_html(os.path.join(OUTPUT_DIR, 'people', f'{person["id"]}.html'), html)

    # ── GitHub Pages 需要的 .nojekyll
    open(os.path.join(OUTPUT_DIR, '.nojekyll'), 'w').close()

    print(f'=== 完成！生成 {len(days)} 天 / {len(topics)} 個議題 / {len(people)} 位人物 ===')

if __name__ == '__main__':
    build()
