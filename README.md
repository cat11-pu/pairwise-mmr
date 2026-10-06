# mmr

一个只依赖 Python 标准库的对局排位分内核：期望胜率、胜方分差修正、连胜与连败
系数、定级赛权重与保护线、长时间不活跃衰减，以及分数的上下界裁剪。时间由调用
方以「第几天」的整数注入，内核不读时钟、不读文件、不联网、不用随机源，同一串
调用永远得到同一批数字。

## 目录

- mmr/core.py：期望胜率、单场结算、休眠衰减与分数裁剪
- tests/test_core.py：行为测试

## 接口速览

```python
from mmr.core import Ladder

ladder = Ladder()
ladder.register("alice", 1600.0)
ladder.register("bob", 1400.0)

outcome = ladder.record_match("alice", "bob", day=1, margin=10)
outcome.winner_delta()          # 赢家这场拿走多少分
outcome.loser_delta()           # 输家这场交出多少分，带符号

ladder.apply_decay("bob", day=200)   # 结算 bob 到第 200 天的休眠衰减
ladder.rating_of("bob")
```

`register` 的 `matches`、`streak`、`last_day` 用来恢复一条已经有历史的记录；
新号保持缺省值即可。所有分数都是浮点数，比较时请留容差。

## 跑测试

在项目根目录执行：

    python3 -m unittest discover -s tests -v
