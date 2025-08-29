"""
FRED API 데이터 수집 모듈
Federal Reserve Economic Data (FRED) API를 통해 미국 경제지표 수집
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
import time

logger = logging.getLogger(__name__)

class FREDCollector:
    """Federal Reserve Economic Data (FRED) API 수집기"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.stlouisfed.org/fred"
        
        # 핵심 경제지표 정의
        self.indicators = {
            # 🏛️ 연준 정책
            'DFF': '연방기금금리',
            'DGS10': '10년 국채수익률',
            'DGS2': '2년 국채수익률',
            'T10Y2Y': '10년-2년 스프레드',
            
            # 💼 고용
            'UNRATE': '실업률',
            'PAYEMS': '비농업고용',
            'ICSA': '신규실업수당청구',
            'CIVPART': '경제활동참가율',
            
            # 💵 인플레이션
            'CPIAUCSL': 'CPI',
            'CPILFESL': '근원CPI',
            'PCEPI': 'PCE물가지수',
            'PPIACO': 'PPI(생산자물가)',
            'IR': '수입물가지수',
            'IQ': '수출물가지수',
            
            # 📈 경제성장
            'GDPC1': '실질GDP',
            'RSXFS': '소매판매',
            'INDPRO': '산업생산지수',
            
            # 🏭 기업활동
            'MANEMP': 'ISM 제조업지수',
            'NMFBAI': 'ISM 서비스업지수',
            'DGORDER': '내구재주문',
            'NEWORDER': '제조업신규주문',
            
            # 🏠 주택
            'HOUST': '주택착공',
            'MORTGAGE30US': '30년모기지금리',
            
            # 📊 경기지표
            'UMCSENT': '미시간소비자신뢰',
            'SAHMREALTIME': 'Sahm Rule',
            'CFNAI': '시카고연준경기지수'
        }
        
        # API 호출 제한 (초당 120회)
        self.rate_limit_delay = 0.01
    
    def get_series_data(self, series_id: str, 
                       start_date: Optional[str] = None,
                       end_date: Optional[str] = None) -> pd.DataFrame:
        """특정 경제지표 데이터 수집"""
        
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        params = {
            'series_id': series_id,
            'api_key': self.api_key,
            'file_type': 'json',
            'observation_start': start_date,
            'observation_end': end_date,
            'sort_order': 'desc',
            'limit': 100
        }
        
        try:
            # Rate limiting
            time.sleep(self.rate_limit_delay)
            
            response = requests.get(
                f"{self.base_url}/series/observations",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            
            # 오류 체크
            if 'error_code' in data:
                logger.error(f"FRED API 오류: {data.get('error_message')}")
                return pd.DataFrame()
            
            observations = data.get('observations', [])
            
            if not observations:
                logger.warning(f"{series_id}: 데이터 없음")
                return pd.DataFrame()
            
            # DataFrame 변환
            df = pd.DataFrame(observations)
            df['date'] = pd.to_datetime(df['date'])
            df['value'] = pd.to_numeric(df['value'], errors='coerce')
            df = df[['date', 'value']].dropna()
            df = df.sort_values('date', ascending=False)
            
            return df
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API 요청 실패 ({series_id}): {e}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"데이터 처리 오류 ({series_id}): {e}")
            return pd.DataFrame()
    
    def get_latest_values(self) -> Dict[str, Dict]:
        """모든 지표의 최신값 조회"""
        
        latest = {}
        total = len(self.indicators)
        
        for idx, (series_id, name) in enumerate(self.indicators.items(), 1):
            logger.info(f"수집 중 [{idx}/{total}]: {name}")
            
            df = self.get_series_data(series_id)
            
            if df.empty:
                continue
            
            # 최신값과 이전값
            latest_row = df.iloc[0] if not df.empty else None
            prev_row = df.iloc[1] if len(df) > 1 else None
            
            if latest_row is not None:
                latest[series_id] = {
                    'name': name,
                    'value': float(latest_row['value']),
                    'date': latest_row['date'].strftime('%Y-%m-%d'),
                    'change': None
                }
                
                # 변화율 계산
                if prev_row is not None and prev_row['value'] != 0:
                    change = float(latest_row['value'] - prev_row['value'])
                    pct_change = (change / abs(prev_row['value'])) * 100
                    
                    latest[series_id]['change'] = {
                        'absolute': round(change, 4),
                        'percent': round(pct_change, 2),
                        'prev_value': float(prev_row['value'])
                    }
        
        logger.info(f"✅ 수집 완료: {len(latest)}/{total} 지표")
        return latest
    
    def check_yield_curve(self) -> Dict:
        """수익률 곡선 역전 체크"""
        
        try:
            # 10년물과 2년물 수익률 조회
            ten_year = self.get_series_data('DGS10')
            two_year = self.get_series_data('DGS2')
            
            if ten_year.empty or two_year.empty:
                return {
                    'status': 'error',
                    'message': '데이터 수집 실패'
                }
            
            # 최신값
            latest_10y = float(ten_year.iloc[0]['value'])
            latest_2y = float(two_year.iloc[0]['value'])
            spread = latest_10y - latest_2y
            
            # 과거 스프레드 추이 (30일)
            historical_spreads = []
            for i in range(min(30, len(ten_year), len(two_year))):
                if i < len(ten_year) and i < len(two_year):
                    hist_spread = float(ten_year.iloc[i]['value']) - float(two_year.iloc[i]['value'])
                    historical_spreads.append(hist_spread)
            
            # 평균 스프레드
            avg_spread = sum(historical_spreads) / len(historical_spreads) if historical_spreads else 0
            
            return {
                'ten_year': round(latest_10y, 3),
                'two_year': round(latest_2y, 3),
                'spread': round(spread, 3),
                'avg_spread_30d': round(avg_spread, 3),
                'inverted': spread < 0,
                'severity': 'severe' if spread < -0.5 else 'moderate' if spread < 0 else 'none',
                'message': self._get_yield_curve_message(spread),
                'date': ten_year.iloc[0]['date'].strftime('%Y-%m-%d')
            }
            
        except Exception as e:
            logger.error(f"수익률 곡선 분석 오류: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def _get_yield_curve_message(self, spread: float) -> str:
        """수익률 곡선 상태 메시지"""
        
        if spread < -1.0:
            return "🔴 심각한 역전 (경기침체 강력 신호)"
        elif spread < -0.5:
            return "🟠 뚜렷한 역전 (경기침체 경고)"
        elif spread < 0:
            return "🟡 경미한 역전 (주의 필요)"
        elif spread < 0.5:
            return "⚠️ 평탄화 (경기둔화 신호)"
        elif spread < 1.0:
            return "➡️ 정상 범위"
        else:
            return "✅ 정상 (경기확장)"
    
    def get_economic_calendar(self) -> List[Dict]:
        """주요 경제지표 발표 일정 (FRED API는 일정 미제공, 더미 데이터)"""
        
        # 실제로는 별도 캘린더 API 필요
        # 여기서는 주요 지표 발표일 예시만 제공
        
        calendar = [
            {'date': '매월 첫째 금요일', 'indicator': '비농업고용 (고용보고서)'},
            {'date': '매월 둘째 주', 'indicator': 'CPI (소비자물가지수)'},
            {'date': '매월 셋째 주', 'indicator': '소매판매'},
            {'date': '분기별', 'indicator': 'GDP (국내총생산)'},
            {'date': 'FOMC 8회/년', 'indicator': '연준 금리결정'}
        ]
        
        return calendar
