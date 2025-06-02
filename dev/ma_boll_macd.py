import sys
sys.path.append("/Users/niez01/Documents/dev/czsc")
from czsc.connectors.ts_connector import get_raw_bars, get_symbols
from pathlib import Path

import czsc
from czsc import Position, Event
from czsc.utils import get_sub_elements
import numpy as np
import pandas as pd
from czsc.objects import Signal
from typing import List
from dev.viz_czsc_chart import generate_stock_kline
from czsc.traders.sig_parse import get_signals_config

def create_boll_macd_strategy(symbol: str, **kwargs) -> Position:
    """BOLL+MACD+MA组合策略
    
    参数说明：
    symbol: str, 交易标的
    kwargs:
        - base_freq: 基础K线周期
        - sma_short: 短期均线周期
        - sma_long: 长期均线周期
        - boll_period: BOLL周期
        - boll_std: BOLL标准差倍数
        - macd_fast: MACD快线周期
        - macd_slow: MACD慢线周期
        - macd_signal: MACD信号线周期
    """
    base_freq = kwargs.get('base_freq', '日线')
    sma_short = kwargs.get('sma_short', 5)
    sma_long = kwargs.get('sma_long', 20)
    boll_period = kwargs.get('boll_period', 20)
    boll_std = kwargs.get('boll_std', 2)
    macd_fast = kwargs.get('macd_fast', 12)
    macd_slow = kwargs.get('macd_slow', 26)
    macd_signal = kwargs.get('macd_signal', 9)

    opens = [
        {
            "name": "开多",
            "operate": "开多",
            "signals_all": [],
            "signals_any": [],
            "signals_not": [],
            "factors": [{
                "name": "三信号同时满足",
                "signals_all": [
                    f"{base_freq}_D1N{sma_short}M{sma_long}双均线_BS辅助V240208_多头_任意_任意_0",  # MA金叉
                    # f"{base_freq}_D1BOLL{boll_period}#{boll_std}_BS辅助V230212_看多_任意_任意_0",  # 突破BOLL上轨
                    # f"{base_freq}_D1MACD{macd_fast}#{macd_slow}#{macd_signal}_BS辅助V230312_看多_任意_任意_0",  # MACD金叉
                ]
            }]
        }
    ]

    exits = [
        {
            "name": "平多",
            "operate": "平多",
            "signals_all": [],
            "signals_any": [],
            "signals_not": [],
            "factors": [{
                "name": "三信号任一满足",
                "signals_all": [
                    f"{base_freq}_D1N{sma_short}M{sma_long}双均线_BS辅助V240208_看空_任意_任意_0",  # MA死叉
                ],
                "signals_any": [],
                "signals_not": []
            },
            # {
            #     "name": "跌破中轨",
            #     "signals_all": [
            #         f"{base_freq}_D1BOLL{boll_period}#{boll_std}_BS辅助V230212_看空_任意_任意_0",  # 跌破BOLL中轨
            #     ],
            #     "signals_any": [],
            #     "signals_not": []
            # },
            # {
            #     "name": "MACD死叉",
            #     "signals_all": [
            #         f"{base_freq}_D1MACD{macd_fast}#{macd_slow}#{macd_signal}_BS辅助V230312_看空_任意_任意_0",  # MACD死叉
            #     ],
            #     "signals_any": [],
            #     "signals_not": []
            # }]
            ]
        }
    ]

    pos = Position(
        name="BOLL+MACD+MA策略",
        symbol=symbol,
        opens=[Event.load(x) for x in opens],
        exits=[Event.load(x) for x in exits],
        interval=3600 * 4,  # 开仓间隔4小时
        timeout=16 * 30,    # 超时平仓时间
        stop_loss=500,      # 止损点数
    )
    return pos

class Strategy(czsc.CzscStrategyBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_stocks = kwargs.get('is_stocks', True)

    @property
    def positions(self):
        pos_list = [
            create_boll_macd_strategy(
                self.symbol,
                base_freq='日线',
                sma_short=5,
                sma_long=20,
                boll_period=20,
                boll_std=2,
                macd_fast=12,
                macd_slow=26,
                macd_signal=9
            )
        ]
        return pos_list

if __name__ == "__main__":
    
    symbols = get_symbols('stock')
    for symbol in symbols:

        search_code = '600171' 
        if search_code not in symbol:
            continue

        tactic = Strategy(symbol=symbol, is_stocks=True)
        # 获取K线数据
        bars = get_raw_bars(symbol, freq='日线', sdt='20230101', edt='20250309')
        
        # 回放测试
        trader = tactic.replay(bars, res_path="results/replay")
        # trader = tactic.backtest(bars, res_path="results/replay")
        
        generate_stock_kline(symbol=symbol)
