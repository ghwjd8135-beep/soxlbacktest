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

if uploaded is not None:
    raw_df = pd.read_csv(uploaded, header=None, names=COLS)
    raw_df['datetime'] = pd.to_datetime(raw_df['datetime'])
    raw_df = raw_df.sort_values('datetime').reset_index(drop=True)
    raw_df['date'] = raw_df['datetime'].dt.date
    raw_df['time'] = raw_df['datetime'].dt.time

    # 거래일별 9:30 시가만 정확히 추출 (다른 시간대는 절대 사용 안 함)
    open_930 = raw_df[raw_df['time'] == time(9, 30)]
    open_map = dict(zip(open_930['date'], open_930['open']))
    trading_days = sorted(open_map.keys())

    trades = []
    capital = initial_capital

    for i, day in enumerate(trading_days):
        if i + 1 >= len(trading_days):
            continue  # 다음 거래일(익일 시가) 없으면 미완결 거래라 제외

        today_open = open_map[day]
        breakout_price = today_open * (1 + breakout_pct)

        day_df = raw_df[(raw_df['date'] == day) & (raw_df['time'] >= time(9, 30))].sort_values('datetime')
        buy_candidates = day_df[day_df['high'] >= breakout_price]

        if buy_candidates.empty:
            continue  # 돌파 없음

        buy_bar = buy_candidates.iloc[0]
        buy_time = buy_bar['datetime']
        buy_price = breakout_price
        stop_price = buy_price * (1 - stoploss_pct)

        next_day = trading_days[i + 1]
        if next_day not in open_map:
            continue
        next_open = open_map[next_day]
        next_930_time = pd.Timestamp.combine(next_day, time(9, 30))

        # 매수 이후 ~ 익일 9:30 이전까지 손절 여부 확인
        monitor_df = raw_df[(raw_df['datetime'] > buy_time) & (raw_df['datetime'] < next_930_time)]
        stop_hit = monitor_df[monitor_df['low'] <= stop_price]

        if not stop_hit.empty:
            sell_bar = stop_hit.iloc[0]
            sell_price = stop_price
            sell_time = sell_bar['datetime']
            exit_reason = "손절"
        else:
            sell_price = next_open
            sell_time = next_930_time
            exit_reason = "익일시가 청산"

        buy_price_fee = buy_price * (1 + fee_pct)
        sell_price_fee = sell_price * (1 - fee_pct)
        ret_pct = (sell_price_fee - buy_price_fee) / buy_price_fee

        capital = capital * (1 + ret_pct)

        trades.append({
            "매수일": day,
            "매수시각": buy_time,
            "매수가": round(buy_price, 3),
            "매도시각": sell_time,
            "매도가": round(sell_price, 3),
            "청산사유": exit_reason,
            "수익률(%)": round(ret_pct * 100, 2),
            "자본금": round(capital, 2),
        })

    if len(trades) == 0:
        st.warning("조건에 맞는 거래가 없습니다. 파라미터를 조정해보세요.")
    else:
        trades_df = pd.DataFrame(trades)

        st.subheader("📋 거래 내역")
        st.dataframe(trades_df, use_container_width=True)

        total_return = (capital - initial_capital) / initial_capital * 100
        win_rate = (trades_df['수익률(%)'] > 0).mean() * 100
        avg_return = trades_df['수익률(%)'].mean()

        equity = trades_df['자본금'].values
        running_max = np.maximum.accumulate(np.insert(equity, 0, initial_capital))
        drawdown = (equity - running_max[1:]) / running_max[1:] * 100
        mdd = drawdown.min() if len(drawdown) > 0 else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("총 거래 횟수", f"{len(trades_df)}회")
        c2.metric("승률", f"{win_rate:.1f}%")
        c3.metric("총 수익률", f"{total_return:.2f}%")
        c4.metric("평균 거래 수익률", f"{avg_return:.2f}%")
        c5.metric("최대 낙폭(MDD)", f"{mdd:.2f}%")

        st.subheader("📈 자본금 변화")
        chart_df = pd.DataFrame({
            "거래번호": range(1, len(trades_df) + 1),
            "자본금": trades_df['자본금']
        }).set_index("거래번호")
        st.line_chart(chart_df)

        csv_download = trades_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("거래 내역 CSV 다운로드", csv_download, "backtest_trades.csv", "text/csv")
else:
    st.info("CSV 파일을 업로드해주세요. (컬럼 순서: datetime, open, high, low, close, volume / 헤더 없음)")
