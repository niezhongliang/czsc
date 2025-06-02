import os
import sys
sys.path.append("/Users/niez01/Documents/dev/czsc")
from typing import List
from datetime import datetime
from czsc.objects import Event, Position, RawBar
from czsc import CzscStrategyBase, Position, Freq
from czsc.connectors.ts_connector import get_raw_bars, get_symbols
import czsc


class Strategy(CzscStrategyBase):

    def create_pos_a(self, symbol, **kwargs):
        base_freq = kwargs.get("base_freq", "30分钟")

        opens = [
            {
                "operate": "开多",
                "signals_not": [],
                "signals_all": [],
                "factors": [
                    {
                        "name": "周线趋势", 
                        "signals_all": ["周线_D1N4TH5_形态V230824_向上_任意_任意_0"],
                        "signals_not": [],
                        "signals_any": [
                            # 趋势线突破
                            "周线_D3N1笔趋势_高低点辅助判断V230913_上升趋势_超强_任意_0"
                        ],
                    },
                    {
                        "name": "日线趋势", 
                        "signals_all": ["日线_D1N4TH5_形态V230824_向上_任意_任意_0"],
                        "signals_not": [],
                        "signals_any": [
                            # 量价配合
                            "日线_D3N1笔趋势_高低点辅助判断V230913_上升趋势_超强_任意_0",
                        ],
                    },
                    {
                        "name": "买点确认", 
                        "signals_all": ["日线_D1#SMA#12_BS3辅助V230319_三买_均线新高_任意_0"],
                        "signals_not": [],
                        "signals_any": [
                          # 三买形态
                            "日线_D1#SMA#20_BS3辅助V230319_三买_均线底分_任意_0",
                            "日线_D1#SMA#34_BS3辅助V230319_三买_均线新高_任意_0"
                        ],
                    }
                ],
            }
        ]

        exits = [
            {
                "operate": "平多",
                "signals_not": [],
                "signals_all": [],
                "factors": [
                    # {
                    #     "name": "日线趋势", 
                    #     "signals_all": ["日线_D1N4TH5_形态V230824_向下_任意_任意_0"],
                    #     "signals_not": [],
                    #     "signals_any": [
                    #         # 量价配合
                    #         "日线_D3N1笔趋势_高低点辅助判断V230913_下降趋势_超强_任意_0"
                    #     ],
                    # },
                    {
                        "name": "卖点确认", 
                        "signals_all": ["日线_D1B_SELL1_一卖_5笔_任意_0"],
                        "signals_not": [],
                        "signals_any": [
                            # 一卖形态
                            "日线_D1B_SELL1_一卖_7笔_任意_0",
                            "日线_D1B_SELL1_一卖_9笔_任意_0",
                        ],
                    }
                ],
            }
        ]

        pos_name = "趋势量价V2"

        T0 = kwargs.get("T0", False)
        pos_name = f"{pos_name}T0" if T0 else f"{pos_name}"

        pos = Position(
            name=pos_name,
            symbol=symbol,
            opens=[Event.load(x) for x in opens],
            exits=[Event.load(x) for x in exits],
            interval=kwargs.get("interval", 3600 * 24),
            timeout=kwargs.get("timeout", 16 * 30 * 2),
            stop_loss=kwargs.get("stop_loss", 1500),  # 适中的止损比例
            T0=T0,
        )
        return pos

    @property
    def positions(self) -> List[Position]:
        _pos = [
            self.create_pos_a(symbol=self.symbol, base_freq="日线", T0=False),
        ]
        return _pos


if __name__ == "__main__":
    symbols = get_symbols('stock')
    search_code = '601008'  # 爱尔眼科
    test_name = None
    for symbol in symbols:
        if search_code in symbol:
            test_name = symbol

    print(f"symbol name is {test_name}")
    today = datetime.now().strftime('%Y%m%d')

    # freq D(day), W(week), M(month)
    bars = get_raw_bars(test_name, freq=Freq.D, sdt="2018-05-01", edt=today, raw_bar=True)

    tactic = Strategy(symbol=test_name)
    tactic.replay(bars, res_path=r"/Users/niez01/Documents/dev/czsc/results/three_buy_one_sell", refresh=True)
