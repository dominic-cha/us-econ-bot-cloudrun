def format_economic_briefing():
    """경제지표 브리핑 메시지 생성 (새로운 포맷)"""
    try:
        korean_time = datetime.now(KST)
        
        # 헤더
        message = f"[🇺🇸 미국 경제지표 브리핑 ({korean_time.strftime('%Y-%m-%d')})]\n"
        
        # 경제지표 섹션
        message += "\n📈 경제지표\n"
        
        # 중요 지표들 데이터 수집 및 포맷팅
        indicators_data = []
        
        # 핵심 지표 순서대로 처리
        core_indicators = ['UNRATE', 'CPIAUCSL', 'PAYEMS', 'FEDFUNDS', 'RSAFS']
        
        for series_id in core_indicators:
            if series_id in ECONOMIC_INDICATORS:
                info = ECONOMIC_INDICATORS[series_id]
                data = get_economic_data(series_id)
                
                if data:
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
                    message += f"   • {info['name']}: 데이터 없음\n"
        
        # 투자 포인트 섹션
        message += "\n🎯 투자 포인트\n"
        
        # 투자 시사점 생성
        investment_points = generate_investment_insights()
        for point in investment_points:
            message += f"   • {point}\n"
        
        # 업데이트 시간
        message += f"\n업데이트: {korean_time.strftime('%H:%M KST')}"
        
        return message
        
    except Exception as e:
        logger.error(f"브리핑 메시지 생성 실패: {e}")
        return f"⚠️ 브리핑 생성 중 오류가 발생했습니다.\n\n업데이트: {datetime.now(KST).strftime('%H:%M KST')}"

def generate_investment_insights():
    """투자 시사점 생성"""
    insights = []
    
    try:
        # 금리 데이터 가져오기
        fed_data = get_economic_data('FEDFUNDS')
        dgs10_data = get_economic_data('DGS10')
        dgs2_data = get_economic_data('DGS2')
        cpi_data = get_economic_data('CPIAUCSL')
        
        # 수익률 역전 확인
        if dgs2_data and dgs10_data:
            if dgs2_data['value'] > dgs10_data['value']:
                insights.append("수익률 역전 - 경기침체 우려, 방어적 포지션 고려")
            elif fed_data and fed_data['value'] > dgs10_data['value']:
                insights.append("금리 역전 - 채권 투자 매력도 상승")
            else:
                insights.append("정상 금리 환경 - 주식 투자 우호적")
        
        # 인플레이션 상황
        if cpi_data:
            if cpi_data['value'] < 2.5:
                insights.append("인플레이션 안정 - 성장주 유리")
            elif cpi_data['value'] > 4.0:
                insights.append("인플레이션 위험 - 실물자산 고려")
            else:
                insights.append("인플레이션 적정 수준 - 균형 포트폴리오 유지")
        
        # 고용 상황
        unemployment = get_economic_data('UNRATE')
        if unemployment:
            if unemployment['change'] > 0.2:
                insights.append("고용시장 악화 - 경기둔화 대비 필요")
            elif unemployment['change'] < -0.1:
                insights.append("고용시장 개선 - 소비 관련 주식 긍정적")
        
        # 최소 2개, 최대 3개 시사점 반환
        return insights[:3] if insights else ["시장 동향 면밀히 관찰 필요"]
        
    except Exception as e:
        logger.error(f"투자 시사점 생성 실패: {e}")
        return ["경제지표 분석을 통한 투자 전략 수립 권장"]
