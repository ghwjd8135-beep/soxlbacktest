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

    # 정규장(9:30~16:00) 데이터만 매매에 사용 (프리/애프터마켓 제외)
    reg_df = raw_df[(raw_df['time'] >= MARKET_OPEN) & (raw_df['time'] <= MARKET_CLOSE)].copy()

    # 날짜별 9:30 시가만 정확히 추출
    open_930 = reg_df[reg_df['time'] == MARKET_OPEN]
    open_map = dict(zip(open_930['date'], open_930['open']))

    trading_days = sorted(open_map.keys())
    results = []

    for day in trading_days:
        day_data = reg_df[reg_df['date'] == day].sort_values('datetime').reset_index(drop=True)
        if day_data.empty:
            continue

        today_open = open_map[day]
        breakout_price = today_open * (1 + breakout_pct)
        stoploss_price = breakout_price * (1 - stoploss_pct)

        entry_price = None
        exit_price = None
        exit_reason = None
        entry_time = None
        exit_time = None

        for _, row in day_data.iterrows():
            if entry_price is None:
                if row['high'] >= breakout_price:
                    entry_price = breakout_price * (1 + fee_pct)
                    entry_time = row['datetime']
                continue

            if row['low'] <= stoploss_price:
                exit_price = stoploss_price * (1 - fee_pct)
                exit_time = row['datetime']
                exit_reason = "손절"
                break

        if entry_price is not None and exit_price is None:
            last_row = day_data.iloc[-1]
            exit_price = last_row['close'] * (1 - fee_pct)
            exit_time = last_row['datetime']
            exit_reason = "장마감 청산"

        if entry_price is not None:
            return_pct = (exit_price - entry_price) / entry_price
            results.append({
                'date': day,
                'entry_time': entry_time,
                'exit_time': exit_time,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'return_pct': return_pct,
                'exit_reason': exit_reason
            })

    if len(results) == 0:
        st.warning("돌파가 발생한 거래일이 없습니다.")
    else:
        result_df = pd.DataFrame(results)

        # --- 자산 곡선 및 MDD 계산 ---
        capital = initial_capital
        equity_list = [initial_capital]
        equity_dates = [trading_days[0]]

        for _, trade in result_df.iterrows():
            capital *= (1 + trade['return_pct'])
            equity_list.append(capital)
            equity_dates.append(trade['date'])

        equity_df = pd.DataFrame({'date': equity_dates, 'equity': equity_list})
        equity_df['peak'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak']

        mdd_pct = equity_df['drawdown'].min() * 100
        mdd_idx = equity_df['drawdown'].idxmin()
        mdd_date = equity_df.loc[mdd_idx, 'date']
        peak_before_mdd = equity_df.loc[:mdd_idx, 'equity'].max()

        final_capital = equity_list[-1]
        total_return_pct = (final_capital - initial_capital) / initial_capital * 100
        win_rate = (result_df['return_pct'] > 0).mean() * 100

        st.subheader("📊 백테스트 결과 요약")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("최종 자산", f"${final_capital:,.2f}")
        c2.metric("총 수익률", f"{total_return_pct:.2f}%")
        c3.metric("승률", f"{win_rate:.1f}%")
        c4.metric("MDD (최대낙폭)", f"{mdd_pct:.2f}%")

        st.caption(f"MDD 발생일: {mdd_date} (직전 최고 자산: ${peak_before_mdd:,.2f})")

        st.subheader("📈 자산 곡선")
        st.line_chart(equity_df.set_index('date')['equity'])

        st.subheader("📉 낙폭(Drawdown) 곡선")
        st.line_chart(equity_df.set_index('date')['drawdown'] * 100)

        st.subheader("📋 거래 내역")
        st.dataframe(result_df)

        st.download_button(
            "결과 CSV 다운로드",
            result_df.to_csv(index=False).encode('utf-8-sig'),
            file_name="backtest_results.csv",
            mime="text/csv"
        )
else:
    st.info("CSV 파일을 업로드해주세요.")
