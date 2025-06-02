import sys
sys.path.append("/Users/niez01/Documents/dev/czsc")

import os
import pandas as pd
from datetime import datetime
from czsc.utils import KlineChart
from czsc.connectors.ts_connector import get_raw_bars, get_symbols
from pathlib import Path
from typing import List
from czsc.objects import RawBar
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

def generate_stock_kline(symbol: str):
    """生成指定股票的K线图并保存

    Args:
        symbol (str): 股票代码，格式如 '000001.SZ#E'
    """
    today = datetime.now().strftime('%Y%m%d')

    # 获取该股票的K线数据
    bars = get_raw_bars(symbol, freq='日线', sdt="20230101", edt=today)

    df = pd.DataFrame(bars)

    # 创建K线图对象
    stock_code = symbol.split('#')[0]
    kline = KlineChart(
        n_rows=3, 
        height=800,
        row_height=[0.5, 0.25, 0.25]
    )

    kline.fig.update_layout(
        title=dict(
            text=f"{stock_code} 日K线图",
            x=0.5,
            xanchor='center', 
            y=0.95, 
            yanchor='top'
        )
    )

    # 添加K线
    kline.add_kline(df, name="K线")

    # 添加均线
    kline.add_sma(df, ma_seq=(5, 10, 21), row=1, visible=True, line_width=1.2)

    # 添加成交量
    kline.add_vol(df, row=2)

    # 添加MACD
    kline.add_macd(df, row=3)

    # 创建保存文件的目录结构
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    base_dir = os.path.join(desktop, 'kline-data')
    today_dir = os.path.join(base_dir, today)

    Path(today_dir).mkdir(parents=True, exist_ok=True)

    # 保存为HTML文件
    kline.fig.write_html(os.path.join(today_dir, f'kline_{stock_code}_{today}.html'))

def draw_czsc_analysis(symbol: str, start_date: str = "2017-01-01"):
    """
    绘制股票的分型、线段（笔）和中枢
    
    参数:
    - symbol: 股票代码
    - start_date: 开始日期
    """
    
    # 第一步：获取数据
    print(f"正在获取 {symbol} 的数据...")
    today = datetime.now().strftime('%Y%m%d')
    
    # 获取日线数据
    bars = get_raw_bars(symbol, freq=Freq.D, sdt=start_date, edt=today, raw_bar=True)
    print(f"bars type: {type(bars)}")
    if isinstance(bars, pd.DataFrame):
        bars = [RawBar(**x) for x in bars.to_dict('records')]
    elif not isinstance(bars, list):
        print(f"Unexpected type: {type(bars)}")
        return

    print(f"获取到 {len(bars)} 根K线数据")
    
    # 第二步：创建 CZSC 对象进行分析
    print("正在进行缠论分析...")
    czsc = CZSC(bars=bars)
    
    # 第三步：提取分型数据
    print(f"识别到 {len(czsc.fx_list)} 个分型")
    fx_data = []
    for fx in czsc.fx_list:
        fx_data.append({
            'dt': fx.dt,
            'fx': fx.fx,
            'mark': fx.mark.value  # 'G' 为顶分型，'D' 为底分型
        })
    
    # 第四步：提取笔（线段）数据  
    print(f"识别到 {len(czsc.bi_list)} 个笔")
    bi_data = []
    if len(czsc.bi_list) > 0:
        # 添加所有笔的起始分型
        for bi in czsc.bi_list:
            bi_data.append({
                'dt': bi.fx_a.dt, 
                'bi': bi.fx_a.fx
            })
        # 添加最后一个笔的结束分型
        bi_data.append({
            'dt': czsc.bi_list[-1].fx_b.dt, 
            'bi': czsc.bi_list[-1].fx_b.fx
        })
    
    # 第五步：识别中枢
    print("正在识别中枢...")
    zs_list = get_zs_seq(czsc.bi_list)
    print(f"识别到 {len(zs_list)} 个中枢")
    
    # 为了在图表上显示中枢，我们需要将中枢转换为可绘制的数据
    zs_data = []
    for i, zs in enumerate(zs_list):
        if zs.is_valid:  # 只显示有效的中枢
            # 为每个中枢创建矩形框的数据点
            start_dt = zs.sdt
            end_dt = zs.edt  
            zg = zs.zg  # 中枢上沿
            zd = zs.zd  # 中枢下沿
            
            zs_data.append({
                'start_dt': start_dt,
                'end_dt': end_dt,
                'zg': zg,
                'zd': zd,
                'zz': zs.zz,  # 中枢中轴
                'name': f'中枢{i+1}'
            })
    
    # 第六步：使用 czsc 自带的绘图功能
    print("正在生成图表...")
    
    # 准备K线数据
    kline_data = [bar.__dict__ for bar in czsc.bars_raw]
    
    # 使用 czsc 的 to_echarts 方法生成图表
    chart = czsc.to_echarts(width="1600px", height="800px")
    
    # 第七步：增加中枢绘制功能
    # 由于 czsc 原生不支持中枢绘制，我们需要手动添加
    chart = add_zentral_to_chart(chart, zs_data)
    
    # 第八步：保存并显示图表
    output_path = f"/Users/niez01/Documents/dev/czsc/results/{symbol}_czsc_analysis.html"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    chart.render(output_path)
    
    print(f"图表已保存到: {output_path}")
    
    # 自动打开浏览器显示图表
    subprocess.run(['open', output_path])
    
    # 第九步：打印分析统计信息
    print("\n=== 缠论分析结果统计 ===")
    print(f"总K线数量: {len(bars)}")
    print(f"分型数量: {len(czsc.fx_list)}")
    print(f"  - 顶分型: {len([fx for fx in czsc.fx_list if fx.mark.value == 'G'])}")
    print(f"  - 底分型: {len([fx for fx in czsc.fx_list if fx.mark.value == 'D'])}")
    print(f"笔数量: {len(czsc.bi_list)}")
    print(f"中枢数量: {len([zs for zs in zs_list if zs.is_valid])}")
    
    if zs_data:
        print("\n=== 中枢详细信息 ===")
        for i, zs in enumerate(zs_data):
            print(f"中枢{i+1}: 时间[{zs['start_dt'].strftime('%Y-%m-%d')} ~ {zs['end_dt'].strftime('%Y-%m-%d')}]")
            print(f"       上沿: {zs['zg']:.2f}, 下沿: {zs['zd']:.2f}, 中轴: {zs['zz']:.2f}")
    
    return chart, czsc, zs_list

def add_zentral_to_chart(chart, zs_data):
    """
    向图表中添加中枢绘制
    由于pyecharts不直接支持矩形绘制，我们用线条来表示中枢
    """
    try:
        from pyecharts.charts import Line
        from pyecharts import options as opts
        
        # 为每个中枢添加上沿和下沿的线条
        for zs in zs_data:
            # 中枢上沿线
            zg_line = Line()
            zg_line.add_xaxis([zs['start_dt'], zs['end_dt']])
            zg_line.add_yaxis(
                series_name=f"{zs['name']}_上沿",
                y_axis=[zs['zg'], zs['zg']],
                linestyle_opts=opts.LineStyleOpts(color="red", width=2, type_="dashed"),
                label_opts=opts.LabelOpts(is_show=False),
                symbol_size=0
            )
            
            # 中枢下沿线  
            zd_line = Line()
            zd_line.add_xaxis([zs['start_dt'], zs['end_dt']])
            zd_line.add_yaxis(
                series_name=f"{zs['name']}_下沿", 
                y_axis=[zs['zd'], zs['zd']],
                linestyle_opts=opts.LineStyleOpts(color="blue", width=2, type_="dashed"),
                label_opts=opts.LabelOpts(is_show=False),
                symbol_size=0
            )
            
            # 中枢中轴线
            zz_line = Line()
            zz_line.add_xaxis([zs['start_dt'], zs['end_dt']])
            zz_line.add_yaxis(
                series_name=f"{zs['name']}_中轴",
                y_axis=[zs['zz'], zs['zz']],
                linestyle_opts=opts.LineStyleOpts(color="orange", width=1, type_="dotted"),
                label_opts=opts.LabelOpts(is_show=False),
                symbol_size=0
            )
            
            # 将线条添加到主图表的第一个子图中
            chart.charts[0].overlap(zg_line)
            chart.charts[0].overlap(zd_line)
            chart.charts[0].overlap(zz_line)
            
    except Exception as e:
        print(f"添加中枢绘制时出错: {e}")
        
    return chart

def create_enhanced_chart(symbol: str, start_date: str = "2020-01-01", freqs: List[str] = None, ma_periods: List[int] = None):
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
        
    czsc = CZSC(bars)
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
        xaxis_rangeslider_visible=False,
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

    # 调整X轴同步
    # fig.update_xaxes(
    #     rangeslider_thickness=0.05,  # 如果保留导航条，调整其厚度
    #     row=2, col=1
    # )

    # # 隐藏周末空白
    # fig.update_xaxes(
    #     rangebreaks=[{'bounds': ['sat', 'mon']}],  # 隐藏周末
    #     type='category'  # 防止日期中断
    # )

    
    # 保存图表
    output_path = f"/Users/niez01/Documents/dev/czsc/results/{symbol}_enhanced_czsc.html"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_html(output_path)
    
    print(f"增强版图表已保存到: {output_path}")
    subprocess.run(['open', output_path])
    
    return fig

def get_stock_info(symbol: str) -> dict:
    """获取股票基本信息"""
    # 这里需要实现获取股票信息的逻辑
    return {
        "name": "股票名称",
        "code": symbol,
        "industry": "所属行业"
    }

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
        print("\n=== 方法2：增强版缠论分析图表 ===")
        # 自定义MA/EMA周期
        chart = create_enhanced_chart(
            test_symbol, 
            "2024-01-01",
            freqs=['D'],
            ma_periods=[20, 60, 120]
        )
        
    else:
        print(f"未找到包含 {search_code} 的股票")


