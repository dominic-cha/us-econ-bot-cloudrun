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
