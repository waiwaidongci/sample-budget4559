# 验证记录（联合研究）

运行方式：`cd backend && python3 -m pytest tests/ -v`（SQLite 临时库 + 队列推送打桩，无需外部服务；生产路径为 PostgreSQL16 + Redis7，语义一致）。

最近一轮：22 passed（约3秒）。

## 全零效应下整族误报（test_fwer_under_all_null_controlled）
- 设定：共同对照4000触达、4名候选各2500触达，全体真实点击率同为0.08（零效应）；外层250轮、内层校准1500次模拟，α=0.05。
- 实测：联合校正整族误报率 0.076 ≤ 0.05+3×MCSE（0.091）；逐项未校正检验整族误报率 0.220，明显放大。结论：联合最大统计量校准把整族误报控制在α附近，逐项检验确实放大误报。
- 共用对照抽样：同一轮模拟中全体候选共用同一次对照抽样，族内统计量相关系数实测>0.2（test_shared_control_draw_induces_correlation）。
- 校正严格性：校正临界值c大于未校正z(1-α/2)，且随检验族规模增大（test_calibration_stricter_than_naive_and_grows_with_family）；校正后p不小于未校正p（test_adjusted_p_not_below_raw）。

## 删减候选（test_withdraw_keeps_original_family 等）
- 候选退出后：旧计算立即失效并注明原因，自动按新版本重算；旧快照完整保留原检验族（3名候选均active）。
- 新计算中退出成员仍计入检验族规模（检验族规模3、活跃候选2），校正临界值与未删减的三候选族完全一致（同种子同零假设），退出成员不再给出结论（标记“退出”）。
- 共同对照不可退出（test_withdraw_control_rejected）。

## 更正交错（test_interleaved_corrections_keep_single_live_run 等）
- 封存读取完整同版数据：run.data_version 与研究当前版本一致，快照含对照+全部候选，SHA256一致（test_seal_uses_complete_same_version_data）。
- 连续两次更正：前两次未发布计算依次失效，仅最新一次重算保持queued，版本严格递增，最新快照采用更正后同版数据。
- 迟归不覆盖：旧计算在更新结论发布后尝试发布被拒绝并标记失效，新结论保持不变（test_late_old_run_never_overwrites_newer_conclusion）；版本滞后任务在worker取件时即判失效（test_stale_version_run_invalidated_at_pickup）。
- 重试不重复发布：同一任务重复处理/重复发布均空转，已发布结论唯一（test_retry_does_not_double_publish）。
- 中断恢复沿用整族随机依据：running任务恢复重算后指标与按封存种子离线复算完全一致（test_recovery_reuses_family_random_basis）；整族未齐备不生效（test_family_must_be_complete_before_effect）。

## 原独立研究照常
- test_independent_regression.py：独立批次录入→冻结→worker计算→完成，指标与SHA256校验不变，且不会进入联合队列。

## API 冒烟（test_joint_api_flow）
- 登录、越权拒绝（viewer 403）、重名409、共同对照唯一409、点击>触达422、封存入队、详情/运行查询、退出后失效原因可见。
