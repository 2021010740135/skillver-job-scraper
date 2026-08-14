# 详情抓取

脚本：`scripts/scrape_details.py`

必须带 `--details-from-decisions PATH [PATH...]`。可一次传入多页决策。只开**这些决策里对上 58 岗**的帖，**全部开完**（不按 `--min-details` 截断）。`--min-details` 只给编排方判断要不要继续翻列表。

详情 URL 需要 `job_link`（以及 `security_id` / `lid`）。清洗 A 已从 classify_input 去掉这些字段，因此本 CLI 默认读 `data/<搜索词>/jobs.json` 合并后再打开页面。可用 `--jobs` 覆盖路径。

`--query` 是搜索词（对应产物目录）。`--position-name` 只是别名。已有 `has_details` 的 id 跳过。

```bash
python3 scripts/scrape_details.py \
  --query "阶跃星辰" \
  --city 上海 \
  --classify-input data/阶跃星辰/classify_input_<B>.json \
  --details-from-decisions data/阶跃星辰/classify_decisions_<B>.json
# 默认 --jobs data/<搜索词>/jobs.json
```

对上 58 岗的全部开；`null` 写入 seen 后跳过。每条详情成功后写入 `data/unexported_details.json`（CSV 成功后会去掉）。单次脚本调用不自动循环翻列表。

产出：`data/<搜索词>/details.json`；更新 `data/seen_jobs.json`；可选 `match_skip.json` / `decisions.json`。

建议始终带 `--city`，作详情 `location` 回退。

下一步：[`clean-details.md`](clean-details.md)。
