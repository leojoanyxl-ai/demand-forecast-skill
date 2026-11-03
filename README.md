# 行业需求预测与经营计划助手

**一个可复用 Skill，两个可运行行业模块：新能源汽车、ABS融资活动。**

维护仓库：[leojoanyxl-ai/demand-forecast-skill](https://github.com/leojoanyxl-ai/demand-forecast-skill)（私有）。

本项目面向业务负责人和战略部门，先确定谁在何时做什么决策，再核对数据、解释经济机制、运行基线和三情景，最后给出“建议＋理由＋适用条件＋风险”。课堂案例信息截止 **2026-11-03**，预测2027年并评估2028年风险。

## 先看结果

- [新能源汽车：需求预测与经营预案](运行结果/新能源汽车/需求预测与经营预案.html)
- [ABS：融资活动预测与业务预案](运行结果/ABS/ABS融资活动预测与业务预案.html)
- [汇报说明：原理、迭代、验证与不足](docs/汇报说明.md)
- [课堂讲稿与答辩准备](docs/课堂讲稿.md)
- [Skill 主文件](demand-forecast/SKILL.md)

HTML下载后用浏览器打开；GitHub文件预览页不执行HTML。运行代码、数据和参数均随仓库提供，正常分析不依赖网络、付费接口或个人电脑上的Excel路径。

## 自己运行

需要Python **3.10及以上**，分析与测试只用标准库。Windows可双击 `demand-forecast/选择行业运行.cmd`；当前电脑优先使用已附带的Python，其他电脑自动寻找Python。

在仓库目录运行：

```sh
python demand-forecast/scripts/run_skill.py --industry nev --output-dir output/nev
python demand-forecast/scripts/run_skill.py --industry abs --output-dir output/abs
```

输出目录必须尚不存在，用新目录保留每次运行。加 `--open` 自动打开报告；加 `--demo` 用明确标注的企业教学数据演示完整核算。默认缺少企业真实数据时，行业分析照常完成，企业部分给条件公式与待补清单。

两个模块分别读取各自 `assets` 中的数据、设置和企业输入。修改情景后重新运行，报告与表格自动更新。新能源汽车弹性唯一入口是 `economic-parameters.json`（或在 `nev-settings.json` 明确覆盖），不能直接把销量弹性填进份额logit系数；ABS路径唯一入口是 `abs-settings.json`。

## 怎样作为 Skill 使用

整个 `demand-forecast` 文件夹就是Skill，`SKILL.md`为入口，`references`为按需规则，`assets`为离线输入，`scripts`为计算和验证。将该文件夹放进支持本地Skill的工具的skills目录后使用 `$demand-forecast`；未安装时可以直接让AI读取主文件的完整路径。单独双击程序会计算，读取Skill还会引导任务卡、经济学解释、证据复核和决策报告。

可复制给AI：

> 请读取本项目 demand-forecast/SKILL.md。使用者为整车企业战略部门，在2026年11月3日可得信息下制定2027年销售与产能预案，并评估2028年风险。核对国内与出口口径，运行新能源汽车模块，区分观测、外部参照和压力假设。缺少企业实际输入时给条件核算，分别报告预测验证和业务可用状态。

> 请使用同一Skill的ABS模块，为管理人战略部门制定2027年项目承接与工时预案，并评估2028年风险。解释融资主体、投资者和管理人的区别，运行历史验证，未取得利差、资产池和政策量化依据时保留未量化状态，禁止套用汽车模型。

## 自己回测与维护

```sh
python -m unittest discover -s demand-forecast/scripts -p "test_*.py"
python tools/check_delivery.py
```

重新运行任一行业就会重算其历史验证并导出逐条明细、汇总和状态。ABS每个起点仅使用此前数据，在训练内选模；当前数据版本和发布日历限制仍存在。新能源汽车的月度基线回测不能证明整个经济情景链已经验证。

更新顺序：新建分支→修改对应CSV/JSON或代码→运行测试与两个示例→检查报告→提交修改→合并。仓库内的GitHub Actions工作流提供相同的运行检查。不要只手改报告数字。完整课堂交付包可在本地执行 `python tools/build_delivery.py` 生成。

## 数据与使用边界

运行所需CSV/JSON完整保留，不用删除数据来换取上传。原始ABS工作簿用于核对和可选重新导入；默认运行已使用便携CSV，无需openpyxl。来源、单位、原文件指纹和验证状态保留。iFinD导出和用户资料的后续对外分发须由拥有者确认权限；本次按用户要求优先私有仓库。

程序完成、统计预测验证和真实业务验收是三个不同状态。这里的参数迁移、情景条件、教学企业数据和回顾性验证不能包装成已识别的因果预测或已批准预算。参见[迭代记录](CHANGELOG.md)和[后续补充清单](docs/汇报说明.md)。
