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
    },
    'DGS2': {
        'name': '2년 국채 수익률',
        'unit': '%',
        'importance': 'important',
        'description': '단기금리 지표'
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

def analyze_yield_curve():
    """수익률 곡선 분석"""
    try:
        dgs2_data = get_economic_data('DGS2')
        dgs10_data = get_economic_data('DGS10')
        
        if dgs2_data and dgs10_data:
            spread = dgs10_data['value'] - dgs2_data['value']
            
            if spread < 0:
                return "⚠️ 수익률 역전 (경기침체 신호)"
            elif spread < 0.5:
                return "🟡 수익률 곡선 평탄화"
            else:
                return "✅ 정상적인 수익률 곡선"
        
        return "데이터 없음"
        
    except Exception:
        return "분석 불가"

def get_market_sentiment():
    """시장 심리 분석"""
    try:
        # 주요 지표들로 시장 심리 판단
        unemployment = get_economic_data('UNRATE')
        cpi = get_economic_data('CPIAUCSL')
        
        sentiment_score = 0
        insights = []
        
        if unemployment and unemployment['change'] < 0:
            sentiment_score += 1
            insights.append("고용시장 개선")
        elif unemployment and unemployment['change'] > 0.2:
            sentiment_score -= 1
            insights.append("고용시장 악화")
        
        if cpi and cpi['value'] < 3.0:
            sentiment_score += 1
            insights.append("인플레이션 안정")
        elif cpi and cpi['value'] > 4.0:
            sentiment_score -= 1
            insights.append("인플레이션 우려")
        
        # 수익률 곡선 분석 추가
        yield_analysis = analyze_yield_curve()
        if "역전" in yield_analysis:
            sentiment_score -= 2
            insights.append("수익률 역전 위험")
        
        if sentiment_score >= 1:
            return "🟢 긍정적", insights
        elif sentiment_score <= -1:
            return "🔴 부정적", insights
        else:
            return "🟡 중립적", insights
            
    except Exception:
        return "🟡 분석 불가", []

def format_economic_briefing():
    """경제지표 브리핑 메시지 생성"""
    try:
        korean_time = datetime.now(KST)
        
        message = f"""🇺🇸 미국 경제지표 브리핑
{korean_time.strftime('%Y년 %m월 %d일')}
{'='*30}

📊 핵심 경제지표"""
        
        # 중요 지표들 먼저 표시
        critical_indicators = {k: v for k, v in ECONOMIC_INDICATORS.items() 
                             if v['importance'] == 'critical'}
        
        for series_id, info in critical_indicators.items():
            data = get_economic_data(series_id)
            
            if data:
                message += f"\n• {info['name']}: {data['value']}{info['unit']} {data['trend']}"
                if abs(data['change']) >= 0.01:  # 유의미한 변화만 표시
                    sign = "+" if data['change'] > 0 else ""
                    message += f" ({sign}{data['change']:.2f})"
            else:
                message += f"\n• {info['name']}: 데이터 없음"
        
        # 금융시장 지표
        message += "\n\n💰 금융시장"
        
        # 국채 수익률 및 분석
        dgs10_data = get_economic_data('DGS10')
        dgs2_data = get_economic_data('DGS2')
        
        if dgs10_data:
            message += f"\n• 10년 국채: {dgs10_data['value']}% {dgs10_data['trend']}"
        if dgs2_data:
            message += f"\n• 2년 국채: {dgs2_data['value']}% {dgs2_data['trend']}"
        
        # 수익률 곡선 분석
        yield_analysis = analyze_yield_curve()
        message += f"\n• 수익률 곡선: {yield_analysis}"
        
        # 기타 경제활동 지표
        message += "\n\n📈 경제활동"
        retail_data = get_economic_data('RSAFS')
        if retail_data:
            message += f"\n• 소매판매: {retail_data['value']}% {retail_data['trend']}"
        
        # 시장 심리 분석
        sentiment, insights = get_market_sentiment()
        message += f"\n\n💡 시장 전망: {sentiment}"
        
        if insights:
            for insight in insights[:3]:  # 최대 3개까지
                message += f"\n  • {insight}"
        
        # 투자 시사점
        message += "\n\n🎯 투자 포인트"
        
        # 금리 기반 시사점
        fed_data = get_economic_data('FEDFUNDS')
        if fed_data and dgs10_data:
            if fed_data['value'] > dgs10_data['value']:
                message += "\n  • 금리 역전 - 채권 투자 매력도 상승"
            else:
                message += "\n  • 정상 금리 환경 - 주식 투자 우호적"
        
        # 인플레이션 기반 시사점
        cpi_data = get_economic_data('CPIAUCSL')
        if cpi_data:
            if cpi_data['value'] < 2.5:
                message += "\n  • 인플레이션 안정 - 성장주 유리"
            elif cpi_data['value'] > 4.0:
                message += "\n  • 인플레이션 위험 - 실물자산 고려"
        
        message += f"""

📊 데이터: Federal Reserve Bank of St. Louis
⏰ 업데이트: {korean_time.strftime('%H:%M KST')}
📅 다음 브리핑: 내일 오전 8시"""
        
        return message
        
    except Exception as e:
        logger.error(f"브리핑 메시지 생성 실패: {e}")
        return f"""⚠️ 브리핑 생성 중 오류가 발생했습니다.

🕐 시간: {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}
📞 지원: 시스템 관리자에게 문의하세요.
🔄 재시도: 몇 분 후 다시 시도됩니다."""

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
