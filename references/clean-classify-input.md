# 清洗 A：分类前（省 token）

脚本：`scripts/clean_classify_input.py`

把 `list_batch_N.json` 收成 Agent 归类输入。只丢多余字段，**永不**因实习 / 日薪（`元/天`）丢卡片。

## 命令

```bash
python3 scripts/clean_classify_input.py \
  --input data/<搜索词>/list_batch_1.json \
  --output data/<搜索词>/classify_input_1.json
```

## `classify_input.jobs` 只保留

`id` `title` `company` `boss_title` `salary` `tags`

- `id` = `encrypt_job_id`
- `company` 来自列表 `boss_name`
- **去掉** `location` `job_link` `security_id` `lid` `encrypt_job_id` 等（详情阶段从 `jobs.json` 取回 URL）

顶层仍保留：`schema_version` `query` `catalog_names` `batch_index` `list_*` `next_list_start_page` `city`（旧文件里的 `target_position_name` 会原样带上，脚本不按单岗校验）。

无 `id` 的坏卡片才丢。

下一步：[`classify-decisions.md`](classify-decisions.md)。
