#!/usr/bin/env python3
"""
미국 경제지표 분석 봇 - Google App Engine 버전
매일 오전 8시 한국시간 기준 경제지표 분석 리포트 전송
"""

import os
import logging
import requests
from datetime import datetime, timedelta
import pytz
from flask import Flask, request, jsonify

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask 앱
app = Flask(__name__)

# 환경변수
FRED_API_KEY = os.environ.get('FRED_API_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# 한국 시간대
KST = pytz.timezone('Asia/Seoul')

# ==================== FRED 데이터 수집 ====================

def get_fred_data(series_id):
    """FRED API에서 데이터 가져오기"""
    
    base_url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        'series_id': series_id,
        'api_key': FRED_API_KEY,
        'file_type': 'json',
        'observation_start': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
        'observation_end': datetime.now().strftime('%Y-%m-%d'),
        'sort_order': 'desc',
        'limit': 10
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        observations = data.get('observations', [])
        if observations and len(observations) >= 2:
            latest = float(observations[0]['value'])
            previous = float(observations[1]['value'])
            change = ((latest - previous) / abs(previous) * 100) if previous != 0 else 0
            
            return {
                'value': latest,
                'change': round(change, 2),
                'date': observations[0]['date']
            }
    except Exception as e:
        logger.error(f"FRED API 오류 ({series_id}): {e}")
    
    return None

def get_all_indicators():
    """모든 경제지표 수집"""
    
    indicators = {
        'DFF': '연방기금금리',
        'DGS10': '10년 국채수익률',
        'DGS2': '2년 국채수익률',
        'T10Y2Y': '10년-2년 스프레드',
        'UNRATE': '실업률',
        'PAYEMS': '비농업고용',
        'ICSA': '신규실업수당청구',
        'CPIAUCSL': 'CPI',
        'CPILFESL': '근원CPI',
        'PPIACO': 'PPI',
        'GDPC1': '실질GDP',
        'RSXFS': '소매판매',
        'INDPRO': '산업생산지수',
        'MANEMP': 'ISM 제조업',
        'NMFBAI': 'ISM 서비스업',
        'HOUST': '주택착공',
        'MORTGAGE30US': '30년 모기지금리',
        'UMCSENT': '소비자신뢰지수',
        'SAHMREALTIME': 'Sahm Rule'
    }
    
    results = {}
    for series_id, name in indicators.items():
        data = get_fred_data(series_id)
        if data:
            data['name'] = name
            results[series_id] = data
            logger.info(f"수집 완료: {name}")
    
    return results

# ==================== 텔레그램 전송 ====================

def send_telegram_message(text):
    """텔레그램 메시지 전송"""
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("텔레그램 설정 누락")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        return result.get('ok', False)
    except Exception as e:
        logger.error(f"텔레그램 전송 실패: {e}")
        return False

def format_report(data):
    """리포트 포맷팅"""
    
    kst_time = datetime.now(KST).strftime('%Y-%m-%d %H:%M')
    
    title = "미국 경제지표 일일 브리핑"
    underline = "=" * len(title)
    
    message = f"""<b>{title}</b>
<b>{underline}</b>
📅 {kst_time} KST

<b>🏛️ 통화정책</b>"""
    
    # 통화정책
    for key in ['DFF', 'DGS10', 'DGS2', 'T10Y2Y']:
        if key in data:
            item = data[key]
            value = f"{item['value']:.2f}%"
            change = "📈" if item['change'] > 0 else "📉" if item['change'] < 0 else "➡️"
            message += f"\n  • {item['name']}: {value} {change} {item['change']:+.1f}%"
    
    # 고용
    message += "\n\n<b>💼 고용시장</b>"
    for key in ['UNRATE', 'PAYEMS', 'ICSA']:
        if key in data:
            item = data[key]
            if key == 'PAYEMS':
                value = f"{item['value']:,.0f}천명"
            elif key == 'ICSA':
                value = f"{item['value']:,.0f}건"
            else:
                value = f"{item['value']:.1f}%"
            change = "📈" if item['change'] > 0 else "📉" if item['change'] < 0 else "➡️"
            message += f"\n  • {item['name']}: {value} {change} {item['change']:+.1f}%"
    
    # 인플레이션
    message += "\n\n<b>💵 인플레이션</b>"
    for key in ['CPIAUCSL', 'CPILFESL', 'PPIACO']:
        if key in data:
            item = data[key]
            value = f"{item['value']:.2f}"
            change = "📈" if item['change'] > 0 else "📉" if item['change'] < 0 else "➡️"
            message += f"\n  • {item['name']}: {value} {change} {item['change']:+.1f}%"
    
    # ISM
    message += "\n\n<b>🏭 기업활동</b>"
    for key in ['MANEMP', 'NMFBAI']:
        if key in data:
            item = data[key]
            value = f"{item['value']:.1f}p"
            status = "(확장)" if item['value'] > 50 else "(위축)"
            message += f"\n  • {item['name']}: {value} {status}"
    
    # 경고 체크
    if 'T10Y2Y' in data and data['T10Y2Y']['value'] < 0:
        message += f"\n\n⚠️ 수익률 곡선 역전: {data['T10Y2Y']['value']:.2f}%p"
    
    if 'SAHMREALTIME' in data and data['SAHMREALTIME']['value'] >= 0.5:
        message += f"\n\n🚨 Sahm Rule 발동: {data['SAHMREALTIME']['value']:.2f}"
    
    message += "\n\n📌 데이터: FRED (세인트루이스 연준)"
    
    return message

# ==================== Flask 라우트 ====================

@app.route('/')
def index():
    """홈페이지"""
    return jsonify({
        'status': 'running',
        'service': 'US Economic Indicators Bot',
        'version': '1.0',
        'time': datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST'),
        'endpoints': ['/daily-report', '/test', '/check-config']
    })

@app.route('/daily-report', methods=['GET', 'POST'])
def daily_report():
    """일일 리포트 생성"""
    
    try:
        logger.info("일일 리포트 생성 시작")
        
        # 데이터 수집
        data = get_all_indicators()
        
        if not data:
            logger.error("데이터 수집 실패")
            return jsonify({'status': 'error', 'message': '데이터 수집 실패'}), 500
        
        # 리포트 생성
        report = format_report(data)
        
        # 텔레그램 전송
        success = send_telegram_message(report)
        
        if success:
            logger.info("리포트 전송 성공")
            return jsonify({
                'status': 'success',
                'message': '리포트 전송 완료',
                'indicators': len(data),
                'time': datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
            })
        else:
            return jsonify({'status': 'error', 'message': '텔레그램 전송 실패'}), 500
            
    except Exception as e:
        logger.error(f"리포트 생성 오류: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/test')
def test():
    """테스트 메시지"""
    
    message = f"""✅ 경제지표 봇 테스트

시간: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')}
설정 상태:
• FRED API: {'✅ 설정됨' if FRED_API_KEY else '❌ 미설정'}
• Telegram Bot: {'✅ 설정됨' if TELEGRAM_BOT_TOKEN else '❌ 미설정'}
• Chat ID: {'✅ 설정됨' if TELEGRAM_CHAT_ID else '❌ 미설정'}

정상 작동 중입니다."""
    
    success = send_telegram_message(message)
    
    return jsonify({
        'status': 'success' if success else 'failed',
        'message': '테스트 메시지 ' + ('전송됨' if success else '실패'),
        'config': {
            'fred': bool(FRED_API_KEY),
            'telegram': bool(TELEGRAM_BOT_TOKEN),
            'chat_id': bool(TELEGRAM_CHAT_ID)
        }
    })

@app.route('/check-config')
def check_config():
    """설정 확인"""
    
    return jsonify({
        'fred_api': bool(FRED_API_KEY),
        'telegram_bot': bool(TELEGRAM_BOT_TOKEN),
        'telegram_chat': bool(TELEGRAM_CHAT_ID),
        'timezone': str(KST),
        'current_time': datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')
    })

@app.route('/health')
def health():
    """헬스 체크"""
    return 'OK', 200

# App Engine 시작
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
