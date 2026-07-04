import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="SOXL 변동성 돌파 백테스트", layout="wide")
st.title("📈 SOXL 변동성 돌파 매매 백테스트")

# ---------------------------
# 사이드바: 파라미터 입력
# ---------------------------
st.sidebar.header("⚙️ 전략 파라미터")
breakout_pct = st.sidebar.slider("돌파율 (%)", 0.5, 10.0, 2.0, 0.1) / 100
stoploss_pct = st.sidebar.slider("손절율 (%)", 0.5, 10.0, 3.0, 0.1) / 100
fee_pct = st.sidebar.number_input("편도 수수료+슬리피지 (%)", value=0.05, step=0.01) / 100
initial_capital = st.sidebar.number_input("초기 자본금 ($)", value=10000, step=1000)

uploaded = st.file_uploader("1분봉 CSV 업로드 (columns: datetime, open, high, low, close, volume)", type="csv")

# ---------------------------
# 백테스트 함수
# ---------------------------
def run_backtest(df, breakout_pct, stoploss_pct, fee_pct):
    df = df.sort_values('datetime').reset_index(drop=True)
    df['date'] = df['datetime'].dt.date
    dates = sorted(df['date'].unique())
    trades = []

    for i in range(len(dates) - 1):
        today = dates[i]
        next_day = dates[i + 1]

        day_df = df[df['date'] == today].reset_index(drop=True)
        next_df = df[df['date'] == next_day].reset_index(drop=True)

        if day_df.empty or next_df.empty:
            continue

        open_price = day_df.loc[0, 'open']
        breakout_price = open_price * (1 + breakout_pct)

        buy_idx = None
        for idx, row in day_df.iterrows():
            if row['high'] >= breakout_price:
                buy_idx = idx
                break

        if buy_idx is None:
            continue  # 돌파 없음, 매매 없음

        buy_price = breakout_price
        stop_price = buy_price * (1 - stoploss_pct)

        sell_price = None
        sell_type = None
        sell_time = None

        # 매수 이후 캔들에서 손절 체크
        for idx in range(buy_idx, len(day_df)):
            row = day_df.loc[idx]
            if row['low'] <= stop_price:
                sell_price = stop_price
                sell_type = "손절"
                sell_time = row['datetime']
                break

        # 손절 안 걸리면 익일 시가 매도
        if sell_price is None:
            sell_price = next_df.loc[0, 'open']
            sell_type = "익일시가"
            sell_time = next_df.loc[0, 'datetime']

        buy_price_adj = buy_price * (1 + fee_pct)
        sell_price_adj = sell_price * (1 - fee_pct)
        pnl_pct = (sell_price_adj - buy_price_adj) / buy_price_adj

        trades.append({
            'date': today,
            'buy_time': day_df.loc[buy_idx, 'datetime'],
            'buy_price': round(buy_price, 3),
            'sell_time': sell_time,
            'sell_price': round(sell_price, 3),
            'sell_type': sell_type,
            'pnl_pct': pnl_pct
        })

    result_df = pd.DataFrame(trades)
    if not result_df.empty:
        result_df['cum_return'] = (1 + result_df['pnl_pct']).cumprod() - 1
    return result_df

# ---------------------------
# 실행 및 결과 출력
# ---------------------------
if uploaded is not None:
    df = pd.read_csv(uploaded, parse_dates=['datetime'])

    if st.button("🚀 백테스트 실행"):
        with st.spinner("백테스트 진행 중..."):
            result_df = run_backtest(df, breakout_pct, stoploss_pct, fee_pct)

        if result_df.empty:
            st.warning("매매 결과가 없습니다. 돌파율 조건을 확인해보세요.")
        else:
            total_trades = len(result_df)
            win_trades = (result_df['pnl_pct'] > 0).sum()
            win_rate = win_trades / total_trades * 100
            total_return = result_df['cum_return'].iloc[-1] * 100
            avg_pnl = result_df['pnl_pct'].mean() * 100
            final_capital = initial_capital * (1 + result_df['cum_return'].iloc[-1])

            st.subheader("📊 요약 결과")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("총 거래 횟수", f"{total_trades}회")
            c2.metric("승률", f"{win_rate:.1f}%")
            c3.metric("총 누적 수익률", f"{total_return:.2f}%")
            c4.metric("최종 자본금", f"${final_capital:,.0f}")

            st.subheader("📈 누적 수익률 추이")
            st.line_chart(result_df.set_index('date')['cum_return'] * 100)

            st.subheader("📋 거래 내역")
            display_df = result_df.copy()
            display_df['pnl_pct'] = (display_df['pnl_pct'] * 100).round(2)
            st.dataframe(display_df, use_container_width=True)

            csv = result_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("💾 거래내역 CSV 다운로드", csv, "backtest_result.csv", "text/csv")
else:
    st.info("👆 CSV 파일을 업로드하면 백테스트를 실행할 수 있습니다.")
