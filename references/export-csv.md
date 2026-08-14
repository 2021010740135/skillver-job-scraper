# 导出 Skillver CSV

脚本：`scripts/export_skillver_csv.py`

把本次 `details.json` 写成 `data/<搜索词>/job_YYYYMMDD.csv`，并并入 `data/unexported_details.json` 里同搜索词、尚未进 CSV 的详情。每一行用该行映射到的标准岗填 `岗位名称` / `job_intent_*`。同一标准岗下可有多条 BOSS 帖。已 `exported` 的 id 跳过。

## 命令

```bash
python3 scripts/export_skillver_csv.py \
  --details data/<搜索词>/details.json \
  --query "<搜索词>" \
  --city 上海 \
  --dry-run

# 确认计数合理后去掉 --dry-run；可加 --append / --report PATH
```

默认 `--seen data/seen_jobs.json`。详情已有 `location` 时可不传 `--city`；旧空 location 仍建议传 `--city` 回退。

正式跑会更新 seen（`exported=true`），并把已写出的 id 从 `unexported_details.json` 去掉。大量 `empty_city` → 检查详情 `location` 或补 `--city`。`salary_unparsed` 含日薪等非社招格式属预期跳过。

## 人机闸门 `WAIT_CSV_REVIEW`

给出 CSV **绝对路径**。等用户回复「CSV 已核验」前，**不宣布任务完成**。
