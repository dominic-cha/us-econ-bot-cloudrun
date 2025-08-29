#!/usr/bin/env python3
"""
미국 경제지표 분석 봇 - FRED API 전용 버전
매일 오전 8시 한국시간 기준 경제지표 분석 리포트 전송
"""

import os
import logging
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
# import schedule
import threading
import pytz

from fred_collector import FREDCollector
from analyzer import EconomicAnalyzer
from telegram_bot import TelegramMessenger

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('economic_bot.log')
    ]
)
logger = logging.getLogger(__name__)

# Flask 앱
app = Flask(__name__)

# 환경변수
FRED_API_KEY = os.environ.get('FRED_API_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', None)  # 선택사항
PORT = int(os.environ.get('PORT', 8080))

# 한국 시간대
KST = pytz.timezone('Asia/Seoul')

# 전역 컴포넌트
fred = None
analyzer = None
telegram = None

def initialize():
    """컴포넌트 초기화"""
    global fred, analyzer, telegram
    
    # 환경변수 체크
    if not all([FRED_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        logger.error("❌ 필수 환경변수 누락")
        logger.error(f"FRED_API_KEY: {'✅' if FRED_API_KEY else '❌'}")
        logger.error(f"TELEGRAM_BOT_TOKEN: {'✅' if TELEGRAM_BOT_TOKEN else '❌'}")
        logger.error(f"TELEGRAM_CHAT_ID: {'✅' if TELEGRAM_CHAT_ID else '❌'}")
        return False
    
    try:
        fred = FREDCollector(FRED_API_KEY)
        analyzer = EconomicAnalyzer(OPENAI_API_KEY)
        telegram = TelegramMessenger(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        
        logger.info("✅ 모든 컴포넌트 초기화 성공")
        return True
        
    except Exception as e:
        logger.error(f"❌ 초기화 실패: {e}")
        return False

def daily_economic_report():
    """일일 경제지표 리포트 생성 및 전송"""
    
    try:
        logger.info("=" * 50)
        logger.info("📊 일일 경제지표 분석 시작")
        logger.info(f"시간: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')}")
        
        # 1. 데이터 수집
        logger.info("1️⃣ FRED 데이터 수집 중...")
        raw_data = fred.get_latest_values()
        
        if not raw_data:
            raise Exception("데이터 수집 실패")
        
        logger.info(f"   ✅ {len(raw_data)}개 지표 수집 완료")
        
        # 2. 수익률 곡선 체크
        logger.info("2️⃣ 수익률 곡선 분석 중...")
        yield_curve = fred.check_yield_curve()
        
        # 3. 경제지표 분석
        logger.info("3️⃣ 경제지표 종합 분석 중...")
        analysis = analyzer.analyze_indicators(raw_data)
        analysis['yield_curve'] = yield_curve
        
        # 4. AI 인사이트 (선택사항)
        if OPENAI_API_KEY:
            logger.info("4️⃣ AI 인사이트 생성 중...")
            ai_insights = analyzer.generate_ai_insights(analysis)
            analysis['ai_insights'] = ai_insights
        
        # 5. 리포트 전송
        logger.info("5️⃣ 텔레그램 리포트 전송 중...")
        
        # 포맷팅된 메시지 생성
        message = format_daily_report(analysis, raw_data)
        
        # 전송
        success = telegram._send_message(message, parse_mode='HTML')
        
        if success:
            logger.info("✅ 일일 리포트 전송 완료!")
        else:
            logger.error("❌ 리포트 전송 실패")
            
        return analysis
        
    except Exception as e:
        logger.error(f"❌ 리포트 생성 중 오류: {e}")
        
        # 오류 알림
        telegram.send_alert(
            'critical',
            f"일일 리포트 생성 실패:\n{str(e)}"
        )
        return None

def format_daily_report(analysis: dict, raw_data: dict) -> str:
    """리포트 포맷팅"""
    
    kst_time = datetime.now(KST).strftime('%Y-%m-%d %H:%M')
    
    message = f"""<b>📊 미국 경제지표 일일 브리핑</b>
<b>📅 {kst_time} KST</b>

<b>🎯 경제 현황 요약</b>
• 시장 국면: {analysis.get('market_phase', 'N/A')}
• 리스크 레벨: {analysis.get('risk_level', 'N/A')}

<b>📈 핵심 경제지표</b>"""
    
    # 카테고리별 지표 정리
    categories = {
        '🏛️ 통화정책': ['DFF', 'DFEDTARU', 'DGS10', 'DGS2', 'T10Y2Y'],
        '💼 고용시장': ['UNRATE', 'PAYEMS', 'ICSA', 'CIVPART'],
        '💵 인플레이션': ['CPIAUCSL', 'CPILFESL', 'PCEPI'],
        '📊 경제성장': ['GDPC1', 'RSXFS', 'INDPRO'],
        '🏠 주택시장': ['HOUST', 'PERMIT', 'MORTGAGE30US']
    }
    
    for category, indicators in categories.items():
        has_data = False
        category_text = f"\n\n<b>{category}</b>"
        
        for ind in indicators:
            if ind in raw_data:
                if not has_data:
                    message += category_text
                    has_data = True
                
                data = raw_data[ind]
                name = data.get('name', ind)
                value = data.get('value', 0)
                change = data.get('change', {})
                
                # 값 포맷팅
                if ind in ['UNRATE', 'DFF', 'DGS10', 'DGS2', 'MORTGAGE30US', 'CIVPART']:
                    value_str = f"{value:.2f}%"
                elif ind == 'PAYEMS':
                    value_str = f"{value:,.0f}천명"
                elif ind == 'ICSA':
                    value_str = f"{value:,.0f}건"
                elif ind == 'HOUST':
                    value_str = f"{value:,.0f}천호"
                else:
                    value_str = f"{value:.2f}"
                
                # 변화 표시
                change_str = ""
                if change:
                    pct = change.get('percent', 0)
                    if pct > 0.1:
                        change_str = f"📈 +{pct:.1f}%"
                    elif pct < -0.1:
                        change_str = f"📉 {pct:.1f}%"
                    else:
                        change_str = "➡️ 0.0%"
                
                message += f"\n• {name}: {value_str} {change_str}"
    
    # 수익률 곡선 특별 섹션
    if 'yield_curve' in analysis:
        yc = analysis['yield_curve']
        message += f"\n\n<b>💹 수익률 곡선 분석</b>"
        message += f"\n• 10년물: {yc.get('ten_year', 0):.3f}%"
        message += f"\n• 2년물: {yc.get('two_year', 0):.3f}%"
        message += f"\n• 스프레드: {yc.get('spread', 0):.3f}%p"
        
        if yc.get('inverted'):
            message += f"\n<b>⚠️ 경고: 수익률 곡선 역전!</b>"
            message += f"\n<i>역사적으로 경기침체 선행지표</i>"
    
    # Sahm Rule 체크
    if 'SAHMREALTIME' in raw_data:
        sahm_value = raw_data['SAHMREALTIME'].get('value', 0)
        if sahm_value >= 0.5:
            message += f"\n\n<b>🚨 Sahm Rule 발동: {sahm_value:.2f}</b>"
            message += f"\n<i>경기침체 진입 신호</i>"
    
    # 투자 권고사항
    if analysis.get('recommendations'):
        message += f"\n\n<b>💡 투자 시사점</b>"
        for rec in analysis['recommendations'][:3]:
            message += f"\n{rec}"
    
    # AI 인사이트 (있는 경우)
    if analysis.get('ai_insights'):
        message += f"\n\n<b>🤖 AI 분석</b>"
        # 200자 제한
        ai_text = analysis['ai_insights'][:200]
        if len(analysis['ai_insights']) > 200:
            ai_text += "..."
        message += f"\n<i>{ai_text}</i>"
    
    # 푸터
    message += f"\n\n<b>📌 정보</b>"
    message += f"\n• 데이터: FRED (세인트루이스 연준)"
    message += f"\n• 다음 업데이트: 내일 오전 8시"
    
    return message

def check_critical_alerts():
    """중요 지표 실시간 모니터링 (1시간마다)"""
    
    try:
        alerts = []
        
        # 1. 실업수당 청구 급증 체크
        icsa = fred.get_series_data('ICSA')
        if not icsa.empty:
            latest = icsa.iloc[-1]['value']
            if latest > 300000:
                alerts.append(f"📈 실업수당 청구 급증: {latest:,.0f}건")
        
        # 2. Sahm Rule 체크
        sahm = fred.get_series_data('SAHMREALTIME')
        if not sahm.empty:
            latest = sahm.iloc[-1]['value']
            if latest >= 0.3:
                alerts.append(f"⚠️ Sahm Rule 경고: {latest:.2f}")
        
        # 3. 수익률 곡선 체크
        yield_curve = fred.check_yield_curve()
        if yield_curve.get('inverted'):
            spread = yield_curve.get('spread', 0)
            if spread < -0.5:
                alerts.append(f"🔴 심각한 수익률 역전: {spread:.2f}%p")
        
        # 알림 전송
        if alerts:
            message = "🚨 <b>경제지표 긴급 알림</b>\n\n"
            message += "\n".join(alerts)
            message += f"\n\n시간: {datetime.now(KST).strftime('%H:%M KST')}"
            
            telegram._send_message(message, parse_mode='HTML')
            logger.warning(f"긴급 알림 전송: {len(alerts)}건")
            
    except Exception as e:
        logger.error(f"긴급 체크 오류: {e}")

def run_scheduler():
    """스케줄러 실행"""
    
    # 매일 오전 8시 (한국시간)
    schedule.every().day.at("08:00").do(daily_economic_report)
    
    # 매시간 긴급 체크
    schedule.every().hour.do(check_critical_alerts)
    
    logger.info("⏰ 스케줄러 시작")
    logger.info("  - 일일 리포트: 매일 08:00 KST")
    logger.info("  - 긴급 체크: 매시간")
    
    while True:
        schedule.run_pending()
        time.sleep(60)

# Flask 라우트
@app.route('/')
def index():
    return jsonify({
        'service': '미국 경제지표 분석 봇',
        'status': 'running',
        'version': '1.0.0',
        'time': datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'components': {
            'fred': fred is not None,
            'analyzer': analyzer is not None,
            'telegram': telegram is not None
        }
    })

@app.route('/trigger', methods=['POST'])
def trigger():
    """수동 리포트 트리거"""
    
    # 간단한 인증
    token = request.headers.get('X-Auth-Token')
    if token != os.environ.get('TRIGGER_TOKEN', 'your-secret-token'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    # 리포트 생성
    result = daily_economic_report()
    
    if result:
        return jsonify({
            'status': 'success',
            'market_phase': result.get('market_phase'),
            'risk_level': result.get('risk_level')
        })
    else:
        return jsonify({'status': 'error'}), 500

@app.route('/test')
def test():
    """테스트 메시지"""
    
    success = telegram.send_alert(
        'info',
        '✅ 경제지표 봇 테스트\n정상 작동 중입니다.'
    )
    
    return jsonify({'status': 'success' if success else 'failed'})

def main():
    """메인 함수"""
    
    logger.info("🚀 미국 경제지표 분석 봇 시작...")
    
    # 초기화
    if not initialize():
        logger.error("초기화 실패. 종료합니다.")
        return
    
    # 시작 알림
    telegram.send_alert(
        'success',
        f"""✅ 경제지표 분석 봇 가동

📊 수집 지표: {len(fred.indicators)}개
⏰ 일일 리포트: 매일 08:00 KST
🔍 긴급 모니터링: 매시간

준비 완료!"""
    )
    
    # 스케줄러 시작 (별도 스레드)
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Flask 서버 실행
    app.run(host='0.0.0.0', port=PORT, debug=False)

if __name__ == '__main__':
    main()
