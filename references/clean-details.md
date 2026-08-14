# 清洗 B：详情后（导出前）

脚本：`scripts/clean_details.py`

把 `details.json` 收到导出所需字段。只丢多余键，**永不**因实习 / 日薪丢行。无 `encrypt_job_id` 或重复 id 才丢。

## 命令

```bash
python3 scripts/clean_details.py --input data/<岗>/details.json
# 默认覆盖原文件；也可用 --output 另写
```

## 只保留

`encrypt_job_id` `title` `company` `salary` `location` `jd` `position_name` `job_intent_id` `job_intent_label`

社招主路径不处理日薪：导出侧会跳过无法解析为 `N K-M K` 的薪资，清洗 B **不**在这里过滤。

下一步：[`export-csv.md`](export-csv.md)。
