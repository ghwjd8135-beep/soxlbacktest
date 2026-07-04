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

    for i, d in enumerate(dates):
        day_df = df[df['date'] == d].reset_index(drop=True)
        if day_df.empty:
            continue

        day_open = day_df.loc[0, 'open']
        breakout_price = day_open * (1 + breakout_pct)

        # 당일 중 돌파가 최초 도달 시점 찾기
        breakout_idx = None
        for j in range(len(day_df)):
            if day_df.loc[j, 'high'] >= breakout_price:
                breakout_idx = j
                break

        if breakout_idx is None:
            continue  # 돌파 없음, 매수 안함

        buy_price = breakout_price
        buy_time = day_df.loc[breakout_idx, 'datetime']
        stoploss_price = buy_price * (1 - stoploss_pct)

        # 돌파 발생 이후 봉들에서 손절 체크 (같은 날, 매수 시점 이후)
        exit_price = None
        exit_time = None
        exit_reason = None

        for k in range(breakout_idx, len(day_df)):
            if day_df.loc[k, 'low'] <= stoploss_price:
                exit_price = stoploss_price
                exit_time = day_df.loc[k, 'datetime']
                exit_reason = "손절"
                break

        if exit_price is None:
            # 당일 손절 안됨 -> 익일 시가 청산
            if i + 1 < len(dates):
                next_day = dates[i + 1]
                next_day_df = df[df['date'] == next_day].reset_index(drop=True)
                if not next_day_df.empty:
                    exit_price = next_day_df.loc[0, 'open']
                    exit_time = next_day_df.loc[0, 'datetime']
                    exit_reason = "익일시가청산"
                else:
                    continue  # 다음날 데이터 없음 -> 결과 제외
            else:
                continue  # 마지막 날짜라 익일 데이터 없음 -> 결과 제외

        # 수수료 반영 (매수/매도 편도 각각)
        buy_price_fee = buy_price * (1 + fee_pct)
        exit_price_fee = exit_price * (1 - fee_pct)

        ret_pct = (exit_price_fee - buy_price_fee) / buy_price_fee

        trades.append({
            "매수일": d,
            "매수시각": buy_time,
            "매수가": buy_price,
            "매도시각": exit_time,
            "매도가": exit_price,
            "청산유형": exit_reason,
            "수익률(%)": ret_pct * 100
        })

    trades_df = pd.DataFrame(trades)
    return trades_df


def calc_equity_curve(trades_df, initial_capital):
    equity = [initial_capital]
    for r in trades_df['수익률(%)']:
        equity.append(equity[-1] * (1 + r / 100))
    trades_df = trades_df.copy()
    trades_df['자본금'] = equity[1:]
    return trades_df


# ---------------------------
# 메인 로직
# ---------------------------
if uploaded is not None:
    raw_df = pd.read_csv(uploaded)
    raw_df['datetime'] = pd.to_datetime(raw_df['datetime'])

    with st.spinner("백테스트 실행 중..."):
        result_df = run_backtest(raw_df, breakout_pct, stoploss_pct, fee_pct)

    if result_df.empty:
        st.warning("조건에 맞는 거래가 없습니다.")
    else:
        result_df = calc_equity_curve(result_df, initial_capital)

        # ---------------------------
        # 성과 지표
        # ---------------------------
        total_trades = len(result_df)
        win_trades = (result_df['수익률(%)'] > 0).sum()
        win_rate = win_trades / total_trades * 100
        total_return = (result_df['자본금'].iloc[-1] / initial_capital - 1) * 100
        avg_return = result_df['수익률(%)'].mean()
        mdd = ((result_df['자본금'].cummax() - result_df['자본금']) / result_df['자본금'].cummax()).max() * 100

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("총 거래수", f"{total_trades} 회")
        col2.metric("승률", f"{win_rate:.1f} %")
        col3.metric("총 수익률", f"{total_return:.1f} %")
        col4.metric("평균 수익률/거래", f"{avg_return:.2f} %")
        col5.metric("MDD", f"{mdd:.1f} %")

        st.subheader("📊 자본금 변화")
        st.line_chart(result_df.set_index('매수일')['자본금'])

        st.subheader("📋 거래 내역")
        st.dataframe(result_df, use_container_width=True)

        csv = result_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("결과 CSV 다운로드", data=csv, file_name="backtest_result.csv", mime="text/csv")
else:
    st.info("👆 1분봉 CSV 파일을 업로드해주세요.")
