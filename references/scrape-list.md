# 列表抓取

脚本：`scripts/scrape_list.py`

按 `--query` 往 BOSS 搜索框输入（公司名、岗名或任意词）。默认**每次只抓 1 页**。规则过滤猎头 / 人力资源服务 / 匿名空公司 / **全局 seen 已见**。**不**在这一步丢掉实习或日薪卡片。不设翻页上限：本页有卡片则给出 `next_list_start_page`，是否继续由编排方按累计映射数决定。

## 命令

```bash
python3 scripts/scrape_list.py \
  --query "阶跃星辰" \
  --city 上海 \
  --list-start-page 1 \
  --page-batch-size 1 \
  --batch-index 1
# --position-name 是 --query 的别名，不必是 catalog 原名
# 可选筛选（对应页面下拉；experience/scale 可逗号或重复）：
#   --job-type 全职 --experience 105 --scale 305,306 --salary 406 --degree 203 --stage 807 --industry 1001
#   --job-type：求职类型 不限/全职/兼职/实习（或 1901/1902/1903；不限可省略）
```

## 写出

| 文件 | 内容 |
|------|------|
| `data/<搜索词>/jobs.json` | 累计列表。含 `job_link` / `security_id` / `lid` |
| `data/<搜索词>/list_batch_<B>.json` | **本批**新卡片（同样含 URL 字段） |
| `data/seen_jobs.json` | 全局去重。本批入选卡片会 `mark_listed` |

列表卡片字段（白名单）：`title` `boss_name` `boss_title` `salary` `location` `tags` `encrypt_job_id` `job_link` `security_id` `lid`。

记下 `next_list_start_page`（`null`/缺失 = 本页无卡片，不要再翻）。`jobs` 可为空。

## 默认值

| 项 | 默认 |
|----|------|
| `--city` | `上海` |
| `--pages` | 不设（本调用只抓 `--page-batch-size` 页） |
| `--page-batch-size` | `1` |
| `--list-start-page` | `1` |
| `--batch-index` | `1` |
| `--seen` | `data/seen_jobs.json` |

下一步：[`clean-classify-input.md`](clean-classify-input.md)。
