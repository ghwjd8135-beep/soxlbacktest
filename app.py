import streamlit as st
import pandas as pd
import numpy as np
from datetime import time

st.set_page_config(page_title="SOXL 변동성 돌파 백테스트", layout="wide")
st.title("📈 SOXL 변동성 돌파 매매 백테스트 (복리)")

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
    df = pd.read_csv(uploaded, header=None, names=COLS)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime').reset_index(drop=True)
    df['date'] = df['datetime'].dt.date
    df['time'] = df['datetime'].dt.time

    session = df[(df['time'] >= MARKET_OPEN) & (df['time'] <= MARKET_CLOSE)].copy()
    dates = sorted(session['date'].unique())

    trades = []
    capital = initial_capital

    for i in range(len(dates) - 1):
        today = dates[i]
        next_day = dates[i + 1]

        day_data = session[session['date'] == today].sort_values('datetime')
        if day_data.empty:
            continue

        day_open = day_data.iloc[0]['open']
        breakout_price = day_open * (1 + breakout_pct)
        stop_price = breakout_price * (1 - stoploss_pct)

        entry_price = None
        entry_time = None
        exit_price = None
        exit_time = None
        exit_reason = None

        for idx, row in day_data.iterrows():
            if entry_price is None:
                if row['high'] >= breakout_price:
                    entry_price = breakout_price
                    entry_time = row['datetime']
                    # 매수 체결 봉에서도 손절 조건 즉시 확인 (버그 수정 포인트)
                    if row['low'] <= stop_price:
                        exit_price = stop_price
                        exit_time = row['datetime']
                        exit_reason = "손절(매수당일)"
                        break
            else:
                if row['low'] <= stop_price:
                    exit_price = stop_price
                    exit_time = row['datetime']
                    exit_reason = "손절(매수당일)"
                    break

        if entry_price is None:
            continue  # 돌파 없었던 날 -> 매매 없음

        if exit_price is None:
            next_day_data = session[session['date'] == next_day].sort_values('datetime')
            if next_day_data.empty:
                continue
            exit_price = next_day_data.iloc[0]['open']
            exit_time = next_day_data.iloc[0]['datetime']
            exit_reason = "익일시가매도"

        buy_cost = entry_price * (1 + fee_pct)
        sell_revenue = exit_price * (1 - fee_pct)
        ret_pct = (sell_revenue - buy_cost) / buy_cost

        capital_before = capital
        capital = capital * (1 + ret_pct)

        trades.append({
            "매수일": today,
            "청산일": exit_time.date(),
            "매수시각": entry_time,
            "청산시각": exit_time,
            "매수가": round(entry_price, 4),
            "청산가": round(exit_price, 4),
            "청산사유": exit_reason,
            "수익률(%)": round(ret_pct * 100, 3),
            "매매전자본": round(capital_before, 2),
            "매매후자본": round(capital, 2),
        })

    result_df = pd.DataFrame(trades)

    if result_df.empty:
        st.warning("조건에 맞는 매매가 없습니다.")
    else:
        st.subheader("📊 매매 결과")
        st.dataframe(result_df, use_container_width=True)

        total_return = (capital - initial_capital) / initial_capital * 100
        win_trades = result_df[result_df['수익률(%)'] > 0]
        win_rate = len(win_trades) / len(result_df) * 100

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("총 매매 횟수", f"{len(result_df)}회")
        col2.metric("승률", f"{win_rate:.1f}%")
        col3.metric("최종 자본", f"${capital:,.2f}")
        col4.metric("총 수익률", f"{total_return:.2f}%")

        st.subheader("📈 자산 곡선 (복리)")
        st.line_chart(result_df.set_index("청산시각")["매매후자본"])

        st.subheader("📉 청산 사유별 통계")
        st.dataframe(result_df['청산사유'].value_counts())
