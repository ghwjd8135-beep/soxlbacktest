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
        prev_date = dates[i]
        curr_date = dates[i + 1]
        prev_day = df[df['date'] == prev_date]
        curr_day = df[df['date'] == curr_date].reset_index(drop=True)

        if prev_day.empty or curr_day.empty:
            continue

        prev_high = prev_day['high'].max()
        prev_low = prev_day['low'].min()
        day_range = prev_high - prev_low

        today_open = curr_day.iloc[0]['open']
        target_price = today_open + day_range * breakout_pct
        stop_price = target_price * (1 - stoploss_pct)

        position = False
        entry_price = None
        entry_time = None
        exit_price = None
        exit_time = None

        for idx, row in curr_day.iterrows():
            if not position:
                if row['high'] >= target_price:
                    position = True
                    entry_price = target_price
                    entry_time = row['datetime']
            else:
                if row['low'] <= stop_price:
                    exit_price = stop_price
                    exit_time = row['datetime']
                    break

        if position and exit_price is None:
            last_row = curr_day.iloc[-1]
            exit_price = last_row['close']
            exit_time = last_row['datetime']

        if position:
            gross_pnl_pct = (exit_price - entry_price) / entry_price
            net_pnl_pct = gross_pnl_pct - fee_pct * 2
            trades.append({
                'date': curr_date,
                'entry_time': entry_time,
                'entry_price': entry_price,
                'exit_time': exit_time,
                'exit_price': exit_price,
                'pnl_pct': net_pnl_pct
            })

    return pd.DataFrame(trades)

# ---------------------------
# 메인 로직
# ---------------------------
if uploaded is not None:
    df = pd.read_csv(
        uploaded,
        header=None,
        names=['datetime', 'open', 'high', 'low', 'close', 'volume']
    )
    df['datetime'] = pd.to_datetime(df['datetime'])

    # 정규장 시간(09:30~16:00 ET)만 필터링
    df['time'] = df['datetime'].dt.time
    market_open = pd.to_datetime('09:30:00').time()
    market_close = pd.to_datetime('16:00:00').time()
    df = df[(df['time'] >= market_open) & (df['time'] <= market_close)].reset_index(drop=True)
    df = df.drop(columns=['time'])

    result_df = run_backtest(df, breakout_pct, stoploss_pct, fee_pct)

    if result_df.empty:
        st.warning("매매 결과가 없습니다. 돌파율 조건을 확인해보세요.")
    else:
        result_df['cum_return'] = (1 + result_df['pnl_pct']).cumprod()

        total_trades = len(result_df)
        win_trades = (result_df['pnl_pct'] > 0).sum()
        win_rate = win_trades / total_trades * 100
        final_capital = initial_capital * result_df['cum_return'].iloc[-1]
        total_return_pct = (final_capital - initial_capital) / initial_capital * 100

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("총 거래 수", total_trades)
        col2.metric("승률", f"{win_rate:.1f}%")
        col3.metric("최종 자본", f"${final_capital:,.2f}")
        col4.metric("총 수익률", f"{total_return_pct:.1f}%")

        st.subheader("📊 자산 곡선")
        equity_df = result_df[['date', 'cum_return']].copy()
        equity_df['equity'] = initial_capital * equity_df['cum_return']
        st.line_chart(equity_df.set_index('date')['equity'])

        st.subheader("📋 거래 내역")
        st.dataframe(result_df)
else:
    st.info("CSV 파일을 업로드해주세요.")
