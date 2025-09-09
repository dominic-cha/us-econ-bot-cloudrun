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
    'RSAFS': {
        'name': '소매판매',
        'unit': '%',
        'importance': 'important',
        'description': '월간 소매판매 증감률'
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

def get_investment_insights():
    """투자 포인트 생성"""
    insights = []
    
    try:
        # 연방기금 금리와 장기 금리 비교
        fed_data = get_economic_data('FEDFUNDS')
        dgs10_data = get_economic_data('DGS10')
        
        if fed_data and dgs10_data:
            if fed_data['value'] > dgs10_data['value']:
                insights.append("금리 역전 - 채권 투자 매력도 상승")
            else:
                insights.append("정상 금리 환경 - 주식 투자 우호적")
        
        # 인플레이션 상황 판단
        cpi_data = get_economic_data('CPIAUCSL')
        if cpi_data:
            if cpi_data['value'] < 2.5:
                insights.append("인플레이션 안정 - 성장주 유리")
            elif cpi_data['value'] > 4.0:
                insights.append("인플레이션 위험 - 실물자산 고려")
            else:
                insights.append("인플레이션 적정 수준 - 균형 포트폴리오")
        
        # 고용 시장 상황
        unemployment_data = get_economic_data('UNRATE')
        if unemployment_data and unemployment_data['change'] > 0.2:
            insights.append("고용시장 둔화 - 방어주 비중 증가")
        
        return insights[:2]  # 최대 2개까지만 반환
        
    except Exception as e:
        logger.error(f"투자 포인트 생성 실패: {e}")
        return ["시장 상황 모니터링 필요"]

def format_economic_briefing():
    """경제지표 브리핑 메시지 생성 (새 포맷)"""
    try:
        korean_time = datetime.now(KST)
        
        # 제목 및 날짜
        message = f"""🇺🇸 미국 경제지표 브리핑 ({korean_time.strftime('%Y-%m-%d')})
--------------------

📈 경제지표"""
        
        # 각 지표 데이터 수집 및 포맷팅
        for series_id, info in ECONOMIC_INDICATORS.items():
            data = get_economic_data(series_id)
            
            if data:
                # 값 포맷팅
                if info['unit'] == '%':
                    if series_id in ['CPIAUCSL', 'RSAFS']:  # 절대값으로 표시할 지표들
                        value_str = f"{data['value']}{info['unit']}"
                    else:
                        value_str = f"{data['value']:.2f}{info['unit']}"
                else:
                    value_str = f"{data['value']}{info['unit']}"
                
                # 변화량 포맷팅
                if abs(data['change']) >= 0.001:  # 유의미한 변화만 표시
                    if data['change'] > 0:
                        change_str = f" ({data['change']:+.2f})"
                    else:
                        change_str = f" ({data['change']:.2f})"
                else:
                    change_str = ""
                
                message += f"\n• {info['name']}: {value_str} {data['trend']}{change_str}"
            else:
                message += f"\n• {info['name']}: 데이터 없음"
        
        # 투자 포인트 추가
        insights = get_investment_insights()
        if insights:
            message += "\n\n🎯 투자 포인트"
            for insight in insights:
                message += f"\n  • {insight}"
        
        # 업데이트 시간 추가
        message += f"\n\n(업데이트: {korean_time.strftime('%H:%M KST')})"
        
        return message
        
    except Exception as e:
        logger.error(f"브리핑 메시지 생성 실패: {e}")
        return f"""⚠️ 브리핑 생성 중 오류가 발생했습니다.

🕐 시간: {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}
📞 지원: 시스템 관리자에게 문의하세요."""

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
    """일일 경제지표 브리핑 전송"""
    logger.info("📊 일일 경제지표 브리핑 시작")
    
    # 평일만 브리핑 전송
    korean_time = datetime.now(KST)
    if korean_time.weekday() >= 5:  # 토요일(5), 일요일(6)
        logger.info("📅 주말이므로 브리핑을 건너뜁니다")
        return True
    
    try:
        # 브리핑 메시지 생성
        briefing_message = format_economic_briefing()
        
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
    logger.info("🚀 US Economic Indicators Bot 시작")
    logger.info(f"📊 모니터링 지표 수: {len(ECONOMIC_INDICATORS)}개")
    logger.info(f"🕐 현재 한국 시간: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')}")
    
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
    
    logger.info("🌐 Flask 웹서버 시작 중...")
    
    # Flask 서버 시작
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
