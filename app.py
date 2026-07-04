import streamlit as st
import pandas as pd
import numpy as np
from datetime import time

st.set_page_config(page_title="SOXL 변동성 돌파 백테스트", layout="wide")
st.title("📈 SOXL 변동성 돌파 매매 백테스트 (익일 시가 매도)")

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

    # 정규장(9:30~16:00)만 필터링 - 프리마켓/애프터마켓 제외
    reg = df[(df['time'] >= MARKET_OPEN) & (df['time'] <= MARKET_CLOSE)].copy()
    reg = reg.sort_values('datetime').reset_index(drop=True)

    trading_days = sorted(reg['date'].unique())

    if len(trading_days) < 2:
        st.warning("최소 2거래일 이상의 데이터가 필요합니다.")
        st.stop()

    # 일별 시가 (당일 9:30 시가) 미리 계산
    daily_open = {}
    for d in trading_days:
        day_data = reg[reg['date'] == d]
        first_bar = day_data.iloc[0]
        daily_open[d] = first_bar['open']

    results = []
    capital = initial_capital

    for i in range(len(trading_days) - 1):
        d = trading_days[i]
        next_d = trading_days[i + 1]

        day_data = reg[reg['date'] == d].reset_index(drop=True)
        o = daily_open[d]
        breakout_price = o * (1 + breakout_pct)
        stop_price = o * (1 - stoploss_pct)

        entry_price = None
        entry_time = None
        exit_price = None
        exit_time = None
        exit_reason = None

        # 당일 분봉 순회하며 돌파 매수 체크
        for idx, row in day_data.iterrows():
            if entry_price is None:
                if row['high'] >= breakout_price:
                    entry_price = breakout_price
                    entry_time = row['datetime']
                    continue  # 진입 발생 분봉에서는 바로 그 분봉 손절 체크 안 함(보수적 처리)

            if entry_price is not None:
                if row['low'] <= stop_price:
                    exit_price = stop_price
                    exit_time = row['datetime']
                    exit_reason = "손절"
                    break

        # 이 날 돌파 매수가 없었으면 매매 없이 넘어감
        if entry_price is None:
            continue

        # 당일 손절 안 걸렸으면 익일 시가 매도
        if exit_price is None:
            exit_price = daily_open[next_d]
            exit_time = pd.Timestamp.combine(next_d, MARKET_OPEN)
            exit_reason = "익일시가매도"

        # 수수료+슬리피지 반영 실질 체결가
        entry_fill = entry_price * (1 + fee_pct)
        exit_fill = exit_price * (1 - fee_pct)

        trade_return = (exit_fill - entry_fill) / entry_fill
        capital *= (1 + trade_return)

        results.append({
            "진입일": d,
            "진입시간": entry_time,
            "진입가(체결)": round(entry_fill, 4),
            "청산일": next_d if exit_reason == "익일시가매도" else d,
            "청산시간": exit_time,
            "청산가(체결)": round(exit_fill, 4),
            "청산사유": exit_reason,
            "수익률(%)": round(trade_return * 100, 3),
            "자본금": round(capital, 2),
        })

    if not results:
        st.warning("조건에 맞는 매매가 발생하지 않았습니다.")
        st.stop()

    result_df = pd.DataFrame(results)

    # --- 자산 곡선(equity curve) 및 MDD 계산 ---
    equity_curve = [initial_capital] + result_df['자본금'].tolist()
    equity_df = pd.DataFrame({'equity': equity_curve})
    equity_df['peak'] = equity_df['equity'].cummax()
    equity_df['drawdown_pct'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak'] * 100

    mdd_pct = equity_df['drawdown_pct'].min()

    # --- 요약 지표 ---
    total_trades = len(result_df)
    win_trades = (result_df['수익률(%)'] > 0).sum()
    win_rate = win_trades / total_trades * 100
    total_return_pct = (capital - initial_capital) / initial_capital * 100

    st.subheader("📊 백테스트 요약")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("최종 자본금", f"${capital:,.2f}")
    col2.metric("총 수익률", f"{total_return_pct:.2f}%")
    col3.metric("총 매매 횟수", f"{total_trades}회")
    col4.metric("승률", f"{win_rate:.2f}%")
    col5.metric("MDD (최대낙폭)", f"{mdd_pct:.2f}%")

    st.subheader("📉 자산 곡선 및 낙폭")
    st.line_chart(equity_df['equity'])
    st.line_chart(equity_df['drawdown_pct'])

    st.subheader("📋 매매 내역")
    st.dataframe(result_df, use_container_width=True)

    st.download_button(
        "매매 내역 CSV 다운로드",
        result_df.to_csv(index=False).encode('utf-8-sig'),
        file_name="backtest_results.csv",
        mime="text/csv",
    )
else:
    st.info("👆 1분봉 CSV 파일을 업로드해주세요. (컬럼 순서: datetime, open, high, low, close, volume / 헤더 없음)")
