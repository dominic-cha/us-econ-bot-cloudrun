import os
import requests
import schedule
import time
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, request
from google.cloud import secretmanager
import logging

# Flask 앱 초기화
app = Flask(__name__)

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 환경 변수
PROJECT_ID = os.getenv('PROJECT_ID', 'us-econ-bot')
KST = timezone(timedelta(hours=9))

# Secret Manager 클라이언트
secret_client = secretmanager.SecretManagerServiceClient()

def get_secret(secret_name):
    """Secret Manager에서 시크릿 값 가져오기"""
    try:
        name = f"projects/{PROJECT_ID}/secrets/{secret_name}/versions/latest"
        response = secret_client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.error(f"시크릿 {secret_name} 가져오기 실패: {e}")
        return None

# API 키 및 설정값 로드
FRED_API_KEY = get_secret('fred-api-key')
BOT_TOKEN = get_secret('telegram-bot-token')
CHAT_ID = get_secret('telegram-chat-id')

# 주요 경제지표 정의
ECONOMIC_INDICATORS = {
    'UNRATE': {
        'name': '실업률',
        'unit': '%',
        'importance': 'critical',
        'description': '미국 실업률'
    },
    'CPIAUCSL': {
        'name': 'CPI',
        'unit': '%',
        'importance': 'critical', 
        'description': '소비자물가지수 (전년동월대비)'
    },
    'PAYEMS': {
        'name': '비농업 취업자',
        'unit': '천명',
        'importance': 'critical',
        'description': '월간 고용 증가'
    },
    'FEDFUNDS': {
        'name': '연방기금 금리',
        'unit': '%',
        'importance': 'critical',
        'description': '기준금리'
    },
    'DGS10': {
        'name': '10년 국채 수익률',
        'unit': '%',
        'importance': 'important',
        'description': '장기금리 지표'
    }
}

def get_economic_data(series_id):
    """FRED API에서 경제지표 데이터 가져오기"""
    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            'series_id': series_id,
            'api_key': FRED_API_KEY,
            'file_type': 'json',
            'sort_order': 'desc',
            'limit': 2
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        observations = data.get('observations', [])
        
        if len(observations) >= 2:
            current = observations[0]
            previous = observations[1]
            
            current_value = float(current['value']) if current['value'] != '.' else None
            previous_value = float(previous['value']) if previous['value'] != '.' else None
            
            if current_value is not None and previous_value is not None:
                change = current_value - previous_value
                trend = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                
                return {
                    'value': current_value,
                    'previous': previous_value,
                    'change': change,
                    'trend': trend,
                    'date': current['date']
                }
        
        return None
        
    except Exception as e:
        logger.error(f"경제지표 {series_id} 데이터 가져오기 실패: {e}")
        return None

def format_economic_briefing():
    """경제지표 브리핑 메시지 생성"""
    try:
        korean_time = datetime.now(KST)
        
        message = f"""🇺🇸 미국 경제지표 브리핑
{korean_time.strftime('%Y년 %m월 %d일 (%A)')}
{'='*35}

📊 주요 경제지표"""
        
        # 각 지표 데이터 수집 및 포맷팅
        for series_id, info in ECONOMIC_INDICATORS.items():
            data = get_economic_data(series_id)
            
            if data:
                if info['importance'] == 'critical':
                    message += f"\n• {info['name']}: {data['value']}{info['unit']} {data['trend']}"
                    if data['change'] != 0:
                        sign = "+" if data['change'] > 0 else ""
                        message += f" ({sign}{data['change']:.2f})"
            else:
                message += f"\n• {info['name']}: 데이터 없음"
        
        message += f"""

💡 시장 포인트
- 최신 데이터 기준 경제동향 분석
- FRED (연준) 공식 데이터 사용
- 다음 업데이트: 내일 오전 8시

📊 데이터 출처: Federal Reserve Bank of St. Louis
⏰ 업데이트: {korean_time.strftime('%H:%M KST')}"""
        
        return message
        
    except Exception as e:
        logger.error(f"브리핑 메시지 생성 실패: {e}")
        return f"⚠️ 브리핑 생성 중 오류가 발생했습니다.\n시간: {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}"

def send_telegram_message(message):
    """텔레그램 메시지 전송"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        logger.info("✅ 텔레그램 브리핑 전송 성공")
        return True
        
    except Exception as e:
        logger.error(f"❌ 텔레그램 전송 실패: {e}")
        return False

def send_daily_briefing():
    """일일 경제지표 브리핑 전송"""
    logger.info("📊 일일 경제지표 브리핑 시작")
    
    # 브리핑 메시지 생성
    briefing_message = format_economic_briefing()
    
    # 텔레그램 전송
    success = send_telegram_message(briefing_message)
    
    if success:
        logger.info("✅ 일일 브리핑 완료")
    else:
        logger.error("❌ 일일 브리핑 실패")
    
    return success

# Flask 라우트
@app.route('/')
def health_check():
    """헬스 체크"""
    return jsonify({
        'status': 'healthy',
        'service': 'US Economic Indicators Bot',
        'timestamp': datetime.now(KST).isoformat()
    })

@app.route('/trigger-briefing', methods=['POST'])
def trigger_briefing():
    """Cloud Scheduler에서 호출하는 브리핑 트리거"""
    try:
        success = send_daily_briefing()
        
        if success:
            return jsonify({
                'status': 'success',
                'message': '브리핑 전송 완료',
                'timestamp': datetime.now(KST).isoformat()
            })
        else:
            return jsonify({
                'status': 'error', 
                'message': '브리핑 전송 실패',
                'timestamp': datetime.now(KST).isoformat()
            }), 500
            
    except Exception as e:
        logger.error(f"브리핑 트리거 오류: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now(KST).isoformat()
        }), 500

@app.route('/test-briefing')
def test_briefing():
    """브리핑 테스트용 엔드포인트"""
    try:
        success = send_daily_briefing()
        
        return jsonify({
            'status': 'success' if success else 'error',
            'message': '테스트 브리핑 완료' if success else '테스트 브리핑 실패',
            'timestamp': datetime.now(KST).isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now(KST).isoformat()
        }), 500

if __name__ == '__main__':
    # 서비스 시작 로그
    logger.info("🚀 US Economic Indicators Bot 시작")
    logger.info(f"📊 모니터링 지표 수: {len(ECONOMIC_INDICATORS)}개")
    
    # 설정 확인
    if FRED_API_KEY:
        logger.info("✅ FRED API Key 설정됨")
    else:
        logger.error("❌ FRED API Key 없음")
    
    if BOT_TOKEN:
        logger.info("✅ Telegram Bot Token 설정됨")
    else:
        logger.error("❌ Telegram Bot Token 없음")
    
    if CHAT_ID:
        logger.info("✅ Telegram Chat ID 설정됨")
    else:
        logger.error("❌ Telegram Chat ID 없음")
    
    # Flask 서버 시작
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
