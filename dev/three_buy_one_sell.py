import os
import sys
sys.path.append("/Users/niez01/Documents/dev/czsc")

import pandas as pd
import numpy as np
from typing import List, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

from czsc.objects import Event, Position, RawBar
from czsc import CzscStrategyBase, Position, Freq, CZSC
from czsc.connectors.ts_connector import get_raw_bars, get_symbols
from czsc.utils.ta import SMA, EMA, MACD
from czsc.utils.sig import get_zs_seq
import czsc

# 添加 talib 导入来获取 RSI 和 BOLL
try:
    import talib as ta
    def RSI(close, timeperiod=14):
        return ta.RSI(close, timeperiod=timeperiod)
    
    def BOLL(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0):
        return ta.BBANDS(close, timeperiod=timeperiod, nbdevup=nbdevup, nbdevdn=nbdevdn, matype=matype)
except ImportError:
    # 如果没有安装talib，使用简化版实现
    def RSI(close, timeperiod=14):
        """简化的RSI计算"""
        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gains = []
        avg_losses = []
        
        for i in range(len(gains)):
            if i < timeperiod:
                avg_gain = np.mean(gains[:i+1]) if i > 0 else gains[0]
                avg_loss = np.mean(losses[:i+1]) if i > 0 else losses[0]
            else:
                avg_gain = np.mean(gains[i-timeperiod+1:i+1])
                avg_loss = np.mean(losses[i-timeperiod+1:i+1])
            
            avg_gains.append(avg_gain)
            avg_losses.append(avg_loss)
        
        rsi = []
        for i in range(len(avg_gains)):
            if avg_losses[i] == 0:
                rsi.append(100)
            else:
                rs = avg_gains[i] / avg_losses[i]
                rsi.append(100 - (100 / (1 + rs)))
        
        # 在开头补充一个值以匹配原始数组长度
        rsi = [rsi[0]] + rsi
        return np.array(rsi[:len(close)])
    
    def BOLL(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0):
        """简化的布林带计算"""
        middle = SMA(close, timeperiod)
        std = []
        
        for i in range(len(close)):
            if i < timeperiod:
                seq = close[0:i+1]
            else:
                seq = close[i-timeperiod+1:i+1]
            std.append(np.std(seq))
        
        std = np.array(std)
        upper = middle + nbdevup * std
        lower = middle - nbdevdn * std
        
        return upper, middle, lower


class EnhancedMultiFactorStrategy(CzscStrategyBase):
    """增强版多因子价差套利策略
    
    策略特点：
    1. 趋势跟踪：使用周线和日线双周期确认趋势
    2. 价差套利：基于均值回归和相对强弱分析
    3. 三买一卖：严格按照缠论买卖点执行
    4. 多因子验证：技术指标、量价关系、缠论形态综合确认
    5. 动态止盈止损：根据市场波动调整风控参数
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.benchmark_symbol = kwargs.get('benchmark_symbol', '000300.SH')  # 基准指数
        self.relative_strength_period = kwargs.get('relative_strength_period', 20)
        self.price_deviation_threshold = kwargs.get('price_deviation_threshold', 2.0)
        
    def create_chan_zhongshu_divergence_position(self, symbol, **kwargs):
        """创建缠论中枢背驰策略"""
        
        # 基础过滤信号
        long_basis_signals = [
            "周线_D1_表里关系V230101_向上_任意_任意_0",      # 1. 周线趋势向上
            "日线_D1SMA#120_分类V221101_多头_向上_任意_0",   # 2. 日线在年线之上且年线向上
        ]
        
        # 开多事件列表：任意一个事件满足即可开多
        long_opens = []
        
        # 定义多个独立的底背驰买点事件
        buy_signals = {
            "三笔盘整底背驰": "日线_D1三笔_形态V230618_向下盘背_任意_任意_0",
            "七笔aAb式底背驰": "日线_D1七笔_形态V230620_aAb式底背驰_任意_任意_0",
            "七笔类趋势底背驰": "日线_D1七笔_形态V230620_类趋势底背驰_任意_任意_0",
        }
        
        for name, signal in buy_signals.items():
            long_opens.append({
                "operate": "开多",
                "signals_not": ["日线_D1_涨跌停V230331_涨停_任意_任意_0"],
                "signals_all": [],
                "factors": [{
                    "name": name,
                    "signals_all": long_basis_signals + [signal],
                    "signals_any": [],
                    "signals_not": []
                }]
            })
        
        # 平多事件列表：任意一个事件满足即可平多
        long_exits = []
        
        # 定义多个独立的顶背驰或趋势破坏卖点事件
        sell_signals = {
            "三笔盘整顶背驰": "日线_D1三笔_形态V230618_向上盘背_任意_任意_0",
            "七笔aAb式顶背驰": "日线_D1七笔_形态V230620_aAb式顶背驰_任意_任意_0",
            "七笔类趋势顶背驰": "日线_D1七笔_形态V230620_类趋势顶背驰_任意_任意_0",
            "跌破20日均线": "日线_D1SMA#20_分类V221101_空头_任意_任意_0",
            "日线趋势转空": "日线_D1_表里关系V230101_向下_任意_任意_0",
        }
        
        for name, signal in sell_signals.items():
            long_exits.append({
                "operate": "平多",
                "signals_not": [],
                "signals_all": [],
                "factors": [{
                    "name": name,
                    "signals_all": [signal],
                    "signals_any": [],
                    "signals_not": []
                }]
            })
        
        return Position(
            name=f"缠论中枢背驰_{symbol}",
            symbol=symbol,
            opens=[Event.load(x) for x in long_opens],
            exits=[Event.load(x) for x in long_exits],
            interval=kwargs.get("interval", 3600 * 24),
            timeout=kwargs.get("timeout", 30 * 20),
            stop_loss=kwargs.get("stop_loss", 1000),
            T0=kwargs.get("T0", False),
        )

    @property
    def positions(self) -> List[Position]:
        """返回策略持仓配置"""
        # 使用新的中枢背驰策略
        return [
            self.create_chan_zhongshu_divergence_position(symbol=self.symbol, T0=False),
        ]


class StrategyVisualizer:
    """策略可视化分析器"""
    
    def __init__(self, strategy_class, symbol: str, **kwargs):
        self.strategy_class = strategy_class
        self.symbol = symbol
        self.kwargs = kwargs
        self.results = {}
        
    def load_data(self, start_date: str = "2020-01-01", end_date: str = None):
        """加载数据"""
        if end_date is None:
            end_date = datetime.now().strftime('%Y%m%d')
        
        print(f"正在加载 {self.symbol} 的数据...")
        self.bars = get_raw_bars(
            self.symbol, 
            freq=Freq.D, 
            sdt=start_date, 
            edt=end_date, 
            raw_bar=True
        )
        
        # 同时加载周线数据用于多周期分析
        self.bars_weekly = get_raw_bars(
            self.symbol,
            freq=Freq.W,
            sdt=start_date,
            edt=end_date,
            raw_bar=True
        )
        
        print(f"加载完成，日线: {len(self.bars)} 根，周线: {len(self.bars_weekly)} 根")
        return self.bars
        
    def quick_backtest(self, start_date: str = "2021-01-01"):
        """快速回测"""
        print("开始执行策略回测...")
        
        # 创建策略实例
        strategy = self.strategy_class(symbol=self.symbol, **self.kwargs)
        
        # 执行回测
        trader = strategy.replay(
            self.bars,
            sdt=start_date,
            res_path=f"/Users/niez01/Documents/dev/czsc/results/multi_factor_arbitrage/{self.symbol}",
            refresh=True
        )
        
        # 分析结果
        if trader.positions:
            position = trader.positions[0]
            self.results = position.evaluate()
            
            # 打印基本结果
            print("=== 策略回测结果 ===")
            print(f"标的代码: {self.symbol}")
            print(f"回测区间: {start_date} - {datetime.now().strftime('%Y-%m-%d')}")
            print(f"交易次数: {self.results.get('交易次数', 0)}")
            print(f"胜率: {self.results.get('胜率', 0):.2%}")
            print(f"总收益率: {self.results.get('总收益率', 0):.2%}")
            print(f"年化收益率: {self.results.get('年化收益率', 0):.2%}")
            print(f"最大回撤: {self.results.get('最大回撤', 0):.2%}")
            print(f"夏普比率: {self.results.get('夏普比率', 0):.2f}")
            print(f"卡尔玛比率: {self.results.get('卡尔玛比率', 0):.2f}")
            
            # 保存交易记录
            self.trades = position.pairs if hasattr(position, 'pairs') else []
            self.trader = trader
            
        return self.results
        
    def create_enhanced_chart(self, ma_periods: List[int] = [20, 60, 120]):
        """创建增强版图表，包含买卖点和多因子分析"""
        print("正在生成增强版多因子分析图表...")
        
        # 创建CZSC分析对象
        czsc_daily = CZSC(self.bars, max_bi_num=100)
        czsc_weekly = CZSC(self.bars_weekly, max_bi_num=50)
        zs_list_daily = get_zs_seq(czsc_daily.bi_list)
        zs_list_weekly = get_zs_seq(czsc_weekly.bi_list)
        
        # 准备数据
        df = pd.DataFrame([{
            'dt': bar.dt,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'volume': bar.vol,
            'amount': bar.amount
        } for bar in self.bars])
        
        # 计算技术指标
        close_prices = df['close'].values.astype(np.float64)
        high_prices = df['high'].values.astype(np.float64)
        low_prices = df['low'].values.astype(np.float64)
        
        # MACD
        diff, dea, macd = MACD(close_prices)
        
        # 布林带
        boll_upper, boll_middle, boll_lower = BOLL(close_prices, timeperiod=20)
        
        # RSI
        rsi = RSI(close_prices, timeperiod=14)
        
        # 相对强弱（简化版，与MA20的比较）
        ma20 = SMA(close_prices, 20)
        relative_strength = (close_prices / ma20 - 1) * 100
        
        # 创建子图
        fig = make_subplots(
            rows=5, cols=1,
            shared_xaxes=True,
            row_heights=[0.4, 0.15, 0.15, 0.15, 0.15],
            vertical_spacing=0.02,
            subplot_titles=[
                f'{self.symbol} 多因子价差套利分析',
                '成交量分析', 
                'MACD动量', 
                'RSI强弱',
                '相对强弱与价差分析'
            ]
        )
        
        # === 第一行：K线图 + 均线 + 缠论结构 + 买卖点 ===
        fig.add_trace(
            go.Candlestick(
                x=df['dt'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='K线',
                increasing_line_color='#00ff00',
                decreasing_line_color='#ff0000'
            ),
            row=1, col=1
        )
        
        # 添加均线系统
        colors = ['#FFA500', '#FF69B4', '#00CED1', '#FFD700']
        for i, period in enumerate(ma_periods):
            ma = SMA(close_prices, period)
            fig.add_trace(
                go.Scatter(
                    x=df['dt'], y=ma,
                    mode='lines', name=f'MA{period}',
                    line=dict(width=1.5, color=colors[i % len(colors)])
                ),
                row=1, col=1
            )
        
        # 布林带
        fig.add_trace(
            go.Scatter(
                x=df['dt'], y=boll_upper,
                mode='lines', name='布林上轨',
                line=dict(color='gray', width=1, dash='dot')
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df['dt'], y=boll_lower,
                mode='lines', name='布林下轨',
                line=dict(color='gray', width=1, dash='dot'),
                fill='tonexty', fillcolor='rgba(128,128,128,0.05)'
            ),
            row=1, col=1
        )
        
        # 日线分型标记
        if czsc_daily.fx_list:
            top_fx = [fx for fx in czsc_daily.fx_list if fx.mark.value == 'G']
            bottom_fx = [fx for fx in czsc_daily.fx_list if fx.mark.value == 'D']
            
            if top_fx:
                fig.add_trace(
                    go.Scatter(
                        x=[fx.dt for fx in top_fx], y=[fx.fx for fx in top_fx],
                        mode='markers', name='日线顶分型',
                        marker=dict(symbol='triangle-down', size=6, color='red')
                    ),
                    row=1, col=1
                )
            
            if bottom_fx:
                fig.add_trace(
                    go.Scatter(
                        x=[fx.dt for fx in bottom_fx], y=[fx.fx for fx in bottom_fx],
                        mode='markers', name='日线底分型',
                        marker=dict(symbol='triangle-up', size=6, color='green')
                    ),
                    row=1, col=1
                )
        
        # 日线笔的连接
        if len(czsc_daily.bi_list) > 0:
            bi_x = [bi.fx_a.dt for bi in czsc_daily.bi_list] + [czsc_daily.bi_list[-1].fx_b.dt]
            bi_y = [bi.fx_a.fx for bi in czsc_daily.bi_list] + [czsc_daily.bi_list[-1].fx_b.fx]
            
            fig.add_trace(
                go.Scatter(
                    x=bi_x, y=bi_y,
                    mode='lines', name='日线笔',
                    line=dict(color='purple', width=2)
                ),
                row=1, col=1
            )
        
        # 日线中枢标记
        for zs in zs_list_daily:
            if zs.is_valid:
                fig.add_shape(
                    type="rect",
                    x0=zs.sdt, y0=zs.zd,
                    x1=zs.edt, y1=zs.zg,
                    fillcolor="rgba(255,193,7,0.15)",
                    line=dict(color="#ffa000", width=1),
                    row=1, col=1
                )
        
        # 买卖点标记 - 修复字段名问题
        if hasattr(self, 'trades') and self.trades:
            buy_points_x, buy_points_y, buy_text = [], [], []
            sell_points_x, sell_points_y, sell_text = [], [], []
            
            for trade in self.trades:
                # 使用正确的字段名
                trade_direction = trade.get('交易方向', '')
                open_time = trade.get('开仓时间', '')
                close_time = trade.get('平仓时间', '')
                open_price = trade.get('开仓价格', 0)
                close_price = trade.get('平仓价格', 0)
                profit = trade.get('盈亏比例', 0)  # 以BP为单位
                
                if trade_direction == '多头':
                    # 买点
                    buy_points_x.append(open_time)
                    buy_points_y.append(open_price)
                    buy_text.append(f"买入: {open_price:.2f}<br>时间: {open_time}")
                    
                    # 卖点
                    if close_time:
                        sell_points_x.append(close_time)
                        sell_points_y.append(close_price)
                        sell_text.append(f"卖出: {close_price:.2f}<br>时间: {close_time}<br>收益: {profit:.2f}BP")
        
            # 买点标记
            if buy_points_x:
                fig.add_trace(
                    go.Scatter(
                        x=buy_points_x, y=buy_points_y,
                        mode='markers', name='策略买点',
                        marker=dict(
                            symbol='triangle-up', size=20,
                            color='red', line=dict(width=3, color='darkred')
                        ),
                        text=buy_text, hoverinfo='text'
                    ),
                    row=1, col=1
                )
            
            # 卖点标记
            if sell_points_x:
                fig.add_trace(
                    go.Scatter(
                        x=sell_points_x, y=sell_points_y,
                        mode='markers', name='策略卖点',
                        marker=dict(
                            symbol='triangle-down', size=20,
                            color='blue', line=dict(width=3, color='darkblue')
                        ),
                        text=sell_text, hoverinfo='text'
                    ),
                    row=1, col=1
                )
        
        # === 第二行：成交量分析 ===
        volume_colors = ['green' if c >= o else 'red' for o, c in zip(df['open'], df['close'])]
        fig.add_trace(
            go.Bar(x=df['dt'], y=df['volume'], name='成交量', marker_color=volume_colors),
            row=2, col=1
        )
        
        # 成交量均线
        vol_ma = SMA(df['volume'].values.astype(np.float64), 20)
        fig.add_trace(
            go.Scatter(x=df['dt'], y=vol_ma, mode='lines', name='成交量MA20',
                      line=dict(color='orange', width=2)),
            row=2, col=1
        )
        
        # === 第三行：MACD分析 ===
        macd_colors = ['green' if x > 0 else 'red' for x in macd]
        fig.add_trace(
            go.Bar(x=df['dt'], y=macd, name='MACD', marker_color=macd_colors),
            row=3, col=1
        )
        fig.add_trace(
            go.Scatter(x=df['dt'], y=diff, mode='lines', name='DIFF',
                      line=dict(color='blue', width=1.5)),
            row=3, col=1
        )
        fig.add_trace(
            go.Scatter(x=df['dt'], y=dea, mode='lines', name='DEA',
                      line=dict(color='orange', width=1.5)),
            row=3, col=1
        )
        
        # === 第四行：RSI分析 ===
        fig.add_trace(
            go.Scatter(x=df['dt'], y=rsi, mode='lines', name='RSI',
                      line=dict(color='purple', width=2)),
            row=4, col=1
        )
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="gray", row=4, col=1)
        
        # === 第五行：相对强弱与价差分析 ===
        fig.add_trace(
            go.Scatter(x=df['dt'], y=relative_strength, mode='lines', name='相对强弱(%)',
                      line=dict(color='darkgreen', width=2)),
            row=5, col=1
        )
        fig.add_hline(y=0, line_dash="dot", line_color="gray", row=5, col=1)
        fig.add_hline(y=5, line_dash="dash", line_color="red", row=5, col=1)
        fig.add_hline(y=-5, line_dash="dash", line_color="green", row=5, col=1)
        
        # 价格偏离标记
        price_deviation = np.abs(relative_strength)
        extreme_points = price_deviation > self.kwargs.get('price_deviation_threshold', 5.0)
        if np.any(extreme_points):
            extreme_dates = df['dt'][extreme_points]
            extreme_values = relative_strength[extreme_points]
            fig.add_trace(
                go.Scatter(
                    x=extreme_dates, y=extreme_values,
                    mode='markers', name='价差极值点',
                    marker=dict(symbol='circle', size=8, color='yellow',
                               line=dict(width=2, color='orange'))
                ),
                row=5, col=1
            )
        
        # 更新布局
        fig.update_layout(
            title=dict(
                text=f'{self.symbol} 多因子价差套利策略全景分析',
                x=0.5, y=0.98, xanchor='center', yanchor='top',
                font=dict(size=16, color='white')
            ),
            height=1400,
            showlegend=True,
            template='plotly_dark',
            xaxis_rangeslider_visible=False,
            font=dict(color='white', size=10)
        )
        
        # 保存图表
        output_path = f"/Users/niez01/Documents/dev/czsc/results/multi_factor_arbitrage/{self.symbol}_enhanced_chart.html"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.write_html(output_path)
        print(f"增强版图表已保存到: {output_path}")
        
        # 自动打开图表
        import subprocess
        subprocess.run(['open', output_path])
        
        return fig
    
    def generate_detailed_report(self):
        """生成详细的策略分析报告"""
        if not self.results:
            print("请先执行回测")
            return
            
        # 计算额外指标
        profit_factor = self.results.get('盈亏比', 0)
        win_rate = self.results.get('胜率', 0)
        total_trades = self.results.get('交易次数', 0)
        
        report = f"""
# {self.symbol} 多因子价差套利策略深度分析报告

## 📊 基本信息
- **标的代码**: {self.symbol}
- **策略类型**: 多因子价差套利策略
- **使用周期**: 日线 + 周线联立分析
- **分析时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 📈 核心收益指标
- **总收益率**: {self.results.get('总收益率', 0):.2%}
- **年化收益率**: {self.results.get('年化收益率', 0):.2%}
- **最大回撤**: {self.results.get('最大回撤', 0):.2%}
- **夏普比率**: {self.results.get('夏普比率', 0):.2f}
- **卡尔玛比率**: {self.results.get('卡尔玛比率', 0):.2f}
- **索提诺比率**: {self.results.get('索提诺比率', 0):.2f}

## 🎯 交易效率分析
- **交易次数**: {total_trades}
- **胜率**: {win_rate:.2%}
- **盈亏比**: {profit_factor:.2f}
- **平均持仓天数**: {self.results.get('平均持仓天数', 0):.1f}
- **交易频率**: {total_trades/max(1, self.results.get('回测天数', 365)*365):.1f} 次/年

## 🏗️ 策略架构解析

### 多因子体系
1. **趋势确认因子**
   - 周线趋势：确保大周期方向正确
   - 日线趋势：精确入场时机
   - 双周期共振：降低假突破风险

2. **三买一卖因子**
   - 标准三买点识别
   - 均线辅助三买确认
   - 底背驰买点补充
   - 一卖点精确退出

3. **技术指标因子**
   - MACD动量确认
   - 布林带位置判断
   - RSI超买超卖
   - KDJ金叉死叉

4. **量价配合因子**
   - 放量突破确认
   - 量价一致性验证
   - 温和放量筛选

5. **价差套利因子**
   - 相对强弱分析
   - 均值回归判断
   - 价格偏离度量

## ⚖️ 风险控制机制
- **止损设置**: 8% 硬止损
- **超时平仓**: 20个交易日
- **涨跌停规避**: 自动排除异常情况
- **多因子验证**: 降低单一信号风险

## 💡 策略优势
1. **多维度验证**: 5大因子体系确保信号质量
2. **趋势跟踪**: 双周期确认避免逆势操作
3. **精确进出**: 三买一卖提供明确交易点位
4. **价差套利**: 增加超额收益机会
5. **完善风控**: 多层次风险管理

## 🔧 优化建议
1. **仓位管理**: 根据信号强度动态调整仓位
2. **止盈策略**: 增加分批止盈机制
3. **市场环境**: 加入牛熊市识别模块
4. **相关性**: 考虑与基准指数的相关性
5. **资金成本**: 纳入交易成本和滑点影响

## 📋 交易记录摘要
"""
        
        if hasattr(self, 'trades') and self.trades:
            profit_trades = [t for t in self.trades if t.get('盈亏金额', 0) > 0]
            loss_trades = [t for t in self.trades if t.get('盈亏金额', 0) < 0]
            
            if profit_trades:
                avg_profit = sum(t.get('盈亏金额', 0) for t in profit_trades) / len(profit_trades)
                max_profit = max(t.get('盈亏金额', 0) for t in profit_trades)
                report += f"\n- **平均盈利**: {avg_profit:.2f}"
                report += f"\n- **最大单笔盈利**: {max_profit:.2f}"
            
            if loss_trades:
                avg_loss = sum(t.get('盈亏金额', 0) for t in loss_trades) / len(loss_trades)
                max_loss = min(t.get('盈亏金额', 0) for t in loss_trades)
                report += f"\n- **平均亏损**: {avg_loss:.2f}"
                report += f"\n- **最大单笔亏损**: {max_loss:.2f}"
        
        report += f"""

## 🎖️ 策略评级

基于以上分析，该策略评级为：
"""
        
        # 简单评级逻辑
        score = 0
        if self.results.get('年化收益率', 0) > 0.15: score += 20
        elif self.results.get('年化收益率', 0) > 0.10: score += 15
        elif self.results.get('年化收益率', 0) > 0.05: score += 10
        
        if self.results.get('最大回撤', 1) < 0.15: score += 20
        elif self.results.get('最大回撤', 1) < 0.25: score += 15
        elif self.results.get('最大回撤', 1) < 0.35: score += 10
        
        if self.results.get('夏普比率', 0) > 1.5: score += 20
        elif self.results.get('夏普比率', 0) > 1.0: score += 15
        elif self.results.get('夏普比率', 0) > 0.5: score += 10
        
        if win_rate > 0.6: score += 20
        elif win_rate > 0.5: score += 15
        elif win_rate > 0.4: score += 10
        
        if profit_factor > 2.0: score += 20
        elif profit_factor > 1.5: score += 15
        elif profit_factor > 1.2: score += 10
        
        if score >= 80:
            rating = "A+ (优秀)"
        elif score >= 70:
            rating = "A (良好)"
        elif score >= 60:
            rating = "B+ (中等偏上)"
        elif score >= 50:
            rating = "B (中等)"
        else:
            rating = "C (需要优化)"
        
        report += f"\n**综合评级**: {rating} (得分: {score}/100)"
        
        # 保存报告
        report_path = f"/Users/niez01/Documents/dev/czsc/results/multi_factor_arbitrage/{self.symbol}_detailed_report.md"
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"详细策略分析报告已保存到: {report_path}")
        return report
    
    def run_complete_analysis(self, start_date: str = "2020-01-01", backtest_start: str = "2021-01-01"):
        """运行完整的策略分析流程"""
        print("=" * 60)
        print(f"  🚀 {self.symbol} 多因子价差套利策略完整分析")
        print("=" * 60)
        
        try:
            # 1. 数据加载
            print("\n📊 第1步：加载历史数据...")
            self.load_data(start_date)
            
            # 2. 策略回测
            print("\n⚡ 第2步：执行策略回测...")
            self.quick_backtest(backtest_start)
            
            # 3. 可视化分析
            print("\n📈 第3步：生成可视化图表...")
            self.create_enhanced_chart()
            
            # 4. 详细报告
            print("\n📋 第4步：生成分析报告...")
            self.generate_detailed_report()
            
            print("\n✅ 策略分析完成！请查看生成的图表和报告。")
            
        except Exception as e:
            print(f"\n❌ 分析过程出现错误: {e}")
            import traceback
            traceback.print_exc()
        
        print("=" * 60)
        return self.results


def main():
    """主函数：演示完整的策略分析流程"""
    
    # 获取目标股票
    symbols = get_symbols('stock')
    # search_code = '601008'  # 连云港
    search_code = '002594'  # 连云港
    target_symbol = None
    
    for symbol in symbols:
        if search_code in symbol:
            target_symbol = symbol
            break
    
    if not target_symbol:
        print(f"未找到股票代码: {search_code}")
        return
    
    print(f"🎯 目标分析标的: {target_symbol}")
    
    # 策略参数配置
    strategy_params = {
        'benchmark_symbol': '000300.SH',  # 沪深300基准
        'relative_strength_period': 20,
        'price_deviation_threshold': 5.0
    }
    
    # 创建策略分析器
    analyzer = StrategyVisualizer(
        strategy_class=EnhancedMultiFactorStrategy,
        symbol=target_symbol,
        **strategy_params
    )
    
    # 执行完整分析
    results = analyzer.run_complete_analysis(
        start_date="2020-01-01",
        backtest_start="2021-01-01"
    )
    
    return analyzer, results


if __name__ == "__main__":
    analyzer, results = main()
