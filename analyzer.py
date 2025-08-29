"""
경제지표 분석 엔진
수집된 데이터를 분석하여 시장 상황 판단 및 투자 인사이트 생성
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class EconomicAnalyzer:
    """경제지표 종합 분석"""
    
    def __init__(self, openai_api_key: str = None):
        self.openai_api_key = openai_api_key
        
        # 경제지표 임계값 (경고 수준)
        self.thresholds = {
            'UNRATE': {
                'critical': 5.0,  # 실업률 5% 이상
                'warning': 4.5,
                'normal': 3.5
            },
            'CPIAUCSL': {  # CPI 전년비 (추정)
                'critical': 4.0,
                'warning': 3.0,
                'normal': 2.0
            },
            'PPIACO': {  # PPI
                'critical': 5.0,
                'warning': 3.5,
                'normal': 2.0
            },
            'DFF': {  # 연방기금금리
                'critical': 5.0,
                'warning': 4.0,
                'normal': 2.0
            },
            'T10Y2Y': {  # 수익률 커브
                'critical': -0.5,
                'warning': 0,
                'normal': 1.0
            },
            'SAHMREALTIME': {  # Sahm Rule
                'critical': 0.5,
                'warning': 0.3,
                'normal': 0.1
            },
            'ICSA': {  # 실업수당 청구
                'critical': 300000,
                'warning': 250000,
                'normal': 200000
            },
            'MANEMP': {  # ISM 제조업 (50 기준)
                'critical': 45,  # 45 미만 심각한 위축
                'warning': 48,   # 48 미만 위축
                'normal': 50     # 50 이상 확장
            },
            'NMFBAI': {  # ISM 서비스업 (50 기준)
                'critical': 45,
                'warning': 48,
                'normal': 50
            }
        }
        
        # 시장 국면 판단 가중치
        self.phase_weights = {
            'GDPC1': 0.25,
            'UNRATE': 0.20,
            'CPIAUCSL': 0.15,
            'RSXFS': 0.15,
            'INDPRO': 0.10,
            'HOUST': 0.10,
            'UMCSENT': 0.05
        }
    
    def analyze_indicators(self, data: Dict) -> Dict:
        """경제지표 종합 분석"""
        
        analysis = {
            'timestamp': datetime.now().isoformat(),
            'indicators': {},
            'alerts': [],
            'market_phase': '',
            'risk_level': '',
            'recommendations': [],
            'summary': {}
        }
        
        # 1. 개별 지표 분석
        for indicator_id, indicator_data in data.items():
            if 'value' in indicator_data:
                result = self._analyze_single_indicator(indicator_id, indicator_data)
                analysis['indicators'][indicator_id] = result
                
                # 경고 수집
                if result['status'] in ['warning', 'critical']:
                    analysis['alerts'].append({
                        'indicator': indicator_data['name'],
                        'status': result['status'],
                        'value': indicator_data['value'],
                        'message': result['interpretation']
                    })
        
        # 2. 시장 국면 판단
        analysis['market_phase'] = self._determine_market_phase(analysis['indicators'], data)
        
        # 3. 리스크 레벨 계산
        analysis['risk_level'] = self._calculate_risk_level(analysis['indicators'], data)
        
        # 4. 투자 권고사항 생성
        analysis['recommendations'] = self._generate_recommendations(
            analysis['market_phase'], 
            analysis['risk_level'],
            analysis['alerts']
        )
        
        # 5. 요약 통계
        analysis['summary'] = self._create_summary(data)
        
        return analysis
    
    def _analyze_single_indicator(self, indicator_id: str, data: Dict) -> Dict:
        """개별 지표 분석"""
        
        value = data.get('value', 0)
        change = data.get('change', {})
        
        result = {
            'current': value,
            'change': change,
            'status': 'normal',
            'trend': '',
            'interpretation': ''
        }
        
        # 임계값 체크
        if indicator_id in self.thresholds:
            thresholds = self.thresholds[indicator_id]
            
            # 지표별 방향성 고려
            if indicator_id in ['T10Y2Y']:  # 낮을수록 위험
                if value <= thresholds['critical']:
                    result['status'] = 'critical'
                elif value <= thresholds['warning']:
                    result['status'] = 'warning'
            else:  # 높을수록 위험
                if value >= thresholds['critical']:
                    result['status'] = 'critical'
                elif value >= thresholds['warning']:
                    result['status'] = 'warning'
        
        # 트렌드 판단
        if change:
            pct = change.get('percent', 0)
            if abs(pct) < 0.5:
                result['trend'] = '→ 보합'
            elif pct > 0:
                result['trend'] = '↗️ 상승'
            else:
                result['trend'] = '↘️ 하락'
        
        # 해석 생성
        result['interpretation'] = self._interpret_indicator(indicator_id, value, change)
        
        return result
    
    def _determine_market_phase(self, indicators: Dict, raw_data: Dict) -> str:
        """시장 국면 판단"""
        
        # 주요 지표 추출
        gdp_growth = self._estimate_gdp_growth(raw_data.get('GDPC1', {}))
        unemployment = raw_data.get('UNRATE', {}).get('value', 0)
        inflation = self._estimate_inflation(raw_data.get('CPIAUCSL', {}))
        retail_sales = raw_data.get('RSXFS', {}).get('change', {}).get('percent', 0)
        
        # Sahm Rule 체크
        sahm_value = raw_data.get('SAHMREALTIME', {}).get('value', 0)
        
        # 수익률 곡선
        yield_spread = raw_data.get('T10Y2Y', {}).get('value', 0)
        
        # 종합 판단
        if sahm_value >= 0.5:
            return "🔴 경기침체 (Recession)"
        elif yield_spread < 0 and unemployment > 4:
            return "🟠 경기둔화 (Slowdown)"
        elif gdp_growth > 3 and unemployment < 3.5:
            return "🟡 과열 (Overheating)"
        elif gdp_growth > 2 and unemployment < 4:
            return "🟢 확장 (Expansion)"
        elif gdp_growth > 0 and gdp_growth <= 2:
            return "🔵 완만한 성장 (Moderate Growth)"
        else:
            return "⚪ 전환기 (Transition)"
    
    def _calculate_risk_level(self, indicators: Dict, raw_data: Dict) -> str:
        """시장 리스크 레벨 계산"""
        
        risk_score = 0
        max_score = 10
        
        # 1. 수익률 곡선 (3점)
        yield_spread = raw_data.get('T10Y2Y', {}).get('value', 1)
        if yield_spread < -0.5:
            risk_score += 3
        elif yield_spread < 0:
            risk_score += 2
        elif yield_spread < 0.5:
            risk_score += 1
        
        # 2. Sahm Rule (3점)
        sahm = raw_data.get('SAHMREALTIME', {}).get('value', 0)
        if sahm >= 0.5:
            risk_score += 3
        elif sahm >= 0.3:
            risk_score += 2
        elif sahm >= 0.2:
            risk_score += 1
        
        # 3. 실업률 (2점)
        unemployment = raw_data.get('UNRATE', {}).get('value', 0)
        if unemployment > 5:
            risk_score += 2
        elif unemployment > 4:
            risk_score += 1
        
        # 4. 인플레이션 (2점)
        inflation = self._estimate_inflation(raw_data.get('CPIAUCSL', {}))
        if inflation > 4 or inflation < 1:
            risk_score += 2
        elif inflation > 3 or inflation < 1.5:
            risk_score += 1
        
        # 리스크 레벨 판정
        risk_pct = (risk_score / max_score) * 100
        
        if risk_pct >= 70:
            return "🔴 매우 높음 (Very High)"
        elif risk_pct >= 50:
            return "🟠 높음 (High)"
        elif risk_pct >= 30:
            return "🟡 중간 (Medium)"
        elif risk_pct >= 15:
            return "🟢 낮음 (Low)"
        else:
            return "🔵 매우 낮음 (Very Low)"
    
    def _generate_recommendations(self, market_phase: str, risk_level: str, alerts: List) -> List[str]:
        """투자 권고사항 생성 (이모티콘 제거)"""
        
        recommendations = []
        
        # 시장 국면별 권고
        if "침체" in market_phase:
            recommendations.extend([
                "현금 비중 확대 권고",
                "방어주 (유틸리티, 필수소비재) 관심",
                "장기 국채 비중 증가 고려"
            ])
        elif "둔화" in market_phase:
            recommendations.extend([
                "포트폴리오 리밸런싱 시점",
                "배당주 비중 증가 검토",
                "성장주 비중 축소 고려"
            ])
        elif "과열" in market_phase:
            recommendations.extend([
                "차익실현 시점 검토",
                "리스크 관리 강화 필요",
                "단기 유동성 확보"
            ])
        elif "확장" in market_phase:
            recommendations.extend([
                "주식 비중 유지/확대",
                "경기민감주 관심",
                "성장주 투자 기회"
            ])
        
        # 리스크 레벨별 권고
        if "매우 높음" in risk_level or "높음" in risk_level:
            recommendations.append("레버리지 투자 금지")
            recommendations.append("헤지 포지션 구축")
        
        # 특별 경고 사항
        for alert in alerts[:2]:  # 상위 2개 경고만
            if alert['status'] == 'critical':
                if 'Sahm' in alert['indicator']:
                    recommendations.append("경기침체 대비 포지션 조정")
                elif '수익률' in alert['indicator']:
                    recommendations.append("수익률 역전 - 방어적 포지션")
                elif 'ISM' in alert['indicator']:
                    recommendations.append("제조업/서비스업 위축 - 경기순환주 회피")
        
        # ISM 지수 관련 권고
        if any('ISM' in ind for ind in [a['indicator'] for a in alerts]):
            recommendations.append("ISM 50 미만 - 경기둔화 대비")
        
        return recommendations[:5]  # 최대 5개 권고사항
    
    def _interpret_indicator(self, indicator_id: str, value: float, change: Dict) -> str:
        """지표별 해석"""
        
        interpretations = {
            'UNRATE': self._interpret_unemployment(value),
            'CPIAUCSL': self._interpret_inflation(value, change),
            'PPIACO': self._interpret_ppi(value, change),
            'DFF': self._interpret_fed_rate(value),
            'GDPC1': self._interpret_gdp(value, change),
            'T10Y2Y': self._interpret_yield_curve(value),
            'SAHMREALTIME': self._interpret_sahm_rule(value),
            'ICSA': self._interpret_jobless_claims(value),
            'RSXFS': self._interpret_retail_sales(change),
            'HOUST': self._interpret_housing_starts(value),
            'UMCSENT': self._interpret_consumer_sentiment(value),
            'MANEMP': self._interpret_ism_manufacturing(value),
            'NMFBAI': self._interpret_ism_services(value),
            'IR': self._interpret_import_prices(change),
            'IQ': self._interpret_export_prices(change)
        }
        
        return interpretations.get(indicator_id, "데이터 분석 중")
    
    def _interpret_unemployment(self, value: float) -> str:
        if value < 3.5:
            return "완전고용 수준 - 임금상승 압력"
        elif value < 4.0:
            return "건전한 고용시장"
        elif value < 5.0:
            return "고용시장 둔화 신호"
        else:
            return "고용시장 악화 - 경기침체 우려"
    
    def _interpret_inflation(self, value: float, change: Dict) -> str:
        # CPI 전년비 추정 (월간 변화율 * 12)
        monthly_change = change.get('percent', 0) if change else 0
        annual_estimate = monthly_change * 12
        
        if annual_estimate > 3:
            return "인플레이션 압력 상승"
        elif annual_estimate > 2:
            return "목표 수준 근접"
        elif annual_estimate > 1:
            return "안정적인 물가 상승"
        else:
            return "디플레이션 우려"
    
    def _interpret_fed_rate(self, value: float) -> str:
        if value >= 5:
            return "긴축적 통화정책"
        elif value >= 3:
            return "중립적 통화정책"
        elif value >= 1:
            return "완화적 통화정책"
        else:
            return "초완화적 통화정책"
    
    def _interpret_gdp(self, value: float, change: Dict) -> str:
        # 분기 성장률 연율 환산 추정
        growth_estimate = change.get('percent', 0) * 4 if change else 0
        
        if growth_estimate > 3:
            return "강한 경제성장"
        elif growth_estimate > 2:
            return "건전한 성장세"
        elif growth_estimate > 0:
            return "성장 둔화"
        else:
            return "경기 위축"
    
    def _interpret_yield_curve(self, value: float) -> str:
        if value < -0.5:
            return "심각한 역전 - 경기침체 임박"
        elif value < 0:
            return "수익률 역전 - 경기침체 경고"
        elif value < 0.5:
            return "평탄화 - 경기둔화 신호"
        else:
            return "정상 수익률 곡선"
    
    def _interpret_sahm_rule(self, value: float) -> str:
        if value >= 0.5:
            return "경기침체 진입 (Sahm Rule 발동)"
        elif value >= 0.3:
            return "경기침체 경고 수준"
        elif value >= 0.2:
            return "고용시장 약화 신호"
        else:
            return "정상 수준"
    
    def _interpret_jobless_claims(self, value: float) -> str:
        if value > 300000:
            return "실업 급증 - 고용시장 악화"
        elif value > 250000:
            return "실업 증가 추세"
        elif value > 200000:
            return "정상 범위"
        else:
            return "낮은 실업 청구 - 강한 고용"
    
    def _interpret_retail_sales(self, change: Dict) -> str:
        pct = change.get('percent', 0) if change else 0
        
        if pct > 1:
            return "강한 소비 증가"
        elif pct > 0:
            return "소비 증가세"
        elif pct > -1:
            return "소비 둔화"
        else:
            return "소비 위축"
    
    def _interpret_housing_starts(self, value: float) -> str:
        if value > 1500:
            return "주택시장 호황"
        elif value > 1300:
            return "활발한 주택건설"
        elif value > 1100:
            return "정상적인 건설활동"
        else:
            return "주택시장 둔화"
    
    def _interpret_consumer_sentiment(self, value: float) -> str:
        if value > 100:
            return "낙관적 소비심리"
        elif value > 90:
            return "긍정적 소비심리"
        elif value > 80:
            return "중립적 소비심리"
        else:
            return "비관적 소비심리"
    
    def _interpret_ism_manufacturing(self, value: float) -> str:
        """ISM 제조업지수 해석 (50 기준선)"""
        if value >= 60:
            return "제조업 강한 확장"
        elif value >= 55:
            return "제조업 확장"
        elif value >= 50:
            return "제조업 완만한 확장"
        elif value >= 48:
            return "제조업 위축 시작"
        elif value >= 45:
            return "제조업 위축"
        else:
            return "제조업 심각한 위축"
    
    def _interpret_ism_services(self, value: float) -> str:
        """ISM 서비스업지수 해석 (50 기준선)"""
        if value >= 60:
            return "서비스업 강한 확장"
        elif value >= 55:
            return "서비스업 확장"
        elif value >= 50:
            return "서비스업 완만한 확장"
        elif value >= 48:
            return "서비스업 위축 시작"
        elif value >= 45:
            return "서비스업 위축"
        else:
            return "서비스업 심각한 위축"
    
    def _interpret_ppi(self, value: float, change: Dict) -> str:
        """PPI (생산자물가) 해석"""
        monthly_change = change.get('percent', 0) if change else 0
        annual_estimate = monthly_change * 12
        
        if annual_estimate > 4:
            return "생산자물가 급등 - 비용 압력 심화"
        elif annual_estimate > 3:
            return "생산자물가 상승 압력"
        elif annual_estimate > 2:
            return "생산자물가 온건한 상승"
        else:
            return "생산자물가 안정적"
    
    def _interpret_import_prices(self, change: Dict) -> str:
        """수입물가 해석"""
        pct = change.get('percent', 0) if change else 0
        
        if pct > 2:
            return "수입물가 급등 - 인플레이션 압력"
        elif pct > 1:
            return "수입물가 상승"
        elif pct > -1:
            return "수입물가 안정"
        else:
            return "수입물가 하락 - 디플레이션 압력"
    
    def _interpret_export_prices(self, change: Dict) -> str:
        """수출물가 해석"""
        pct = change.get('percent', 0) if change else 0
        
        if pct > 2:
            return "수출물가 강세 - 경쟁력 약화 우려"
        elif pct > 0:
            return "수출물가 상승"
        elif pct > -2:
            return "수출물가 안정"
        else:
            return "수출물가 약세 - 경쟁력 개선"
    
    def _estimate_gdp_growth(self, gdp_data: Dict) -> float:
        """GDP 성장률 추정"""
        if not gdp_data or 'change' not in gdp_data:
            return 0
        
        # 분기 성장률을 연율로 환산
        quarterly_change = gdp_data['change'].get('percent', 0)
        return quarterly_change * 4
    
    def _estimate_inflation(self, cpi_data: Dict) -> float:
        """인플레이션율 추정"""
        if not cpi_data or 'change' not in cpi_data:
            return 0
        
        # 월간 변화율을 연율로 환산
        monthly_change = cpi_data['change'].get('percent', 0)
        return monthly_change * 12
    
    def _create_summary(self, data: Dict) -> Dict:
        """요약 통계 생성"""
        
        summary = {
            'total_indicators': len(data),
            'updated_indicators': sum(1 for d in data.values() if 'value' in d),
            'critical_indicators': [],
            'improving_indicators': [],
            'deteriorating_indicators': []
        }
        
        for indicator_id, indicator_data in data.items():
            if 'change' in indicator_data and indicator_data['change']:
                pct_change = indicator_data['change'].get('percent', 0)
                
                # 개선/악화 판단 (지표 특성에 따라)
                if indicator_id in ['UNRATE', 'CPIAUCSL', 'ICSA']:  # 낮을수록 좋은 지표
                    if pct_change < -1:
                        summary['improving_indicators'].append(indicator_data['name'])
                    elif pct_change > 1:
                        summary['deteriorating_indicators'].append(indicator_data['name'])
                else:  # 높을수록 좋은 지표
                    if pct_change > 1:
                        summary['improving_indicators'].append(indicator_data['name'])
                    elif pct_change < -1:
                        summary['deteriorating_indicators'].append(indicator_data['name'])
        
        return summary
