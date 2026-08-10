# 战力公式算法规范 v10

## 核心原则
- 各队各指标独立计算EMA，在各自比赛日上连续更新
- 不强制配对场次，不使用累计场均
- VPS只做数据匹配和最新EMA值相加，算法逻辑由沙箱维护

## 四项独立EMA
对每支球队，在其**自己的比赛日期序列**上分别计算：

| 指标 | 数据源 | 说明 |
|------|--------|------|
| gf EMA | 每场进球数 | 攻击力 |
| ga EMA | 每场失球数 | 防守力 |
| pts EMA | 每场积分 | 战绩走势 |

### overall（总战力）
- h_ms = 主队全部比赛
- a_ms = 客队全部比赛

### side（主客场战力）
- h_ms = 主队**主场**比赛 (home_home_recent)
- a_ms = 客队**客场**比赛 (away_away_recent)

## 对位组合

合并双方比赛日期为统一时间线，每个日期点：

```
home_strength[d] = h_gf_ema[d] + a_ga_ema[d]
away_strength[d] = a_gf_ema[d] + h_ga_ema[d]
```

- 主队比赛日：更新主队EMA，客队EMA沿用上一场值
- 客队比赛日：更新客队EMA，主队EMA沿用上一场值
- 双方同日：同时更新

## EMA参数
- span = 10, alpha = 2/11
- 初始值 = 首场原始值（不从0开始）

## K线输出
- kline_strength: 主队战力K线（home_strength序列）
- away_strength: 客队战力K线（away_strength序列）
- kline_pts: 主队积分EMA K线
- away_pts: 客队积分EMA K线

## 历史版本
- v1~v4: 原始单场值直接对位相加后EMA（场次不同步问题）
- v5: 累计场均再EMA（越打越收敛，掩盖单场差异）
- v6: 各队独立EMA后按index合并（时间节点不同步）
- v7: 累计场均+统一时间线（同上收敛问题）
- v8: carry-forward原始值再EMA（双重EMA）
- v9: 增量EMA（carry-forward段画平线）
- **v10: 各队独立EMA + 统一时间线取最新值对位相加（当前版本）**
