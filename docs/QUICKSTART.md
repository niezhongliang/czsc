# CZSC 快速入门指南

## 🚀 5分钟快速体验

### 1. 环境安装

```bash
# 安装CZSC库
pip install czsc -U

# 或从源码安装
pip install git+https://github.com/waditu/czsc.git -U

# 安装可选依赖
pip install tushare akshare jqdatasdk
```

### 2. 基础数据获取

```python
import czsc
from czsc.connectors.research import get_raw_bars, get_symbols

# 获取股票列表
symbols = get_symbols('中证500成分股')
print(f"获取到 {len(symbols)} 只股票")

# 获取K线数据
symbol = symbols[0]  # 选择第一只股票
bars = get_raw_bars(symbol, freq='30分钟', sdt='20220101', edt='20231201')
print(f"获取到 {len(bars)} 根K线数据")
```

### 3. 缠论分析入门

```python
from czsc import CZSC

# 创建CZSC分析对象
czsc = CZSC(bars, max_bi_num=50)

# 查看基础信息
print(f"原始K线数量: {len(czsc.bars_raw)}")
print(f"去包含K线数量: {len(czsc.bars_ubi)}")
print(f"分型数量: {len(czsc.fx_list)}")
print(f"笔数量: {len(czsc.bi_list)}")

# 查看最后一笔信息
if czsc.bi_list:
    last_bi = czsc.bi_list[-1]
    print(f"最后一笔: {last_bi.direction.value}, 力度: {last_bi.power}")
```

### 4. 可视化分析

```python
# 方法1: 使用内置echarts绘图
czsc.open_in_browser()

# 方法2: 使用plotly绘图
fig = czsc.to_plotly()
fig.show()

# 方法3: 使用增强版绘图（在dev目录中的示例）
import sys
sys.path.append("./dev")
from viz_czsc_chart import create_chart

chart = create_chart(symbol, "2022-01-01", freqs=['D'], ma_periods=[20, 60])
```

## 📊 因子开发实战

### 1. 编写自定义信号函数

```python
from collections import OrderedDict
from czsc import CZSC, Direction
from czsc.utils.sig import create_single_signal

def my_bi_power_signal_V240101(c: CZSC, **kwargs) -> OrderedDict:
    """笔力度信号示例
    
    :param c: CZSC对象
    :param kwargs: 参数配置 {'di': 1, 'threshold': 50}
    :return: 信号字典
    """
    di = int(kwargs.get("di", 1))
    threshold = float(kwargs.get("threshold", 50))
    
    freq = c.freq.value
    k1, k2, k3 = freq, f"D{di}", "笔力度V240101"
    
    # 检查数据是否充足
    if len(c.bi_list) < di + 2:
        return create_single_signal(k1=k1, k2=k2, k3=k3, v1="其他")
    
    # 获取目标笔
    bi = c.bi_list[-di]
    
    # 计算信号值
    if bi.direction == Direction.Up and bi.power >= threshold:
        v1 = "强势上涨"
    elif bi.direction == Direction.Down and bi.power >= threshold:
        v1 = "强势下跌"
    elif bi.direction == Direction.Up:
        v1 = "弱势上涨"
    elif bi.direction == Direction.Down:
        v1 = "弱势下跌"
    else:
        v1 = "其他"
    
    return create_single_signal(k1=k1, k2=k2, k3=k3, v1=v1)

# 测试信号函数
signals = my_bi_power_signal_V240101(czsc, di=1, threshold=30)
print("自定义信号:", signals)
```

### 2. 信号验证与分析

```python
from czsc import SignalAnalyzer

# 配置信号参数
signals_config = [
    {'name': 'my_bi_power_signal_V240101', 'freq': '30分钟', 'di': 1, 'threshold': 30},
    {'name': 'my_bi_power_signal_V240101', 'freq': '30分钟', 'di': 1, 'threshold': 50},
    {'name': 'my_bi_power_signal_V240101', 'freq': '60分钟', 'di': 1, 'threshold': 30},
]

# 批量验证信号
symbols_test = symbols[:10]  # 选择10只股票测试
sa = SignalAnalyzer(
    symbols=symbols_test,
    read_bars=get_raw_bars,
    signals_config=signals_config,
    results_path="./signal_analysis_results"
)

# 执行分析（这会需要一些时间）
# sa.execute(max_workers=4)
print("信号分析配置完成，可调用sa.execute()执行")
```

### 3. 构建交易策略

```python
from czsc import CzscStrategyBase, Event, Position, Signal, Factor

class MyBiPowerStrategy(CzscStrategyBase):
    """基于笔力度的交易策略"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.threshold = kwargs.get('threshold', 50)
    
    @property
    def positions(self):
        # 开多条件：强势上涨笔
        long_opens = [{
            "operate": "开多",
            "factors": [{
                "signals_all": [
                    f"30分钟_D1_笔力度V240101_强势上涨_任意_任意_0"
                ],
                "signals_not": [
                    f"30分钟_D1_涨跌停V230331_涨停_任意_任意_0"  # 排除涨停
                ]
            }]
        }]
        
        # 开空条件：强势下跌笔
        short_opens = [{
            "operate": "开空", 
            "factors": [{
                "signals_all": [
                    f"30分钟_D1_笔力度V240101_强势下跌_任意_任意_0"
                ],
                "signals_not": [
                    f"30分钟_D1_涨跌停V230331_跌停_任意_任意_0"  # 排除跌停
                ]
            }]
        }]
        
        # 平仓条件：反向信号
        exits = [
            {
                "operate": "平多",
                "factors": [{
                    "signals_all": [f"30分钟_D1_笔力度V240101_强势下跌_任意_任意_0"]
                }]
            },
            {
                "operate": "平空",
                "factors": [{
                    "signals_all": [f"30分钟_D1_笔力度V240101_强势上涨_任意_任意_0"]
                }]
            }
        ]
        
        return [Position(
            name=f"笔力度策略_{self.threshold}",
            symbol=self.symbol,
            opens=[Event.load(x) for x in long_opens + short_opens],
            exits=[Event.load(x) for x in exits],
            interval=3600*2,   # 2小时开仓间隔
            timeout=20*30,     # 20根K线超时
            stop_loss=300      # 3%止损
        )]

# 创建策略实例
strategy = MyBiPowerStrategy(symbol=symbol, threshold=50)
print(f"策略信号配置: {len(strategy.signals_config)} 个")
```

### 4. 策略回测

```python
# 简单回测
try:
    # 准备回测数据
    bars_backtest = get_raw_bars(symbol, freq='30分钟', sdt='20220101', edt='20231201')
    
    # 执行回测
    trader = strategy.replay(
        bars=bars_backtest,
        sdt='20220601',  # 回测开始时间
        res_path="./backtest_results"
    )
    
    # 查看回测结果
    if trader.positions:
        position = trader.positions[0]
        results = position.evaluate()
        
        print("=== 回测结果 ===")
        print(f"交易次数: {results.get('交易次数', 0)}")
        print(f"胜率: {results.get('胜率', 0):.2%}")
        print(f"总收益率: {results.get('总收益率', 0):.2%}")
        print(f"年化收益率: {results.get('年化收益率', 0):.2%}")
        print(f"最大回撤: {results.get('最大回撤', 0):.2%}")
        print(f"夏普比率: {results.get('夏普比率', 0):.2f}")
        
except Exception as e:
    print(f"回测出现错误: {e}")
    print("请确保信号函数已正确注册到signals模块中")
```

## 🎯 常用信号函数速查

### 缠论核心信号

```python
# 笔方向信号
"30分钟_D1_表里关系V230101_向上_任意_任意_0"     # 当前笔向上
"30分钟_D1_表里关系V230101_向下_任意_任意_0"     # 当前笔向下

# 中枢相关信号
"30分钟_D1_三买形态V230228_一买_任意_任意_0"     # 一买点
"30分钟_D1_三买形态V230228_二买_任意_任意_0"     # 二买点
"30分钟_D1_三买形态V230228_三买_任意_任意_0"     # 三买点

# 背驰信号
"30分钟_D1_MACD背驰V221201_底背驰_任意_任意_0"  # 底背驰
"30分钟_D1_MACD背驰V221201_顶背驰_任意_任意_0"  # 顶背驰
```

### 技术指标信号

```python
# MACD信号
"30分钟_D1_MACD快慢线V221101_多头_任意_任意_0"   # MACD多头
"30分钟_D1_MACD快慢线V221101_空头_任意_任意_0"   # MACD空头

# 均线信号
"30分钟_D1_双均线V221203_多头_任意_任意_0"       # 双均线多头
"30分钟_D1_双均线V221203_空头_任意_任意_0"       # 双均线空头

# 成交量信号
"30分钟_D1_成交量突增V221216_放量_任意_任意_0"   # 成交量放量
```

### K线形态信号

```python
# 涨跌停信号
"30分钟_D1_涨跌停V230331_涨停_任意_任意_0"       # 涨停
"30分钟_D1_涨跌停V230331_跌停_任意_任意_0"       # 跌停

# K线形态
"30分钟_D1_大阴线V230215_大阴线_任意_任意_0"     # 大阴线
"30分钟_D1_大阳线V230215_大阳线_任意_任意_0"     # 大阳线
```

## 🔧 调试技巧

### 1. 数据检查

```python
# 检查K线数据质量
from czsc.utils.kline_quality import check_high_low, check_price_gap

# 检查高低价关系
issues = check_high_low(bars)
if issues:
    print(f"发现 {len(issues)} 个高低价异常")

# 检查价格跳空
gaps = check_price_gap(bars, threshold=0.1)
if gaps:
    print(f"发现 {len(gaps)} 个价格跳空")
```

### 2. 信号调试

```python
# 查看所有可用信号
from czsc.traders import generate_czsc_signals

# 生成所有信号
signals_config = [
    {'name': 'czsc.signals.cxt_bi_status_V230101', 'freq': '30分钟', 'di': 1},
    {'name': 'czsc.signals.tas_macd_base_V221028', 'freq': '30分钟'},
]

czsc_signals = generate_czsc_signals(bars, signals_config, sdt='20230101')
for sig_name, sig_value in czsc_signals.items():
    print(f"{sig_name}: {sig_value}")
```

### 3. 性能优化

```python
# 使用缓存加速
from czsc.utils import disk_cache

@disk_cache()
def cached_get_bars(symbol, freq, sdt, edt):
    return get_raw_bars(symbol, freq, sdt, edt)

# 批量并行处理
from concurrent.futures import ProcessPoolExecutor

def process_symbol(symbol):
    bars = cached_get_bars(symbol, '30分钟', '20220101', '20231201')
    czsc = CZSC(bars)
    return len(czsc.bi_list)

# 并行处理多个标的
with ProcessPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(process_symbol, symbols[:10]))
print(f"笔数量统计: {results}")
```

## 📚 进阶学习

### 1. 多周期分析

```python
class MultiTimeframeStrategy(CzscStrategyBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.freqs = ['5分钟', '30分钟', '日线']  # 多周期配置
    
    @property
    def positions(self):
        # 多周期信号组合
        opens = [{
            "operate": "开多",
            "factors": [{
                "signals_all": [
                    "5分钟_D1_表里关系V230101_向上_任意_任意_0",
                    "30分钟_D1_表里关系V230101_向上_任意_任意_0", 
                    "日线_D1_表里关系V230101_向上_任意_任意_0"
                ]
            }]
        }]
        return [Position(symbol=self.symbol, opens=[Event.load(x) for x in opens])]
```

### 2. 因子组合优化

```python
from czsc.traders import OpensOptimize

# 参数优化
optimizer = OpensOptimize(
    strategy_class=MyBiPowerStrategy,
    param_grid={
        'threshold': [30, 50, 70],
        'stop_loss': [200, 300, 500]
    }
)

# best_params = optimizer.optimize(symbols[:5], bars_func=get_raw_bars)
```

### 3. 实盘交易准备

```python
# 使用Redis存储策略权重
from czsc.traders import RedisWeightsClient

redis_client = RedisWeightsClient(host='localhost', port=6379)

# 获取策略权重
weights = redis_client.get_strategy_weights('my_strategy')
print(f"当前权重: {weights}")
```

## 🎯 下一步

1. **阅读源码**: 深入理解`czsc/analyze.py`和`czsc/objects.py`
2. **学习信号**: 研究`czsc/signals/`目录下的各种信号函数实现
3. **实战练习**: 基于自己的交易理念开发信号函数和策略
4. **社区交流**: 加入飞书群或知识星球与其他用户交流经验

---

**提示**: 这只是一个快速入门指南，CZSC库功能强大且复杂，建议结合官方文档和示例代码深入学习。 