# tests 目录说明

这个目录存放的是复现项目的自动化验证测试，用来检查数据解析、模型实现、算法协议、全量实验调度和最终报告保护逻辑是否符合论文复现要求。

注意：这里的测试不是论文的 552 个全量计算实验结果。全量实验仍然必须通过 `scripts/submit_full.py --dry-run` 确认 552 个任务，然后用异步队列实际运行 `138` 个实例乘以 `BC`、`BD`、`SAA-BC`、`SAA-BD` 四种方法。

## 测试覆盖内容

- `test_data_loader.py`
  - 检查 canonical JSON 数据读取。
  - 检查 138 个 stochastic instances 的路径、字段、scenario probability、车辆数、penalty 等数据规则。
  - 防止优化程序误读旧版 `processed/instances/**`。

- `test_model_core.py`
  - 检查二阶段随机 ConVRP extensive-form 的核心变量块。
  - 检查只为每个 scenario 中实际出现的客户建立二阶段变量。
  - 检查目标函数分解：`total_cost = travel_cost + consistency_penalty + skipping_cost`。

- `test_branch_cut.py`
  - 检查 BC 的 subtour elimination separation。
  - 覆盖 integer incumbent lazy SEC、root fractional min-cut SEC、callback 合同和 primal heuristic 相关行为。
  - 用小实例验证 Gurobi callback 不在回调内部递归调用主模型优化。

- `test_benders.py`
  - 检查论文 Section 3.2.2 的 branch-and-check BD 结构。
  - 覆盖 master lower-bound cut、integer optimality cut、固定 `y` 后的 scenario subproblem 求解。
  - 检查当前实现不再使用外层 iterative BD-like 路径作为正式 run path。

- `test_saa.py`
  - 检查 SAA-BC 和 SAA-BD 的论文协议参数：
    - SAA-BC: `M=20`, `|N|=5`, 每个 sample problem `30` 分钟。
    - SAA-BD: `M=20`, `|N|=15`, 每个 sample problem `30` 分钟。
  - 检查 sample membership 可复现。
  - 检查 full-Omega evaluation 和 SAA 统计字段。

- `test_experiment_protocol.py`
  - 锁定论文计算时间协议。
  - 检查 standalone `BC`/`BD` 为 full Omega、10 小时上限。
  - 检查 SAA sample problem 为 30 分钟上限。

- `test_full_experiment_queue.py`
  - 检查 full experiment 队列必须包含所有 instance-method 组合。
  - 对 canonical 138 个实例，应生成 `138 * 4 = 552` 个任务。
  - 检查 registry 去重、dead pid/tmux session 恢复逻辑。

- `test_result_completeness.py`
  - 检查 raw result 完整性规则。
  - 只有带 `paper_equivalent_run=true` 的结果才计入最终完整性。
  - 检查缺少任一方法或任一实例时不能判定 complete。

- `test_table_alignment.py`
  - 检查论文基准表可以生成 alignment table。
  - 检查在 552 个结果未完成前，partial raw results 不会被当作完整论文表格结果。

- `test_final_report_guard.py`
  - 检查最终报告保护逻辑。
  - 未完成 552 个 full-run、缺少 alignment tables、或存在非 solver 差异时，不能声明“完整复现成功”。
  - 只有所有必要条件满足时，`can_claim_full_reproduction=true`。

## 推荐运行方式

轻量非求解器测试：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -m unittest \
  tests.test_table_alignment \
  tests.test_result_completeness \
  tests.test_final_report_guard \
  tests.test_experiment_protocol \
  tests.test_full_experiment_queue -v
```

需要 Gurobi 的模型和算法测试：

```bash
source scripts/activate_env.sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -m unittest \
  tests.test_data_loader \
  tests.test_model_core \
  tests.test_branch_cut \
  tests.test_benders \
  tests.test_saa -v
```

## 与论文实验的关系

这些测试只证明代码路径、模型约束、统计字段、队列和最终报告 guard 符合复现协议。它们不能替代论文的全量计算实验。

最终能否声明“完整复现成功”，仍以以下命令的结果为准：

```bash
source scripts/activate_env.sh
PYTHONPATH=src:. python scripts/check_result_completeness.py
PYTHONPATH=src:. python scripts/final_report_guard.py
```

其中 `final_report_guard.py` 必须输出：

```json
{"can_claim_full_reproduction": true}
```
