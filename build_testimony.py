#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
口供資料庫 — 靜態網站生成器
輸出至 docs-testimony/

用法：
  python3 build_testimony.py           # 正式版（只顯示已發布）
  python3 build_testimony.py --preview # 預覽版（顯示全部）
"""

import os
import json
import sys
from jinja2 import Environment, FileSystemLoader
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
OUTPUT_DIR = os.path.join(BASE_DIR, 'docs-testimony')


def load_json(filename):
    with open(os.path.join(DATA_DIR, filename), 'r', encoding='utf-8') as f:
        return json.load(f)


def write_html(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'  生成：{os.path.relpath(path, BASE_DIR)}')


def text_to_html(text):
    """將純文字段落轉為 HTML（空行 → 新段落）"""
    if not text:
        return ''
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    if not paragraphs:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        return '<p>' + '</p><p>'.join(lines) + '</p>'
    return ''.join(f'<p>{p.replace(chr(10), "<br>")}</p>' for p in paragraphs)


TESTIMONY_TYPE_LABELS = {
    'committee_statement_1': '委員會證人陳述書／口供一',
    'committee_statement_2': '委員會證人陳述書／口供二',
    'police_statement': '警方口供',
    'oral': '親身作供',
}

def build(preview=False):
    # 載入數據
    testimonies = load_json('testimonies.json')['testimonies']
    people = load_json('people.json')['people']
    days = load_json('days.json')['days']
    topics = load_json('topics.json')['topics']

    # 過濾未發布（預覽模式跳過）
    if not preview:
        testimonies = [t for t in testimonies if t.get('published')]

    # 建立查找表
    people_map = {p['id']: p for p in people}
    days_map = {d['id']: d for d in days}
    topics_map = {t['id']: t for t in topics}

    # 豐富數據
    def enrich(t):
        return {
            **t,
            'witness': people_map.get(t.get('witness_id', ''), {}),
            'day': days_map.get(t.get('day_id', ''), {}),
            'topics_data': [topics_map[tid] for tid in t.get('topic_ids', []) if tid in topics_map],
            'testimony_type_label': TESTIMONY_TYPE_LABELS.get(t.get('testimony_type', ''), ''),
        }

    enriched = [enrich(t) for t in testimonies]
    enriched.sort(key=lambda t: (
        t['day'].get('day_number', 999),
        t['witness'].get('name', '')
    ))

    # 建立搜索索引（供 Fuse.js 使用）
    search_index = []
    for t in enriched:
        witness_id = t.get('witness_id', '')
        search_index.append({
            'id': t['id'],
            'witness_name': t['witness'].get('name', ''),
            'witness_role': t['witness'].get('role', ''),
            'witness_org': t['witness'].get('represented_by', ''),
            'day_id': t.get('day_id', ''),
            'day_label': f"第{t['day'].get('day_number', '?')}天" if t.get('day') else '',
            'day_date': t['day'].get('date', ''),
            'witness_id': witness_id,
            'topic_ids': t.get('topic_ids', []),
            'topic_names': [tp['name'] for tp in t.get('topics_data', [])],
            'testimony_type_label': t.get('testimony_type_label', ''),
            'content': t.get('content', ''),
            'url': f'witnesses/{witness_id}.html#testimony-{t["id"]}' if witness_id else ''
        })

    # 篩選器選項：只列出實際有口供記錄的日期、證人、議題
    seen_days, seen_witnesses, seen_topics = set(), set(), set()
    filter_days, filter_witnesses, filter_topics = [], [], []

    for t in enriched:
        if t.get('day_id') and t['day_id'] not in seen_days:
            seen_days.add(t['day_id'])
            filter_days.append(t['day'])
        if t.get('witness_id') and t['witness_id'] not in seen_witnesses:
            seen_witnesses.add(t['witness_id'])
            filter_witnesses.append(t['witness'])
        for tp in t.get('topics_data', []):
            if tp['id'] not in seen_topics:
                seen_topics.add(tp['id'])
                filter_topics.append(tp)

    filter_days.sort(key=lambda d: d.get('day_number', 999))
    filter_witnesses.sort(key=lambda p: p.get('name', ''))
    filter_topics.sort(key=lambda t: t.get('name', ''))

    # 設定 Jinja2
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    env.filters['text_to_html'] = text_to_html

    ctx_base = dict(
        preview=preview,
        generated_at=datetime.now().strftime('%Y-%m-%d %H:%M'),
        filter_days=filter_days,
        filter_witnesses=filter_witnesses,
        filter_topics=filter_topics,
    )

    # 生成 index.html
    tmpl = env.get_template('testimony/index.html')
    html = tmpl.render(
        **ctx_base,
        root='.',
        testimonies=enriched,
        search_index_json=json.dumps(search_index, ensure_ascii=False),
    )
    write_html(os.path.join(OUTPUT_DIR, 'index.html'), html)

    # 生成證人頁面（每人一頁，包含所有口供）
    tmpl_witness = env.get_template('testimony/witness.html')
    # 按 witness_id 分組
    from collections import defaultdict
    by_witness = defaultdict(list)
    for t in enriched:
        wid = t.get('witness_id', '')
        if wid:
            by_witness[wid].append(t)

    witness_count = 0
    for wid, wts in by_witness.items():
        person = people_map.get(wid, {})
        # 按聽證日排序
        wts_sorted = sorted(wts, key=lambda t: t['day'].get('day_number', 999))
        html = tmpl_witness.render(
            **ctx_base,
            root='..',
            person=person,
            testimonies=wts_sorted,
        )
        write_html(os.path.join(OUTPUT_DIR, 'witnesses', f'{wid}.html'), html)
        witness_count += 1

    # 生成代表律師頁面
    lawyers = load_json('lawyers.json')
    tmpl = env.get_template('testimony/lawyers.html')
    html = tmpl.render(**ctx_base, root='.', lawyers=lawyers)
    write_html(os.path.join(OUTPUT_DIR, 'lawyers.html'), html)

    # 生成文件資料庫頁面
    docs = load_json('documents.json')
    tmpl = env.get_template('testimony/documents.html')
    html = tmpl.render(**ctx_base, root='.', docs=docs)
    write_html(os.path.join(OUTPUT_DIR, 'documents.html'), html)

    print(f'\n完成！共生成 {len(enriched)} 份口供記錄，{witness_count} 個證人頁面。')
    print(f'輸出目錄：{OUTPUT_DIR}')


if __name__ == '__main__':
    preview = '--preview' in sys.argv
    print('=== 預覽模式（包含草稿）===' if preview else '=== 正式模式（只含已發布）===')
    build(preview=preview)
