import streamlit as st
import pandas as pd
import numpy as np
from datetime import time

st.set_page_config(page_title="SOXL 변동성 돌파 백테스트", layout="wide")
st.title("📈 SOXL 변동성 돌파 매매 백테스트")

st.sidebar.header("⚙️ 전략 파라미터")
breakout_pct = st.sidebar.slider("돌파율 (%)", 0.5, 10.0, 2.0, 0.1) / 100
stoploss_pct = st.sidebar.slider("손절율 (%)", 0.5, 10.0, 3.0, 0.1) / 100
fee_pct = st.sidebar.number_input("편도 수수료+슬리피지 (%)", value=0.05, step=0.01) / 100
initial_capital = st.sidebar.number_input("초기 자본금 ($)", value=10000, step=1000)

uploaded = st.file_uploader("1분봉 CSV 업로드 (헤더 없음)", type="csv")

COLS = ["datetime", "open", "high", "low", "close", "volume"]
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

if uploaded is not None:
    raw_df = pd.read_csv(uploaded, header=None, names=COLS)
    raw_df['datetime'] = pd.to_datetime(raw_df['datetime'])
    raw_df = raw_df.sort_values('datetime').reset_index(drop=True)
    raw_df['date'] = raw_df['datetime'].dt.date
    raw_df['time'] = raw_df['datetime'].dt.time

    # 거래일별 9:30 시가만 정확히 추출 (프리장 값 사용 안 함)
    open_930 = raw_df[raw_df['time'] == MARKET_OPEN]
    open_map = dict(zip(open_930['date'], open_930['open']))
    trading_days = sorted(open_map.keys())

    results = []

    for i, day in enumerate(trading_days):
        # ✅ 정규장(9:30~16:00) 데이터만 사용 - 프리장/애프터장 제외
        day_data = raw_df[
            (raw_df['date'] == day) &
            (raw_df['time'] >= MARKET_OPEN) &
            (raw_df['time'] <= MARKET_CLOSE)
        ].sort_values('datetime')

        if day_data.empty:
            continue

        today_open = open_map[day]
        breakout_price = today_open * (1 + breakout_pct)

        # 돌파 시점 탐색 (정규장 내에서만)
        buy_candidates = day_data[day_data['high'] >= breakout_price]
        if buy_candidates.empty:
            continue  # 돌파 없음 -> 당일 매매 없음

        buy_row = buy_candidates.iloc[0]
        buy_time = buy_row['datetime']
        buy_price = breakout_price

        # 매수 이후 남은 정규장 데이터에서 스탑로스 탐색
        after_buy = day_data[day_data['datetime'] > buy_time]
        stop_price = buy_price * (1 - stoploss_pct)
        stop_candidates = after_buy[after_buy['low'] <= stop_price]

        if not stop_candidates.empty:
            stop_row = stop_candidates.iloc[0]
            sell_time = stop_row['datetime']
            sell_price = stop_price
            exit_reason = "스탑로스"
        else:
            # 당일 정규장 내 스탑로스 미발생 -> 익일 9:30 시가 매도
            if i + 1 >= len(trading_days):
                continue  # 마지막 날 & 다음날 데이터 없음 -> 제외
            next_day = trading_days[i + 1]
            sell_price = open_map[next_day]
            sell_time = pd.Timestamp.combine(next_day, MARKET_OPEN)
            exit_reason = "익일시가매도"

        buy_price_fee = buy_price * (1 + fee_pct)
        sell_price_fee = sell_price * (1 - fee_pct)
        ret_pct = (sell_price_fee - buy_price_fee) / buy_price_fee

        results.append({
            "매수일": day,
            "매수시간": buy_time,
            "매수가": round(buy_price, 4),
            "매도시간": sell_time,
            "매도가": round(sell_price, 4),
            "청산사유": exit_reason,
            "수익률(%)": round(ret_pct * 100, 3),
        })

    if not results:
        st.warning("조건에 맞는 매매가 없습니다. 파라미터를 조정해보세요.")
    else:
        result_df = pd.DataFrame(results)

        # 복리 자산 곡선 계산
        capital = initial_capital
        equity_curve = []
        for r in result_df["수익률(%)"]:
            capital *= (1 + r / 100)
            equity_curve.append(capital)
        result_df["누적자산"] = equity_curve

        st.subheader("📊 백테스트 결과")
        col1, col2, col3 = st.columns(3)
        col1.metric("총 거래 횟수", f"{len(result_df)}회")
        col2.metric("승률", f"{(result_df['수익률(%)'] > 0).mean() * 100:.1f}%")
        col3.metric("최종 자산", f"${equity_curve[-1]:,.2f}")

        st.line_chart(result_df.set_index("매수일")["누적자산"])
        st.dataframe(result_df, use_container_width=True)
