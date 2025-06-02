import sys
sys.path.append("/Users/niez01/Documents/dev/czsc")
import os
import pandas as pd
from datetime import datetime
from czsc.connectors.ts_connector import get_raw_bars, get_symbols
from typing import List
from czsc import CZSC, Freq
from czsc.utils.sig import get_zs_seq
import subprocess
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from czsc.utils.ta import SMA, EMA

ma_colors = {
    5: '#FF6B6B',    # 红色
    10: '#4ECDC4',   # 青色
    20: '#45B7D1',   # 蓝色
    60: '#96CEB4',   # 绿色
    120: '#FFEEAD',  # 黄色
    250: '#D4A5A5'   # 紫色
}


def create_chart(symbol: str, start_date: str = "2020-01-01", freqs: List[str] = None, ma_periods: List[int] = None):
    """
    创建增强版的缠论分析图表，包含更详细的中枢绘制和MACD指标
    """
    if freqs is None:
        freqs = ['D']
        
    today = datetime.now().strftime('%Y%m%d')
    
    # 修改子图布局，每个周期单独一个图表
    fig = make_subplots(
        rows=2,  # 固定为2行：K线和MACD
        cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],  # K线图占70%，MACD占30%
        vertical_spacing=0.05,
        # specs=[[{"secondary_y": True}], [{"secondary_y": False}]]
    )
    
    # 获取数据
    bars = get_raw_bars(symbol, freq=Freq[freqs[0]], sdt=start_date, edt=today, raw_bar=True)
    if not isinstance(bars, list):
        print(f"bars is not list, type: {type(bars)}")
        return
        
    czsc = CZSC(bars, max_bi_num=60)
    zs_list = get_zs_seq(czsc.bi_list)
    
    # 添加K线图
    kline_data = [bar.__dict__ for bar in czsc.bars_raw]
    df = pd.DataFrame(kline_data)
    
    # K线图部分
    fig.add_trace(
        go.Candlestick(
            x=df['dt'],
            open=df['open'],
            high=df['high'], 
            low=df['low'],
            close=df['close'],
            name='K线',
            increasing_line_color='#00ff00',  # 更亮的绿色
            decreasing_line_color='#ff0000',  # 更亮的红色
            increasing_fillcolor='#00ff00',
            decreasing_fillcolor='#ff0000'
        ),
        row=1, col=1
    )
    
    # 分型显示
    if czsc.fx_list:
        top_fx = [fx for fx in czsc.fx_list if fx.mark.value == 'G']
        bottom_fx = [fx for fx in czsc.fx_list if fx.mark.value == 'D']
        
        if top_fx:
            fig.add_trace(
                go.Scatter(
                    x=[fx.dt for fx in top_fx],
                    y=[fx.fx for fx in top_fx],
                    mode='markers',
                    marker=dict(
                        symbol='triangle-down',
                        size=10,
                        color='#d32f2f',
                        line=dict(width=2, color='#b71c1c')
                    ),
                    name='顶分型'
                ),
                row=1, col=1
            )
            
        if bottom_fx:
            fig.add_trace(
                go.Scatter(
                    x=[fx.dt for fx in bottom_fx],
                    y=[fx.fx for fx in bottom_fx],
                    mode='markers', 
                    marker=dict(
                        symbol='triangle-up',
                        size=10,
                        color='#2e7d32',
                        line=dict(width=2, color='#1b5e20')
                    ),
                    name='底分型'
                ),
                row=1, col=1
            )
    
    # 笔的显示
    if len(czsc.bi_list) > 0:
        bi_x = [bi.fx_a.dt for bi in czsc.bi_list] + [czsc.bi_list[-1].fx_b.dt]
        bi_y = [bi.fx_a.fx for bi in czsc.bi_list] + [czsc.bi_list[-1].fx_b.fx]
        
        fig.add_trace(
            go.Scatter(
                x=bi_x,
                y=bi_y,
                mode='lines+markers',
                line=dict(
                    color='#7b1fa2',
                    width=2,
                    dash='solid'
                ),
                marker=dict(
                    size=6,
                    color='#7b1fa2',
                    line=dict(width=1, color='#4a148c')
                ),
                name='笔'
            ),
            row=1, col=1
        )
    
    # 中枢显示
    for zs in zs_list:
        if zs.is_valid:
            fig.add_shape(
                type="rect",
                x0=zs.sdt, y0=zs.zd,
                x1=zs.edt, y1=zs.zg,
                fillcolor="rgba(255,193,7,0.2)",
                line=dict(color="#ffa000", width=2),
                name=f"中枢",
                row=1, col=1
            )
            
            fig.add_shape(
                type="line",
                x0=zs.sdt, y0=zs.zz,
                x1=zs.edt, y1=zs.zz,
                line=dict(color="#ffa000", width=1, dash="dot"),
                row=1, col=1
            )
    
    # MACD部分
    from czsc.utils.ta import MACD
    import numpy as np
    
    close_prices = np.array([bar.close for bar in bars], dtype=np.double)
    diff, dea, macd = MACD(close_prices)
    
    fig.add_trace(
        go.Bar(
            x=df['dt'],
            y=macd,
            name='MACD',
            marker_color=['#00ff00' if x > 0 else '#ff0000' for x in macd]  # 更亮的颜色
        ),
        row=2, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=df['dt'],
            y=diff,
            mode='lines',
            name='DIFF',
            line=dict(color='#00ff00', width=1.5)  # 更亮的绿色
        ),
        row=2, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=df['dt'],
            y=dea,
            mode='lines',
            name='DEA',
            line=dict(color='#ff0000', width=1.5)  # 更亮的红色
        ),
        row=2, col=1
    )
    
    # 计算并添加MA和EMA
    if ma_periods:
        for period in ma_periods:
            # 计算MA和EMA
            ma = SMA(df['close'].values, period)
            ema = EMA(df['close'].values, period)
            
            # 添加MA线
            fig.add_trace(
                go.Scatter(
                    x=df['dt'],
                    y=ma,
                    mode='lines',
                    name=f'MA{period}',
                    line=dict(
                        color=ma_colors.get(period, '#000000'),
                        width=1.5
                    )
                ),
                row=1, col=1
            )
            
            # 添加EMA线
            fig.add_trace(
                go.Scatter(
                    x=df['dt'],
                    y=ema,
                    mode='lines',
                    name=f'EMA{period}',
                    line=dict(
                        color=ma_colors.get(period, '#000000'),
                        width=1.5,
                        dash='dot'  # 使用虚线表示EMA
                    )
                ),
                row=1, col=1
            )
            
            # 计算并添加MA和EMA的交叉点
            cross_points = []
            for i in range(1, len(df)):
                # 判断是否发生交叉
                if (ma[i-1] < ema[i-1] and ma[i] > ema[i]) or (ma[i-1] > ema[i-1] and ma[i] < ema[i]):
                    cross_points.append({
                        'dt': df['dt'].iloc[i],
                        'price': df['close'].iloc[i],
                        'prev_price': df['close'].iloc[i-period] if i >= period else None,
                        'type': '金叉' if ma[i] > ema[i] else '死叉'
                    })
            
            # 添加交叉点标记
            cross_x = []
            cross_y = []
            cross_text = []
            for point in cross_points:
                if point['prev_price'] is not None:
                    price_change = point['price'] - point['prev_price']
                    change_pct = (price_change / point['prev_price']) * 100
                    text = f"{point['type']}<br>{period}周期前: {point['prev_price']:.2f}<br>当前: {point['price']:.2f}<br>变化: {change_pct:+.2f}%"
                    cross_x.append(point['dt'])
                    cross_y.append(point['price'])
                    cross_text.append(text)
            
            fig.add_trace(
                go.Scatter(
                    x=cross_x,
                    y=cross_y,
                    mode='markers',
                    name=f'MA{period}/EMA{period}交叉点',
                    marker=dict(
                        symbol='star',
                        size=15,
                        color=ma_colors.get(period, '#000000'),
                        line=dict(width=2, color='white')
                    ),
                    text=cross_text,
                    hoverinfo='text'
                ),
                row=1, col=1
            )
    
    # 更新布局
    fig.update_layout(
        title=dict(
            text=f'{symbol}-{freqs[0]} 缠论分析图表',
            x=0.5,
            y=0.95,
            xanchor='center',
            yanchor='top',
            font=dict(color='white')  # 标题文字颜色
        ),
        xaxis_rangeslider_visible=True,
        height=1000,
        showlegend=True,
        template='plotly_dark',  # 使用暗色模板
        paper_bgcolor='black',   # 背景色
        plot_bgcolor='black',    # 绘图区域背景色
        hovermode='x unified',
        font=dict(color='white'),  # 全局文字颜色
        legend=dict(
            font=dict(color='white'),  # 图例文字颜色
            bgcolor='rgba(0,0,0,0.5)'  # 图例背景色
        ),
        xaxis=dict(
            gridcolor='rgba(128,128,128,0.2)',  # 网格线颜色
            zerolinecolor='rgba(128,128,128,0.2)'
        ),
        yaxis=dict(
            gridcolor='rgba(128,128,128,0.2)',  # 网格线颜色
            zerolinecolor='rgba(128,128,128,0.2)'
        )
    )
    
    # 保存图表
    output_path = f"/Users/niez01/Documents/dev/czsc/results/{symbol}_czsc.html"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_html(output_path)
    
    print(f"图表已保存到: {output_path}")
    subprocess.run(['open', output_path])
    
    return fig

if __name__ == "__main__":
    # 获取股票列表
    symbols = get_symbols('stock')
    search_code = '601008'  # 爱尔眼科
    
    # 查找股票
    test_symbol = None
    for symbol in symbols:
        if search_code in symbol:
            test_symbol = symbol
            break
    
    if test_symbol:
        print(f"找到股票: {test_symbol}")
        
        # 方法2：使用增强版绘图（基于plotly）
        print("\n=== 缠论分析图表 ===")
        # 自定义MA/EMA周期
        chart = create_chart(
            test_symbol, 
            "2018-01-01",
            freqs=['D'],
            ma_periods=[20, 60, 120]
        )
        
    else:
        print(f"未找到包含 {search_code} 的股票")


