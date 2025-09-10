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

# Secret Manager 클라이언트 (지연 초기화)
secret_client = None

def get_secret_client():
    """Secret Manager 클라이언트 지연 초기화"""
    global secret_client
    if secret_client is None:
        try:
            secret_client = secretmanager.SecretManagerServiceClient()
        except Exception as e:
            print(f"⚠️ Secret Manager 클라이언트 초기화 실패: {e}")
            secret_client = False
    return secret_client

def get_secret(secret_name):
    """Secret Manager에서 시크릿 값 가져오기 (에러 방지)"""
    try:
        client = get_secret_client()
        if not client:
            print(f"❌ Secret Manager 클라이언트 없음: {secret_name}")
            return None
            
        name = f"projects/{PROJECT_ID}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        print(f"❌ 시크릿 {secret_name} 가져오기 실패: {e}")
        return None

# API 키 및 설정값 로드 (안전한 초기화)
try:
    FRED_API_KEY = get_secret('fred-api-key')
except Exception as e:
    print(f"⚠️ FRED API Key 로드 실패: {e}")
    FRED_API_KEY = None

try:
    BOT_TOKEN = get_secret('telegram-bot-token')
except Exception as e:
    print(f"⚠️ Bot Token 로드 실패: {e}")
    BOT_TOKEN = None

try:
    CHAT_ID = get_secret('telegram-chat-id')
except Exception as e:
    print(f"⚠️ Chat ID 로드 실패: {e}")
    CHAT_ID = None

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
    'RSAFS': {
        'name': '소매판매',
        'unit': '%',
        'importance': 'important',
        'description': '월간 소매판매 증감률'
    }
}

def get_economic_data(series_id):
    """FRED API에서 경제지표 데이터 가져오기 (개선된 버전)"""
    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            'series_id': series_id,
            'api_key': FRED_API_KEY,
            'file_type': 'json',
            'sort_order': 'desc',
            'limit': 3,  # 더 많은 데이터 요청
            'output_type': 1  # 실제 데이터만
        }
        
        logger.info(f"🔍 FRED API 호출: {series_id}")
        
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        # API 응답 로깅
        logger.info(f"📊 {series_id} API 응답: {len(data.get('observations', []))}개 데이터")
        
        observations = data.get('observations', [])
        
        if not observations:
            logger.warning(f"⚠️ {series_id}: 데이터 없음")
            return None
        
        # 유효한 데이터 찾기 (. 이 아닌 실제 값)
        valid_observations = []
        for obs in observations:
            if obs.get('value') != '.' and obs.get('value') is not None:
                try:
                    float(obs['value'])
                    valid_observations.append(obs)
                except (ValueError, TypeError):
                    continue
        
        if len(valid_observations) < 1:
            logger.warning(f"⚠️ {series_id}: 유효한 데이터 없음")
            return None
        
        # 최신 데이터와 이전 데이터
        current = valid_observations[0]
        previous = valid_observations[1] if len(valid_observations) > 1 else current
        
        current_value = float(current['value'])
        previous_value = float(previous['value'])
        
        change = current_value - previous_value
        trend = "📈" if change > 0 else "📉" if change < 0 else "➡️"
        
        result = {
            'value': current_value,
            'previous': previous_value,
            'change': change,
            'trend': trend,
            'date': current['date']
        }
        
        logger.info(f"✅ {series_id}: {current_value} ({change:+.2f})")
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ {series_id} 네트워크 오류: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ {series_id} 데이터 처리 오류: {e}")
        return None

def format_economic_briefing():
    """경제지표 브리핑 메시지 생성 (실제 데이터 사용)"""
    try:
        korean_time = datetime.now(KST)
        
        # 헤더
        message = f"[🇺🇸 미국 경제지표 브리핑 ({korean_time.strftime('%Y-%m-%d')})]\n"
        
        # API 키 확인
        if not FRED_API_KEY:
            logger.error("❌ FRED API Key가 없습니다")
            return "⚠️ FRED API 키 설정이 필요합니다."
        
        logger.info("📊 경제지표 데이터 수집 시작")
        
        # 경제지표 섹션
        message += "\n📈 경제지표\n"
        
        # 핵심 지표 순서대로 처리
        core_indicators = ['UNRATE', 'CPIAUCSL', 'PAYEMS', 'FEDFUNDS', 'RSAFS']
        
        success_count = 0
        
        for series_id in core_indicators:
            if series_id in ECONOMIC_INDICATORS:
                info = ECONOMIC_INDICATORS[series_id]
                data = get_economic_data(series_id)
                
                if data:
                    success_count += 1
                    
                    # 변화량 포맷팅
                    if abs(data['change']) >= 0.01:
                        change_text = f" ({data['change']:+.2f})"
                    else:
                        change_text = ""
                    
                    # 값 포맷팅 (단위별로 다르게)
                    if info['unit'] == '%':
                        value_text = f"{data['value']:.2f}%"
                    elif info['unit'] == '천명':
                        value_text = f"{data['value']:,.1f}{info['unit']}"
                    else:
                        value_text = f"{data['value']:.2f}{info['unit']}"
                    
                    message += f"   • {info['name']}: {value_text}{change_text}\n"
                else:
                    message += f"   • {info['name']}: 데이터 수집 실패\n"
        
        logger.info(f"✅ 성공적으로 수집된 지표: {success_count}/{len(core_indicators)}개")
        
        # 데이터가 하나도 없으면 오류 메시지
        if success_count == 0:
            return f"⚠️ 경제지표 데이터를 가져올 수 없습니다.\n\n업데이트: {korean_time.strftime('%H:%M KST')}"
        
        # 투자 포인트 섹션
        message += "\n🎯 투자 포인트\n"
        message += "   • 금리 역전 - 채권 투자 매력도 상승\n"
        message += "   • 인플레이션 위험 - 실물자산 고려\n"
        
        # 업데이트 시간과 성공률
        message += f"\n업데이트: {korean_time.strftime('%H:%M KST')} ({success_count}/{len(core_indicators)} 성공)"
        
        return message
        
    except Exception as e:
        logger.error(f"브리핑 메시지 생성 실패: {e}")
        return f"⚠️ 브리핑 생성 중 오류가 발생했습니다.\n\n업데이트: {datetime.now(KST).strftime('%H:%M KST')}"

def send_telegram_message(message):
    """텔레그램 메시지 전송"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        
        result = response.json()
        if result.get('ok'):
            logger.info("✅ 텔레그램 브리핑 전송 성공")
            return True
        else:
            logger.error(f"❌ 텔레그램 API 오류: {result}")
            return False
        
    except Exception as e:
        logger.error(f"❌ 텔레그램 전송 실패: {e}")
        return False

def send_daily_briefing():
    """일일 경제지표 브리핑 전송 (로깅 강화)"""
    logger.info("📊 일일 경제지표 브리핑 시작")
    
    # 평일만 브리핑 전송
    korean_time = datetime.now(KST)
    if korean_time.weekday() >= 5:  # 토요일(5), 일요일(6)
        logger.info("📅 주말이므로 브리핑을 건너뜁니다")
        return True
    
    try:
        # FRED API 키 확인
        if not FRED_API_KEY:
            logger.error("❌ FRED API Key가 설정되지 않음")
            return False
        
        logger.info(f"✅ FRED API Key: {FRED_API_KEY[:8]}...")
        
        # 브리핑 메시지 생성
        briefing_message = format_economic_briefing()
        
        # 메시지 미리보기 로깅
        logger.info(f"📝 브리핑 메시지 미리보기: {briefing_message[:100]}...")
        
        # 텔레그램 전송
        success = send_telegram_message(briefing_message)
        
        if success:
            logger.info("✅ 일일 브리핑 완료")
        else:
            logger.error("❌ 일일 브리핑 실패")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ 브리핑 프로세스 오류: {e}")
        return False

# Flask 라우트
@app.route('/')
def health_check():
    """헬스 체크"""
    korean_time = datetime.now(KST)
    
    # 설정 상태 확인
    config_status = {
        'fred_api': '✅' if FRED_API_KEY else '❌',
        'telegram_bot': '✅' if BOT_TOKEN else '❌',
        'telegram_chat': '✅' if CHAT_ID else '❌'
    }
    
    return jsonify({
        'status': 'healthy',
        'service': 'US Economic Indicators Bot',
        'timestamp': korean_time.isoformat(),
        'config': config_status,
        'indicators_count': len(ECONOMIC_INDICATORS),
        'timezone': 'Asia/Seoul'
    })

@app.route('/trigger-briefing', methods=['POST'])
def trigger_briefing():
    """Cloud Scheduler에서 호출하는 브리핑 트리거"""
    try:
        logger.info("🔔 스케줄러에서 브리핑 트리거 호출")
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
        logger.info("🧪 테스트 브리핑 요청")
        success = send_daily_briefing()
        
        return jsonify({
            'status': 'success' if success else 'error',
            'message': '테스트 브리핑 완료' if success else '테스트 브리핑 실패',
            'timestamp': datetime.now(KST).isoformat()
        })
        
    except Exception as e:
        logger.error(f"테스트 브리핑 오류: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now(KST).isoformat()
        }), 500

@app.route('/indicators')
def get_indicators():
    """현재 모니터링 중인 경제지표 목록"""
    return jsonify({
        'indicators': ECONOMIC_INDICATORS,
        'total_count': len(ECONOMIC_INDICATORS),
        'critical_count': len([k for k, v in ECONOMIC_INDICATORS.items() if v['importance'] == 'critical']),
        'timestamp': datetime.now(KST).isoformat()
    })

if __name__ == '__main__':
    # 서비스 시작 로그
    print("🚀 US Economic Indicators Bot 시작")
    print(f"📊 모니터링 지표 수: {len(ECONOMIC_INDICATORS)}개")
    print(f"🕐 현재 한국 시간: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')}")
    
    # 설정 확인 (Secret Manager 에러 방지)
    try:
        if FRED_API_KEY:
            print("✅ FRED API Key 설정됨")
        else:
            print("❌ FRED API Key 없음")
    except Exception as e:
        print(f"⚠️ FRED API Key 확인 중 오류: {e}")
    
    try:
        if BOT_TOKEN:
            print("✅ Telegram Bot Token 설정됨")
        else:
            print("❌ Telegram Bot Token 없음")
    except Exception as e:
        print(f"⚠️ Telegram Bot Token 확인 중 오류: {e}")
    
    try:
        if CHAT_ID:
            print("✅ Telegram Chat ID 설정됨")
        else:
            print("❌ Telegram Chat ID 없음")
    except Exception as e:
        print(f"⚠️ Telegram Chat ID 확인 중 오류: {e}")
    
    print("🌐 Flask 웹서버 시작 중...")
    
    # Flask 서버 시작 (수정된 부분)
    port = int(os.getenv('PORT', 8080))
    print(f"🔌 포트 {port}에서 서버 시작")
    
    try:
        app.run(
            host='0.0.0.0', 
            port=port, 
            debug=False,
            threaded=True,  # 추가
            use_reloader=False  # 추가
        )
    except Exception as e:
        print(f"❌ Flask 서버 시작 실패: {e}")
        import sys
        sys.exit(1)
