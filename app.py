네, 확인해보니 1, 2번 로직은 기존 코드에 반영되어 있었어요. 근데 말씀하신 부분을 더 명확하게 하고, 3번(복리/단리 비교)까지 추가해서 전체 코드를 다시 정리했습니다.

## 로직 확인

**1. 매수 조건**: 당일 시가(9:30 첫 봉의 open) 기준 `돌파율%` 상승한 가격을 장중(9:30~16:00) 고가가 터치하면 그 돌파가에 매수 → 매수 직후 `손절율%` 하락한 가격을 장중 저가가 터치하면 그 자리에서 손절 매도

**2. 청산 조건**: 당일 안에 손절 안 걸리면 **다음 거래일 첫 봉(9:30) 시가**로 전량 매도 ✅ (전에 실수로 "당일 마감"으로 잘못 짰던 부분 수정 완료)

**3. 복리 vs 단리 비교**: 사이드바 체크박스로 켜면 두 자산곡선을 한 차트에 같이 그려서 바로 비교 가능하게 만들었어요
- 복리: 매매마다 직전 자산 전체로 재투자
- 단리: 매매마다 항상 **초기자본 고정** 기준으로 손익만 누적 (재투자 안 함)

## 전체 코드

```python
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

st.sidebar.header("💰 투자 방식 비교")
compare_mode = st.sidebar.checkbox("복리 vs 단리 비교 모드", value=True)

uploaded = st.file_uploader("1분봉 CSV 업로드 (헤더 없음)", type="csv")

COLS = ["datetime", "open", "high", "low", "close", "volume"]
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

if uploaded is not None:
    raw = pd.read_csv(uploaded, header=None, names=COLS, skiprows=1)
    raw['datetime'] = pd.to_datetime(raw['datetime'])
    raw['date'] = raw['datetime'].dt.date
    raw['time'] = raw['datetime'].dt.time

    session = raw[(raw['time'] >= MARKET_OPEN) & (raw['time'] <= MARKET_CLOSE)].copy()
    session = session.sort_values('datetime').reset_index(drop=True)

    trading_days = sorted(session['date'].unique())
    trades = []

    for i, d in enumerate(trading_days):
        day_bars = session[session['date'] == d].sort_values('datetime').reset_index(drop=True)
        if day_bars.empty:
            continue

        day_open = day_bars.iloc[0]['open']
        breakout_price = day_open * (1 + breakout_pct)

        entry_price = None
        entry_time = None
        exit_price = None
        exit_time = None
        exit_reason = None
        stoploss_price = None

        for idx, bar in day_bars.iterrows():
            if entry_price is None:
                if bar['high'] >= breakout_price:
                    entry_price = breakout_price
                    entry_time = bar['datetime']
                    stoploss_price = entry_price * (1 - stoploss_pct)
                    if bar['low'] <= stoploss_price:
                        exit_price = stoploss_price
                        exit_time = bar['datetime']
                        exit_reason = "손절(당일)"
                        break
            else:
                if bar['low'] <= stoploss_price:
                    exit_price = stoploss_price
                    exit_time = bar['datetime']
                    exit_reason = "손절(당일)"
                    break

        if entry_price is None:
            continue

        if exit_price is None:
            if i + 1 >= len(trading_days):
                continue
            next_day = trading_days[i + 1]
            next_bars = session[session['date'] == next_day].sort_values('datetime').reset_index(drop=True)
            if next_bars.empty:
                continue
            exit_price = next_bars.iloc[0]['open']
            exit_time = next_bars.iloc[0]['datetime']
            exit_reason = "익일시가청산"

        gross_ret = (exit_price - entry_price) / entry_price
        net_ret = gross_ret - fee_pct * 2

        trades.append({
            "매수일": d, "매수시각": entry_time, "매수가": entry_price,
            "매도시각": exit_time, "매도가": exit_price,
            "청산사유": exit_reason, "수익률(%)": net_ret * 100
        })

    if len(trades) == 0:
        st.warning("조건에 맞는 매매가 없습니다. 돌파율/손절율을 조정해보세요.")
    else:
        trade_df = pd.DataFrame(trades)

        compound_equity = [initial_capital]
        for r in trade_df["수익률(%)"] / 100:
            compound_equity.append(compound_equity[-1] * (1 + r))
        compound_equity = compound_equity[1:]

        simple_equity = []
        cum_profit = 0
        for r in trade_df["수익률(%)"] / 100:
            cum_profit += initial_capital * r
            simple_equity.append(initial_capital + cum_profit)

        trade_df["복리 자산"] = compound_equity
        trade_df["단리 자산"] = simple_equity

        def calc_mdd(eq):
            arr = np.array(eq)
            peak = np.maximum.accumulate(arr)
            return ((arr - peak) / peak).min() * 100

        compound_mdd = calc_mdd(compound_equity)
        simple_mdd = calc_mdd(simple_equity)
        compound_final = compound_equity[-1]
        simple_final = simple_equity[-1]
        compound_return_pct = (compound_final / initial_capital - 1) * 100
        simple_return_pct = (simple_final / initial_capital - 1) * 100
        win_rate = (trade_df["수익률(%)"] > 0).mean() * 100

        st.subheader("📊 백테스트 결과 요약")
        c1, c2, c3 = st.columns(3)
        c1.metric("총 매매 횟수", f"{len(trade_df)} 회")
        c2.metric("승률", f"{win_rate:.1f}%")
        c3.metric("평균 수익률/매매", f"{trade_df['수익률(%)'].mean():.2f}%")

        st.markdown("### 💰 복리 vs 단리 비교")
        colA, colB = st.columns(2)
        with colA:
            st.markdown("**복리 (재투자)**")
            st.write(f"최종 자산: ${compound_final:,.2f}")
            st.write(f"총 수익률: {compound_return_pct:,.2f}%")
            st.write(f"MDD: {compound_mdd:,.2f}%")
        with colB:
            st.markdown("**단리 (원금 고정)**")
            st.write(f"최종 자산: ${simple_final:,.2f}")
            st.write(f"총 수익률: {simple_return_pct:,.2f}%")
            st.write(f"MDD: {simple_mdd:,.2f}%")

        if compare_mode:
            st.line_chart(trade_df.set_index("매수일")[["복리 자산", "단리 자산"]])
        else:
            st.line_chart(trade_df.set_index("매수일")[["복리 자산"]])

        st.markdown("### 📋 매매 상세 내역")
        st.dataframe(trade_df, use_container_width=True)

        csv = trade_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("거래내역 CSV 다운로드", csv, "trades.csv", "text/csv")
```

한 가지 참고하실 점: 돌파 발생한 그 1분봉 안에서 고가가 돌파가를 찍고 그 뒤 저가가 바로 손절가까지 떨어지는 경우, 같은 봉에서 손절까지 같이 체크하도록 넣어놨어요 (급등 후 급락하는 캔들 대응). 실행해보시고 결과 이상하면 말씀해주세요 👍
